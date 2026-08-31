"""
kb_sync.py — Incrementally sync the knowledge base into the Gemini File Search store.

This is what makes "add a new article without redoing the whole thing" true.

How it works
------------
1. Reads every Markdown file under kb/ (each has YAML frontmatter: id, title, url,
   product, category).
2. Computes a content hash for each article.
3. Compares against manifest.json (the record of what's already indexed):
       - new article            -> index it
       - changed article        -> delete old version, re-index
       - unchanged article      -> skip (costs nothing)
       - article deleted on disk -> remove it from the store
4. Saves the updated manifest.

Day-to-day workflow for your team:
    1. Add or edit a .md file in kb/scorecard/ or kb/compyle/
    2. Run:  python kb_sync.py
That's it. Only the changed files are re-indexed. Indexing costs $0.15 per 1M
tokens; a typical article is well under a cent.

Usage:
    python kb_sync.py            # sync everything
    python kb_sync.py --dry-run  # show what would change, do nothing
    python kb_sync.py --reset    # delete the store and rebuild from scratch
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import frontmatter
from google import genai

import config

import os

KB_DIR = Path(os.getenv("KB_DIR", Path(__file__).parent / "kb"))
MANIFEST_PATH = Path(os.getenv("KB_MANIFEST_PATH", Path(__file__).parent / "manifest.json"))
REQUIRED_FIELDS = ("id", "title", "url", "product")


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"_store": None, "articles": {}}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


# ---------------------------------------------------------------------------
# Article loading
# ---------------------------------------------------------------------------
def load_articles() -> dict:
    """Return {article_id: {meta..., 'body': str, 'hash': str}} for every kb file."""
    articles = {}
    for path in sorted(KB_DIR.rglob("*.md")):
        post = frontmatter.load(path)
        meta = post.metadata

        missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
        if missing:
            print(f"  ! SKIPPING {path.relative_to(KB_DIR)} — missing frontmatter: {missing}")
            continue

        product = str(meta["product"]).lower()
        if product not in config.PRODUCTS:
            print(f"  ! SKIPPING {path.relative_to(KB_DIR)} — unknown product '{product}'")
            continue

        article_id = str(meta["id"])
        # We index the title as a heading + the body. Frontmatter (YAML) is NOT
        # indexed, so embeddings stay clean. Structured fields travel as metadata.
        indexed_text = f"# {meta['title']}\n\n{post.content.strip()}\n"
        digest = hashlib.sha256(indexed_text.encode("utf-8")).hexdigest()

        if article_id in articles:
            print(f"  ! DUPLICATE id '{article_id}' in {path.name} — ids must be unique")
            sys.exit(1)

        articles[article_id] = {
            "id": article_id,
            "title": str(meta["title"]),
            "url": str(meta["url"]),
            "product": product,
            "category": str(meta.get("category", "")),
            "path": str(path.relative_to(KB_DIR)),
            "body": indexed_text,
            "hash": digest,
        }
    return articles


# ---------------------------------------------------------------------------
# Gemini File Search operations
# ---------------------------------------------------------------------------
def get_or_create_store(client, manifest) -> str:
    if config.STORE_NAME_OVERRIDE:
        return config.STORE_NAME_OVERRIDE
    if manifest.get("_store"):
        return manifest["_store"]

    print(f"Creating File Search store '{config.STORE_DISPLAY_NAME}' ...")
    store = client.file_search_stores.create(
        config={
            "display_name": config.STORE_DISPLAY_NAME,
        }
    )
    manifest["_store"] = store.name
    save_manifest(manifest)
    print(f"  -> {store.name}")
    print("  (saved to manifest.json — add it to .env as FILE_SEARCH_STORE_NAME for the server)")
    return store.name


def wait(client, operation):
    while not operation.done:
        time.sleep(3)
        operation = client.operations.get(operation)
    return operation


def find_document_name(client, store_name: str, display_name: str):
    """Resolve the auto-generated document resource name from our stable display_name.

    Wrapped defensively: the documents listing API varies slightly between
    google-genai versions, and it's only needed for precise updates/removals, so
    if it isn't available we just return None and the first sync still succeeds.
    """
    try:
        for doc in client.file_search_stores.documents.list(parent=store_name):
            if getattr(doc, "display_name", None) == display_name:
                return doc.name
    except Exception:  # noqa: BLE001
        return None
    return None


def delete_document(client, store_name: str, article_id: str, manifest: dict):
    doc_name = manifest["articles"].get(article_id, {}).get("doc_name")
    if not doc_name:
        doc_name = find_document_name(client, store_name, article_id)
    if doc_name:
        try:
            client.file_search_stores.documents.delete(name=doc_name)
        except Exception as e:  # noqa: BLE001
            print(f"    (warning: could not delete old doc for {article_id}: {e})")


def upload_article(client, store_name: str, art: dict):
    """Index one article, attaching url/title/product as searchable metadata."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write(art["body"])
        tmp_path = tmp.name
    try:
        operation = client.file_search_stores.upload_to_file_search_store(
            file=tmp_path,
            file_search_store_name=store_name,
            config={
                # display_name is our stable id; it shows up in citations and lets
                # us find/delete this exact document later.
                "display_name": art["id"],
                # custom_metadata is returned in grounding data at query time, which
                # is how the bot links back to the real public article URL.
                "custom_metadata": [
                    {"key": "url", "string_value": art["url"]},
                    {"key": "title", "string_value": art["title"]},
                    {"key": "product", "string_value": art["product"]},
                    {"key": "category", "string_value": art["category"]},
                    {"key": "article_id", "string_value": art["id"]},
                ],
            },
        )
        wait(client, operation)
    finally:
        os.unlink(tmp_path)

    return find_document_name(client, store_name, art["id"])


