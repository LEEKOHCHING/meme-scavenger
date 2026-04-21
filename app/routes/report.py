"""
Token report API.

GET /api/report/{token_address}
    Returns the cached analysis report for a token.
    Returns 404 if no report exists yet (still generating in background).
"""

import logging

from fastapi import APIRouter, HTTPException

from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/{token_address}")
def get_report(token_address: str):
    """
    Fetch the stored analysis report for a token address.
    The report is generated in the background after purchase and cached for 7 days.
    Returns 404 while the report is still being generated.
    """
    token_address = token_address.lower()

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT report, tweet_count, generated_at
                FROM token_reports
                WHERE token_address = ?
            """, token_address)
            row = cur.fetchone()
    except Exception as exc:
        logger.error(f"[report] DB error: {exc}")
        raise HTTPException(500, "Database error")

    if not row:
        raise HTTPException(404, "Report not ready yet")

    return {
        "token_address": token_address,
        "report":        row[0],
        "tweet_count":   row[1],
        "generated_at":  row[2].isoformat(),
    }
