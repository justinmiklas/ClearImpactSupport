# Clear Impact Support Bot — .NET Backend (developer hand-off)

This is the **runtime service** your products embed: an ASP.NET Core (.NET 8) Minimal
API that answers support questions from the Clear Impact knowledge base via Gemini's
File Search tool, with a hard "never make things up" guardrail. It's a faithful port of
the reference Python backend (`server.py`).

## What is and isn't in .NET

| Component | Lives in | Why |
| --- | --- | --- |
| **Runtime API** (this project) | **.NET / C#** | Embedded in / hosted by your platform. Ported here. |
| **Chat widget** (`widget/support-widget.js`) | Plain JS | Framework-agnostic — drop into any Razor/Blazor/MVC page as-is. |
| **Content pipeline** (`hubspot_export.py`, `kb_sync.py`) | **Python** (recommended) | An occasional admin job, not part of the product runtime. The exporter depends on `trafilatura` for article-text extraction, which has no .NET equivalent. Run it as a scheduled job/container. |

The Python pipeline produces a `manifest.json` and a Gemini **File Search store**. This
.NET service reads that manifest (for verified links + the store id) and queries the store.
**No official Google .NET SDK exists**, so this calls the Gemini REST API directly via
`HttpClient` — intentionally dependency-light.

## Project layout

| File | Purpose |
| --- | --- |
| `Program.cs` | Minimal API: DI, CORS, `POST /chat`, `GET /health`. |
| `GeminiClient.cs` | REST client for `generateContent` + the File Search tool. |
| `ManifestSourceResolver.cs` | Loads `manifest.json`; turns grounding chunks into verified article links; resolves the store name. |
| `SupportPrompt.cs` | System prompt, refusal text, the no-answer sentinel, product display names. |
| `Models.cs` | API contract, options, Gemini/manifest DTOs. |
| `appsettings.json` | Deployment knobs (model, store, filter mode, allowed origins). |

## Run it

```bash
# 1. Make the Python pipeline's output available to this service:
#    copy the generated manifest.json next to the built app, or point
#    SupportBot:ManifestPath at its absolute path.

# 2. Provide the API key (never commit it):
setx GEMINI_API_KEY "your-key"          # Windows, new shell after
# or: dotnet user-secrets set "SupportBot:ApiKey" "your-key"

# 3. Run
dotnet restore
dotnet run
# GET http://localhost:5xxx/health   -> sanity check (shows store + article count)
```

## Configuration (`appsettings.json` → `SupportBot`)

- `Model` — Gemini model (default `gemini-3.1-flash-lite`; must support File Search).
- `FileSearchStoreName` — usually leave blank; read from `manifest.json` `_store`.
- `ManifestPath` — path to the pipeline's `manifest.json`.
- `ProductFilterMode` — `all` (search everything; current choice), `scoped`, or `strict`.
- `AllowedOrigins` — your real product domains (CORS). Localhost/null are added for the demo.
- API key — `GEMINI_API_KEY` env var (preferred) or `SupportBot:ApiKey` (user-secrets).

## Embedding the widget (Razor example)

The widget only talks to this API; it never holds the key. Serve `support-widget.js`
as a static asset and add one tag to your layout, per product:

```html
<!-- In a Scorecard page/layout -->
<script src="~/js/support-widget.js"
        data-endpoint="https://your-host/chat"
        data-product="scorecard"
        data-accent="#2563eb"
        data-title="Scorecard Support"></script>
```

Use `data-product="compyle"` in Compyle. (Both work the same; `data-product` only sets
which app the user is in — retrieval searches the whole KB in `all` mode.)

## Gemini REST contract (for reference)

Request: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
with header `x-goog-api-key`. Body (camelCase):

```jsonc
{
  "systemInstruction": { "parts": [ { "text": "..." } ] },
  "contents": [ { "role": "user", "parts": [ { "text": "How do I add a measure?" } ] } ],
  "tools": [ { "fileSearch": { "fileSearchStoreNames": ["fileSearchStores/abc"],
                               "metadataFilter": "product=\"scorecard\"" } } ],
  "generationConfig": { "temperature": 0.2 }
}
```

Response: answer text is in `candidates[0].content.parts[].text`; sources are in
`candidates[0].groundingMetadata.groundingChunks[].retrievedContext`. We treat a response
with **zero** grounding chunks as unsupported and return the refusal message.

> Field-name caveat: File Search is new. We read the cited article id from
> `retrievedContext.title` and fall back to `documentName`/`uri`/`customMetadata`. If a
> future API tweak renames these, adjust `RetrievedContext` in `Models.cs` and the lookup
> in `ManifestSourceResolver.cs`. Links are resolved from the manifest, so they're never
> model-invented.

## Production checklist

- [ ] Put `/chat` behind your app's auth (signed token/session) so only logged-in users call it.
- [ ] Add rate limiting (`AddRateLimiter`) per user/IP to control cost and abuse.
- [ ] Lock `AllowedOrigins` to your real product domains; drop the localhost/null dev entries.
- [ ] Enable billing on the Gemini project; review Google's data-use terms for the paid tier.
- [ ] Host the manifest.json refresh: run the Python pipeline on a schedule and redeploy/refresh
      the manifest this service reads (or load it from shared storage and reload periodically).
- [ ] Log questions + whether they were answered to find documentation gaps.
