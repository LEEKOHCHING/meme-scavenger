"""
Score all graduated tokens 0–100.

Weights:
  Social Active  40%  — posted in last 7 days?
  Social Content 30%  — Claude judges if dev is still committed
  Trade          20%  — DexScreener 24h volume
  Human eval     10%  — Lee's manual humanpoint (0–10)

Run from project root:
    python scripts/score_tokens.py

Scores are saved to graduated_tokens.score.
Blacklisted tokens (blacklist=1) are skipped.
Re-running is safe — scores are simply overwritten.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.scraper.scorer import score_all_tokens

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/score_tokens.log", encoding="utf-8"),
    ],
)


async def main():
    logger = logging.getLogger("score_tokens_script")
    logger.info("=== Starting token scoring ===")
    stats = await score_all_tokens()
    logger.info(
        f"=== Done === scored={stats['scored']} total={stats['total']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
