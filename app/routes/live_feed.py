from fastapi import APIRouter
from ..database import get_db
from ..live_logger import SOURCE_COLORS

router = APIRouter(prefix="/api/feed", tags=["feed"])


@router.get("")
def get_feed(limit: int = 30, since_id: int = 0):
    """
    Return live events newer than since_id, newest-last (for appending).
    Frontend polls this every few seconds with the last seen id.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP (?) id, source, event_type, symbol, message, created_at
            FROM   live_events
            WHERE  id > ?
            ORDER  BY id ASC
        """, limit, since_id)
        rows = cur.fetchall()

    return [
        {
            "id":         r[0],
            "source":     r[1],
            "color":      SOURCE_COLORS.get(r[1], "#666"),
            "event_type": r[2],
            "symbol":     r[3],
            "message":    r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]
