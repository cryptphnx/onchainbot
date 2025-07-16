import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import websockets
from eth_abi import decode_abi
from eth_utils import keccak, to_hex

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Environment/config variables
ALCHEMY_API_KEY: str = os.getenv("ALCHEMY_API_KEY", "")
if not ALCHEMY_API_KEY:
    logger.error("ALCHEMY_API_KEY is not set")

WS_URL: str = f"wss://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
WALLETS_FILE: str = os.getenv("WALLETS_FILE", "wallets.json")
REDIS_CHANNEL: str = os.getenv("REDIS_CHANNEL", "uniswap_v3_swaps")

# Uniswap V3 Swap event signature
_SWAP_SIG_TEXT = "Swap(address,address,int256,int256,uint160,uint128,int24)"
_SWAP_TOPIC0: str = to_hex(keccak(text=_SWAP_SIG_TEXT))

async def load_wallets(path: str) -> List[str]:
    """
    Load wallet addresses from a JSON file. Expects a JSON array of hex strings.
    """
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception("Failed to load wallets file '%s'", path)
        return []
    # Normalize to lowercase for comparison
    return [addr.lower() for addr in data if isinstance(addr, str)]

def decode_swap_event(log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decode a Uniswap V3 Swap event log into a dict.
    Returns None if the log is not a Swap event.
    """
    try:
        topics = log.get("topics", [])
        if not topics or topics[0] != _SWAP_TOPIC0:
            return None
        # Indexed parameters: sender and recipient
        sender = "0x" + topics[1][-40:]
        recipient = "0x" + topics[2][-40:]
        # Data contains: amount0(int256), amount1(int256), sqrtPriceX96(uint160), liquidity(uint128), tick(int24)
        data_bytes = bytes.fromhex(log.get("data", "")[2:])
        amount0, amount1, sqrt_price_x96, liquidity, tick = decode_abi(
            ["int256", "int256", "uint160", "uint128", "int24"], data_bytes
        )
        return {
            "transactionHash": log.get("transactionHash"),
            "logIndex": int(log.get("logIndex", "0x0"), 16),
            "blockNumber": int(log.get("blockNumber", "0x0"), 16),
            "sender": sender.lower(),
            "recipient": recipient.lower(),
            "amount0": amount0,
            "amount1": amount1,
            "sqrtPriceX96": sqrt_price_x96,
            "liquidity": liquidity,
            "tick": tick,
        }
    except Exception:
        logger.exception("Failed to decode log: %s", log)
        return None

async def publish_event(
    redis_client: redis.Redis, channel: str, message: Dict[str, Any]
) -> None:
    """
    Publish a JSON message to a Redis channel.
    """
    try:
        await redis_client.publish(channel, json.dumps(message))
    except Exception:
        logger.exception("Failed to publish message to Redis: %s", message)

async def subscribe_and_process(wallets: List[str]) -> None:
    """
    Connect to Alchemy WS, subscribe to Swap logs, decode and forward relevant events.
    """
    # Create Redis client
    redis_client = redis.from_url(REDIS_URL)
    try:
        async with websockets.connect(WS_URL) as ws:
            # Subscribe to all Swap events
            subscribe_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["logs", {"topics": [_SWAP_TOPIC0]}],
            }
            await ws.send(json.dumps(subscribe_payload))
            logger.info("Subscribed to Uniswap V3 Swap events: topic=%s", _SWAP_TOPIC0)

            # Listen for incoming logs
            while True:
                message = await ws.recv()
                data = json.loads(message)
                params = data.get("params")
                if not params:
                    continue
                log = params.get("result")
                if not log:
                    continue
                event = decode_swap_event(log)
                if not event:
                    continue
                # Filter by monitored wallets
                if event["sender"] in wallets or event["recipient"] in wallets:
                    await publish_event(redis_client, REDIS_CHANNEL, event)
                    logger.info(
                        "Published Swap event tx=%s logIndex=%d",
                        event["transactionHash"], event["logIndex"],
                    )
    except Exception:
        logger.exception("WebSocket connection failed or closed.")
    finally:
        await redis_client.close()

async def main() -> None:
    """
    Entry point: Load wallets and run the subscription loop.
    """
    wallets = await load_wallets(WALLETS_FILE)
    if not wallets:
        logger.error("No wallets to monitor. Exiting.")
        return
    await subscribe_and_process(wallets)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down subscriber.")
