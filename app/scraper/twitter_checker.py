"""
Twitter account checker.

For every graduated token with a twitter_url and xchecked != 1:
  1. Resolve the handle to a Twitter user ID.
  2. Fetch that user's latest non-retweet tweet.
  3. Save tweet text + created_at to graduated_tokens.
  4. Set xchecked = 1 (regardless of outcome — suspended, no tweets, etc.)

Twitter API v2 endpoints used (Bearer Token / app-only auth):
  GET /2/users/by/username/{username}   → resolve handle → user_id
  GET /2/users/{id}/tweets              → latest tweet

Rate limits (Basic tier, app-level):
  User lookup  : 300 req / 15 min = 20 / min
  User timeline: 1500 req / 15 min = 100 / min
  → 4-second delay between accounts keeps us safely within both limits.
"""

import asyncio
import logging
from datetime import datetime
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..database import get_db

logger = logging.getLogger(__name__)

BASE          = "https://api.twitter.com/2"
DELAY_SECONDS = 4.0   # 15 req/min — well under both rate limits


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.twitter_bearer_token}",
        "User-Agent": "MemeScavengerChecker/1.0",
    }


def _handle_from_url(url: str) -> str | None:
    """Extract bare handle from https://x.com/<handle>"""
    if not url:
        return None
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        return parts[0] if len(parts) == 1 else None
    except Exception:
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_unchecked() -> list[tuple]:
    """Return (address, symbol, twitter_url) for all tokens not yet X-checked."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT address, symbol, twitter_url
            FROM   graduated_tokens
            WHERE  twitter_url IS NOT NULL
              AND  (xchecked IS NULL OR xchecked <> 1)
            ORDER  BY scraped_at DESC
        """)
        return cur.fetchall()


def _mark_checked(address: str, tweet_text: str | None = None, tweet_at: datetime | None = None):
    """Save latest tweet (if any) and mark xchecked = 1."""
    with get_db() as conn:
        conn.cursor().execute("""
            UPDATE graduated_tokens
            SET    xchecked       = 1,
                   latest_tweet   = COALESCE(?, latest_tweet),
                   latest_tweet_at = COALESCE(?, latest_tweet_at)
            WHERE  address = ?
        """, tweet_text, tweet_at, address)


# ── Twitter API calls ─────────────────────────────────────────────────────────

async def _get_user_id(client: httpx.AsyncClient, handle: str) -> str | None:
    """
    Resolve handle → Twitter user_id.
    Returns None if account not found, suspended, or any error.
    """
    url = f"{BASE}/users/by/username/{handle}"
    try:
        r = await client.get(url, headers=_headers(), timeout=15)
    except Exception as exc:
        logger.warning(f"[xcheck] Network error looking up @{handle}: {exc}")
        return None

    if r.status_code == 200:
        body = r.json()
        # Twitter may return 200 but with top-level errors (suspended, etc.)
        if "errors" in body and "data" not in body:
            detail = body["errors"][0].get("detail", "unknown error")
            logger.info(f"[xcheck] @{handle}: {detail}")
            return None
        return body.get("data", {}).get("id")

    if r.status_code == 404:
        logger.info(f"[xcheck] @{handle}: account not found (404)")
        return None

    if r.status_code == 403:
        logger.info(f"[xcheck] @{handle}: account suspended / forbidden (403)")
        return None

    if r.status_code == 429:
        logger.warning(f"[xcheck] Rate limited on user lookup. Sleeping 15 min…")
        await asyncio.sleep(900)
        return None  # skip this account for now; will be retried next run

    logger.warning(f"[xcheck] @{handle}: user lookup HTTP {r.status_code}")
    return None


async def _get_latest_tweet(
    client: httpx.AsyncClient, user_id: str
) -> tuple[str | None, datetime | None]:
    """
    Fetch the most recent non-retweet tweet for user_id.
    Returns (text, created_at) or (None, None).
    """
    url = f"{BASE}/users/{user_id}/tweets"
    params = {
        "max_results": 5,                   # fetch a few to skip retweets
        "tweet.fields": "created_at,text",
        "exclude": "retweets",              # only original tweets
    }
    try:
        r = await client.get(url, headers=_headers(), params=params, timeout=15)
    except Exception as exc:
        logger.warning(f"[xcheck] Network error fetching tweets for {user_id}: {exc}")
        return None, None

    if r.status_code == 429:
        logger.warning("[xcheck] Rate limited on timeline. Sleeping 15 min…")
        await asyncio.sleep(900)
        return None, None

    if r.status_code != 200:
        logger.warning(f"[xcheck] Timeline HTTP {r.status_code} for user {user_id}")
        return None, None

    body  = r.json()
    tweets = body.get("data") or []
    if not tweets:
        return None, None

    latest   = tweets[0]
    text     = latest.get("text")
    raw_time = latest.get("created_at")
    tweet_at = None
    if raw_time:
        try:
            tweet_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            pass

    return text, tweet_at


# ── Main loop ─────────────────────────────────────────────────────────────────

async def check_twitter_accounts() -> dict:
    """
    Walk every unchecked token, fetch its latest tweet, and mark it done.

    Returns:
        {"found": int, "no_tweet": int, "failed": int, "total": int}
    """
    if not settings.twitter_bearer_token:
        logger.error("[xcheck] TWITTER_BEARER_TOKEN not set — aborting")
        return {}

    tokens = _get_unchecked()
    stats  = {"found": 0, "no_tweet": 0, "failed": 0, "total": len(tokens)}

    if not tokens:
        logger.info("[xcheck] Nothing to check — all accounts already verified.")
        return stats

    logger.info(
        f"[xcheck] {len(tokens)} accounts to check. "
        f"ETA ~{len(tokens) * DELAY_SECONDS / 60:.1f} min"
    )

    async with httpx.AsyncClient() as client:
        for i, (address, symbol, twitter_url) in enumerate(tokens, 1):
            handle = _handle_from_url(twitter_url)
            if not handle:
                logger.warning(f"[xcheck] [{i}/{len(tokens)}] Bad URL, skipping: {twitter_url}")
                _mark_checked(address)
                stats["failed"] += 1
                continue

            logger.info(f"[xcheck] [{i}/{len(tokens)}] {symbol} (@{handle})")

            # Step 1: resolve user ID
            user_id = await _get_user_id(client, handle)
            if not user_id:
                # Suspended / deleted — still mark checked so we don't retry
                _mark_checked(address)
                stats["failed"] += 1
                await asyncio.sleep(DELAY_SECONDS)
                continue

            # Step 2: fetch latest tweet
            tweet_text, tweet_at = await _get_latest_tweet(client, user_id)

            if tweet_text:
                stats["found"] += 1
                logger.info(
                    f"[xcheck]   ✓ Latest tweet ({tweet_at}): "
                    f"{tweet_text[:80]}{'…' if len(tweet_text) > 80 else ''}"
                )
            else:
                stats["no_tweet"] += 1
                logger.info(f"[xcheck]   – No tweets found")

            _mark_checked(address, tweet_text, tweet_at)
            await asyncio.sleep(DELAY_SECONDS)

    logger.info(f"[xcheck] Done: {stats}")
    return stats
