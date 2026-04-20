"""
Server-side Demo Swap service.

Flow
────
  User has already paid the MemeScavenger contract (buy() tx confirmed).
  Now the hot wallet uses its OWN pre-funded USDT to buy demo tokens on
  PancakeSwap and deliver them directly to the user's wallet.

  1. approve(pancake_router, total_usdt_wei)   ← hot wallet approves its own USDT
  2. For each demo token:
       swapExactTokensForTokensSupportingFeeOnTransferTokens(
           amountIn, 0, [USDT, token], to=user_wallet, deadline
       )
     Tokens are sent DIRECTLY to the user's wallet by PancakeSwap.
     Hot wallet never holds the output tokens.

  Hot wallet requirements:
    • BNB for gas (a few dollars covers hundreds of swaps)
    • USDT matching total tier price (10 / 20 / 30 USDT per order)

Returns
───────
  {
    "swaps": [
      {"token": {address,name,symbol,img_url}, "success": bool,
       "received": "1234.5678", "tx_hash": "0x..."},
      ...
    ],
    "total_usdt": 10
  }
"""
import logging
import time
from typing import Any

from ..config import settings
from ..database import get_db

logger = logging.getLogger(__name__)

# ── BSC addresses ─────────────────────────────────────────────────────────────
USDT_ADDRESS   = "0x55d398326f99059fF775485246999027B3197955"
WBNB_ADDRESS   = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
PANCAKE_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

TIER_USDT     = [10, 20, 30]
USDT_DECIMALS = 18

