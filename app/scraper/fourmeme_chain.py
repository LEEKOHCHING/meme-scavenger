"""
BSC on-chain scanner for Four.meme listType=None graduated tokens.

Four.meme's public search API only exposes NOR_DEX and BIN_DEX tokens.  A
second population — tokens with listType=None — is completely invisible through
any token-list parameter combination.  These tokens are discovered here by
scanning the official Four.meme TokenManager2 contract for LiquidityAdded
events.

Contract scanned (BSC):
  Four.meme TokenManager2  0x5c952063c7fc8610FFDB798152D69F0B9550762b

Graduation event (V2):
  LiquidityAdded(address base, uint256 offers, address quote, uint256 funds)
  topic0  = keccak256("LiquidityAdded(address,uint256,address,uint256)")
          = 0xc18aa71171b358b706fe3dd345299685ba21a5316c66ffa9e319268b033c44b0
  All four parameters are non-indexed → all reside in log.data
  base address: data[2+24 : 2+64]  (first 32-byte word, skipping 12 zero-bytes
                                     of address padding)

Token address conventions:
  - V3 and earlier tokens end in ...4444
  - V9 tokens end in ...ffff
  Both are genuine Four.meme tokens emitted by the official contract.

State (last scanned block) is persisted in scan_state so each run only
fetches new blocks.  On first run the full history from ~block 37,500,000
(April 2024) is scanned.
"""

import logging
import time

import httpx

from ..config import settings
from ..database import get_db
from ..live_logger import log_event

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Official Four.meme TokenManager2 on BSC
TOKEN_MANAGER2 = "0x5c952063c7fc8610FFDB798152D69F0B9550762b"

# keccak256("LiquidityAdded(address,uint256,address,uint256)")
GRADUATION_TOPIC = "0xc18aa71171b358b706fe3dd345299685ba21a5316c66ffa9e319268b033c44b0"

# ERC-20 view selectors
_NAME_SEL   = "0x06fdde03"   # name()
_SYMBOL_SEL = "0x95d89b41"   # symbol()

# Seconds to sleep on rate-limit or transient error
_RETRY_SLEEP = 10


# ── RPC helpers ───────────────────────────────────────────────────────────────

def _rpc(method: str, params: list) -> object:
    """Single JSON-RPC call; raises on HTTP error or JSON-RPC error."""
    r = httpx.post(
        settings.bsc_rpc_url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body.get("result")


def _get_current_block() -> int:
    return int(_rpc("eth_blockNumber", []), 16)


def _get_logs(contract: str, topic0: str, from_block: int, to_block: int) -> list[dict]:
    return _rpc("eth_getLogs", [{
        "address":   contract,
        "topics":    [topic0],
        "fromBlock": hex(from_block),
        "toBlock":   hex(to_block),
    }]) or []


def _eth_call(contract: str, selector: str) -> str | None:
    """Call a no-arg view function; returns raw hex or None."""
    try:
        result = _rpc("eth_call", [
            {"to": contract, "data": selector},
            "latest",
        ])
        return result if result and result != "0x" else None
    except Exception as exc:
        logger.debug(f"[chain] eth_call {selector} on {contract} failed: {exc}")
        return None


def _decode_abi_string(hex_data: str) -> str:
    """Decode an ABI-encoded string returned by name() / symbol()."""
    try:
        data = hex_data[2:] if hex_data.startswith("0x") else hex_data
        if len(data) < 128:
            return ""
        length = int(data[64:128], 16)
        if length == 0:
            return ""
        return bytes.fromhex(data[128: 128 + length * 2]).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _erc20_name(address: str) -> str:
    raw = _eth_call(address, _NAME_SEL)
    return _decode_abi_string(raw) if raw else "UNKNOWN"


def _erc20_symbol(address: str) -> str:
    raw = _eth_call(address, _SYMBOL_SEL)
    return _decode_abi_string(raw) if raw else "UNKNOWN"


# ── Scan-state persistence ────────────────────────────────────────────────────

def _get_scan_cursor(key: str) -> int:
    """Return the last scanned block for this key, or the config default."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM scan_state WHERE scan_key = ?", key)
            row = cur.fetchone()
            if row:
                return int(row[0])
    except Exception as exc:
        logger.warning(f"[chain] Could not read scan cursor ({key}): {exc}")
    return settings.four_meme_start_block


def _set_scan_cursor(key: str, block: int):
    """Upsert the last scanned block."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT scan_key FROM scan_state WHERE scan_key = ?", key)
            if cur.fetchone():
                cur.execute(
                    "UPDATE scan_state SET value = ? WHERE scan_key = ?",
                    str(block), key,
                )
            else:
                cur.execute(
                    "INSERT INTO scan_state (scan_key, value) VALUES (?, ?)",
                    key, str(block),
                )
    except Exception as exc:
        logger.warning(f"[chain] Could not save scan cursor ({key}={block}): {exc}")


