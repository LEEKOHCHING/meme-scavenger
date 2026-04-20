"""
Twitter / X Filtered Stream — real-time tweet archiver.

Subscribes to all twitter accounts stored in graduated_tokens.twitter_url
and saves every incoming tweet to token_tweets table.

Twitter v2 Filtered Stream docs:
  https://developer.twitter.com/en/docs/twitter-api/tweets/filtered-stream

Rate limits (Basic tier):
  - 25 stream rules, up to 512 chars each
  - One concurrent stream connection per app

Usage:
    python scripts/run_twitter_stream.py
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..database import get_db
from ..live_logger import log_event

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

STREAM_URL     = "https://api.twitter.com/2/tweets/search/stream"
RULES_URL      = "https://api.twitter.com/2/tweets/search/stream/rules"

HANDLES_PER_RULE   = 20     # keep well under 512-char rule limit
RECONNECT_DELAY    = 30     # base seconds between reconnect attempts
MAX_RECONNECT_WAIT = 300    # cap at 5 minutes

TWEET_FIELDS  = "created_at,author_id,text,public_metrics,lang,referenced_tweets"
EXPANSIONS    = "author_id"
USER_FIELDS   = "username"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.twitter_bearer_token}",
        "User-Agent": "MemeScavengerStream/1.0",
    }


def _extract_handle(url: str) -> str | None:
    """Pull the bare @handle (lowercased) from an x.com/twitter.com URL."""
    if not url:
        return None
    try:
        path = urlparse(url).path.strip("/").split("/")[0].lower()
        return path if path else None
    except Exception:
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_handle_map() -> dict[str, str]:
    """
    Return {handle_lowercase: token_address} for all tokens with a twitter_url.
    """
    result: dict[str, str] = {}
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT address, twitter_url FROM graduated_tokens "
            "WHERE twitter_url IS NOT NULL"
        )
        for address, url in cur.fetchall():
            handle = _extract_handle(url)
            if handle:
                result[handle] = address
    logger.info(f"[stream] Loaded {len(result)} tracked handles from DB")
    return result


def _save_tweet(tweet: dict, author_username: str | None, handle_map: dict[str, str]):
    """Persist one tweet to token_tweets (ignore duplicates)."""
    tweet_id = tweet.get("id", "")
    text     = tweet.get("text", "")
    lang     = tweet.get("lang")
    author_id = tweet.get("author_id")

    # Timestamps
    raw_ts = tweet.get("created_at")
    tweet_created_at = None
    if raw_ts:
        try:
            tweet_created_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Public metrics
    metrics      = tweet.get("public_metrics") or {}
    rt_count     = metrics.get("retweet_count", 0)
    like_count   = metrics.get("like_count", 0)
    reply_count  = metrics.get("reply_count", 0)
    quote_count  = metrics.get("quote_count", 0)

    # Retweet / reply flags
    refs       = tweet.get("referenced_tweets") or []
    is_retweet = any(r.get("type") == "retweeted" for r in refs)
    is_reply   = any(r.get("type") == "replied_to" for r in refs)

    # Match to token
    handle        = (author_username or "").lower()
    token_address = handle_map.get(handle)

    raw_json = json.dumps(tweet, ensure_ascii=False)

    try:
        with get_db() as conn:
            conn.cursor().execute("""
                INSERT INTO token_tweets (
                    tweet_id, token_address, twitter_handle, author_id,
                    text, lang, tweet_created_at,
                    retweet_count, like_count, reply_count, quote_count,
                    is_retweet, is_reply, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                tweet_id, token_address, handle or None, author_id,
                text, lang, tweet_created_at,
                rt_count, like_count, reply_count, quote_count,
                1 if is_retweet else 0,
                1 if is_reply   else 0,
                raw_json,
            )
        logger.info(
            f"[stream] Saved tweet {tweet_id} | @{handle} | "
            f"{'RT ' if is_retweet else ''}token={token_address or 'unknown'}"
        )
        log_event(
            source="TWITTER",
            event_type="tweet",
            message=f"Captured latest post from @{handle}",
            token_address=token_address,
        )
    except Exception as exc:
        # Unique constraint violation = duplicate, silently skip
        if "UQ_token_tweets_tweet_id" in str(exc) or "2627" in str(exc) or "2601" in str(exc):
            logger.debug(f"[stream] Duplicate tweet {tweet_id} — skipped")
        else:
            logger.error(f"[stream] Failed to save tweet {tweet_id}: {exc}")


# ── Rule management ───────────────────────────────────────────────────────────

async def _get_rules(client: httpx.AsyncClient) -> list[dict]:
    """Return current stream rules from Twitter."""
    r = await client.get(RULES_URL, headers=_headers())
    r.raise_for_status()
    return r.json().get("data") or []


