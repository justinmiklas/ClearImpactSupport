# AI Support Bot for Clear Impact Scorecard & Compyle

An in-app support assistant that answers **only** from your support documentation,
**never** makes things up, and lets you **add new articles one at a time** without
rebuilding anything. Powered by Gemini's managed File Search (RAG) tool.

---

## Why this design

Your four requirements map almost exactly onto one Google feature shipped in late
2025: the **Gemini API File Search tool** — a fully managed Retrieval-Augmented
Generation (RAG) system built into the API. It handles chunking, embedding, vector
storage, retrieval, and citations for you, so there is **no separate vector database
to run** (no Pinecone, Weaviate, pgvector, etc.).

| Your requirement | How it's met |
| --- | --- |
| Use Gemini (cost) | File Search runs on cheap Flash models; storage + query-time embeddings are **free**, you pay only ~$0.15/1M tokens to index a file once. |
| Knowledge base of your docs | A folder of Markdown articles (`kb/`) indexed into one File Search store. |
| Only answer from your docs, with links | Retrieval is restricted to *your store only* (File Search can't be combined with web search), and every answer's source URLs come straight from grounding metadata. |
| Never make up answers | Two-layer guardrail: a strict system prompt **plus** a hard code check — an answer with zero retrieved sources is replaced with a safe "I couldn't find that" message. |
| Easily add articles incrementally | Drop a `.md` file in `kb/` and run `kb_sync.py`. Only changed files are re-indexed; the store persists everything else. |

### Architecture

```
  Your app (Scorecard / Compyle)
        │  embeds
        ▼
  support-widget.js  ──HTTPS──►  server.py (FastAPI, holds Gemini key)
                                      │
                                      ▼
                          Gemini model + File Search tool
                                      │  retrieves from
                                      ▼
                          File Search store  ◄── kb_sync.py ◄── kb/*.md
                          (one store, articles
                           tagged by product)
```

The browser widget never holds the API key — it only talks to your backend.

### Why one store for both products

All articles live in **one** File Search store and are tagged with a `product`
metadata value (`scorecard` or `compyle`). At query time the backend filters on
that tag, so Scorecard users only ever get Scorecard answers and vice-versa. This
keeps article management to a single workflow. (If you'd rather isolate them
completely, you can create two stores — the code is structured to make that a
small change.)

---

## Setup

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
#    edit .env and paste your GEMINI_API_KEY (from https://aistudio.google.com/apikey)

# 3. Index the knowledge base (creates the store on first run)
python kb_sync.py
#    -> copy the printed fileSearchStores/... name into .env as FILE_SEARCH_STORE_NAME

# 4. Run the backend
uvicorn server:app --reload --port 8001

# 5. Try it
#    open widget/demo.html in a browser (or serve it) and chat in the bottom-right
```

---

## Adding or updating articles (the day-to-day workflow)

1. Create a Markdown file anywhere under `kb/scorecard/` or `kb/compyle/`.
2. Give it frontmatter (see format below).
3. Run `python kb_sync.py`.

Only new or changed files are re-indexed. Deleting a `.md` file and re-running
removes it from the bot too. Use `python kb_sync.py --dry-run` to preview changes.

### Article format

````markdown
---
id: scorecard-creating-a-scorecard          # unique, stable, never reuse
title: Creating a Scorecard                  # shown as the source link text
url: https://help.clearimpact.com/articles/creating-a-scorecard   # public link the bot returns
product: scorecard                           # scorecard | compyle
category: Getting Started                     # optional, for your own organization
last_reviewed: 2026-06-01                     # optional
---

Article body in plain Markdown. Write it the way you'd explain it to a customer.
Short, task-focused articles with clear steps retrieve and answer best.
````

The `url` is what the bot links to, so it should point at your real, public help
article. The source of truth stays in these files (keep them in Git for version
history and review).

> **Tip:** if your docs already live in a help desk (Zendesk, Intercom, HelpScout,
> etc.), write a small exporter that pulls each article into this Markdown +
> frontmatter shape on a schedule, then run `kb_sync.py`. The rest is unchanged.

---

## Cost model

Using **Gemini 3.1 Flash-Lite** ($0.25 in / $1.50 out per 1M tokens) as an example:

- **Indexing:** $0.15 per 1M tokens, one time per article (and only again if it
  changes). A 1,000-article KB averaging ~800 tokens each ≈ 800K tokens ≈ **~$0.12
  to index the entire library.** Negligible.
- **Storage & query-time embeddings:** **free.**
- **Per question:** roughly system prompt + a few retrieved chunks (~3–5K input
  tokens) + a short answer (~250 output tokens) ≈ **$0.001–$0.002 per question.**
  ~1,000 questions/day ≈ **~$1–$2/day.**

Cut it further by switching `GEMINI_MODEL` to `gemini-2.5-flash-lite`
($0.10/$0.40) and by enabling **context caching** for the (identical every time)
system prompt. Verify current rates at https://ai.google.dev/gemini-api/docs/pricing.

---

## How "never make up answers" is enforced

There are two independent layers, in `config.py` and `server.py`:

1. **Prompt layer.** The system instruction tells the model to answer *only* from
   retrieved documentation and to emit a sentinel token (`NO_ANSWER_IN_DOCS`) when
   the docs don't cover the question.
2. **Code layer (the real guarantee).** After generation, the backend inspects the
   response's grounding metadata. **If no document chunks were retrieved, the answer
   is discarded** and the user gets the safe fallback instead. Source links shown to
   the user are taken *only* from grounding metadata, so every link is a real,
   indexed article — the model cannot present a URL it wasn't given.

Tune the fallback wording and escalation path in `REFUSAL_MESSAGE` (`config.py`).

---

## Production hardening checklist

- [ ] Enable **billing** on the Gemini project (free tier has low rate limits and uses data for training).
- [ ] Put the backend behind auth from your apps (signed token / session) so only logged-in users can call `/chat`.
- [ ] Add **rate limiting** per user/IP to control cost and abuse.
- [ ] Restrict `ALLOWED_ORIGINS` to your real app domains only.
- [ ] Add **context caching** on the system prompt to cut per-query cost.
- [ ] Log questions + whether they were answered, to find gaps in your docs (the "couldn't find" questions are a backlog of articles to write).
- [ ] Review Google's data-use terms for the paid tier before sending customer data.
- [ ] Have a human spot-check answers during rollout; even grounded RAG can occasionally state a retrieved fact in a misleading way.

---

## Files

| File | Purpose |
| --- | --- |
| `config.py` | Model, store, refusal text, and the grounding system prompt. |
| `kb_sync.py` | Incremental indexer — the "add an article easily" workflow. |
| `server.py` | FastAPI backend with the grounding guardrail. |
| `kb/` | Your knowledge base (Markdown + frontmatter). Sample articles included. |
| `widget/support-widget.js` | Embeddable chat widget for both apps. |
| `widget/demo.html` | Local demo page. |
| `manifest.json` | Auto-generated record of what's indexed. Don't edit by hand. |

---

## Alternatives considered

- **Hand-rolled RAG (pgvector / Pinecone + your own embedding pipeline):** more
  control, but you run and tune the vector DB, chunking, and re-indexing yourself.
  File Search removes that work and the storage cost. Worth revisiting only if you
  outgrow File Search limits (20 GB/store recommended).
- **Vertex AI Search (Google Cloud):** enterprise-grade, connects to Drive/SharePoint/etc.,
  but needs a GCP project and more setup. Good upgrade path if you later want
  multi-source ingestion.
- **NotebookLM:** no-code and great for research, but it's a standalone product,
  not an embeddable in-app bot — doesn't fit this use case.
