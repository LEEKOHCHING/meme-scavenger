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
GROK_MODEL    = "grok-4.20-0309-reasoning"
DELAY_SECONDS = 5   # between calls — be polite to the API

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a crypto community analyst evaluating whether a meme token's official X account is still active.

IMPORTANT: You MUST use your real-time X search capability to look up the account before answering. Do NOT rely on training data or memory. Always search X live first.

Your job:
1. SEARCH X NOW for the official account profile provided.
   - Look ONLY at posts published BY that account itself.
   - Do NOT search the broader X platform for token name or symbol mentions.
   - Do NOT include replies or posts from other accounts — only the account's own tweets.

2. Count posts published BY that account in the last 7 days (cutoff date is provided).
   - Only count posts dated on or after the cutoff date.
   - If the most recent post is older than the cutoff, the count is zero.
   - If you cannot access the account, state that clearly and assign score 0.

3. Score the account's own posting activity (0-100):
   0-10   Zero posts in the last 7 days — account silent or abandoned
   11-40  1-2 posts — minimal activity
   41-65  3-6 posts — moderate activity, some engagement
   66-85  7-14 posts — active, regular updates
   86-100 15+ posts — highly active, strong momentum

4. Write a report (3-4 paragraphs, under 300 words):
   - State the exact number of posts this account published in the last 7 days.
   - Describe the content and tone of those posts.
   - If score >= 20: cautiously optimistic, cite what you actually observed.
   - If score < 20: honest and neutral — do not manufacture optimism.
   - Never say "100x", "moon", "guaranteed", or predict price.
   - No bullet points, no headers — prose only.

Return ONLY a raw JSON object with exactly two fields:
{"score": <int>, "report": "<text>"}
No markdown, no explanation outside the JSON.
"""


def _build_prompt(token: dict) -> str:
    from datetime import datetime, timezone, timedelta
    today  = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=7)

    name   = token.get("name") or token.get("symbol")
    symbol = token.get("symbol", "?")
    handle = token.get("twitter_handle")

    if not handle:
        return (
            f"Meme token: {name} (${symbol}). No official X account available. "
            "Return: {\"score\": 0, \"report\": \"No official X account is linked for this token. Activity cannot be assessed.\"}"
        )

    return (
        f"Today's date: {today}. Cutoff date (7 days ago): {cutoff}. "
        f"Meme token: {name} (${symbol}) on BNB Smart Chain. "
        f"Official X account: @{handle}. "
        f"Visit the profile of @{handle} and count posts published BY @{handle} between {cutoff} and {today}. "
        "Do NOT search for the token name or symbol across X — only look at this account's own posts. "
        "Score the account's posting activity (0-100) and write a report. "
        "Return only: {\"score\": <int>, \"report\": \"<text>\"}"
    )


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
                    "temperature": 0,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            # Parse with raw_decode to be tolerant, then extract score+report manually
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Fallback: extract score and report via regex to handle embedded newlines
                score_m  = re.search(r'"score"\s*:\s*(\d+)', raw)
                report_m = re.search(r'"report"\s*:\s*"([\s\S]*?)"\s*}', raw)
                if score_m and report_m:
                    report_text = report_m.group(1).replace('\n', ' ').replace('\r', '').strip()
                    data = {"score": int(score_m.group(1)), "report": report_text}
                else:
                    raise
            return data

    except json.JSONDecodeError as exc:
        logger.warning(f"[grok] JSON parse error: {exc} | raw: {raw[:200]}")
    except Exception as exc:
        logger.error(f"[grok] API error: {exc}")
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(limit: int, rescore: bool, address: str | None = None):
    if not settings.grok_api_key:
        logger.error("GROK_API_KEY not set in .env — aborting")
        return

    tokens = get_tokens(limit, rescore, address)
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
        logger.info(f"  → score={score}\n{report}")
        stats["scored"] += 1

        time.sleep(DELAY_SECONDS)

    logger.info(
        f"=== Done === scored={stats['scored']} failed={stats['failed']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=30,  help="Number of tokens to process")
    parser.add_argument("--rescore", action="store_true",   help="Re-score already scored tokens")
    parser.add_argument("--address", type=str, default=None, help="Score a single token by contract address")
    args = parser.parse_args()

    asyncio.run(main(args.limit, args.rescore, args.address))
