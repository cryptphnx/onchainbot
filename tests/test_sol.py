"""
Unit tests for ingestion.sol module using sample payloads.
"""
import asyncio
from decimal import Decimal

import pytest

from ingestion.sol import (
    decode_helius_swap,
    decode_jito_swap,
    get_jupiter_price,
    event_bus,
)

# Sample Helius enhanced swap notification
HELIUS_SAMPLE = {
    "params": {
        "result": {
            "type": "swap",
            "account": "WalletA",
            "transaction": "TxHashA",
            "swap": {
                "source": "Jupiter",
                "route": ["Mint1", "Mint2"],
                "amountIn": "1000"
            }
        }
    }
}

# Sample Jito swap message
JITO_SAMPLE = {
    "data": {
        "type": "swap",
        "account": "WalletB",
        "transaction": "TxHashB",
        "route": ["MintX", "MintY"],
        "amountIn": "2000"
    }
}


@pytest.mark.asyncio
async def test_decode_helius_swap(monkeypatch):
    # Mock Jupiter price lookup
    monkeypatch.setattr(
        "ingestion.sol.get_jupiter_price",
        lambda a, b, amt: Decimal("1500"),
    )
    evt = await decode_helius_swap(HELIUS_SAMPLE)
    assert evt["wallet"] == "WalletA"
    assert evt["tokenIn"] == "Mint1"
    assert evt["tokenOut"] == "Mint2"
    assert evt["amountIn"] == Decimal(1000)
    assert evt["amountOutMin"] == Decimal("1500")
    assert evt["txHash"] == "TxHashA"


@pytest.mark.asyncio
async def test_decode_jito_swap(monkeypatch):
    monkeypatch.setattr(
        "ingestion.sol.get_jupiter_price",
        lambda a, b, amt: Decimal("3000"),
    )
    evt = await decode_jito_swap(JITO_SAMPLE)
    assert evt["wallet"] == "WalletB"
    assert evt["tokenIn"] == "MintX"
    assert evt["tokenOut"] == "MintY"
    assert evt["amountIn"] == Decimal(2000)
    assert evt["amountOutMin"] == Decimal("3000")
    assert evt["txHash"] == "TxHashB"


def test_decode_helius_non_swap():
    evt = asyncio.get_event_loop().run_until_complete(
        decode_helius_swap({"params": {"result": {"type": "other"}}})
    )
    assert evt is None


def test_decode_jito_non_swap():
    evt = asyncio.get_event_loop().run_until_complete(
        decode_jito_swap({"data": {"type": "other"}})
    )
    assert evt is None


@pytest.mark.asyncio
async def test_get_jupiter_price(monkeypatch):
    class DummyResp:
        async def json(self):
            return {"data": [{"price": 42}]}

    class DummySession:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, url): return DummyResp()

    monkeypatch.setattr("aiohttp.ClientSession", DummySession)
    price = await get_jupiter_price("A","B",123)
    assert price == Decimal("42")