# ── DB helper ─────────────────────────────────────────────────────────────────

def _insert_if_new(address: str, name: str, symbol: str) -> bool:
    """
    Insert the token into graduated_tokens if not already present.
    Returns True if a new row was inserted.
    Does NOT update existing rows — the API scraper + update_social have richer data.
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM graduated_tokens WHERE address = ?", address)
        if cur.fetchone():
            return False
        cur.execute("""
            INSERT INTO graduated_tokens
                (address, name, symbol, list_type)
            VALUES (?, ?, ?, 'CHAIN_SCAN')
        """, address, name or "UNKNOWN", symbol or "UNKNOWN")
        return True


# ── Main ──────────────────────────────────────────────────────────────────────

_CURSOR_KEY = "four_meme_v2_last_block"


def scan_chain_for_graduations() -> dict:
    """
    Scan the Four.meme TokenManager2 contract for LiquidityAdded graduation
    events and insert any previously unseen tokens into graduated_tokens.

    This discovers listType=None tokens that are invisible to the search API.
    The official contract 0x5c952063 is exclusive to Four.meme and only emits
    for genuine Four.meme tokens (both V3 ...4444 and V9 ...ffff address styles).

    Returns:
        {"discovered": int, "skipped": int, "blocks_scanned": int, "errors": int}
    """
    stats = {"discovered": 0, "skipped": 0, "blocks_scanned": 0, "errors": 0}

    try:
        current_block = _get_current_block()
    except Exception as exc:
        logger.error(f"[chain] Cannot get current block: {exc}")
        return stats

    logger.info(f"[chain] Current BSC block: {current_block:,}")

    from_block = _get_scan_cursor(_CURSOR_KEY) + 1
    if from_block > current_block:
        logger.info(f"[chain] Already up to date (cursor={from_block - 1:,})")
        return stats

    total_blocks = current_block - from_block + 1
    logger.info(
        f"[chain] Scanning {total_blocks:,} blocks "
        f"({from_block:,} → {current_block:,}) "
        f"on {TOKEN_MANAGER2[:10]}…"
    )

    chunk = settings.chain_scan_chunk
    block = from_block

    while block <= current_block:
        end = min(block + chunk - 1, current_block)
        retries = 0
        logs = []

        while True:
            try:
                logs = _get_logs(TOKEN_MANAGER2, GRADUATION_TOPIC, block, end)
                break
            except Exception as exc:
                retries += 1
                if retries > 3:
                    logger.error(
                        f"[chain] blocks {block:,}-{end:,}: "
                        f"giving up after {retries} retries — {exc}"
                    )
                    stats["errors"] += 1
                    logs = []
                    break
                logger.warning(
                    f"[chain] blocks {block:,}-{end:,}: "
                    f"error (retry {retries}/3): {str(exc)[:80]}"
                )
                time.sleep(_RETRY_SLEEP)

        for log in logs:
            # LiquidityAdded(address base, uint256 offers, address quote, uint256 funds)
            # All params non-indexed → all in data.
            # base = first 32-byte word: data[2+24:2+64]  (skip 12 zero-bytes of padding)
            data = log.get("data", "")
            if len(data) < 66:
                stats["errors"] += 1
                continue

            token_address = ("0x" + data[26:66]).lower()
            if len(token_address) != 42:
                stats["errors"] += 1
                continue

            try:
                name   = _erc20_name(token_address)
                symbol = _erc20_symbol(token_address)
                is_new = _insert_if_new(token_address, name, symbol)

                if is_new:
                    stats["discovered"] += 1
                    logger.info(f"[chain] ✓ {symbol} ({name}) @ {token_address}")
                    log_event(
                        "FOURMEME",
                        f"Chain scan discovered: {symbol} ({name})",
                        "chain_discovered",
                        symbol=symbol,
                        token_address=token_address,
                    )
                else:
                    stats["skipped"] += 1

            except Exception as exc:
                logger.error(f"[chain] Error processing token {token_address}: {exc}")
                stats["errors"] += 1

        stats["blocks_scanned"] += (end - block + 1)
        _set_scan_cursor(_CURSOR_KEY, end)
        block = end + 1

        # Brief pause to avoid hammering the RPC
        if block <= current_block:
            time.sleep(0.05)

    logger.info(
        f"[chain] Done — "
        f"discovered={stats['discovered']} skipped={stats['skipped']} "
        f"errors={stats['errors']} blocks={stats['blocks_scanned']:,}"
    )
    return stats