# ── Minimal ABIs ──────────────────────────────────────────────────────────────
_USDT_ABI = [
    {
        "name": "transferFrom", "type": "function",
        "inputs": [
            {"name": "sender",    "type": "address"},
            {"name": "recipient", "type": "address"},
            {"name": "amount",    "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "approve", "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
]

_ROUTER_ABI = [
    {
        "name": "swapExactTokensForTokensSupportingFeeOnTransferTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn",     "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path",         "type": "address[]"},
            {"name": "to",           "type": "address"},
            {"name": "deadline",     "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "getAmountsOut", "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path",     "type": "address[]"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
    },
]

_ERC20_ABI = [
    {
        "name": "decimals", "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
    {
        "name": "balanceOf", "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_w3():
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(settings.bsc_rpc_url, request_kwargs={"timeout": 60}))
    # BSC uses PoA — inject middleware to handle extraData field
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except ImportError:
        try:
            from web3.middleware import geth_poa_middleware
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except ImportError:
            pass   # older web3; proceed without it
    return w3


def get_demo_tokens() -> list[dict]:
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


# ── Main entry point ──────────────────────────────────────────────────────────

def execute_demo_swap(user_wallet: str, tier: int) -> dict[str, Any]:
    """
    Randomly select ONE demo token, swap the full tier amount into it,
    and deliver directly to user_wallet via PancakeSwap.
    Raises RuntimeError for configuration / on-chain errors.
    """
    import random as _random

    if not settings.hot_wallet_private_key:
        raise RuntimeError("HOT_WALLET_PRIVATE_KEY is not configured on the server.")
    if not settings.hot_wallet_address:
        raise RuntimeError("HOT_WALLET_ADDRESS is not configured on the server.")

    all_tokens = get_demo_tokens()
    if not all_tokens:
        raise RuntimeError("No demo tokens configured.")

    # Pick exactly ONE token — full tier price goes to it
    demo_tokens = [_random.choice(all_tokens)]

    total_usdt  = TIER_USDT[tier]
    fee_pct     = settings.platform_fee_pct          # e.g. 5.0
    net_usdt    = round(total_usdt * (1 - fee_pct / 100), 6)
    total_wei   = int(net_usdt * (10 ** USDT_DECIMALS))
    n           = 1

    logger.info(
        f"[demo_swap] tier={tier} total={total_usdt} USDT "
        f"fee={fee_pct}% net={net_usdt} USDT"
    )

    from web3 import Web3
    from eth_account import Account

    w3      = _build_w3()
    account = Account.from_key(settings.hot_wallet_private_key)
    hot     = Web3.to_checksum_address(settings.hot_wallet_address)
    user_cs = Web3.to_checksum_address(user_wallet)

    usdt   = w3.eth.contract(address=Web3.to_checksum_address(USDT_ADDRESS),   abi=_USDT_ABI)
    router = w3.eth.contract(address=Web3.to_checksum_address(PANCAKE_ROUTER), abi=_ROUTER_ABI)

    def _send(fn, gas: int = 130_000):
        """Build → sign → send → wait for receipt."""
        nonce = w3.eth.get_transaction_count(hot, "pending")
        tx = fn.build_transaction({
            "from":     hot,
            "nonce":    nonce,
            "gas":      gas,
            "gasPrice": w3.eth.gas_price,
        })
        signed  = account.sign_transaction(tx)
        raw     = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return receipt

    # ── 1. Approve PancakeSwap Router to spend hot wallet's USDT ─────────────
    logger.info(f"[demo_swap] approve router — hot wallet spends its own {total_usdt} USDT")
    _send(usdt.functions.approve(Web3.to_checksum_address(PANCAKE_ROUTER), total_wei))

    # ── 2. Swap each demo token; tokens go straight to user's wallet ──────────
    deadline = int(time.time()) + 1200   # 20-minute window
    results  = []

    wbnb_cs = Web3.to_checksum_address(WBNB_ADDRESS)

    for i, token in enumerate(demo_tokens):
        amt = total_wei   # full amount → single token

        token_cs = Web3.to_checksum_address(token["address"])
        symbol   = token.get("symbol", token_cs[:8])

        # Pick best path: direct USDT→token, or via WBNB
        direct_path = [Web3.to_checksum_address(USDT_ADDRESS), token_cs]
        via_wbnb    = [Web3.to_checksum_address(USDT_ADDRESS), wbnb_cs, token_cs]

        path = direct_path
        try:
            out = router.functions.getAmountsOut(amt, direct_path).call()
            if not out or out[-1] == 0:
                raise ValueError("zero output on direct path")
        except Exception:
            path = via_wbnb

        logger.info(f"[demo_swap] swap {symbol} via {'direct' if path == direct_path else 'WBNB'}, amt={amt}")

        try:
            # Snapshot user's token balance before swap
            erc20 = w3.eth.contract(address=token_cs, abi=_ERC20_ABI)
            try:
                decimals   = erc20.functions.decimals().call()
                bal_before = erc20.functions.balanceOf(user_cs).call()
            except Exception:
                decimals   = 18
                bal_before = 0

            receipt = _send(
                router.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                    amt,       # amountIn
                    0,         # amountOutMin = 0 (demo — no slippage guard)
                    path,
                    user_cs,   # ← tokens land directly in user's wallet
                    deadline,
                ),
                gas=380_000,
            )

            if receipt.status == 1:
                try:
                    bal_after    = erc20.functions.balanceOf(user_cs).call()
                    received_raw = max(bal_after - bal_before, 0)
                    received_fmt = f"{received_raw / (10 ** decimals):,.0f}"
                except Exception:
                    received_fmt = "?"

                results.append({
                    "token":    token,
                    "success":  True,
                    "received": received_fmt,
                    "tx_hash":  receipt.transactionHash.hex(),
                })
                logger.info(f"[demo_swap] ✓ {symbol} received={received_fmt} tx={receipt.transactionHash.hex()}")
            else:
                results.append({"token": token, "success": False, "error": "Swap reverted on-chain"})
                logger.warning(f"[demo_swap] ✗ {symbol} swap reverted")

        except Exception as exc:
            msg = str(exc)[:200]
            logger.error(f"[demo_swap] ✗ {symbol} exception: {msg}")
            results.append({"token": token, "success": False, "error": msg})

    return {
        "swaps":      results,
        "total_usdt": total_usdt,
        "fee_usdt":   round(total_usdt - net_usdt, 6),
        "net_usdt":   net_usdt,
    }
