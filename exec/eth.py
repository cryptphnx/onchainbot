"""
Execution module for Ethereum mirror trades via 0x Swap API and Flashbots bundles.

Dependencies: web3, aiohttp, pyflashbots>=0.6.0.

Environment variables:
  ETH_RPC_URL         Ethereum JSON-RPC endpoint
  OX_API              0x API key for swap quotes
  FLASHBOTS_SIGNER_KEY  Private key for Flashbots authentication
  FLASHBOTS_RELAY_URL   (optional) Flashbots relay URL (default: https://relay.flashbots.net)

Expose:
  async mirror_buy(event: TradeEvent, mirror_ratio: Decimal) -> (tx_hash: str, price: Decimal)
  async mirror_sell(position: Position) -> (tx_hash: str, price: Decimal)
"""
import os
import asyncio
from decimal import Decimal

import aiohttp
from web3 import AsyncWeb3, AsyncHTTPProvider
from eth_account import Account

from pyflashbots import Flashbots

# Optional imports for type hinting
try:
    from core.positions import TradeEvent, Position
except ImportError:
    TradeEvent = None  # type: ignore
    Position = None  # type: ignore

# Load configuration from environment
ETH_RPC_URL = os.getenv("ETH_RPC_URL")
if not ETH_RPC_URL:
    raise RuntimeError("ETH_RPC_URL env var is required for exec.eth")
OX_API = os.getenv("OX_API")
if not OX_API:
    raise RuntimeError("OX_API env var is required for exec.eth")
FLASHBOTS_SIGNER_KEY = os.getenv("FLASHBOTS_SIGNER_KEY")
if not FLASHBOTS_SIGNER_KEY:
    raise RuntimeError("FLASHBOTS_SIGNER_KEY env var is required for exec.eth")
FLASHBOTS_RELAY_URL = os.getenv(
    "FLASHBOTS_RELAY_URL", "https://relay.flashbots.net"
)

# Initialize Web3 and Flashbots provider
w3 = AsyncWeb3(AsyncHTTPProvider(ETH_RPC_URL))
signer = Account.from_key(FLASHBOTS_SIGNER_KEY)
flashbots = Flashbots(w3, signer, FLASHBOTS_RELAY_URL)

# 0x API settings
SLIPPAGE = 0.4
ZERO_API_BASE = "https://api.0x.org"


async def _get_quote(sell_token: str, buy_token: str, sell_amount: int) -> dict:
    """Fetch a swap quote from 0x Swap API."""
    params = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "sellAmount": sell_amount,
        "slippagePercentage": SLIPPAGE,
        "takerAddress": signer.address,
    }
    headers = {"0x-api-key": OX_API}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{ZERO_API_BASE}/swap/v1/quote", params=params, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _send_bundle(tx: dict) -> str:
    """
    Sign and send a single-transaction Flashbots bundle,
    retrying once with gas escalation if the first attempt fails.
    """
    # target next block
    block_number = await w3.eth.block_number
    target = block_number + 1
    try:
        signed = signer.sign_transaction(tx)
        bundle = [{"signed_transaction": signed.rawTransaction}]
        await flashbots.send_bundle(bundle, target_block_number=target)
        return signed.hash.hex()
    except Exception:
        # escalate gas: double baseFeePerGas if available, else gasPrice
        header = await w3.eth.get_block("latest")
        base = getattr(header, "baseFeePerGas", None)
        if base:
            tx["maxFeePerGas"] = base * 2
        else:
            tx["gasPrice"] = tx.get("gasPrice", 0) * 2
        signed = signer.sign_transaction(tx)
        bundle = [{"signed_transaction": signed.rawTransaction}]
        await flashbots.send_bundle(bundle, target_block_number=target)
        return signed.hash.hex()


async def mirror_buy(event: "TradeEvent", mirror_ratio: Decimal) -> (str, Decimal):
    """
    Mirror a buy event by querying 0x for a quote to buy event.tokenOut
    using event.tokenIn as sellToken scaled by mirror_ratio.
    Returns the bundle tx hash and the quoted price.
    """
    sell_amount = int(event.amountIn * mirror_ratio)
    quote = await _get_quote(event.tokenIn, event.tokenOut, sell_amount)
    price = Decimal(str(quote.get("guaranteedPrice", quote.get("price"))))
    tx = {
        "to": quote["to"],
        "data": quote["data"],
        "value": int(quote.get("value", 0)),
        "gas": int(quote["gas"]),
        "gasPrice": int(quote["gasPrice"]),
        "chainId": int(quote["chainId"]),
    }
    tx_hash = await _send_bundle(tx)
    return tx_hash, price


async def mirror_sell(position: "Position") -> (str, Decimal):
    """
    Mirror a sell for the given Position by selling position.size of the asset
    into ETH, returning the bundle tx hash and the quoted price.
    """
    sell_amount = int(position.size)
    quote = await _get_quote(position.token, "ETH", sell_amount)
    price = Decimal(str(quote.get("guaranteedPrice", quote.get("price"))))
    tx = {
        "to": quote["to"],
        "data": quote["data"],
        "value": int(quote.get("value", 0)),
        "gas": int(quote["gas"]),
        "gasPrice": int(quote["gasPrice"]),
        "chainId": int(quote["chainId"]),
    }
    tx_hash = await _send_bundle(tx)
    return tx_hash, price


__all__ = ["mirror_buy", "mirror_sell"]
