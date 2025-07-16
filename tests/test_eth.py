"""
Unit tests for ingestion.eth module.
"""
import asyncio

import pytest
import json

from ingestion.eth import (
    load_wallets,
    decode_v2_swap,
    decode_v3_swap,
    decode_1inch_swap,
    subscribe_pending,
    event_bus,
)


@pytest.mark.asyncio
async def test_load_wallets(tmp_path):
    """Test that load_wallets correctly reads ETH addresses."""
    file = tmp_path / "wallets.json"
    content = [
        {"chain": "ETH", "address": "0x0000000000000000000000000000000000000000"},
        {"chain": "SOL", "address": "irrelevant"},
    ]
    file.write_text(json.dumps(content))
    addrs = await load_wallets(file)
    assert addrs == ["0x0000000000000000000000000000000000000000"]


def test_decode_v2_swap():
    """TODO: add tests for Uniswap V2 swap decoding."""
    pytest.skip("Not implemented")


def test_decode_v3_swap():
    """TODO: add tests for Uniswap V3 swap decoding."""
    pytest.skip("Not implemented")


def test_decode_1inch_swap():
    """TODO: add tests for 1inch swap decoding."""
    pytest.skip("Not implemented")


@pytest.mark.asyncio
async def test_subscribe_pending(monkeypatch):
    """TODO: add tests for websocket subscription logic."""
    pytest.skip("Not implemented")
