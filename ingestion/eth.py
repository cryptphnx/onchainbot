"""
Async ingestion of pending Ethereum swaps (Uniswap V2/V3 and 1inch) via Alchemy websocket.
"""
import asyncio
import json
import os
import time
from asyncio import Queue
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import websockets
from eth_abi import decode as decode_abi
from web3.exceptions import ABIFunctionNotFound
from web3 import Web3

# Structured logger
structlog.configure(logger_factory=structlog.stdlib.LoggerFactory())
logger = structlog.get_logger()

# Configuration
ALCHEMY_WS_URL: str = os.getenv("ALCHEMY_WS_URL", "")
if not ALCHEMY_WS_URL:
    logger.error("ALCHEMY_WS_URL is not set; aborting startup")

ETH_WALLETS_FILE = Path(os.getenv("ETH_WALLETS_FILE", "wallets_eth.json"))

# Known router addresses
UNISWAP_V2_ROUTER = Web3.to_checksum_address("0x7a250d5630B4cF539739DF2C5dAcb4c659F2488D")
UNISWAP_V3_ROUTER = Web3.to_checksum_address("0xE592427A0AEce92De3Edee1f18E0157C05861564")
ONEINCH_ROUTER = Web3.to_checksum_address("0x11111112542d85b3ef69ae05771c2dccff4faa26")

# Event bus for downstream consumers
event_bus: Queue[Dict[str, Any]] = Queue()


async def load_wallets(path: Path) -> List[str]:
    """
    Load ETH wallet addresses from a JSON file. Expects a list of dicts with 'chain'=='ETH'.
    Returns checksum-format addresses.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("loading wallets file failed", path=path)
        return []
    addrs: List[str] = []
    for entry in data:
        try:
            if entry.get("chain") == "ETH":
                addrs.append(Web3.to_checksum_address(entry["address"]))
        except Exception:
            logger.exception("invalid wallet entry skipped", entry=entry)
    return addrs


def decode_v2_swap(tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode Uniswap V2 swapExactTokensForTokens calls.
    """
    try:
        if Web3.to_checksum_address(tx.get("to", "")) != UNISWAP_V2_ROUTER:
            return None
        data = tx.get("input", "")
        b = bytes.fromhex(data[2:])
        sig = b[:4]
        # swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
        sig_expected = Web3.keccak(text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")[:4]
        if sig != sig_expected:
            return None
        args = decode_abi(
            ["uint256", "uint256", "address[]", "address", "uint256"], b[4:]
        )
        amount_in, amount_out_min, path, recipient, deadline = args
        return {
            "wallet": tx.get("from"),
            "tokenIn": path[0],
            "tokenOut": path[-1],
            "amountIn": Decimal(amount_in),
            "amountOutMin": Decimal(amount_out_min),
            "txHash": tx.get("hash"),
            "timestamp": int(time.time()),
        }
    except ABIFunctionNotFound:
        return None
    except Exception:
        logger.exception("v2 decode failed", tx_hash=tx.get("hash"))
        return None


def decode_v3_swap(tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode Uniswap V3 exactInputSingle calls.
    """
    # TODO: implement V3 decoding
    return None


def decode_1inch_swap(tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode 1inch swap transactions.
    """
    # TODO: implement 1inch decoding
    return None


async def subscribe_pending(addresses: List[str]) -> None:
    """
    Subscribe to Alchemy pending transactions for given addresses and push swaps to event_bus.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(ALCHEMY_WS_URL) as ws:
                sub = {"jsonrpc": "2.0", "id": 0,
                       "method": "alchemy_pendingTransactions",
                       "params": [{"fromAddress": addresses}]}
                await ws.send(json.dumps(sub))
                logger.info("subscribed", method="alchemy_pendingTransactions")
                backoff = 1
                async for msg in ws:
                    data = json.loads(msg)
                    tx = data.get("params", {}).get("result")
                    if not tx or tx.get("from") not in addresses:
                        continue
                    evt = decode_v2_swap(tx) or decode_v3_swap(tx) or decode_1inch_swap(tx)
                    if evt:
                        await event_bus.put(evt)
                        logger.info("swap event queued", tx_hash=evt.get("txHash"))
        except Exception:
            logger.exception("connection error, retrying in %s seconds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def main() -> None:
    """
    Load wallets and start the pending transaction subscriber.
    """
    addresses = await load_wallets(ETH_WALLETS_FILE)
    if not addresses:
        logger.error("no eth wallets, exiting")
        return
    await subscribe_pending(addresses)


if __name__ == "__main__":
    asyncio.run(main())
