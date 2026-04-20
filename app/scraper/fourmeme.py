"""
Four.meme graduated token scraper.

Graduated tokens live in two listTypes:
  NOR_DEX  — BNB-quoted tokens that migrated to PancakeSwap
  BIN_DEX  — BNB_MPC-quoted tokens that migrated to PancakeSwap

Image path is a relative URL on four.meme, e.g. /market/418q2FFZFBCPM.jpg
We prepend https://four.meme to get the full CDN URL before downloading.

Usage (standalone):  python scripts/scrape_graduated.py
Usage (from router): await scrape_graduated()
"""

import asyncio
import json
import logging

import httpx

from ..database import get_db
from ..live_logger import log_event

logger = logging.getLogger(__name__)

API_BASE      = "https://four.meme/meme-api/v1"
SEARCH_URL    = f"{API_BASE}/public/token/search"
IMG_CDN       = "https://static.four.meme"  # real CDN for token images
PAGE_SIZE     = 100
REQUEST_DELAY = 0.7                          # seconds between pages

# Four.meme rejects requests without these headers
HEADERS = {
    "Content-Type": "application/json",
    "Accept":        "application/json",
    "Origin":        "https://four.meme",
    "Referer":       "https://four.meme/",
    "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# Both listTypes contain graduated (DEX-migrated) tokens
GRADUATED_LIST_TYPES = ["NOR_DEX", "BIN_DEX"]


# ── Field mapping ─────────────────────────────────────────────────────────────

def _parse(raw: dict, list_type: str) -> dict:
    """Map Four.meme list-API fields to our DB columns."""
    img_raw = raw.get("img", "")
    img_full = (IMG_CDN + img_raw) if img_raw and img_raw.startswith("/") else img_raw

    # progress: API returns "1" for 100 %, "0.5" for 50 %, etc.
    progress_raw = raw.get("progress")
    try:
        progress_val = float(progress_raw) * 100 if progress_raw is not None else None
    except (TypeError, ValueError):
        progress_val = None

    return {
        "address":         raw.get("tokenAddress", "").lower(),
        "name":            raw.get("name"),
        "symbol":          raw.get("shortName"),          # ticker
        "description":     None,                          # not in public list API
        "label":           raw.get("tag"),                # Meme | AI | Defi | Games | …
        "img_url":         img_full or None,
        "total_supply":    None,
        "raised_amount":   None,
        "sale_rate":       None,
        "reserve_rate":    None,
        "launch_time":     int(raw["createDate"]) if raw.get("createDate") else None,
        "last_price":      str(raw["price"]) if raw.get("price") is not None else None,
        "market_cap":      str(raw["cap"])   if raw.get("cap")   is not None else None,
        "volume_24h":      str(raw.get("day1Vol") or raw.get("volume") or ""),
        "holder_count":    raw.get("hold"),
        "progress":        progress_val,
        "web_url":         None,
        "twitter_url":     None,
        "telegram_url":    None,
        "dex_type":        "PANCAKE_SWAP",
        "version":         str(raw["version"]) if raw.get("version") is not None else None,
        "list_type":       list_type,
        "is_ai_created":   bool(raw["aiCreator"]) if raw.get("aiCreator") is not None else None,
        "fee_plan":        None,
        "creator_address": raw.get("userAddress", "").lower() or None,
        "raw_json":        json.dumps(raw, ensure_ascii=False),
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def _upsert(conn, d: dict) -> bool:
    """INSERT or UPDATE; returns True if newly inserted."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM graduated_tokens WHERE address = ?", d["address"])
    if cur.fetchone():
        cur.execute("""
            UPDATE graduated_tokens SET
                name=?,symbol=?,label=?,img_url=?,
                launch_time=?,last_price=?,market_cap=?,volume_24h=?,
                holder_count=?,progress=?,version=?,list_type=?,
                is_ai_created=?,creator_address=?,raw_json=?,
                updated_at=GETDATE()
            WHERE address=?
        """,
            d["name"], d["symbol"], d["label"], d["img_url"],
            d["launch_time"], d["last_price"], d["market_cap"], d["volume_24h"],
            d["holder_count"], d["progress"], d["version"], d["list_type"],
            d["is_ai_created"], d["creator_address"], d["raw_json"],
            d["address"],
        )
        return False
    else:
        cur.execute("""
            INSERT INTO graduated_tokens (
                address,name,symbol,description,label,img_url,
                total_supply,raised_amount,sale_rate,reserve_rate,
                launch_time,last_price,market_cap,volume_24h,holder_count,progress,
                web_url,twitter_url,telegram_url,dex_type,version,list_type,
                is_ai_created,fee_plan,creator_address,raw_json
            ) VALUES (?,?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?)
        """,
            d["address"], d["name"], d["symbol"], d["description"], d["label"], d["img_url"],
            d["total_supply"], d["raised_amount"], d["sale_rate"], d["reserve_rate"],
            d["launch_time"], d["last_price"], d["market_cap"], d["volume_24h"],
            d["holder_count"], d["progress"],
            d["web_url"], d["twitter_url"], d["telegram_url"],
            d["dex_type"], d["version"], d["list_type"],
            d["is_ai_created"], d["fee_plan"], d["creator_address"], d["raw_json"],
        )
        return True


# ── Main ──────────────────────────────────────────────────────────────────────

async def scrape_graduated() -> dict:
    """
    Scrape NOR_DEX + BIN_DEX graduated tokens and archive them.

    Pagination note:
      sort=ASC (lowest-activity first) produces clean, non-overlapping pages —
      each page is 100% unique until the API returns an empty response.
      sort=DESC (highest-activity first) has ~90% overlap on page 2 because
      the live ranking shifts between consecutive requests, causing many tokens
      to appear twice.  ASC is stable and exhausts the full token list cleanly
      (~10 pages for NOR_DEX, ~3 pages for BIN_DEX).

    Returns summary stats dict.
    """
    stats = {"inserted": 0, "updated": 0, "pages": 0, "errors": 0}

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        for list_type in GRADUATED_LIST_TYPES:
            logger.info(f"[scraper] ── listType={list_type} ──")
            page = 1

            while True:
                logger.info(f"[scraper] {list_type} page {page} …")
                try:
                    r = await client.post(SEARCH_URL, json={
                        "type":      "NEW",
                        "listType":  list_type,
                        "pageIndex": page,
                        "pageSize":  PAGE_SIZE,
                        "sort":      "ASC",     # ASC gives clean non-overlapping pages
                        "status":    "TRADE",   # TRADE = graduated to PancakeSwap DEX
                    })
                    r.raise_for_status()
                    body    = r.json()
                    records = body.get("data") or []
                    records = records if isinstance(records, list) else []
                except Exception as exc:
                    logger.error(f"[scraper] API error {list_type} page {page}: {exc}")
                    stats["errors"] += 1
                    break

                if not records:
                    logger.info(f"[scraper] {list_type} exhausted at page {page}.")
                    break

                stats["pages"] += 1

                for raw in records:
                    parsed  = _parse(raw, list_type)
                    address = parsed["address"]
                    if not address or len(address) != 42:
                        stats["errors"] += 1
                        continue

                    # DB upsert
                    try:
                        with get_db() as conn:
                            is_new = _upsert(conn, parsed)
                        stats["inserted" if is_new else "updated"] += 1
                        if is_new:
                            sym  = parsed.get("symbol") or "?"
                            name = parsed.get("name") or sym
                            log_event(
                                "FOURMEME",
                                f"New graduated token: {sym} ({name})",
                                "new_token",
                                symbol=sym,
                                token_address=parsed.get("address"),
                            )
                    except Exception as exc:
                        logger.error(f"[scraper] DB error {address}: {exc}")
                        stats["errors"] += 1
                        continue

                    # No local image download — img_url (CDN) is sufficient

                logger.info(
                    f"[scraper] {list_type} p{page}: "
                    f"ins={stats['inserted']} upd={stats['updated']} err={stats['errors']}"
                )
                await asyncio.sleep(REQUEST_DELAY)
                page += 1

    # Supplement with on-chain scan to catch listType=None tokens invisible to the API
    from .fourmeme_chain import scan_chain_for_graduations
    chain_stats = await asyncio.to_thread(scan_chain_for_graduations)
    stats["chain_discovered"] = chain_stats.get("discovered", 0)
    stats["chain_blocks"]     = chain_stats.get("blocks_scanned", 0)
    logger.info(f"[scraper] Chain scan: {chain_stats}")

    log_event(
        "FOURMEME",
        f"Scrape complete — {stats['inserted']} new, {stats['updated']} updated, "
        f"{stats['chain_discovered']} chain-discovered",
        "scrape_done",
    )
    logger.info(f"[scraper] Complete: {stats}")
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(scrape_graduated())
