"""
GeckoTerminal social data fetcher.

Fetches twitter_handle, telegram_handle, websites, description
for each graduated token in the DB.

Rate limit: 30 req/min (free tier). We use 15/min → 4 sec between requests.
"""

import asyncio
import logging
from urllib.parse import urlparse

import httpx

from ..database import get_db
from ..live_logger import log_event

logger = logging.getLogger(__name__)

GT_BASE       = "https://api.geckoterminal.com/api/v2"
DELAY_SECONDS = 12.0         # 5 req/min — safely under 10/min public limit
HEADERS       = {"Accept": "application/json", "User-Agent": "MemeScavengerArchiver/1.0"}


# ── Validation helpers ────────────────────────────────────────────────────────

# Known celebrity / exchange accounts being used as fake project socials
_TW_SPAM_HANDLES = {
    "elonmusk", "heyibinance", "cz_binance", "binance", "richardteng",
    "_richardteng", "realdonaldtrump", "vitalikbuterin", "saylor",
    "michael_saylor", "bscnews", "bnbchain", "pancakeswap",
    "binancezh", "binancemovie", "binancejp",
}

# Website domains that are not legitimate project sites
_WEB_SPAM_DOMAINS = (
    "example.com",
    "x.com", "twitter.com", "t.co",        # social media posts
    "wikipedia.org",                         # encyclopedia
    "binance.com", "bnbchain.org",           # exchange pages
    "amazon.com", "youtube.com",             # product/video links
    "four.meme",                             # referral links back to the platform
    "t.me",                                  # telegram links in website field
    "weixin.qq.com", "weibo.com",            # Chinese social media posts
    "metro.co.uk",                           # news articles
)


def _twitter_url(handle: str | None) -> str | None:
    """
    Return a clean x.com profile URL, or None if invalid.

    Valid format: https://x.com/<handle>  — exactly ONE path segment.
    Anything with sub-paths (/status/, /i/, /hashtag/, etc.) is a tweet
    link or internal page, not a profile, so it is rejected.
    """
    if not handle:
        return None
    handle = handle.strip().lstrip("@")
    url = handle if handle.startswith("http") else f"https://x.com/{handle}"

    parsed = urlparse(url)

    # Must be x.com or twitter.com
    domain = parsed.netloc.lower().lstrip("www.")
    if domain not in ("x.com", "twitter.com"):
        return None

    # Path must be exactly /<handle> — one non-empty segment, nothing after it
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 1:
        return None  # tweet, internal page, or empty

    handle_clean = parts[0].lower()

    # Reject known celebrity / exchange handles
    if handle_clean in _TW_SPAM_HANDLES:
        return None

    # Normalise to x.com
    return f"https://x.com/{parts[0]}"


def _telegram_url(handle: str | None) -> str | None:
    """Return a clean t.me URL, or None if invalid."""
    if not handle:
        return None
    handle = handle.strip().lstrip("@")
    if handle.startswith("http"):
        return handle
    return f"https://t.me/{handle}"


def _first_website(websites: list) -> str | None:
    """Return the first legitimate website URL, skipping known spam domains."""
    for w in (websites or []):
        if not w or not w.startswith("http"):
            continue
        domain = urlparse(w).netloc.lower().lstrip("www.")
        if any(domain == s or domain.endswith("." + s) for s in _WEB_SPAM_DOMAINS):
            continue
        # Skip URLs that look like post/product links, not homepages
        path = urlparse(w).path.lower()
        if any(p in path for p in ("/status/", "/post/", "/dp/", "/square/", "?code=")):
            continue
        return w
    return None


# ── DB ────────────────────────────────────────────────────────────────────────

def _get_unchecked(limit: int = 0) -> list[tuple]:
    """
    Return tokens that still need a GeckoTerminal pass:
      - never checked before (gt_checked_at IS NULL), OR
      - checked before but img_url is still missing
    """
    with get_db() as conn:
        cur = conn.cursor()
        sql = """
            SELECT address, symbol FROM graduated_tokens
            WHERE gt_checked_at IS NULL
               OR img_url IS NULL
            ORDER BY launch_time DESC
        """
        if limit:
            sql = sql.replace("SELECT", f"SELECT TOP {limit}")
        cur.execute(sql)
        return cur.fetchall()


