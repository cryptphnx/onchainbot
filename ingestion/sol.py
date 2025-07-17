"""
Async ingestion of Solana swap events via Helius Enhanced WS and Jito shardstream.
Filters for Swap events, enriches with Jupiter price quote, and emits to event_bus.
"""
import asyncio
import json
import os
import time
from asyncio import Queue, TimeoutError
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import structlog
import websockets

# Structured logger
structlog.configure(logger_factory=structlog.stdlib.LoggerFactory())
logger = structlog.get_logger()

# Configuration
HELIUS_WS_URL: str = os.getenv("HELIUS_WS_URL", "")
JITO_SHRED_URL: str = os.getenv("JITO_SHRED_URL", "")
SOL_WALLETS_FILE = Path(os.getenv("SOL_WALLETS_FILE", "wallets_sol.json"))

# Local event bus for downstream consumers
event_bus: Queue[Dict[str, Any]] = Queue()

# Maximum queued events before dropping oldest
_MAX_QUEUE_SIZE = 5000


async def load_wallets(path: Path) -> List[str]:
    """
    Load wallet addresses from a JSON file. Expects list of dicts with 'chain' == 'SOL'.
    Returns base58 strings.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to load wallets file", path=path)
        return []
    addrs: List[str] = []
    for entry in data:
        try:
            if entry.get("chain") == "SOL":
                addrs.append(entry["address"])
        except Exception:
            logger.exception("invalid wallet entry skipped", entry=entry)
    return addrs


async def get_jupiter_price(
    token_in: str, token_out: str, amount_in: int
) -> Decimal:
    """
    Query Jupiter quote API to get minimum output amount for the swap.
    """
    url = (
        f"https://quote-api.jup.ag/v6/price?inputMint={token_in}"
        f"&outputMint={token_out}&amount={amount_in}&swapMode=ExactIn"
    )
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(url) as resp:
            data = await resp.json()
    # expected JSON keys: data['data'][0]['price'] or ['estimatedAmountOut']
    try:
        amt = data["data"][0]["price"]
    except Exception:
        logger.error("unexpected Jupiter response", data=data)
        raise
    return Decimal(str(amt))


async def decode_helius_swap(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode a Helius Enhanced WS swap notification into our event schema.
    Expects 'params' -> 'result' containing swap details.
    """
    try:
        res = msg.get("params", {}).get("result", {})
        if res.get("type") != "swap":
            return None
        swap = res.get("swap", {})
        route = swap.get("route", [])
        if len(route) < 2:
            return None
        amount_in = int(swap.get("amountIn", 0))
        # fetch price quote (sync or async)
        quote = get_jupiter_price(route[0], route[-1], amount_in)
        amount_out_min = await quote if asyncio.iscoroutine(quote) else quote

        evt = {
            "wallet":    res.get("account"),
            "tokenIn":   route[0],
            "tokenOut":  route[-1],
            "amountIn":  Decimal(amount_in),
            "amountOutMin": amount_out_min,
            "txHash":    res.get("transaction"),
            "timestamp": int(time.time()),
        }
        return evt
    except Exception:
        logger.exception("failed to decode helius swap", msg=msg)
        return None


async def decode_jito_swap(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode a Jito shardstream swap message into our event schema.
    """
    try:
        data = msg.get("data", {})
        if data.get("type") != "swap":
            return None
        route = data.get("route", [])
        if len(route) < 2:
            return None
        amount_in = int(data.get("amountIn", 0))
        quote = get_jupiter_price(route[0], route[-1], amount_in)
        amount_out_min = await quote if asyncio.iscoroutine(quote) else quote

        evt = {
            "wallet":    data.get("account"),
            "tokenIn":   route[0],
            "tokenOut":  route[-1],
            "amountIn":  Decimal(amount_in),
            "amountOutMin": amount_out_min,
            "txHash":    data.get("transaction"),
            "timestamp": int(time.time()),
        }
        return evt
    except Exception:
        logger.exception("failed to decode jito swap", msg=msg)
        return None


async def _process_and_enqueue(evt: Dict[str, Any]) -> None:
    """Apply back-pressure: drop oldest if full, then enqueue with timeout."""
    q = event_bus
    # drop oldest if queue too large
    while q.qsize() > _MAX_QUEUE_SIZE:
        _ = q.get_nowait()
        logger.warning("dropped oldest event due to queue overflow")
    try:
        await asyncio.wait_for(q.put(evt), timeout=1)
    except TimeoutError:
        logger.warning("queue put timed out, dropping event", evt=evt)


async def subscribe_helius(addresses: List[str]) -> None:
    """
    Connect to Helius WS addressSubscription and enqueue decoded swaps.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(HELIUS_WS_URL) as ws:
                sub = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "addressSubscription",
                    "params": {"addresses": addresses, "type": "swap"},
                }
                await ws.send(json.dumps(sub))
                logger.info("helius subscribed to swaps")
                backoff = 1
                async for msg in ws:
                    data = json.loads(msg)
                    evt = await decode_helius_swap(data)
                    if evt:
                        await _process_and_enqueue(evt)
        except Exception:
            logger.exception("helius connection error, retrying in %s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def subscribe_jito(addresses: List[str]) -> None:
    """
    Connect to Jito shardstream WS and enqueue decoded swaps.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(JITO_SHRED_URL) as ws:
                sub = json.dumps({"addresses": addresses})
                await ws.send(sub)
                logger.info("jito subscribed to addresses")
                backoff = 1
                async for msg in ws:
                    data = json.loads(msg)
                    evt = await decode_jito_swap(data)
                    if evt:
                        await _process_and_enqueue(evt)
        except Exception:
            logger.exception("jito connection error, retrying in %s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def main() -> None:
    """
    Load SOL wallets and run both Helius and Jito subscribers concurrently.
    """
    addrs = await load_wallets(SOL_WALLETS_FILE)
    if not addrs:
        logger.error("no SOL wallets, exiting")
        return
    await asyncio.gather(subscribe_helius(addrs), subscribe_jito(addrs))


if __name__ == "__main__":
    asyncio.run(main())
