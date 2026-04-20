"""
Fetch social data (Twitter, Telegram, Website, Description) from GeckoTerminal
for all graduated tokens that haven't been checked yet.

Run from project root:
    python scripts/update_social.py

Processes ~12 tokens/minute. For 1,120 tokens: ~95 minutes total.
Progress is saved after each token — safe to interrupt and resume.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.scraper.social import update_social

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/update_social.log", encoding="utf-8"),
    ],
)


async def main():
    logger = logging.getLogger("social_script")
    logger.info("=== Starting GeckoTerminal social data update ===")
    stats = await update_social()   # limit=0 means all unchecked
    logger.info(
        f"=== Done === "
        f"found={stats['found']} empty={stats['empty']} "
        f"errors={stats['errors']} total={stats['total']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
