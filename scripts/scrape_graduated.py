"""
Standalone script — scrape all graduated tokens from Four.meme.

Run from the project root:
    python scripts/scrape_graduated.py

Windows Task Scheduler daily job:
    Program:   python
    Arguments: scripts/scrape_graduated.py
    Start in:  C:\A 03 SOFTWARE HOUSE PROJECT\meme-scavenger
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scraper.fourmeme import scrape_graduated

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scrape_graduated.log", encoding="utf-8"),
    ],
)


async def main():
    logger = logging.getLogger("scrape_script")
    logger.info("=== Starting Four.meme graduated token scrape ===")
    stats = await scrape_graduated()
    logger.info(
        f"=== Done === "
        f"inserted={stats['inserted']} updated={stats['updated']} "
        f"pages={stats['pages']} errors={stats['errors']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
