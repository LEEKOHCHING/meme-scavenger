"""
Batch X Activity Scorer — powered by xAI Grok

For every token in graduated_tokens that has a twitter_url and hasn't been
scored yet (x_score IS NULL), calls Grok to:
  1. Search X for posts from the last 30 days
  2. Return a JSON with { "score": 0-100, "report": "..." }
  3. Save score + report back into graduated_tokens

Score interpretation:
  0-10   No posts found in the last month — community silent
  11-40  Minimal activity — sporadic posts, low engagement
  41-65  Moderate activity — some community pulse
  66-85  Active community — regular posts, real engagement
  86-100 High conviction signals — strong narrative momentum

Run from project root:
    python scripts/score_tokens.py [--limit N] [--rescore]

    --limit N    Process N tokens (default: 30)
    --rescore    Re-score tokens that already have a score
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

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

GROK_API_URL  = "https://api.x.ai/v1/chat/completions"
GROK_MODEL    = "grok-3"
DELAY_SECONDS = 5   # between calls — be polite to the API

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a crypto community analyst scoring meme tokens based on their X (Twitter) activity.

Your job:
1. Search X for posts about the given token published strictly within the last 7 days.
   - Use today's date (provided in the prompt) as the reference point.
   - A post counts only if it was published on or after (today minus 7 days).
   - Do NOT include posts older than 7 days, even if they are the most recent ones available.
   - If the most recent post you can find is older than 7 days, treat the last-7-day count as zero.

2. Score the community activity (0-100) based solely on last-7-day posts:
   0-10   No posts found in the last 30 days — community silent or account gone
   11-40  Minimal — only a handful of sporadic posts, low engagement
   41-65  Moderate — some genuine community pulse with real interactions
   66-85  Active — regular posts, real engagement, visible momentum
   86-100 Strong — high conviction community, sustained daily activity

3. Write a report (3-4 paragraphs, under 300 words):
   - State how many posts you found in the last 7 days and when the most recent one was.
   - If score >= 20: cautiously optimistic, cite specific signals you found.
   - If score < 20: honest and neutral — do not manufacture optimism.
   - Never say "100x", "moon", "guaranteed", or predict price.
   - No bullet points, no headers — prose only.

Return ONLY a raw JSON object with exactly two fields:
{"score": <int>, "report": "<text>"}
No markdown, no explanation outside the JSON.
"""


def _build_prompt(token: dict) -> str:
    from datetime import datetime, timezone, timedelta
    today     = datetime.now(timezone.utc).date()
    cutoff    = today - timedelta(days=7)

    name   = token.get("name") or token.get("symbol")
    symbol = token.get("symbol", "?")
    handle = token.get("twitter_handle")

    parts = [f"Today's date: {today}. Only count posts published on or after {cutoff}."]
    parts.append(f"Meme token: {name} (${symbol}) on BNB Smart Chain.")
    if handle:
        parts.append(f"Official X account: @{handle}.")
    if token.get("description"):
        parts.append(f"Description: {token['description']}.")
    parts.append(
        f"Search X for posts about this token published between {cutoff} and {today}. "
        "Score the last-7-day community activity (0-100) and write a report. "
        "Return only a JSON object: {\"score\": <int>, \"report\": \"<text>\"}"
    )
    return " ".join(parts)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_tokens(limit: int, rescore: bool) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
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
        parts = [p for p in twitter_url.replace("https://", "").replace("http://", "")
                 .split("/") if p and p not in ("x.com", "twitter.com", "www.x.com")]
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


# ── Grok call ─────────────────────────────────────────────────────────────────

async def call_grok(prompt: str) -> dict | None:
    raw = ""
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                GROK_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.grok_api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       GROK_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens":  600,
                    "temperature": 0.5,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            return json.loads(raw)

    except json.JSONDecodeError as exc:
        logger.warning(f"[grok] JSON parse error: {exc} | raw: {raw[:200]}")
    except Exception as exc:
        logger.error(f"[grok] API error: {exc}")
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(limit: int, rescore: bool):
    if not settings.grok_api_key:
        logger.error("GROK_API_KEY not set in .env — aborting")
        return

    tokens = get_tokens(limit, rescore)
    logger.info(f"=== Scoring {len(tokens)} tokens via Grok ===")

    stats = {"scored": 0, "failed": 0}

    for i, tok in enumerate(tokens, 1):
        symbol  = tok["symbol"]
        address = tok["address"]
        handle  = tok.get("twitter_handle") or "(no handle)"

        logger.info(f"[{i}/{len(tokens)}] ${symbol} @{handle}")

        prompt = _build_prompt(tok)
        result = await call_grok(prompt)

        if not result:
            logger.warning(f"  → failed (no result)")
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
            logger.warning(f"  → empty report")
            stats["failed"] += 1
            time.sleep(DELAY_SECONDS)
            continue

        save_score(address, score, report)
        logger.info(f"  → score={score}  {report[:80]}…")
        stats["scored"] += 1

        time.sleep(DELAY_SECONDS)

    logger.info(
        f"=== Done === scored={stats['scored']} failed={stats['failed']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=30, help="Number of tokens to process")
    parser.add_argument("--rescore", action="store_true",  help="Re-score already scored tokens")
    args = parser.parse_args()

    asyncio.run(main(args.limit, args.rescore))
