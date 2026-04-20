"""
Demo mode API routes.

POST /api/demo/deliver  — after user pays contract, server swaps demo tokens and delivers to user
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.demo_swap import execute_demo_swap

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demo", tags=["demo"])


class DeliverRequest(BaseModel):
    wallet:   str   # user's BSC wallet address
    tier:     int   # 0 / 1 / 2
    tx_hash:  str   # confirmed buy() tx hash (for logging / audit)


@router.post("/deliver")
def demo_deliver(req: DeliverRequest):
    """
    Called after the user's contract buy() tx is confirmed.
    The server's hot wallet (pre-funded with USDT) swaps each demo token
    and sends them directly to the user's wallet via PancakeSwap.
    User's payment went to the MemeScavenger contract — not touched here.
    """
    if req.tier not in (0, 1, 2):
        raise HTTPException(400, "tier must be 0, 1 or 2")
    if not req.wallet.startswith("0x") or len(req.wallet) != 42:
        raise HTTPException(400, "Invalid wallet address")

    logger.info(f"[demo/deliver] wallet={req.wallet} tier={req.tier} tx={req.tx_hash}")

    try:
        result = execute_demo_swap(req.wallet, req.tier)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("[demo/deliver] unexpected error")
        raise HTTPException(500, f"Server error during token delivery: {exc}")

    return result
