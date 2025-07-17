"""
Risk management utilities for mirror trading positions.

- `MIRROR_RATIO`: fraction of original size to mirror (Decimal, env default 0.02)
- `TTL_SECONDS`: time-to-live for positions in seconds (int, env default 86400)
- `should_exit(position, wallet_balance)`: exit if drawdown ≥90% or age > TTL_SECONDS
"""
import os
import time
from decimal import Decimal, InvalidOperation

from core.positions import Position

# Configuration
try:
    MIRROR_RATIO = Decimal(os.getenv("MIRROR_RATIO", "0.02"))
except InvalidOperation as err:
    raise ValueError(f"Invalid MIRROR_RATIO env var: {os.getenv('MIRROR_RATIO')}" ) from err

try:
    TTL_SECONDS = int(os.getenv("TTL_SECONDS", "86400"))
except ValueError as err:
    raise ValueError(f"Invalid TTL_SECONDS env var: {os.getenv('TTL_SECONDS')}" ) from err


def should_exit(position: Position, wallet_balance: Decimal) -> bool:
    """
    Determine whether a position should be exited based on drawdown or age.

    Exit conditions:
      * wallet_balance / position.size <= 0.1 (i.e. drawdown ≥90%)
      * (current_time - position.opened_at) > TTL_SECONDS

    Returns True if any exit condition is met.
    """
    # Drawdown check (only if initial size > 0)
    if position.size > 0:
        try:
            if wallet_balance / position.size <= Decimal("0.1"):
                return True
        except InvalidOperation:
            # Defensive: if division fails, do not exit on drawdown
            pass

    # Time-to-live (TTL) check
    if time.time() - position.opened_at > TTL_SECONDS:
        return True

    return False
