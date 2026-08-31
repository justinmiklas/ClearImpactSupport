"""
server.py — Backend for the in-app support bot.

Responsibilities:
  * Hold the Gemini API key (it NEVER touches the browser).
  * Run each question through Gemini + the File Search tool, scoped to the right product.
  * Enforce grounding: if the answer isn't backed by retrieved documentation, return
    the safe "I couldn't find that" message instead of anything invented.
  * Return real source links, resolved from manifest.json so they always point at
    your live help-center article (independent of SDK/citation quirks).

Run it:
    python -m uvicorn server:app --port 8001
"""

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import config

MANIFEST_PATH = Path(__file__).parent / "manifest.json"


# ---------------------------------------------------------------------------
# Load the manifest so we can map indexed documents back to public article URLs.
# ---------------------------------------------------------------------------
def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"_store": None, "articles": {}}


_MANIFEST = _load_manifest()
ARTICLES = _MANIFEST.get("articles", {})                      # article_id -> record
BY_DOCNAME = {r["doc_name"]: r for r in ARTICLES.values() if r.get("doc_name")}


def _store_name() -> str:
    if config.STORE_NAME_OVERRIDE:
        return config.STORE_NAME_OVERRIDE
    if _MANIFEST.get("_store"):
        return _MANIFEST["_store"]
    raise RuntimeError("No File Search store found. Run kb_sync.py first.")


STORE_NAME = _store_name()


# ---------------------------------------------------------------------------
# CORS: which web pages may call this server.
# In production set ALLOWED_ORIGINS in .env to your real app domains. We also
# always allow the local demo page (file:// shows up as the "null" origin) and
# localhost so testing works out of the box.
# ---------------------------------------------------------------------------
if "*" in config.ALLOWED_ORIGINS:
    CORS_ORIGINS = ["*"]
else:
    _DEV = [
        "null",
        "http://localhost", "http://127.0.0.1",
        "http://localhost:8000", "http://localhost:5173",
        "http://localhost:8001", "http://127.0.0.1:8001",
    ]
    CORS_ORIGINS = list(dict.fromkeys(config.ALLOWED_ORIGINS + _DEV))

app = FastAPI(title="AI Support Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=config.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Public-page protections: per-IP rate limiting + embed permissions.
# The chat page is public, so we cap how fast one visitor can send messages
# (controls cost/abuse) and restrict which sites may embed it in an iframe.
# ---------------------------------------------------------------------------
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
FRAME_ANCESTORS = os.getenv(
    "FRAME_ANCESTORS",
    "'self' https://clearimpact.com https://www.clearimpact.com https://*.clearimpact.com",
)
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    # Rate limit only the expensive endpoint.
    if request.url.path == "/chat" and request.method == "POST":
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        now = time.time()
        dq = _hits[ip]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= RATE_LIMIT_PER_MIN:
            resp = JSONResponse(
                {
                    "answer": "You're sending messages a little quickly. "
                              "Please wait a moment and try again.",
                    "sources": [],
                    "answered": False,
                },
                status_code=429,
            )
            resp.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS}"
            return resp
        dq.append(now)

    response = await call_next(request)
    # Allow only your own site(s) to embed the chat page.
    response.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS}"
    return response


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class Turn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    product: str
    history: list[Turn] = Field(default_factory=list)


class Source(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    answered: bool


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def _build_contents(req: ChatRequest) -> list:
    contents = []
    for turn in req.history[-6:]:
        role = "model" if turn.role == "model" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn.text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=req.message)]))
    return contents


def _resolve_sources(candidate):
    """Return (sources, grounded). 'grounded' is True if the model actually
    retrieved any documentation chunks — that's what we use to decide whether the
    answer is trustworthy. Source links are resolved from the manifest."""
    gm = getattr(candidate, "grounding_metadata", None)
    chunks = getattr(gm, "grounding_chunks", None) if gm else None
    if not chunks:
        return [], False

    seen, sources = set(), []
    for ch in chunks:
        rc = getattr(ch, "retrieved_context", None)
        if not rc:
            continue

        rec = None
        # 1) The file's display_name (our article id) usually comes back as title.
        ident = getattr(rc, "title", None)
        if ident and ident in ARTICLES:
            rec = ARTICLES[ident]
        # 2) Otherwise try the document resource name / uri.
        if rec is None:
            docref = getattr(rc, "document_name", None) or getattr(rc, "uri", None)
            if docref and docref in BY_DOCNAME:
                rec = BY_DOCNAME[docref]
        # 3) Otherwise fall back to any custom metadata echoed back.
        if rec is None:
            md = {}
            for m in (getattr(rc, "custom_metadata", None) or []):
                md[getattr(m, "key", None)] = (
                    getattr(m, "string_value", None) or getattr(m, "numeric_value", None)
                )
            if md.get("url"):
                rec = {"url": md["url"], "title": md.get("title") or md["url"]}

        if rec and rec.get("url") and rec["url"] not in seen:
            seen.add(rec["url"])
            sources.append(Source(title=rec.get("title") or rec["url"], url=rec["url"]))

    return sources, True


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    product = req.product.lower()
    if product not in config.LAUNCH_PRODUCTS:
        raise HTTPException(400, f"Unknown product '{req.product}'")

    product_name = config.PRODUCT_DISPLAY_NAMES[product]
    system_instruction = config.SYSTEM_INSTRUCTION.format(product_name=product_name)

    store = [STORE_NAME]
    if config.PRODUCT_FILTER_MODE == "all":
        file_search = types.FileSearch(file_search_store_names=store)
    elif config.PRODUCT_FILTER_MODE == "strict":
        file_search = types.FileSearch(
            file_search_store_names=store, metadata_filter=f'product="{product}"'
        )
    else:  # "scoped"
        file_search = types.FileSearch(
            file_search_store_names=store,
            metadata_filter=f'product="{product}" OR product="general"',
        )

    try:
        response = client.models.generate_content(
            model=config.MODEL,
            contents=_build_contents(req),
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[types.Tool(file_search=file_search)],
                temperature=0.2,
            ),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Model error: {e}")

    candidate = response.candidates[0] if response.candidates else None
    try:
        text = (response.text or "").strip() if candidate else ""
    except Exception:  # noqa: BLE001
        text = ""
    sources, grounded = _resolve_sources(candidate) if candidate else ([], False)

    # ---- The "never make up answers" guardrail -----------------------------
    # Refuse if the model signalled it couldn't answer, OR nothing was retrieved
    # from the docs, OR there's no text. Grounding is the strong guarantee.
    if (config.NO_ANSWER_SENTINEL in text) or (not grounded) or (not text):
        return ChatResponse(answer=config.REFUSAL_MESSAGE, sources=[], answered=False)

    return ChatResponse(answer=text, sources=sources, answered=True)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": config.MODEL,
        "store": STORE_NAME,
        "articles_indexed": len(ARTICLES),
        "cors_origins": CORS_ORIGINS,
    }


# ---------------------------------------------------------------------------
# Serve the public full-page chat UI (webchat/index.html) at "/".
# Registered LAST so the API routes above always take precedence.
# ---------------------------------------------------------------------------
WEBCHAT_DIR = Path(__file__).parent / "webchat"
if WEBCHAT_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEBCHAT_DIR), html=True), name="webchat")
