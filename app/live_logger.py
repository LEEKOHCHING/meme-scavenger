"""
Shared live-event logger.

All scrapers import `log_event` to write activity into live_events.
The frontend polls /api/feed to display these in the Live Show.

Source codes and their display colours:
  TWITTER   #1DA1F2  — tweets received / account checks
  FOURMEME  #39FF14  — new graduated tokens scraped
  DEX       #FF6B35  — DexScreener price / volume checks
  GECKO     #8B5CF6  — GeckoTerminal social data
  ALCHEMY   #F0B90B  — on-chain / RPC events
  SYSTEM    #666666  — general system messages
"""

import logging

from .database import get_db

logger = logging.getLogger(__name__)

# ── Source → hex colour (shown in the Live Show feed) ─────────────────────────
SOURCE_COLORS = {
    "TWITTER":  "#1DA1F2",
    "FOURMEME": "#39FF14",
    "DEX":      "#FF6B35",
    "GECKO":    "#8B5CF6",
    "ALCHEMY":  "#F0B90B",
    "SYSTEM":   "#666666",
}

# Keep only the latest N rows so the table never grows unbounded
MAX_ROWS = 2000


def log_event(
    source: str,
    message: str,
    event_type: str = "info",
    symbol: str | None = None,
    token_address: str | None = None,
) -> None:
    """
    Write one live event to the DB.  Always silent on error — never let
    logging crash a scraper.

    Args:
        source:        One of TWITTER / FOURMEME / DEX / GECKO / ALCHEMY / SYSTEM
        message:       Short human-readable description (max ~280 chars)
        event_type:    Free-form category string (tweet, new_token, price, etc.)
        symbol:        Token symbol if relevant
        token_address: Contract address if relevant
    """
    source = source.upper()
    message = message[:280]   # hard cap

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO live_events (source, event_type, symbol, message, token_address)
                VALUES (?, ?, ?, ?, ?)
            """, source, event_type, symbol, message, token_address)

            # Prune old rows — keep table lean
            cur.execute("""
                DELETE FROM live_events
                WHERE id NOT IN (
                    SELECT TOP (?) id FROM live_events ORDER BY id DESC
                )
            """, MAX_ROWS)

    except Exception as exc:
        # Never propagate — logging should never break main flow
        logger.debug(f"[live_logger] Failed to write event: {exc}")
