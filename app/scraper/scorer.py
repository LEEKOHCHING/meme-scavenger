"""
Token scoring engine.

Scores every non-blacklisted graduated token 0–100:

  Social Active  (0–40)  Has any post in the last 7 days?
  Social Content (0–30)  Claude judges if dev is still committed to the project.
  Trade          (0–20)  Recent volume from DexScreener.
  Human eval     (0–10)  Manual 'humanpoint' set by Lee (NULL → treated as 0).

Data sources:
  - token_tweets        : tweets received via Filtered Stream
  - graduated_tokens    : latest_tweet / latest_tweet_at from twitter_checker
  - token_metrics       : most-recent DexScreener snapshot

Run:
  python scripts/score_tokens.py
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from ..database import get_db

logger = logging.getLogger(__name__)

ANTHROPIC_API  = "https://api.anthropic.com/v1/messages"
LLM_MODEL      = "claude-haiku-4-5-20251001"   # cheap + fast for bulk scoring
LLM_DELAY      = 0.5   # seconds between LLM calls (avoid bursting)


# ── Trade score ───────────────────────────────────────────────────────────────

def _trade_score(volume_h24: float | None) -> int:
    """
    0–20 points based on 24h trading volume.
    Just having any volume earns points; high volume maxes out.
    """
    if not volume_h24 or volume_h24 <= 0:
        return 0
    if volume_h24 >= 100_000:
        return 20
    if volume_h24 >= 10_000:
        return 17
    if volume_h24 >= 1_000:
        return 13
    if volume_h24 >= 100:
        return 8
    return 3   # tiny amount but still alive


# ── Social Active score ───────────────────────────────────────────────────────

def _social_active_score(tweet_count_7d: int) -> int:
    """
    0 or 40 — binary: did this account post anything in the last 7 days?
    Even one post counts; frequency bonuses are handled in content scoring.
    """
    return 40 if tweet_count_7d > 0 else 0


# ── Social Content (LLM) ──────────────────────────────────────────────────────

_CONTENT_SYSTEM = """\
You are a crypto project analyst evaluating whether a BSC meme token developer
is still genuinely active on their project. You will receive recent tweets.

Score 0–30:
  25–30  Clear dev activity: technical updates, roadmap progress, real community
         building, responses to users, genuine project announcements.
  15–24  Regular posting, mix of project content and general crypto posts,
         some signs of ongoing effort.
  5–14   Mostly price hype, copied memes, shilling, or vague motivational posts
         with little actual project substance.
  0–4    Spam, pure noise, inactive ghost account, or content completely
         unrelated to the project.

Reply ONLY with valid JSON — no extra text:
{"score": <integer 0-30>, "reason": "<one concise sentence>"}
"""


async def _llm_content_score(symbol: str, tweets: list[str]) -> tuple[int, str]:
    """
    Ask Claude to score the social content quality.
    Returns (score 0-30, reason string).
    Falls back to 10 on any API error.
    """
    if not settings.anthropic_api_key:
        logger.warning("[scorer] No ANTHROPIC_API_KEY — defaulting content score to 10")
        return 10, "API key not configured"

    tweet_block = "\n".join(f"- {t}" for t in tweets[:10])  # max 10 tweets
    user_msg = (
        f"Token symbol: {symbol}\n\n"
        f"Recent tweets (last 7 days):\n{tweet_block}\n\n"
        f"Score the developer's commitment to this project."
    )

    payload = {
        "model":      LLM_MODEL,
        "max_tokens": 256,
        "system":     _CONTENT_SYSTEM,
        "messages":   [{"role": "user", "content": user_msg}],
    }
    headers = {
        "x-api-key":         settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(ANTHROPIC_API, json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning(f"[scorer] LLM HTTP {r.status_code}: {r.text[:120]}")
            return 10, f"LLM error {r.status_code}"

        text = r.json()["content"][0]["text"].strip()
        logger.debug(f"[scorer] LLM raw: {text}")
        # Extract JSON even if wrapped in markdown code fences
        if "```" in text:
            text = text.split("```")[-2].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        # Find first {...} block
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning(f"[scorer] No JSON in LLM response: {text[:80]}")
            return 10, "parse error"
        data   = json.loads(text[start:end])
        score  = max(0, min(30, int(data.get("score", 10))))
        reason = data.get("reason", "")
        return score, reason

    except Exception as exc:
        logger.warning(f"[scorer] LLM call failed for {symbol}: {exc}")
        return 10, f"error: {exc}"


# ── DB getters ────────────────────────────────────────────────────────────────

def _get_tokens() -> list[dict]:
    """Return all non-blacklisted tokens with their data needed for scoring."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                t.address,
                t.symbol,
                t.humanpoint,
                t.latest_tweet,
                t.latest_tweet_at,
                m.volume_h24
            FROM graduated_tokens t
            LEFT JOIN (
                SELECT address, volume_h24
                FROM token_metrics
                WHERE snapshot_date = (
                    SELECT MAX(snapshot_date) FROM token_metrics
                )
            ) m ON m.address = t.address
            WHERE t.blacklist = 0 OR t.blacklist IS NULL
            ORDER BY t.launch_time DESC
        """)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_recent_tweets(address: str, days: int = 7) -> list[str]:
    """
    Return tweet texts for this token from the last N days.
    Combines token_tweets (stream) + latest_tweet (checker) as fallback.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    texts: list[str] = []

    with get_db() as conn:
        cur = conn.cursor()
        # Stream tweets
        cur.execute("""
            SELECT text FROM token_tweets
            WHERE token_address = ?
              AND tweet_created_at >= ?
              AND is_retweet = 0
            ORDER BY tweet_created_at DESC
        """, address, cutoff)
        texts = [row[0] for row in cur.fetchall() if row[0]]

    return texts


