"""
DexScreener daily metrics scraper.

Fetches price / volume / liquidity / txn data for every graduated token
and saves a daily snapshot to token_metrics.

API endpoint:
    GET https://api.dexscreener.com/latest/dex/tokens/{addr1,addr2,...}
    Up to 30 addresses per request. Returns all pairs for each token.

Rate limit: public API ~ 300 req/min.
We use 1 batch (30 tokens) every 2 seconds → 15 batches/min → comfortably safe.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timezone

import httpx

from ..database import get_db
from ..live_logger import log_event

logger = logging.getLogger(__name__)

DS_URL         = "https://api.dexscreener.com/latest/dex/tokens"
BATCH_SIZE     = 30     # DexScreener max addresses per request
DELAY_SECONDS  = 2.0    # between batches → 15 req/min  (limit ~300/min)
HEADERS        = {"User-Agent": "MemeScavengerMetrics/1.0", "Accept": "application/json"}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_all_addresses() -> list[str]:
    """Return all token addresses from graduated_tokens."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT address FROM graduated_tokens ORDER BY launch_time DESC")
        return [row[0] for row in cur.fetchall()]


def _already_checked_today(addresses: list[str], today: date) -> set[str]:
    """Return addresses that already have a snapshot for today."""
    if not addresses:
        return set()
    with get_db() as conn:
        cur = conn.cursor()
        placeholders = ",".join("?" * len(addresses))
        cur.execute(
            f"SELECT address FROM token_metrics "
            f"WHERE snapshot_date = ? AND address IN ({placeholders})",
            today, *addresses,
        )
        return {row[0].lower() for row in cur.fetchall()}


def _best_pair(pairs: list[dict]) -> dict | None:
    """
    Pick the best pair for a token: highest liquidity_usd.
    Falls back to highest volume_h24 if liquidity data is missing.
    """
    if not pairs:
        return None
    return max(
        pairs,
        key=lambda p: (
            (p.get("liquidity") or {}).get("usd") or 0,
            (p.get("volume") or {}).get("h24") or 0,
        ),
    )