# ---------------------------------------------------------------------------
# Main sync
# ---------------------------------------------------------------------------
def sync(dry_run: bool = False, reset: bool = False):
    if not config.GEMINI_API_KEY:
        sys.exit("ERROR: GEMINI_API_KEY is not set (put it in .env)")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    manifest = load_manifest()

    if reset and manifest.get("_store"):
        print(f"--reset: deleting store {manifest['_store']}")
        if not dry_run:
            try:
                client.file_search_stores.delete(
                    name=manifest["_store"], config={"force": True}
                )
            except Exception as e:  # noqa: BLE001
                print(f"  (warning: {e})")
        manifest = {"_store": None, "articles": {}}
        save_manifest(manifest)

    store_name = get_or_create_store(client, manifest) if not dry_run else (
        manifest.get("_store") or "(store will be created)"
    )

    disk = load_articles()
    indexed = manifest["articles"]

    to_add = [a for a in disk.values() if a["id"] not in indexed]
    to_update = [
        a for a in disk.values()
        if a["id"] in indexed and indexed[a["id"]]["hash"] != a["hash"]
    ]
    to_delete = [aid for aid in indexed if aid not in disk]
    unchanged = len(disk) - len(to_add) - len(to_update)

    print("\nPlan:")
    print(f"  {len(to_add):>3} new     {[a['id'] for a in to_add]}")
    print(f"  {len(to_update):>3} changed {[a['id'] for a in to_update]}")
    print(f"  {len(to_delete):>3} removed {to_delete}")
    print(f"  {unchanged:>3} unchanged (skipped)\n")

    if dry_run:
        print("--dry-run: no changes made.")
        return

    for art in to_add:
        print(f"+ indexing  {art['id']}")
        doc_name = upload_article(client, store_name, art)
        indexed[art["id"]] = {**_record(art), "doc_name": doc_name}
        save_manifest(manifest)

    for art in to_update:
        print(f"~ updating  {art['id']}")
        delete_document(client, store_name, art["id"], manifest)
        doc_name = upload_article(client, store_name, art)
        indexed[art["id"]] = {**_record(art), "doc_name": doc_name}
        save_manifest(manifest)

    for aid in to_delete:
        print(f"- removing  {aid}")
        delete_document(client, store_name, aid, manifest)
        del indexed[aid]
        save_manifest(manifest)

    print("\nDone. Knowledge base is in sync.")


def _record(art: dict) -> dict:
    return {
        "hash": art["hash"],
        "title": art["title"],
        "url": art["url"],
        "product": art["product"],
        "category": art["category"],
        "path": art["path"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync the KB into Gemini File Search.")
    parser.add_argument("--dry-run", action="store_true", help="show changes, do nothing")
    parser.add_argument("--reset", action="store_true", help="delete store and rebuild")
    args = parser.parse_args()
    sync(dry_run=args.dry_run, reset=args.reset)
