"""
Batch X Activity Scorer — powered by twitterapi.io + Anthropic Claude

For every token in graduated_tokens that has a twitter_url and hasn't been
scored yet (x_score IS NULL), this script:
  1. Fetches real tweets from @handle via twitterapi.io Advanced Search
     (last 7 days: from:handle since_time:UNIX until_time:UNIX)
  2. Passes the actual tweet data to Claude for scoring + report generation
  3. Saves score + report back into graduated_tokens

Score interpretation:
  0-10   No posts found in the last 7 days — account silent or abandoned
  11-40  1-2 posts — minimal activity
  41-65  3-6 posts — moderate activity, some engagement
  66-85  7-14 posts — active, regular updates
  86-100 15+ posts — highly active, strong momentum

Run from project root:
    python scripts/score_tokens.py [--limit N] [--rescore] [--address 0x...]

    --limit N      Process N tokens (default: 30)
    --rescore      Re-score tokens that already have a score
    --address 0x.. Score a single token by contract address
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.config import settings
from app.database import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/score_tokens.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("score_tokens")

TWITTERAPIIO_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"
DELAY_SECONDS    = 2    # between tokens
MAX_TWEETS       = 20   # max tweets to pass to Claude (cost control)


# ── twitterapi.io ──────────────────────────────────────────────────────────────

async def fetch_tweets(handle: str) -> list[dict]:
    """
    Fetch tweets posted BY @handle in the last 7 days via twitterapi.io.
    Returns a list of tweet dicts. Returns [] on error or no tweets.
    """
    if not settings.twitterapiio_key:
        logger.warning("[twitter] TWITTERAPIIO_KEY not set — skipping tweet fetch")
        return []

    now_ts    = int(datetime.now(timezone.utc).timestamp())
    cutoff_ts = now_ts - 7 * 24 * 3600
    query     = f"from:{handle} since_time:{cutoff_ts} until_time:{now_ts}"

    all_tweets = []
    cursor     = None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(3):  # max 3 pages (~150 tweets)
                params = {"query": query, "queryType": "Latest"}
                if cursor:
                    params["cursor"] = cursor

                try:
                    resp = await client.get(
                        TWITTERAPIIO_URL,
                        headers={"X-API-Key": settings.twitterapiio_key},
                        params=params,
                    )
                    if resp.status_code == 429:
                        logger.info(f"[twitter] @{handle}: rate limited on page {page+1}, using {len(all_tweets)} tweets so far")
                        break
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.warning(f"[twitter] @{handle} page {page+1} HTTP {e.response.status_code}")
                    break

                data   = resp.json()
                tweets = data.get("tweets", [])
                if not tweets:
                    break

                for t in tweets:
                    all_tweets.append({
                        "text":         t.get("text", ""),
                        "createdAt":    t.get("createdAt", ""),
                        "likeCount":    t.get("likeCount", 0),
                        "retweetCount": t.get("retweetCount", 0),
                        "viewCount":    t.get("viewCount", 0),
                    })

                if not data.get("has_next_page") or not data.get("next_cursor"):
                    break
                cursor = data["next_cursor"]
                await asyncio.sleep(1)

    except Exception as exc:
        logger.warning(f"[twitter] fetch_tweets @{handle}: {exc}")

    logger.info(f"[twitter] @{handle}: {len(all_tweets)} tweets (last 7d)")
    return all_tweets


# ── Prompt ─────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a crypto community analyst evaluating a meme token's X account activity.
You will be given real tweet data fetched directly from the account for the last 7 days.

Scoring guide (based on number of posts in the last 7 days):
  0-10   Zero posts — account silent or abandoned
  11-40  1-2 posts — minimal activity
  41-65  3-6 posts — moderate activity, some engagement
  66-85  7-14 posts — active, regular updates
  86-100 15+ posts — highly active, strong momentum

Report guidelines (3-4 paragraphs, under 300 words):
  - State the exact number of posts found.
  - Describe the content, tone, and engagement levels of those posts.
  - If score >= 20: cautiously optimistic, cite what you actually observed.
  - If score < 20: honest and neutral — do not manufacture optimism.
  - Never say "100x", "moon", "guaranteed", or predict price.
  - No bullet points, no headers — prose only.

Return ONLY a raw JSON object with exactly two fields:
{"score": <int>, "report": "<text>"}
No markdown, no explanation outside the JSON.
"""


def _build_prompt(token: dict, tweets: list[dict]) -> str:
    name   = token.get("name") or token.get("symbol")
    symbol = token.get("symbol", "?")
    handle = token.get("twitter_handle")
    today  = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=7)

    if not handle:
        return (
            f'Meme token: {name} (${symbol}). No official X account linked. '
            'Return: {"score": 0, "report": "No official X account is linked for this token. Activity cannot be assessed."}'
        )

    if not tweets:
        return (
            f"Meme token: {name} (${symbol}) on BNB Smart Chain. "
            f"Official X account: @{handle}. Date range: {cutoff} to {today}.\n\n"
            "TWEET DATA: No tweets found in this period.\n\n"
            'Return: {"score": 0, "report": "No posts were found on the official X account in the last 7 days. The account appears to be inactive."}'
        )

    sample = tweets[:MAX_TWEETS]
    lines  = []
    for i, t in enumerate(sample, 1):
        eng  = f"👍{t['likeCount']} 🔁{t['retweetCount']} 👁{t['viewCount']}"
        text = t["text"][:200].replace("\n", " ")
        lines.append(f"  [{i}] {t['createdAt'][:10]} | {eng} | {text}")

    return (
        f"Meme token: {name} (${symbol}) on BNB Smart Chain. "
        f"Official X account: @{handle}. Date range: {cutoff} to {today} (last 7 days).\n\n"
        f"REAL TWEET DATA — {len(tweets)} posts found (showing {len(sample)}):\n"
        + "\n".join(lines) + "\n\n"
        f"Based on the above {len(tweets)} real tweets, score the account (0-100) and write a report. "
        'Return only: {"score": <int>, "report": "<text>"}'
    )


