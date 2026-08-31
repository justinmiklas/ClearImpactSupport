"""
hubspot_export.py — Export the Clear Impact help center into the bot's kb/ folder.

Tailored to support.clearimpact.com, which is a single HubSpot knowledge base
covering multiple products. Because article URLs are flat (/en/<slug>) and don't
name the product, we classify each article two ways:

  1. ENUMERATE every article by crawling the section index pages
     (e.g. /en/compyle-documentation), which list all of their articles.
  2. CLASSIFY each article by the breadcrumb on its own page
     (Help Center > <Section> > <Sub-category>), which is the authoritative
     "home" of the article and handles cross-listed articles correctly.

Output: kb/<product>/<slug>.md with frontmatter (id, title, url, product,
category) — ready for kb_sync.py.

Products:
  scorecard | compyle            -> product-specific
  general                        -> Control, Suite, training, account-level
                                    (surfaced in BOTH bots — see PRODUCT_FILTER_MODE)

Setup:
    pip install -r requirements-export.txt
    python hubspot_export.py --dry-run         # preview, writes nothing
    python hubspot_export.py                    # write the files
    python hubspot_export.py --product compyle  # one product only
    python kb_sync.py                           # then index into Gemini
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

BASE = "https://support.clearimpact.com"
HOST = "support.clearimpact.com"

# Section index slug -> (product tag, breadcrumb section name).
# Order matters only as a fallback; the per-article breadcrumb wins.
SECTIONS = {
    "scorecard-documentation":      ("scorecard", "Scorecard Documentation"),
    "scorecard-video-tutorials":    ("scorecard", "Scorecard Video Tutorials"),
    "compyle-documentation":        ("compyle",   "Compyle Documentation"),
    "compyle-video-tutorials":      ("compyle",   "Compyle Video Tutorials"),
    "control-documentation":        ("general",   "Control Documentation"),
    "unlimited-suite-documentation":("general",   "Unlimited Suite Documentation"),
    "clear-impact-live-training":   ("general",   "Clear Impact Live Training"),
    "collaborate-with-clear-impact":("general",   "Collaborate with Clear Impact"),
}
INDEX_SLUGS = set(SECTIONS)
SECTION_NAME_PRODUCT = {name: prod for prod, name in SECTIONS.values()}

# Pages with less than this much body text are treated as video/slide-deck/landing
# pages and skipped (a text bot can't use a video anyway).
MIN_BODY_CHARS = 250

# Slugs containing any of these are skipped outright (non-text assets).
EXCLUDE_SLUG_SUBSTRINGS = ["slide-deck", "webinar-slide", "-slide"]

KB_DIR = Path(__file__).parent / "kb"
USER_AGENT = "clearimpact-kb-exporter/1.0"
REQUEST_PAUSE_SEC = 0.3


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if r.status_code == 200:
            return r.text
        print(f"    ! HTTP {r.status_code} for {url}")
    except requests.RequestException as e:
        print(f"    ! error fetching {url}: {e}")
    return None


def canonical(url: str) -> str:
    p = urlparse(url)
    return f"{BASE}{p.path}".rstrip("/")


def slug_of(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Enumerate article URLs from the section index pages
# ---------------------------------------------------------------------------
def enumerate_articles(only_product: str | None) -> dict:
    """Return {canonical_url: (fallback_product, fallback_section_name)}."""
    found: dict = {}
    for slug, (product, name) in SECTIONS.items():
        if only_product and product != only_product:
            continue
        html = fetch(f"{BASE}/en/{slug}")
        time.sleep(REQUEST_PAUSE_SEC)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        count = 0
        for a in main.find_all("a", href=True):
            p = urlparse(a["href"])
            if p.fragment:                       # skip in-page / nav anchors
                continue
            if p.netloc and p.netloc != HOST:    # skip external links
                continue
            if not p.path.startswith("/en/"):
                continue
            seg = p.path[len("/en/"):].strip("/")
            if not seg or "/" in seg:            # only /en/<slug>
                continue
            if seg in INDEX_SLUGS or seg.startswith("kb-tickets"):
                continue
            if any(x in seg for x in EXCLUDE_SLUG_SUBSTRINGS):
                continue
            found.setdefault(f"{BASE}/en/{seg}", (product, name))
            count += 1
        print(f"  {slug:<32} {count:>4} article links")
    return found


# ---------------------------------------------------------------------------
# Per-article parsing
# ---------------------------------------------------------------------------
def breadcrumb_items(soup: BeautifulSoup) -> list[str]:
    """Return ordered breadcrumb labels, e.g. ['Help Center','Compyle Documentation','Participants...']."""
    root = None
    for a in soup.find_all("a", href=True):
        path = urlparse(a["href"]).path.rstrip("/")
        label = a.get_text(strip=True).lower()
        if path == "/en" and label in ("help center", "home"):
            root = a
            break
    if not root:
        return []
    container = root.find_parent(["ul", "ol", "nav"])
    if not container:
        return []
    items = [li.get_text(" ", strip=True) for li in container.find_all("li")]
    if not items:
        items = [a.get_text(" ", strip=True) for a in container.find_all("a")]
    return [i for i in items if i]


def classify(soup: BeautifulSoup, fallback: tuple) -> tuple[str, str]:
    """Determine (product, category) from the breadcrumb, falling back to the section."""
    fb_product, fb_section = fallback
    items = breadcrumb_items(soup)

    product, section_name = fb_product, fb_section
    for it in items:
        if it in SECTION_NAME_PRODUCT:
            product, section_name = SECTION_NAME_PRODUCT[it], it
            break

    # Category = the breadcrumb item after the section (the sub-category),
    # excluding Help Center, the section itself, and the article title (last item).
    category = ""
    tail = [it for it in items if it not in ("Help Center", "Home") and it != section_name]
    if len(tail) >= 2:           # [sub-category, article-title]
        category = tail[-2]
    elif tail:
        category = tail[0]
    if not category:
        category = section_name or ""
    return product, category


def get_title(soup: BeautifulSoup, url: str) -> str:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return re.sub(r"\s*[|\-]\s*Help Center.*$", "", soup.title.string).strip()
    return slug_of(url).replace("-", " ").title()


def extract_body(html: str, url: str) -> str | None:
    return trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_images=False,
        include_links=False,
        favor_recall=True,
    )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def write_article(product: str, url: str, title: str, category: str, body: str, dry_run: bool) -> Path:
    slug = slug_of(url)
    article_id = f"{product}-{slug}"
    out_dir = KB_DIR / product
    out_path = out_dir / f"{slug}.md"
    fm = (
        "---\n"
        f"id: {article_id}\n"
        f'title: "{title.replace(chr(34), chr(39))}"\n'
        f"url: {url}\n"
        f"product: {product}\n"
        f'category: "{category.replace(chr(34), chr(39))}"\n'
        f"last_reviewed: {time.strftime('%Y-%m-%d')}\n"
        "---\n\n"
    )
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(fm + body.strip() + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(only_product: str | None, dry_run: bool, limit: int | None, clean: bool = False):
    print("Enumerating articles from section index pages...")
    articles = enumerate_articles(only_product)
    urls = sorted(articles)
    if limit:
        urls = urls[:limit]
    print(f"\n{len(urls)} unique article URLs to process.\n")

    # For safe --clean pruning later: which folders are in scope, and how many
    # article files exist there now (used to detect an incomplete crawl).
    scope_products = [only_product] if only_product else ["scorecard", "compyle", "general"]
    scope_dirs = [KB_DIR / p for p in scope_products]
    existing_before = sum(len(list(d.glob("*.md"))) for d in scope_dirs if d.exists())

    counts: dict = {}
    skipped: list = []
    written: set = set()
    for url in urls:
        html = fetch(url)
        time.sleep(REQUEST_PAUSE_SEC)
        if not html:
            skipped.append((url, "fetch failed"))
            continue
        soup = BeautifulSoup(html, "html.parser")
        product, category = classify(soup, articles[url])
        title = get_title(soup, url)
        body = extract_body(html, url)
        if not body or len(body) < MIN_BODY_CHARS:
            skipped.append((url, "thin/no body (likely video or slide deck)"))
            continue
        path = write_article(product, url, title, category, body, dry_run)
        written.add(path.resolve())
        counts[product] = counts.get(product, 0) + 1
        verb = "would write" if dry_run else "wrote"
        print(f"  [{product:<9}] {verb}: {path.name:<55} <- {title}")

    print("\n--- Summary ---")
    for prod in sorted(counts):
        print(f"  {prod:<10} {counts[prod]} articles")
    print(f"  skipped    {len(skipped)} (thin/non-text or fetch errors)")

    # --clean: remove local files for articles that are no longer published in
    # HubSpot, so the knowledge base stays an exact mirror. Guarded so a failed or
    # partial crawl can never wipe the knowledge base.
    if clean and not dry_run:
        total_written = len(written)
        safe = existing_before == 0 or total_written >= max(1, int(existing_before * 0.5))
        if not safe:
            print(f"\n  --clean SKIPPED: only {total_written} files written vs "
                  f"{existing_before} already present.")
            print("  That looks like an incomplete crawl, so existing files were left alone.")
        else:
            pruned = 0
            for d in scope_dirs:
                if not d.exists():
                    continue
                for f in d.glob("*.md"):
                    if f.resolve() not in written:
                        f.unlink()
                        pruned += 1
                        print(f"  pruned (no longer published): {f.relative_to(KB_DIR.parent)}")
            print(f"\n  --clean removed {pruned} article file(s) no longer in HubSpot.")

    # Write a QA list of skipped pages so you can review what didn't export.
    if not dry_run:
        report = KB_DIR.parent / "export_skipped.txt"
        report.write_text("\n".join(f"{u}\t{why}" for u, why in skipped), encoding="utf-8")
        print(f"\n  Review skipped pages in: {report.name}")
        print("  Next: spot-check kb/, then run  python kb_sync.py")
    else:
        print("\n  Dry run only — no files written.")
        if skipped:
            print("  Would skip:")
            for u, why in skipped[:20]:
                print(f"    - {u}  ({why})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Clear Impact help center to kb/ Markdown.")
    parser.add_argument("--product", choices=["scorecard", "compyle", "general"],
                        help="export only one product's articles")
    parser.add_argument("--dry-run", action="store_true", help="preview, write nothing")
    parser.add_argument("--limit", type=int, help="cap number of articles (for testing)")
    parser.add_argument("--clean", action="store_true",
                        help="also delete local files for articles no longer in HubSpot "
                             "(safely skipped if the crawl looks incomplete)")
    args = parser.parse_args()
    run(args.product, args.dry_run, args.limit, args.clean)
