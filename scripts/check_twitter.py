"""
Check every X/Twitter account in graduated_tokens that hasn't been verified yet.

Fetches the latest tweet for each account and saves it to the DB.
Accounts that are suspended, deleted, or have no tweets are still
marked as checked (xchecked = 1) so they are skipped on future runs.

Run from project root:
    python scripts/check_twitter.py

~4 seconds per account. For 48 accounts: ~3 minutes total.
Safe to interrupt and resume — progress is saved after each account.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.scraper.twitter_checker import check_twitter_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/check_twitter.log", encoding="utf-8"),
    ],
)


async def main():
    logger = logging.getLogger("check_twitter_script")
    logger.info("=== Starting Twitter account checker ===")
    stats = await check_twitter_accounts()
    if stats:
        logger.info(
            f"=== Done === "
            f"found={stats['found']} no_tweet={stats['no_tweet']} "
            f"failed={stats['failed']} total={stats['total']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
