"""
Standalone BSC on-chain scanner — initial backfill and incremental catch-up.

Scans Four.meme TokenManager contracts for LiquidityAdded graduation events
and inserts any previously unseen tokens into graduated_tokens.

On first run this performs a full historical scan from the configured start
block (default ~44,000,000) and may take several minutes.  Subsequent runs
only scan newly produced blocks.

Run from the project root:
    python scripts/scan_chain.py

Windows Task Scheduler (daily or after scrape_graduated.bat):
    Program:   python
    Arguments: scripts/scan_chain.py
    Start in:  C:\\A 03 SOFTWARE HOUSE PROJECT\\meme-scavenger
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scraper.fourmeme_chain import scan_chain_for_graduations

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scan_chain.log", encoding="utf-8"),
    ],
)

if __name__ == "__main__":
    logger = logging.getLogger("scan_chain")
    logger.info("=== Starting BSC on-chain graduation scan ===")
    stats = scan_chain_for_graduations()
    logger.info(
        f"=== Done === "
        f"discovered={stats['discovered']} skipped={stats['skipped']} "
        f"blocks={stats['blocks_scanned']:,} errors={stats['errors']}"
    )