def _save_metric(address: str, pair: dict | None, pair_count: int, today: date):
    """Insert one daily snapshot row. Silently skips if duplicate."""
    if pair:
        volume     = pair.get("volume") or {}
        change     = pair.get("priceChange") or {}
        liquidity  = pair.get("liquidity") or {}
        txns_h1    = (pair.get("txns") or {}).get("h1") or {}
        txns_h24   = (pair.get("txns") or {}).get("h24") or {}

        price_usd        = pair.get("priceUsd")
        price_change_m5  = change.get("m5")
        price_change_h1  = change.get("h1")
        price_change_h6  = change.get("h6")
        price_change_h24 = change.get("h24")
        volume_m5        = volume.get("m5")
        volume_h1        = volume.get("h1")
        volume_h6        = volume.get("h6")
        volume_h24       = volume.get("h24")
        liquidity_usd    = liquidity.get("usd")
        market_cap       = pair.get("marketCap")
        fdv              = pair.get("fdv")
        txns_h1_buys     = txns_h1.get("buys")
        txns_h1_sells    = txns_h1.get("sells")
        txns_h24_buys    = txns_h24.get("buys")
        txns_h24_sells   = txns_h24.get("sells")
        pair_address     = pair.get("pairAddress")
        dex_id           = pair.get("dexId")
        raw_json         = json.dumps(pair, ensure_ascii=False)
    else:
        # Token not found on DexScreener — still record the snapshot
        (price_usd, price_change_m5, price_change_h1, price_change_h6,
         price_change_h24, volume_m5, volume_h1, volume_h6, volume_h24,
         liquidity_usd, market_cap, fdv, txns_h1_buys, txns_h1_sells,
         txns_h24_buys, txns_h24_sells, pair_address, dex_id, raw_json) = [None] * 19

    try:
        with get_db() as conn:
            conn.cursor().execute("""
                INSERT INTO token_metrics (
                    address, snapshot_date,
                    pair_address, dex_id, pair_count,
                    price_usd,
                    price_change_m5, price_change_h1, price_change_h6, price_change_h24,
                    volume_m5, volume_h1, volume_h6, volume_h24,
                    liquidity_usd, market_cap, fdv,
                    txns_h1_buys, txns_h1_sells, txns_h24_buys, txns_h24_sells,
                    raw_json
                ) VALUES (
                    ?,?,  ?,?,?,  ?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,  ?,?,?,?,  ?
                )
            """,
                address, today,
                pair_address, dex_id, pair_count,
                price_usd,
                price_change_m5, price_change_h1, price_change_h6, price_change_h24,
                volume_m5, volume_h1, volume_h6, volume_h24,
                liquidity_usd, market_cap, fdv,
                txns_h1_buys, txns_h1_sells, txns_h24_buys, txns_h24_sells,
                raw_json,
            )
    except Exception as exc:
        if "UQ_token_metrics_addr_date" in str(exc) or "2627" in str(exc) or "2601" in str(exc):
            logger.debug(f"[dex] Duplicate snapshot for {address} on {today} — skipped")
        else:
            logger.error(f"[dex] Failed to save metric for {address}: {exc}")


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run_daily_metrics() -> dict:
    """
    Fetch and store today's trading metrics for all graduated tokens.
    Skips tokens that already have a snapshot for today.

    Returns:
        {"found": int, "not_listed": int, "skipped": int,
         "errors": int, "total": int}
    """
    today     = date.today()
    addresses = _get_all_addresses()
    already   = _already_checked_today(addresses, today)

    pending = [a for a in addresses if a.lower() not in already]
    stats   = {
        "found":      0,
        "not_listed": 0,
        "skipped":    len(already),
        "errors":     0,
        "total":      len(addresses),
    }

    if not pending:
        logger.info(f"[dex] All {len(addresses)} tokens already snapshotted today.")
        return stats

    logger.info(
        f"[dex] {len(pending)} tokens to fetch "
        f"({len(already)} already done today). "
        f"ETA ~{len(pending) / BATCH_SIZE * DELAY_SECONDS / 60:.1f} min"
    )
    log_event("DEX", f"Daily snapshot started — {len(pending)} tokens to check", "scan_start")

    # Build batches of BATCH_SIZE
    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]

    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
        for batch_num, batch in enumerate(batches, 1):
            url = f"{DS_URL}/{','.join(batch)}"
            logger.info(f"[dex] Batch {batch_num}/{len(batches)} — {len(batch)} tokens")

            for attempt in range(3):
                try:
                    r = await client.get(url)

                    if r.status_code == 200:
                        body  = r.json()
                        pairs = body.get("pairs") or []

                        # Group pairs by base token address (lowercased)
                        pair_map: dict[str, list] = {}
                        for p in pairs:
                            base_addr = (p.get("baseToken") or {}).get("address", "").lower()
                            pair_map.setdefault(base_addr, []).append(p)

                        notable = []   # tokens worth showing in live feed
                        for addr in batch:
                            token_pairs = pair_map.get(addr.lower(), [])
                            best        = _best_pair(token_pairs)
                            _save_metric(addr, best, len(token_pairs), today)

                            if best:
                                vol24 = (best.get("volume") or {}).get("h24") or 0
                                liq   = (best.get("liquidity") or {}).get("usd") or 0
                                sym   = (best.get("baseToken") or {}).get("symbol", "?")
                                logger.debug(
                                    f"[dex]   {addr[:10]}… "
                                    f"pairs={len(token_pairs)} "
                                    f"vol24=${vol24:,.0f} liq=${liq:,.0f}"
                                )
                                stats["found"] += 1
                                # Only surface tokens with meaningful activity
                                if vol24 >= 1000:
                                    notable.append((sym, vol24, liq, addr))
                            else:
                                stats["not_listed"] += 1

                        # Log up to 3 notable tokens per batch to keep feed lively
                        notable.sort(key=lambda x: x[1], reverse=True)
                        for sym, vol24, liq, addr in notable[:3]:
                            log_event(
                                "DEX",
                                f"{sym}  vol24=${vol24:,.0f}  liq=${liq:,.0f}",
                                "price_update",
                                symbol=sym,
                                token_address=addr,
                            )

                        break  # success

                    elif r.status_code == 429:
                        wait = 60 if attempt == 0 else 120
                        logger.warning(
                            f"[dex] Rate limited (attempt {attempt+1}). "
                            f"Sleeping {wait}s…"
                        )
                        await asyncio.sleep(wait)

                    else:
                        logger.warning(
                            f"[dex] Batch {batch_num}: HTTP {r.status_code}"
                        )
                        stats["errors"] += len(batch)
                        break

                except Exception as exc:
                    logger.error(f"[dex] Batch {batch_num} error: {exc}")
                    stats["errors"] += len(batch)
                    break

            await asyncio.sleep(DELAY_SECONDS)

    log_event(
        "DEX",
        f"Snapshot done — {stats['found']} listed, {stats['not_listed']} unlisted",
        "scan_done",
    )
    logger.info(f"[dex] Done: {stats}")
    return stats
