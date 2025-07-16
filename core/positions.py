"""
In-memory Position map keyed by (wallet, token).

Expose:
• open(position: TradeEvent, mirror_ratio: Decimal) -> Position
• update(position: TradeEvent) -> None
• close(wallet: str, token: str) -> Position

Record fields: size, avg_price, opened_at, last_update, origin_tx.

Concurrency-safe using asyncio.Lock.
"""
import asyncio
from decimal import Decimal
from typing import Dict, Tuple

from pydantic import BaseModel, Field


class TradeEvent(BaseModel):
    wallet: str
    token_in: str = Field(..., alias="tokenIn")
    token_out: str = Field(..., alias="tokenOut")
    amount_in: Decimal = Field(..., alias="amountIn")
    amount_out_min: Decimal = Field(..., alias="amountOutMin")
    tx_hash: str = Field(..., alias="txHash")
    timestamp: int

    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias = True


class Position(BaseModel):
    wallet: str
    token: str
    size: Decimal
    avg_price: Decimal
    opened_at: int
    last_update: int
    origin_tx: str


# Internal state
_lock = asyncio.Lock()
_positions: Dict[Tuple[str, str], Position] = {}


async def open(position: TradeEvent, mirror_ratio: Decimal) -> Position:
    """
    Open a new position for the given trade event, applying mirror_ratio
    to the trade's output amount for the initial size.
    """
    key = (position.wallet, position.token_out)
    async with _lock:
        if key in _positions:
            raise ValueError(f"Position already open for wallet={position.wallet}, token={position.token_out}")
        size = position.amount_out_min * mirror_ratio
        avg_price = position.amount_in / position.amount_out_min
        pos = Position(
            wallet=position.wallet,
            token=position.token_out,
            size=size,
            avg_price=avg_price,
            opened_at=position.timestamp,
            last_update=position.timestamp,
            origin_tx=position.tx_hash,
        )
        _positions[key] = pos
        return pos


async def update(position: TradeEvent) -> None:
    """
    Update an existing position with a new trade event.
    Adjusts size by the event's output amount and recomputes a weighted avg_price.
    """
    key = (position.wallet, position.token_out)
    async with _lock:
        pos = _positions.get(key)
        if pos is None:
            raise KeyError(f"No open position for wallet={position.wallet}, token={position.token_out}")
        # compute new metrics
        new_qty = position.amount_out_min
        new_price = position.amount_in / position.amount_out_min
        total_qty = pos.size + new_qty
        # weighted average price
        pos.avg_price = (pos.avg_price * pos.size + new_price * new_qty) / total_qty
        pos.size = total_qty
        pos.last_update = position.timestamp


async def close(wallet: str, token: str) -> Position:
    """
    Close and return the position for the given wallet and token.
    """
    key = (wallet, token)
    async with _lock:
        pos = _positions.pop(key, None)
        if pos is None:
            raise KeyError(f"No open position to close for wallet={wallet}, token={token}")
        return pos


__all__ = ["TradeEvent", "Position", "open", "update", "close"]
