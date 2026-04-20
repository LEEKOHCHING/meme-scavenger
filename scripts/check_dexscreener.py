"""
Daily DexScreener metrics snapshot.

Fetches price / volume / liquidity / txn data for all 1,100+ graduated tokens
and saves one row per token to token_metrics.

Run from project root:
    python scripts/check_dexscreener.py

- Batches 30 tokens per API request → ~38 requests for 1,120 tokens
- 2-second delay between batches → finishes in ~80 seconds
- Safe to interrupt and re-run; tokens already snapshotted today are skipped
- Schedule daily via Windows Task Scheduler (see scripts/register_task.bat)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.makedirs("logs", exist_ok=True)

from app.scraper.dexscreener import run_daily_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/check_dexscreener.log", encoding="utf-8"),
    ],
)


async def main():
    logger = logging.getLogger("dexscreener_script")
    logger.info("=== Starting DexScreener daily metrics snapshot ===")
    stats = await run_daily_metrics()
    logger.info(
        f"=== Done === "
        f"found={stats.get('found',0)} "
        f"not_listed={stats.get('not_listed',0)} "
        f"skipped={stats.get('skipped',0)} "
        f"errors={stats.get('errors',0)} "
        f"total={stats.get('total',0)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
