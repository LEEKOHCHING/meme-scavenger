"""
Start the Twitter / X Filtered Stream archiver.

Connects to Twitter's v2 Filtered Stream, tracks all accounts stored in
graduated_tokens.twitter_url, and saves every new tweet to token_tweets.

Run from project root:
    python scripts/run_twitter_stream.py

The script runs indefinitely — use Ctrl+C or Task Manager to stop it.
Reconnects automatically on network drops.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.scraper.twitter_stream import run_stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/twitter_stream.log", encoding="utf-8"),
    ],
)


if __name__ == "__main__":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger = logging.getLogger("twitter_stream_script")
    logger.info("=== Starting Twitter Filtered Stream archiver ===")
    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        logger.info("=== Stopped by user ===")
