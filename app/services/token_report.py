"""
Token Report Service — powered by xAI Grok

Grok has native real-time access to X (Twitter) data, so a single API call
replaces the previous two-step pipeline (Twitter API fetch → Claude analysis).

Flow:
  1. Check DB cache (7-day TTL) → return immediately if fresh
  2. Build prompt with token name/symbol/twitter handle
  3. Call Grok API → get back an optimistic 2-paragraph analysis
  4. Save to token_reports table → return

Cache policy: reports are valid for 7 days.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..database import get_db

logger = logging.getLogger(__name__)

REPORT_TTL_DAYS = 7
GROK_API_URL    = "https://api.x.ai/v1/chat/completions"
GROK_MODEL      = "grok-3"

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a crypto community analyst. Your job is to search X (Twitter) for recent
activity about a meme token and write a short, optimistic but honest briefing for
someone who just received it.

Rules:
- Search X for posts from the last 30 days about this token
- Write exactly 2 short paragraphs (2-3 sentences each)
- Total length: under 80 words
- Tone: cautiously optimistic, grounded in real signals you find
- Never say "100x", "moon", "guaranteed", or predict price movement
- No bullet points, no headers — flowing prose only
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_handle(twitter_url: str) -> str | None:
    if not twitter_url:
        return None
    parts = [p for p in urlparse(twitter_url).path.split("/") if p]
    return parts[0] if parts else None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_cached_report(token_address: str) -> dict | None:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT report, tweet_count, generated_at
                FROM token_reports
                WHERE token_address = ?
                  AND generated_at >= DATEADD(DAY, ?, GETDATE())
            """, token_address, -REPORT_TTL_DAYS)
            row = cur.fetchone()
            if row:
                return {
                    "report":       row[0],
                    "tweet_count":  row[1],
                    "generated_at": row[2].isoformat(),
                    "cached":       True,
                }
    except Exception as exc:
        logger.warning(f"[report] cache lookup failed: {exc}")
    return None


def _get_token_info(token_address: str) -> dict | None:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT address, name, symbol, twitter_url, description
                FROM graduated_tokens
                WHERE address = ?
            """, token_address)
            row = cur.fetchone()
            if row:
                return {
                    "address":     row[0],
                    "name":        row[1],
                    "symbol":      row[2],
                    "twitter_url": row[3],
                    "description": row[4],
                }
    except Exception as exc:
        logger.warning(f"[report] token lookup failed: {exc}")
    return None


def _save_report(token_address: str, report: str, tweet_count: int = 0):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM token_reports WHERE token_address = ?",
                token_address,
            )
            if cur.fetchone():
                cur.execute("""
                    UPDATE token_reports
                    SET report = ?, tweet_count = ?, generated_at = GETDATE()
                    WHERE token_address = ?
                """, report, tweet_count, token_address)
            else:
                cur.execute("""
                    INSERT INTO token_reports (token_address, report, tweet_count)
                    VALUES (?, ?, ?)
                """, token_address, report, tweet_count)
        logger.info(f"[report] saved report for {token_address}")
    except Exception as exc:
        logger.error(f"[report] save failed: {exc}")


# ── Grok API call ─────────────────────────────────────────────────────────────

async def _generate_report_grok(token: dict) -> str | None:
    if not settings.grok_api_key:
        logger.warning("[report] GROK_API_KEY not configured")
        return None

    handle = _extract_handle(token.get("twitter_url", ""))
    name   = token.get("name") or token.get("symbol")
    symbol = token.get("symbol", "?")

    # Build user prompt — give Grok enough context to search X
    parts = [f"Meme token: {name} (${symbol}) on BNB Smart Chain."]
    if handle:
        parts.append(f"Official X account: @{handle}.")
    if token.get("description"):
        parts.append(f"Description: {token['description']}.")
    parts.append(
        "Search X for posts about this token from the last 30 days. "
        "Based on what you find, write a 2-paragraph analysis explaining "
        "why someone who just received this token might want to hold it. "
        "Be optimistic but honest. Under 80 words total."
    )
    user_prompt = " ".join(parts)

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                GROK_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.grok_api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": GROK_MODEL,
                    "messages": [
                        {"role": "system",  "content": _SYSTEM},
                        {"role": "user",    "content": user_prompt},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.7,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            logger.info(f"[report] Grok generated report for ${symbol} ({len(text)} chars)")
            return text

    except Exception as exc:
        logger.error(f"[report] Grok API error: {exc}")
        return None


# ── Public entry point ────────────────────────────────────────────────────────

async def get_or_create_report(token_address: str) -> dict | None:
    """
    1. Cache hit (< 7 days)  → return immediately
    2. Cache miss             → call Grok → save → return
    3. No Grok key / error   → return None silently
    """
    token_address = token_address.lower()

    cached = _get_cached_report(token_address)
    if cached:
        logger.info(f"[report] cache hit for {token_address}")
        return cached

    token = _get_token_info(token_address)
    if not token:
        return None

    report_text = await _generate_report_grok(token)
    if not report_text:
        return None

    _save_report(token_address, report_text)
    return {
        "report":       report_text,
        "tweet_count":  0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached":       False,
    }
