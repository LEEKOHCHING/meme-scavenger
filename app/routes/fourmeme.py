"""
API routes for the Four.meme graduated token archive.

GET  /api/fourmeme/stats                 — total count, last scraped, label breakdown
GET  /api/fourmeme/graduated             — paginated list (supports ?page=&size=&label=&q=)
GET  /api/fourmeme/graduated/{address}   — single token detail
POST /api/fourmeme/scrape                — trigger a fresh scrape run (admin)
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..database import get_db
from ..scraper.fourmeme import scrape_graduated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fourmeme", tags=["fourmeme"])

_scrape_running = False   # simple guard — prevent concurrent runs


# ── GET /api/fourmeme/stats ───────────────────────────────────────────────────

@router.get("/stats")
def get_stats():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM graduated_tokens")
        total = cur.fetchone()[0]

        cur.execute("SELECT MAX(updated_at) FROM graduated_tokens")
        last_updated = cur.fetchone()[0]

        cur.execute("""
            SELECT label, COUNT(*) AS cnt
            FROM graduated_tokens
            WHERE label IS NOT NULL
            GROUP BY label
            ORDER BY cnt DESC
        """)
        by_label = [{"label": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) FROM graduated_tokens WHERE img_local IS NOT NULL
        """)
        with_image = cur.fetchone()[0]

    return {
        "total":        total,
        "with_image":   with_image,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "by_label":     by_label,
    }


# ── GET /api/fourmeme/graduated ───────────────────────────────────────────────

@router.get("/graduated")
def list_graduated(
    page:  int   = Query(1,   ge=1),
    size:  int   = Query(50,  ge=1, le=200),
    label: str   = Query(None),   # filter by label (Meme, AI, Defi …)
    q:     str   = Query(None),   # keyword search on name / symbol
    sort:  str   = Query("launch_time"),  # launch_time | market_cap | holder_count
):
    allowed_sorts = {"launch_time", "market_cap", "holder_count", "scraped_at"}
    if sort not in allowed_sorts:
        sort = "launch_time"

    offset = (page - 1) * size
    params = []
    where_clauses = []

    if label:
        where_clauses.append("label = ?")
        params.append(label)

    if q:
        where_clauses.append("(name LIKE ? OR symbol LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_db() as conn:
        cur = conn.cursor()

        # Total for pagination
        cur.execute(f"SELECT COUNT(*) FROM graduated_tokens {where_sql}", *params)
        total = cur.fetchone()[0]

        # Page of results
        cur.execute(f"""
            SELECT
                address, name, symbol, label, img_url,
                last_price, market_cap, volume_24h, holder_count, progress,
                web_url, twitter_url, telegram_url, launch_time, is_ai_created,
                updated_at
            FROM graduated_tokens
            {where_sql}
            ORDER BY {sort} DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, *params, offset, size)

        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Serialise datetime objects
    for r in rows:
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
        if r.get("launch_time"):
            r["launch_time"] = int(r["launch_time"])

    return {
        "total": total,
        "page":  page,
        "size":  size,
        "items": rows,
    }


# ── GET /api/fourmeme/graduated/{address} ────────────────────────────────────

@router.get("/graduated/{address}")
def get_graduated(address: str):
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(400, "Invalid token address")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                address, name, symbol, description, label,
                img_url, img_local, total_supply, raised_amount,
                sale_rate, reserve_rate, launch_time,
                last_price, market_cap, volume_24h, holder_count, progress,
                web_url, twitter_url, telegram_url,
                dex_type, version, list_type, is_ai_created, fee_plan,
                creator_address, raw_json, scraped_at, updated_at
            FROM graduated_tokens
            WHERE address = ?
        """, address.lower())
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Token not found in archive")

    cols = [d[0] for d in cur.description]
    data = dict(zip(cols, row))

    for ts_field in ("scraped_at", "updated_at"):
        if data.get(ts_field):
            data[ts_field] = data[ts_field].isoformat()

    return data


# ── GET /api/fourmeme/demo-tokens ────────────────────────────────────────────

@router.get("/demo-tokens")
def get_demo_tokens():
    """Return all tokens flagged demo=1, for the Demo Mode swap distribution."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT address, name, symbol, img_url
            FROM graduated_tokens
            WHERE demo = 1
            ORDER BY id
        """)
        rows = cur.fetchall()
    return [
        {"address": r[0], "name": r[1] or r[2], "symbol": r[2] or "?", "img_url": r[3]}
        for r in rows
    ]


# ── POST /api/fourmeme/scrape ─────────────────────────────────────────────────

@router.post("/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    global _scrape_running
    if _scrape_running:
        return {"status": "already_running"}

    async def _run():
        global _scrape_running
        _scrape_running = True
        try:
            stats = await scrape_graduated()
            logger.info(f"[scrape task] completed: {stats}")
        finally:
            _scrape_running = False

    background_tasks.add_task(_run)
    return {"status": "started"}