async def _delete_all_rules(client: httpx.AsyncClient):
    """Delete every existing stream rule."""
    rules = await _get_rules(client)
    if not rules:
        logger.info("[stream] No existing rules to delete")
        return
    ids = [rule["id"] for rule in rules]
    payload = {"delete": {"ids": ids}}
    r = await client.post(RULES_URL, headers=_headers(), json=payload)
    r.raise_for_status()
    logger.info(f"[stream] Deleted {len(ids)} old rules")


async def _add_rules(client: httpx.AsyncClient, handles: list[str]):
    """
    Create stream rules batching handles into groups of HANDLES_PER_RULE.
    Rule value: `from:h1 OR from:h2 OR ...`
    """
    if not handles:
        logger.warning("[stream] No handles to add — stream will receive nothing")
        return

    rules = []
    for i in range(0, len(handles), HANDLES_PER_RULE):
        batch = handles[i : i + HANDLES_PER_RULE]
        value = " OR ".join(f"from:{h}" for h in batch)
        tag   = f"batch_{i // HANDLES_PER_RULE + 1}"

        # Safety check (Twitter limit: 512 chars per rule)
        if len(value) > 512:
            logger.error(f"[stream] Rule too long ({len(value)} chars): {value[:80]}…")
            continue

        rules.append({"value": value, "tag": tag})
        logger.debug(f"[stream] Rule {tag}: {value[:80]}{'…' if len(value) > 80 else ''}")

    payload = {"add": rules}
    r = await client.post(RULES_URL, headers=_headers(), json=payload)
    body = r.json()

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to add rules: {r.status_code} {body}")

    meta = body.get("meta", {})
    logger.info(
        f"[stream] Added {meta.get('summary', {}).get('created', '?')} rules "
        f"covering {len(handles)} handles"
    )


async def sync_rules(handles: list[str]):
    """Replace all stream rules with the current handle list."""
    async with httpx.AsyncClient(timeout=30) as client:
        await _delete_all_rules(client)
        await _add_rules(client, handles)


# ── Stream loop ───────────────────────────────────────────────────────────────

async def _stream_once(handle_map: dict[str, str]):
    """
    Open one stream connection and process tweets until disconnect.
    Returns normally on clean disconnect; raises on fatal errors.
    """
    params = {
        "tweet.fields": TWEET_FIELDS,
        "expansions":   EXPANSIONS,
        "user.fields":  USER_FIELDS,
    }

    logger.info("[stream] Connecting to filtered stream…")

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "GET", STREAM_URL,
            headers=_headers(),
            params=params,
        ) as response:

            if response.status_code == 429:
                logger.warning("[stream] Rate limited (429). Sleeping 15 min…")
                await asyncio.sleep(900)
                return

            if response.status_code != 200:
                body = await response.aread()
                raise RuntimeError(
                    f"Stream returned {response.status_code}: {body[:200]}"
                )

            logger.info("[stream] Connected. Waiting for tweets…")
            tweet_count = 0

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line:
                    continue  # heartbeat keep-alive

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"[stream] Non-JSON line: {line[:80]}")
                    continue

                # Extract tweet data
                tweet = payload.get("data")
                if not tweet:
                    logger.debug(f"[stream] No data field: {line[:120]}")
                    continue

                # Resolve author username from expansions
                includes  = payload.get("includes") or {}
                users     = includes.get("users") or []
                author_id = tweet.get("author_id", "")
                username  = next(
                    (u["username"] for u in users if u.get("id") == author_id),
                    None,
                )

                _save_tweet(tweet, username, handle_map)
                tweet_count += 1

    logger.info(f"[stream] Stream closed after {tweet_count} tweets")


async def run_stream():
    """
    Main entry point.  Syncs rules from DB, then streams forever
    with automatic reconnection.
    """
    if not settings.twitter_bearer_token:
        logger.error("[stream] TWITTER_BEARER_TOKEN not set — aborting")
        return

    # Build handle map from DB
    handle_map = _load_handle_map()
    handles    = sorted(handle_map.keys())

    if not handles:
        logger.error("[stream] No twitter handles found in DB — aborting")
        return

    logger.info(f"[stream] Syncing {len(handles)} handles to stream rules…")
    log_event("TWITTER", f"Stream started — tracking {len(handles)} accounts", "stream_start")
    await sync_rules(handles)

    # Stream with exponential backoff reconnect
    delay = RECONNECT_DELAY
    while True:
        try:
            await _stream_once(handle_map)
            delay = RECONNECT_DELAY   # reset on clean disconnect
        except asyncio.CancelledError:
            logger.info("[stream] Cancelled — shutting down")
            break
        except Exception as exc:
            logger.error(f"[stream] Error: {exc}. Reconnecting in {delay}s…")
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_WAIT)
