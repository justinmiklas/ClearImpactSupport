# Clear Impact Support Bot — Developer Hand-off

An in-app AI support assistant for Scorecard and Compyle. It answers user questions
**only** from the Clear Impact help center (support.clearimpact.com), links to the
source articles, and refuses (pointing to support@clearimpact.com) when the docs don't
cover the question — it never invents answers.

## How it works

A managed RAG system on **Google Gemini's File Search** tool. The help center is
indexed into one Gemini "store"; at query time the model may only answer from retrieved
articles, and a server-side guardrail discards any answer that isn't backed by a
retrieved document. Source links are resolved from `manifest.json` (never model-written),
so they always point at a real article. Retrieval currently searches the **entire**
knowledge base (Scorecard, Compyle, and Control), because the products integrate.

## What's in the package

| Component | Stack | Role | Status |
| --- | --- | --- | --- |
| Runtime API (`dotnet/SupportBot.Api`) | ASP.NET Core 8 | The service your products call. Calls Gemini REST via HttpClient. | Reference build — integrate & deploy |
| Chat widget (`widget/support-widget.js`) | Vanilla JS | Embeds in any Razor/Blazor page. Renders answers + "Learn More" links. | Done — drop in |
| Content pipeline (`hubspot_export.py`, `kb_sync.py`) | Python (Dockerized) | Refreshes the knowledge base from HubSpot. Runs as a scheduled job. | Done & tested |
| Local updater (`update.bat`) | Windows batch | One-click manual refresh for the content owner. | Done & tested |
| Reference backend (`server.py`) | Python/FastAPI | The original; use as the behavior spec for the .NET service. | Done |

Deeper docs: **`dotnet/README.md`** (the .NET service), **`DOCKER.md`** (scheduling the
pipeline), **`README.md`** (overall design & costs).

## What's verified vs. what remains

Verified working end-to-end (against a live key): content export, indexing, grounded
answers with links, and correct refusals. The assistant's rules, tone, and all-products
retrieval are tuned and in `config.py` (Python) / `SupportPrompt.cs` (.NET).

Remaining work is deployment, and it's yours:

- [ ] **Host the .NET service** somewhere always-on (today only the local Python server runs).
- [ ] **Auth**: put `/chat` behind your app login so only signed-in users can call it.
- [ ] **Rate limit** per user/IP to control cost and abuse.
- [ ] **Lock CORS** `AllowedOrigins` to your real product domains; remove the localhost/null dev entries.
- [ ] **Secrets**: provision `GEMINI_API_KEY` to the service and the pipeline (not in source).
- [ ] **Enable Gemini billing**; review Google's paid-tier data-use terms before sending customer data.
- [ ] **Schedule the pipeline** (Docker) daily/weekly; ensure the `/data` volume persists
      `manifest.json`, and make the refreshed `manifest.json` available to the .NET service.
- [ ] **Embed the widget** in Scorecard (`data-product="scorecard"`) and Compyle
      (`data-product="compyle"`), pointing `data-endpoint` at the hosted service.
- [ ] **Log** questions + answered/refused to surface documentation gaps over time.

## Decisions worth knowing

- **No official Google .NET SDK** exists, so the service calls the Gemini REST API directly
  via `HttpClient` — intentional and dependency-light.
- **The pipeline stays Python on purpose.** Its article-text extraction relies on a Python
  library (`trafilatura`) with no .NET equivalent; rewriting it in C# would be worse, and it
  isn't part of the product runtime. Run it as a scheduled container.
- **HubSpot is the single source of truth.** Never edit the exported article files; they're
  regenerated. To update content, edit in HubSpot and re-run the pipeline.
- **Cost is minimal**: indexing the library costs pennies; storage and query-time embeddings
  are free; each question is roughly $0.001–0.002 on Gemini Flash-Lite.

## Two flags

- File Search is new (late 2025); its citation field names may shift across SDK/REST
  versions. The code parses several variants and resolves links from `manifest.json`, so
  links are never invented — but verify citation mapping on your installed version. One spot
  to adjust: `RetrievedContext` / `ManifestSourceResolver`.
- The .NET project was authored against the verified REST contract but **not compiled** in
  the authoring environment — expect a normal `restore`/`build`/integrate pass.
