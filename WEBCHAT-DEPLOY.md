# Hosting the Support Assistant as a page on clearimpact.com

This publishes the bot as a **public full-page chat**, hosted on Render (from GitHub)
and embedded on clearimpact.com — a working stand-in until the dev team integrates it
into the products.

## How it fits together

```
  clearimpact.com  (Avada page)
        │  embeds via <iframe>
        ▼
  Render web service ─── serves the chat page (/)  AND  the chat API (/chat)
        │  queries
        ▼
  Gemini File Search store  (your knowledge base, already indexed)
```

Because one Render service serves both the page and the API, there's no cross-origin
setup between them, and your Gemini key stays on the server — never in the page.

## Before you start

- A **GitHub** account and a **Render** account (render.com).
- Your **GEMINI_API_KEY** — the *same* key you used with `kb_sync.py`, so the service
  can reach the knowledge store you already built.
- `manifest.json` present in the project (it is — created when you ran `kb_sync.py`).

## Step 1 — Put the project on GitHub

Create a new **private** repo and push this project folder to it. Two things matter:

- **Do commit `manifest.json`** — the server reads it at runtime for the store id and
  article links. (It contains only public URLs and ids, no secrets.)
- **Do NOT commit `.env`** — it holds your key. The included `.gitignore` already
  excludes it. You'll set the key in Render instead.

If you're new to GitHub, the desktop app (github.com/apps/desktop) is the easiest way:
create the repo, drag in the folder, and click **Publish**.

## Step 2 — Deploy on Render

**Option A — Blueprint (easiest):** the repo includes `render.yaml`.

1. In Render, click **New → Blueprint**, connect your GitHub, and pick the repo.
2. Render reads `render.yaml` and sets everything up. When prompted, paste your
   **GEMINI_API_KEY** (it's the one value marked "sync: false").
3. Click **Apply**. First build takes a few minutes.

**Option B — Manual:** New → Web Service → pick the repo, then set
Build `pip install -r requirements.txt`, Start `uvicorn server:app --host 0.0.0.0 --port $PORT`,
Health check `/health`, and add the env vars listed in `render.yaml`.

**Plan note:** the **Starter** plan (~$7/mo) keeps the service always on. The **Free**
plan works but sleeps after ~15 min idle, so the first visitor after a quiet spell waits
~30–50s for it to wake. For a customer-facing page, Starter is worth it.

## Step 3 — Verify

Render gives you a URL like `https://clearimpact-support-bot.onrender.com`.

- Visit `…/health` → should show `"status":"ok"` and your article count.
- Visit the base URL → the chat page loads. Ask something real (e.g. "How do I create a
  participant?") and confirm you get an answer **with Learn More links**, then ask
  something off-topic and confirm it politely declines.

## Step 4 — Embed it on clearimpact.com (Avada)

1. In WordPress, create a new page (e.g. **Support Assistant**). Use a **full-width**
   template with minimal header/footer for the most app-like feel.
2. Add an Avada **Code Block** element and paste this, replacing the URL with your
   Render URL:

```html
<iframe
  src="https://YOUR-APP.onrender.com/"
  title="Clear Impact Support Assistant"
  style="width:100%; height:82vh; min-height:640px; border:0; border-radius:14px; box-shadow:0 8px 28px rgba(13,43,85,.10);"
  loading="lazy"></iframe>
```

3. Publish. The chat now lives on your site. The service only allows *your* domains to
   embed it (via the `FRAME_ANCESTORS` setting), so it can't be framed by other sites.

## Keeping it up to date

Same as before, plus one push:

1. Run `update.bat` locally (refreshes the knowledge store from HubSpot).
2. Commit and push the updated `manifest.json` to GitHub.
3. Render auto-redeploys within a minute.

The article *content* updates in the store immediately; pushing `manifest.json` keeps the
**Learn More links** correct for any brand-new articles.

## Good to know

- **Cost/abuse:** the API key is server-side only, the bot answers solely from your docs
  (so it can't be used as a free general chatbot), and requests are rate-limited per
  visitor (`RATE_LIMIT_PER_MIN`, default 20/min — raise or lower it in Render).
- **Gemini billing:** enable billing on the Google project before real traffic; the free
  tier has low limits.
- **Branding:** colors, header text, and the starter questions live at the top of
  `webchat/index.html` if you want to tweak them.