# ── Claude call ────────────────────────────────────────────────────────────────

async def call_claude(prompt: str) -> dict | None:
    raw = ""
    try:
        client  = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = await asyncio.to_thread(
            client.messages.create,
            model=settings.anthropic_model,
            max_tokens=700,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$",          "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract via regex (handles embedded newlines in report)
            score_m  = re.search(r'"score"\s*:\s*(\d+)',          raw)
            report_m = re.search(r'"report"\s*:\s*"([\s\S]*?)"\s*}', raw)
            if score_m and report_m:
                report_text = report_m.group(1).replace("\n", " ").replace("\r", "").strip()
                return {"score": int(score_m.group(1)), "report": report_text}
            raise

    except json.JSONDecodeError as exc:
        logger.warning(f"[claude] JSON parse error: {exc} | raw: {raw[:200]}")
    except Exception as exc:
        logger.error(f"[claude] API error: {exc}")
    return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_tokens(limit: int, rescore: bool, address: str | None = None) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        if address:
            cur.execute("""
                SELECT address, name, symbol, twitter_url, description
                FROM graduated_tokens
                WHERE address = ?
            """, address.lower())
        else:
            condition = "" if rescore else "AND x_score IS NULL"
            cur.execute(f"""
                SELECT TOP {limit}
                    address, name, symbol, twitter_url, description
                FROM graduated_tokens
                WHERE twitter_url IS NOT NULL
                  {condition}
                ORDER BY launch_time DESC
            """)
        rows = cur.fetchall()

    tokens = []
    for r in rows:
        twitter_url = r[3] or ""
        parts = [
            p for p in twitter_url
            .replace("https://", "").replace("http://", "")
            .split("/")
            if p and p not in ("x.com", "twitter.com", "www.x.com")
        ]
        handle = parts[0] if parts else None
        tokens.append({
            "address":        r[0],
            "name":           r[1],
            "symbol":         r[2],
            "twitter_url":    twitter_url,
            "twitter_handle": handle,
            "description":    r[4],
        })
    return tokens


def save_score(address: str, score: int, report: str):
    with get_db() as conn:
        conn.cursor().execute("""
            UPDATE graduated_tokens
            SET x_score     = ?,
                x_report    = ?,
                x_scored_at = GETDATE()
            WHERE address = ?
        """, score, report, address)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(limit: int, rescore: bool, address: str | None = None):
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env — aborting")
        return
    if not settings.twitterapiio_key:
        logger.warning("TWITTERAPIIO_KEY not set — tweet fetch disabled")

    tokens = get_tokens(limit, rescore, address)
    logger.info(f"=== Scoring {len(tokens)} tokens via twitterapi.io + Claude ({settings.anthropic_model}) ===")

    stats = {"scored": 0, "failed": 0, "tweets_total": 0}

    for i, tok in enumerate(tokens, 1):
        symbol      = tok["symbol"]
        tok_address = tok["address"]
        handle      = tok.get("twitter_handle")

        logger.info(f"[{i}/{len(tokens)}] ${symbol} @{handle or '(no handle)'}")

        # 1. Fetch real tweets
        tweets = await fetch_tweets(handle) if handle else []
        stats["tweets_total"] += len(tweets)

        # 2. Build prompt + call Claude
        prompt = _build_prompt(tok, tweets)
        result = await call_claude(prompt)

        if not result:
            logger.warning("  → failed (no result from Claude)")
            stats["failed"] += 1
            time.sleep(DELAY_SECONDS)
            continue

        score  = result.get("score")
        report = result.get("report", "").strip()

        if not isinstance(score, int) or not (0 <= score <= 100):
            logger.warning(f"  → invalid score: {score!r}")
            stats["failed"] += 1
            time.sleep(DELAY_SECONDS)
            continue

        if not report:
            logger.warning("  → empty report")
            stats["failed"] += 1
            time.sleep(DELAY_SECONDS)
            continue

        save_score(tok_address, score, report)
        logger.info(f"  → score={score}\n{report}")
        stats["scored"] += 1

        time.sleep(DELAY_SECONDS)

    logger.info(
        f"=== Done === scored={stats['scored']} failed={stats['failed']} "
        f"total_tweets_fetched={stats['tweets_total']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=30,  help="Number of tokens to process")
    parser.add_argument("--rescore", action="store_true",   help="Re-score already scored tokens")
    parser.add_argument("--address", type=str, default=None, help="Score a single token by contract address")
    args = parser.parse_args()

    asyncio.run(main(args.limit, args.rescore, args.address))
