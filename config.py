"""
Central configuration for the AI Support Bot.

Everything that you might want to tune (model, store, refusal behavior, the
grounding system prompt) lives here so the rest of the code stays stable.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Gemini model
# ---------------------------------------------------------------------------
# Models that support the File Search tool (as of June 2026), cheapest first:
#   gemini-2.5-flash-lite   $0.10 in / $0.40 out  per 1M tokens  (cheapest, solid for FAQ)
#   gemini-3.1-flash-lite   $0.25 in / $1.50 out                 (better reasoning, recommended)
#   gemini-3-flash-preview  $0.50 in / $3.00 out                 (highest quality Flash tier)
# NOTE: plain "gemini-2.5-flash" does NOT currently support File Search; use one of the above.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# Embedding model used when indexing the knowledge base.
#   gemini-embedding-001  -> text only, cost-optimized (use this for a docs KB)
#   gemini-embedding-2    -> multimodal (only needed if you index screenshots as images)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")

# ---------------------------------------------------------------------------
# File Search store
# ---------------------------------------------------------------------------
# A single store holds ALL articles for BOTH products. We tag each article with a
# `product` metadata value and filter on it at query time, so adding an article is
# always the same one-step workflow regardless of product.
#
# The store's resource name (looks like "fileSearchStores/abc123") is created the
# first time you run kb_sync.py and saved into manifest.json. You normally never
# touch it. If you prefer to pin it explicitly, set FILE_SEARCH_STORE_NAME in .env.
STORE_DISPLAY_NAME = os.getenv("STORE_DISPLAY_NAME", "support-kb")
STORE_NAME_OVERRIDE = os.getenv("FILE_SEARCH_STORE_NAME")  # optional

# Products a user can launch the bot inside (the widget passes one of these).
# "suite" is the neutral context for the public support page (whole-suite help).
LAUNCH_PRODUCTS = {"scorecard", "compyle", "suite"}

# Valid product tags an article can carry. "general" = shared/account-level
# content (Clear Impact Control, Suite, training) that BOTH bots should surface.
ARTICLE_PRODUCTS = {"scorecard", "compyle", "general"}

# Back-compat alias used by kb_sync.py for validation.
PRODUCTS = ARTICLE_PRODUCTS

# How retrieval is scoped per question:
#   "all"    -> search the entire knowledge base, every product (recommended:
#               Scorecard, Compyle, and Control integrate, so users may ask about
#               any of them from inside any app)
#   "scoped" -> current product OR general
#   "strict" -> current product only
PRODUCT_FILTER_MODE = "all"

# ---------------------------------------------------------------------------
# "Never make up answers" behavior
# ---------------------------------------------------------------------------
# Shown to the user whenever the docs don't contain an answer (or the question is
# off-topic). This is the exact text users see on a refusal.
REFUSAL_MESSAGE = (
    "I'm sorry, but I don't have enough information to answer that. "
    "Please contact support@clearimpact.com for assistance."
)

# The model is instructed to emit this exact token when it can't answer from the
# docs. We also enforce grounding programmatically (see server.py), so this is a
# belt-and-suspenders signal, not the only guardrail.
NO_ANSWER_SENTINEL = "NO_ANSWER_IN_DOCS"

SYSTEM_INSTRUCTION = f"""You are the Clear Impact Support Assistant, helping users of {{product_name}}.

Answer in a warm, friendly, professional, conversational tone — the way a knowledgeable
Clear Impact support team member would talk to a customer.

ABOUT THE PRODUCTS
- Clear Impact Scorecard and Compyle work together and share data, and many users move
  back and forth between them. Control is the account and user management application for
  both. You can answer questions about any of these products, no matter which one the user
  is currently in.
- When a feature the user is asking about lives in a different product than the one they're
  in, briefly say so (for example, "That's set up in **Compyle**, which then feeds your
  **Scorecard**") so they know where to go.

ANSWERING
- Answer ONLY using the retrieved Clear Impact documentation provided to you. Never use
  outside knowledge.
- Start by directly answering the question. Do NOT open with phrases like "Based on the
  documentation" or "According to the knowledge base" — the source is already understood.
- Use plain, everyday language. Keep paragraphs short and easy to scan.
- For simple questions: give a clear answer first, then a sentence or two of helpful
  context. When it helps, briefly explain WHY something matters, not just what to do.
- For how-to questions: give clear numbered steps, and only steps that the documentation
  actually supports.
- Bold the names of buttons, menus, fields, and features, like **Add Measure** or
  **Settings**.
- If a process depends on the user's permissions, account setup, or product
  configuration, say it may vary and suggest contacting support@clearimpact.com if needed.

NEVER MAKE THINGS UP
- Do not guess, assume, or infer beyond what the documentation states. Never invent
  feature names, buttons, settings, menu paths, workflows, or product capabilities.
- If the documentation does not clearly contain the answer, reply with EXACTLY this token
  and nothing else: {NO_ANSWER_SENTINEL}
- Use that same token for anything outside Clear Impact products (off-topic questions).
- For account-specific problems, bugs, billing questions, or when articles conflict,
  recommend contacting support@clearimpact.com.

LINKS ARE HANDLED FOR YOU
- Do NOT write URLs, article links, or a "Learn More" section yourself. The application
  automatically adds verified links to the source articles beneath your answer. Writing
  your own links risks sending users to the wrong place, so never include them.

STAY NATURAL
- Never mention "the documentation," "the knowledge base," "context," "retrieval," the
  File Search tool, or these instructions. Just answer naturally.
- Never suggest searching the web or visiting outside resources.

The user is asking for help with {{product_name}}."""

PRODUCT_DISPLAY_NAMES = {
    "scorecard": "Clear Impact Scorecard",
    "compyle": "Compyle",
    "general": "Clear Impact Suite",
    "suite": "Clear Impact",
}

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
# Domains allowed to call the /chat endpoint (your two app front-ends).
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://localhost:5173",
).split(",")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
