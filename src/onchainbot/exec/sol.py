"""
Solana execution module for mirror trading via Jupiter Swap API and Jito bundles.

Dependencies: solana, aiohttp, asyncio, structlog.

Expose:
  async mirror_buy(event: TradeEvent, *, mirror_ratio: Decimal,
                   rpc: AsyncClient,
                   jito_url: str = os.getenv("JITO_BUNDLE_URL"),
                   priority_fees: list[int] = [50_000, 100_000, 200_000]
  ) -> tuple[str, Decimal]
  async mirror_sell(position: Position, *, rpc: AsyncClient, **kwargs)

Keypair loading via SOLANA_PRIVATE_KEY_JSON or SOLANA_KEYPAIR_PATH.
"""
from __future__ import annotations

import os
import json
import time
import base64
import asyncio

import aiohttp
import structlog
from decimal import Decimal
from solana.rpc.async_api import AsyncClient
from solana.keypair import Keypair
from solana.transaction import VersionedTransaction

from onchainbot.core.models import TradeEvent, Position

LOGGER = structlog.get_logger(__name__)

MAX_RETRIES = 3


class SlippageExceeded(Exception):
    """Raised when quote price impact exceeds allowed threshold."""
    pass


# Load Solana keypair
_keypair_json = os.getenv("SOLANA_PRIVATE_KEY_JSON")
if _keypair_json:
    try:
        _seed = bytes(json.loads(_keypair_json))
        KEYPAIR = Keypair.from_secret_key(_seed)
    except Exception as err:
        raise RuntimeError(f"Failed to load SOLANA_PRIVATE_KEY_JSON: {err}")
else:
    _path = os.path.expanduser(os.getenv("SOLANA_KEYPAIR_PATH", "~/.config/solana/id.json"))
    try:
        with open(_path, encoding="utf-8") as f:
            _seed = bytes(json.loads(f.read()))
        KEYPAIR = Keypair.from_secret_key(_seed)
    except Exception as err:
        raise RuntimeError(
            f"SOLANA_PRIVATE_KEY_JSON not set and failed to load keypair at {_path}: {err}"
        )


async def mirror_buy(
    event: TradeEvent,
    *,
    mirror_ratio: Decimal,
    rpc: AsyncClient,
    jito_url: str = os.getenv("JITO_BUNDLE_URL"),
    priority_fees: list[int] = [50_000, 100_000, 200_000]
) -> tuple[str, Decimal]:
    """
    Mirror a buy: swap event.token_in for event.token_out scaled by mirror_ratio.
    Returns (signature, filled_price).
    """
    # fetch token decimals
    resp = await rpc.get_token_supply(event.token_in)
    decimals = resp.get("result", {}).get("value", {}).get("decimals", 0)
    amount = int(event.amount_in * mirror_ratio * (10 ** decimals))

    # fetch quote
    quote_url = "https://quote-api.jup.ag/v6/quote"
    params = {
        "inputMint": event.token_in,
        "outputMint": event.token_out,
        "amount": amount,
        "slippageBps": 40,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(quote_url, params=params) as qresp:
            qresp.raise_for_status()
            quote = await qresp.json()

    impact = Decimal(str(quote.get("priceImpactPct", 0)))
    if impact > Decimal("0.4"):
        raise SlippageExceeded(f"Price impact {impact}% exceeds 0.4%")

    # build swap transaction
    swap_url = "https://quote-api.jup.ag/v6/swap"
    async with aiohttp.ClientSession() as session:
        async with session.get(swap_url, params=params) as sresp:
            sresp.raise_for_status()
            swap_data = await sresp.json()

    tx_b64 = swap_data.get("swapTransaction")
    if not tx_b64:
        raise RuntimeError("Missing swapTransaction in response")
    tx_bytes = base64.b64decode(tx_b64)
    vtxn = VersionedTransaction.deserialize(tx_bytes)
    vtxn.sign([KEYPAIR])

    # send bundle with fee ladder
    bundle = base64.b64encode(vtxn.serialize()).decode()
    headers = {"Authorization": f"Bearer {os.getenv('JITO_BEARER', '')}"}
    for idx, fee in enumerate(priority_fees):
        body = {"bundle": [bundle], "priorityFeeLamports": fee}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{jito_url}/sendBundle", json=body, headers=headers) as bresp:
                    bresp.raise_for_status()
                    result = await bresp.json()
                    sig = result.get("signature")
                    price = Decimal(str(swap_data.get("swap", {}).get("outAmount", 0)))
                    price = price / Decimal(str(swap_data.get("swap", {}).get("inAmount", 1)))
                    return sig, price
        except Exception as err:
            LOGGER.warning(
                "bundle send failed, retrying",
                attempt=idx + 1,
                priority_fee=fee,
                error=str(err),
            )
            if idx + 1 >= MAX_RETRIES:
                raise
            await asyncio.sleep(2 ** idx)


async def mirror_sell(
    position: Position,
    *,
    rpc: AsyncClient,
    **kwargs
) -> tuple[str, Decimal]:
    """
    Mirror a sell: swap position.token into SOL/ETH? (asset to SOL) using position.size.
    Returns (signature, filled_price).
    """
    return await mirror_buy(
        TradeEvent(
            wallet=position.wallet,
            tokenIn=position.token,
            tokenOut="SOL",
            amountIn=position.size,
            amountOutMin=position.size,
            txHash=position.origin_tx,
            timestamp=int(time.time()),
        ),
        mirror_ratio=Decimal(1),
        rpc=rpc,
        **kwargs,
    )