def _save_social(address: str, data: dict):
    """Update one token with social data from GeckoTerminal."""
    attr = data.get("data", {}).get("attributes", {})

    twitter  = _twitter_url(attr.get("twitter_handle"))
    telegram = _telegram_url(attr.get("telegram_handle"))
    website  = _first_website(attr.get("websites") or [])
    desc     = attr.get("description") or None
    img_url  = attr.get("image_url") or None

    with get_db() as conn:
        conn.cursor().execute("""
            UPDATE graduated_tokens SET
                twitter_url   = COALESCE(twitter_url,  ?),
                telegram_url  = COALESCE(telegram_url, ?),
                web_url       = COALESCE(web_url,      ?),
                description   = COALESCE(description,  ?),
                img_url       = COALESCE(img_url,      ?),
                gt_checked_at = GETDATE()
            WHERE address = ?
        """, twitter, telegram, website, desc, img_url, address)


def _mark_checked(address: str):
    """Mark as checked even if GeckoTerminal returned nothing (404 etc.)."""
    with get_db() as conn:
        conn.cursor().execute(
            "UPDATE graduated_tokens SET gt_checked_at = GETDATE() WHERE address = ?",
            address,
        )


# ── Main loop ─────────────────────────────────────────────────────────────────

async def update_social(limit: int = 0) -> dict:
    """
    Fetch social data for all tokens where gt_checked_at IS NULL.

    Args:
        limit: max tokens to process (0 = all unchecked)

    Returns:
        {"found": int, "empty": int, "errors": int, "total": int}
    """
    tokens = _get_unchecked(limit)
    stats  = {"found": 0, "empty": 0, "errors": 0, "total": len(tokens)}

    if not tokens:
        logger.info("[social] Nothing to update — all tokens already checked.")
        return stats

    logger.info(f"[social] {len(tokens)} tokens to check. ETA ~{len(tokens)*DELAY_SECONDS/60:.1f} min")

    async with httpx.AsyncClient(headers=HEADERS, timeout=12) as client:
        for i, (address, symbol) in enumerate(tokens, 1):
            url = f"{GT_BASE}/networks/bsc/tokens/{address}/info"
            for attempt in range(3):   # up to 3 attempts per token
                try:
                    r = await client.get(url)

                    if r.status_code == 200:
                        body = r.json()
                        _save_social(address, body)
                        attr = body.get("data", {}).get("attributes", {})

                        # Use filtered values — what was actually written to DB
                        tw  = _twitter_url(attr.get("twitter_handle"))
                        tg  = _telegram_url(attr.get("telegram_handle"))
                        web = _first_website(attr.get("websites") or [])
                        desc = attr.get("description") or None

                        if any([tw, tg, web, desc]):
                            stats["found"] += 1
                            logger.info(
                                f"[social] [{i}/{len(tokens)}] {symbol}: "
                                f"tw={tw}  tg={tg}  web={web}"
                            )
                            parts = []
                            if tw:  parts.append(f"tw ✓")
                            if tg:  parts.append(f"tg ✓")
                            if web: parts.append(f"web ✓")
                            log_event("GECKO", f"{symbol}: found {' '.join(parts)}", "social_found",
                                      symbol=symbol, token_address=address)
                        else:
                            stats["empty"] += 1
                            logger.debug(f"[social] [{i}/{len(tokens)}] {symbol}: no valid social data after filtering")
                            log_event("GECKO", f"{symbol}: no social data", "social_empty",
                                      symbol=symbol, token_address=address)
                        break  # success — move to next token

                    elif r.status_code == 404:
                        logger.debug(f"[social] [{i}/{len(tokens)}] {symbol}: not on GeckoTerminal")
                        _mark_checked(address)
                        stats["empty"] += 1
                        break

                    elif r.status_code == 429:
                        wait = 65 if attempt == 0 else 120
                        logger.warning(f"[social] Rate limited (attempt {attempt+1}). Sleeping {wait}s…")
                        await asyncio.sleep(wait)
                        # retry same token

                    else:
                        logger.warning(f"[social] [{i}/{len(tokens)}] {symbol}: HTTP {r.status_code}")
                        stats["errors"] += 1
                        break

                except Exception as exc:
                    logger.error(f"[social] [{i}/{len(tokens)}] {address}: {exc}")
                    stats["errors"] += 1
                    break

            await asyncio.sleep(DELAY_SECONDS)

    logger.info(f"[social] Done: {stats}")
    return stats
