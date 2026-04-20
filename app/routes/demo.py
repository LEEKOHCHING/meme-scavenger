"""
Demo mode API routes.

POST /api/demo/deliver  — after user pays contract, server swaps demo tokens and delivers to user
"""
import logging
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_db
from ..live_logger import log_event
from ..services.demo_swap import execute_demo_swap

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demo", tags=["demo"])

TIER_PRICES = {0: 10, 1: 20, 2: 30}
TIER_DROPS  = {
    0: ["DOGE", "SHIB", "FLOKI"],
    1: ["PEPE", "BONK", "WIF"],
    2: ["BRETT", "MAGA", "POPCAT"],
}
TIER_NAMES  = {0: "Basic Pack", 1: "Elite Chest", 2: "Mythic Crate"}


class DeliverRequest(BaseModel):
    wallet:   str   # user's BSC wallet address
    tier:     int   # 0 / 1 / 2
    tx_hash:  str   # confirmed buy() tx hash (for logging / audit)


def _record_purchase(wallet: str, tier: int, tx_hash: str, swaps: list) -> int | None:
    """
    Insert into purchases + purchase_tokens (one row per swapped token).
    Returns the new purchase id, or None on error.
    Safe to call multiple times — duplicate tx_hash is silently skipped.
    """
    try:
        price_u   = TIER_PRICES[tier]
        tier_name = TIER_NAMES[tier]

        with get_db() as conn:
            cur = conn.cursor()

            # Idempotency guard — don't double-record the same tx
            cur.execute("SELECT id FROM purchases WHERE tx_hash = ?", tx_hash)
            if cur.fetchone():
                logger.info(f"[demo/deliver] purchase already recorded for {tx_hash}")
                return None

            cur.execute(
                """
                INSERT INTO purchases (wallet_address, tier, price_u, tx_hash)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?)
                """,
                wallet, tier, price_u, tx_hash,
            )
            purchase_id = cur.fetchone()[0]

            # Store each swap result in purchase_tokens
            for s in swaps:
                tok = s.get("token", {})
                cur.execute(
                    """
                    INSERT INTO purchase_tokens
                        (purchase_id, token_address, token_name, token_symbol,
                         img_url, amount_received, swap_tx_hash, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    purchase_id,
                    tok.get("address"),
                    tok.get("name") or tok.get("symbol"),
                    tok.get("symbol"),
                    tok.get("img_url"),
                    s.get("received") if s.get("success") else None,
                    s.get("tx_hash"),
                    1 if s.get("success") else 0,
                )

        # Summary for live feed
        success_symbols = [
            s["token"]["symbol"] for s in swaps
            if s.get("success") and s.get("token", {}).get("symbol")
        ]
        summary = ", ".join(f"${sym}" for sym in success_symbols[:3])
        if len(success_symbols) > 3:
            summary += f" +{len(success_symbols) - 3}"

        wallet_short = wallet[:6] + "…" + wallet[-4:]
        log_event(
            "ALCHEMY",
            f"{wallet_short} bought {tier_name} → {summary or 'tokens delivered'}",
            "purchase",
        )
        logger.info(
            f"[demo/deliver] purchase recorded id={purchase_id} "
            f"tier={tier} tokens={len(swaps)}"
        )
        return purchase_id

    except Exception as exc:
        logger.error(f"[demo/deliver] failed to record purchase for {tx_hash}: {exc}")
        return None


@router.post("/deliver")
def demo_deliver(req: DeliverRequest):
    """
    Called after the user's contract buy() tx is confirmed.
    The server's hot wallet (pre-funded with USDT) swaps each demo token
    and sends them directly to the user's wallet via PancakeSwap.
    User's payment went to the MemeScavenger contract — not touched here.

    Purchase is recorded here (not via /api/purchases) to avoid the strict
    on-chain event verification that is not applicable in demo mode.
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

    # Record purchase + all swap results after successful delivery
    _record_purchase(req.wallet, req.tier, req.tx_hash, result.get("swaps", []))

    return result