def _save_score(
    address: str,
    score: int,
    s_active: int,
    s_content: int,
    s_trade: int,
    content_reason: str,
):
    with get_db() as conn:
        conn.cursor().execute("""
            UPDATE graduated_tokens SET
                score                = ?,
                score_social_active  = ?,
                score_social_content = ?,
                score_trade          = ?,
                score_updated_at     = GETDATE()
            WHERE address = ?
        """, score, s_active, s_content, s_trade, address)


# ── Main ──────────────────────────────────────────────────────────────────────

async def score_all_tokens() -> dict:
    """
    Score every non-blacklisted graduated token and update the DB.

    Returns summary stats dict.
    """
    tokens = _get_tokens()
    stats  = {"scored": 0, "skipped_no_data": 0, "total": len(tokens)}
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    logger.info(f"[scorer] Scoring {len(tokens)} tokens…")

    for i, tok in enumerate(tokens, 1):
        address    = tok["address"]
        symbol     = tok["symbol"] or address[:8]
        humanpoint = tok["humanpoint"] or 0
        volume_h24 = tok["volume_h24"]

        # ── 1. Gather recent tweets ───────────────────────────────────────────
        stream_tweets = _get_recent_tweets(address, days=7)

        # Fallback: use latest_tweet from checker if within 7 days
        checker_tweet = None
        if not stream_tweets and tok["latest_tweet"] and tok["latest_tweet_at"]:
            tweet_dt = tok["latest_tweet_at"]
            if tweet_dt.tzinfo is None:
                tweet_dt = tweet_dt.replace(tzinfo=timezone.utc)
            if tweet_dt >= cutoff:
                checker_tweet = tok["latest_tweet"]

        all_tweets   = stream_tweets or ([checker_tweet] if checker_tweet else [])
        tweet_count  = len(all_tweets)

        # ── 2. Social Active (0–40) ───────────────────────────────────────────
        s_active = _social_active_score(tweet_count)

        # ── 3. Social Content (0–30) via LLM ─────────────────────────────────
        s_content      = 0
        content_reason = ""
        if all_tweets:
            s_content, content_reason = await _llm_content_score(symbol, all_tweets)
            await asyncio.sleep(LLM_DELAY)

        # ── 4. Trade (0–20) ───────────────────────────────────────────────────
        s_trade = _trade_score(volume_h24)

        # ── 5. Total ──────────────────────────────────────────────────────────
        total = s_active + s_content + s_trade + humanpoint

        _save_score(address, total, s_active, s_content, s_trade, content_reason)
        stats["scored"] += 1

        logger.info(
            f"[scorer] [{i}/{len(tokens)}] {symbol:12s} "
            f"score={total:3d}  "
            f"active={s_active}  content={s_content}  "
            f"trade={s_trade}  human={humanpoint}"
            + (f"  | {content_reason}" if content_reason else "")
        )

    logger.info(f"[scorer] Done: {stats}")
    return stats
