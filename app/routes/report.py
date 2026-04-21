"""
Token report API.

GET /api/report/{token_address}
    Returns the pre-generated Grok report from graduated_tokens.x_report.
    Returns 404 if the token has not been scored yet.
"""

import logging

from fastapi import APIRouter, HTTPException

from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/{token_address}")
def get_report(token_address: str):
    token_address = token_address.lower()

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT x_report, x_score, x_scored_at
                FROM graduated_tokens
                WHERE address = ?
                  AND x_report IS NOT NULL
            """, token_address)
            row = cur.fetchone()
    except Exception as exc:
        logger.error(f"[report] DB error: {exc}")
        raise HTTPException(500, "Database error")

    if not row:
        raise HTTPException(404, "No report available for this token")

    return {
        "token_address": token_address,
        "report":        row[0],
        "score":         row[1],
        "generated_at":  row[2].isoformat() if row[2] else None,
    }
