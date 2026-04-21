"""
Leaderboard API — for Hackathon judges.

GET /api/leaderboard?page=1&limit=20
    Returns graduated tokens ranked by x_score DESC.
    Only tokens that have been scored (x_score IS NOT NULL) are included.
"""

import logging
from fastapi import APIRouter, Query

from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
def get_leaderboard(
    page:  int = Query(1,  ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * limit

    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Total count
            cur.execute("""
                SELECT COUNT(*)
                FROM graduated_tokens
                WHERE x_score IS NOT NULL
            """)
            total = cur.fetchone()[0]

            # Paginated rows
            cur.execute("""
                SELECT address, name, symbol, img_url, x_score, x_report
                FROM graduated_tokens
                WHERE x_score IS NOT NULL
                ORDER BY x_score DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, offset, limit)
            rows = cur.fetchall()

    except Exception as exc:
        logger.error(f"[leaderboard] DB error: {exc}")
        return {"total": 0, "page": page, "limit": limit, "tokens": []}

    tokens = [
        {
            "address":  r[0],
            "name":     r[1] or r[2],
            "symbol":   r[2],
            "img_url":  r[3],
            "score":    r[4],
            "report":   r[5],
        }
        for r in rows
    ]

    return {
        "total":  total,
        "page":   page,
        "limit":  limit,
        "pages":  (total + limit - 1) // limit,
        "tokens": tokens,
    }
