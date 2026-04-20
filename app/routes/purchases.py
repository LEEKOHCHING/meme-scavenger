import logging
import random
import re

import httpx
from eth_hash.auto import keccak
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..database import get_db
from ..live_logger import log_event
from ..models import PurchaseRequest, PurchaseResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchases", tags=["purchases"])

TIER_PRICES = {0: 10, 1: 20, 2: 30}
USDT_DECIMALS = 10 ** 18

TIER_DROPS = {
    0: ["DOGE", "SHIB", "FLOKI"],
    1: ["PEPE", "BONK", "WIF"],
    2: ["BRETT", "MAGA", "POPCAT"],
}

# Correct keccak256 computed at startup
PURCHASE_EVENT_SIG = "0x" + keccak(b"Purchase(address,uint8,uint256,uint256)").hex()
logger.info(f"Purchase event sig: {PURCHASE_EVENT_SIG}")


def _rpc(method: str, params: list, req_id: int = 1):
    r = httpx.post(
        settings.bsc_rpc_url,
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("result")


def _verify_tx(tx_hash: str, wallet: str, tier: int) -> bool:
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
        logger.warning(f"[verify] Invalid tx_hash format: {tx_hash}")
        return False
    try:
        # 1. Get receipt
        receipt = _rpc("eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            logger.warning(f"[verify] Receipt not found: {tx_hash}")
            return False

        # 2. Check mined successfully
        if receipt.get("status") != "0x1":
            logger.warning(f"[verify] Tx failed on-chain: {tx_hash} status={receipt.get('status')}")
            return False

        # 3. Check called our contract
        tx_to = receipt.get("to", "").lower()
        contract = settings.bsc_contract_address.lower()
        if contract and tx_to != contract:
            logger.warning(f"[verify] Wrong contract. Expected {contract}, got {tx_to}")
            return False

        # 4. Find Purchase event in logs
        expected_price = TIER_PRICES[tier] * USDT_DECIMALS
        logs = receipt.get("logs", [])
        logger.info(f"[verify] tx={tx_hash} found {len(logs)} logs")

        for i, log in enumerate(logs):
            topics = log.get("topics", [])
            if not topics:
                continue

            logger.info(f"[verify] log[{i}] topic0={topics[0]}")

            if topics[0].lower() != PURCHASE_EVENT_SIG.lower():
                continue

            # topics[1] = buyer address (indexed, padded 32 bytes)
            if len(topics) < 3:
                logger.warning(f"[verify] Purchase log missing topics: {topics}")
                continue

            log_buyer = "0x" + topics[1][-40:]
            log_tier  = int(topics[2], 16)
            data      = log.get("data", "0x")[2:]
            log_price = int(data[:64], 16) if len(data) >= 64 else 0

            logger.info(
                f"[verify] Purchase log — buyer={log_buyer} tier={log_tier} "
                f"price={log_price} expected_price={expected_price}"
            )

            if log_buyer.lower() != wallet.lower():
                logger.warning(f"[verify] Buyer mismatch: {log_buyer} != {wallet}")
                continue
            if log_tier != tier:
                logger.warning(f"[verify] Tier mismatch: {log_tier} != {tier}")
                continue
            if log_price != expected_price:
                logger.warning(f"[verify] Price mismatch: {log_price} != {expected_price}")
                continue

            logger.info(f"[verify] ✅ Verification passed for {tx_hash}")
            return True

        logger.warning(f"[verify] No matching Purchase event found in {len(logs)} logs")
        return False

    except Exception as e:
        logger.exception(f"[verify] Exception verifying {tx_hash}: {e}")
        return False


@router.post("", response_model=PurchaseResponse)
def create_purchase(body: PurchaseRequest):
    if body.tier not in TIER_PRICES:
        raise HTTPException(400, "Invalid tier")
    if body.price_u != TIER_PRICES[body.tier]:
        raise HTTPException(400, "Price mismatch")

    logger.info(f"Purchase request: wallet={body.wallet_address} tier={body.tier} tx={body.tx_hash}")

    if not _verify_tx(body.tx_hash, body.wallet_address, body.tier):
        raise HTTPException(400, "Transaction verification failed")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM purchases WHERE tx_hash = ?", body.tx_hash)
        if cur.fetchone():
            raise HTTPException(409, "Transaction already redeemed")

        cur.execute(
            """
            INSERT INTO purchases (wallet_address, tier, price_u, tx_hash)
            OUTPUT INSERTED.id, INSERTED.wallet_address,
                   INSERTED.tier, INSERTED.price_u, INSERTED.tx_hash, INSERTED.created_at
            VALUES (?, ?, ?, ?)
            """,
            body.wallet_address, body.tier, body.price_u, body.tx_hash,
        )
        row = cur.fetchone()

        drop_token = random.choice(TIER_DROPS[body.tier])
        cur.execute(
            "INSERT INTO item_drops (purchase_id, token_name, token_symbol, rarity) VALUES (?, ?, ?, ?)",
            row.id, drop_token, drop_token, ["common", "rare", "mythic"][body.tier],
        )

    logger.info(f"Purchase recorded: id={row.id} drop={drop_token}")
    tier_names = {0: "Basic Pack", 1: "Elite Chest", 2: "Mythic Crate"}
    wallet_short = body.wallet_address[:6] + "…" + body.wallet_address[-4:]
    log_event(
        "ALCHEMY",
        f"{wallet_short} bought {tier_names[body.tier]} → dropped {drop_token}",
        "purchase",
    )
    return PurchaseResponse(
        id=row.id,
        wallet_address=row.wallet_address,
        tier=row.tier,
        price_u=row.price_u,
        tx_hash=row.tx_hash,
        created_at=row.created_at,
    )


@router.get("")
def get_history(wallet: str):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet):
        raise HTTPException(400, "Invalid wallet address")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.tier, p.price_u, p.tx_hash, p.created_at,
                   d.token_symbol, d.rarity
            FROM purchases p
            LEFT JOIN item_drops d ON d.purchase_id = p.id
            WHERE p.wallet_address = ?
            ORDER BY p.created_at DESC
            """,
            wallet,
        )
        rows = cur.fetchall()
    return [
        {
            "id":           r.id,
            "tier":         r.tier,
            "price_u":      r.price_u,
            "tx_hash":      r.tx_hash,
            "created_at":   r.created_at.isoformat(),
            "token_symbol": r.token_symbol,
            "rarity":       r.rarity,
        }
        for r in rows
    ]


@router.get("/{purchase_id}/drop")
def get_drop(purchase_id: int):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT token_name, token_symbol, rarity FROM item_drops WHERE purchase_id = ?",
            purchase_id,
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Drop not found")
    return {"token_name": row.token_name, "token_symbol": row.token_symbol, "rarity": row.rarity}
