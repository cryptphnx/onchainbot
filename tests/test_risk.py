"""
Unit tests for risk management logic in core/risk.py.
"""
import importlib
import time
from decimal import Decimal

import pytest

import core.risk as risk
from core.positions import Position


def test_config_defaults(monkeypatch):
    # Unset environment to pick up defaults
    monkeypatch.delenv("MIRROR_RATIO", raising=False)
    monkeypatch.delenv("TTL_SECONDS", raising=False)
    importlib.reload(risk)
    assert risk.MIRROR_RATIO == Decimal("0.02")
    assert risk.TTL_SECONDS == 86400


@pytest.mark.parametrize(
    "size,balance,age_offset,expected",
    [
        (Decimal("100"), Decimal("100"), 0, False),  # no drawdown, within TTL
        (Decimal("100"), Decimal("10"), 0, True),   # exactly 90% drawdown
        (Decimal("100"), Decimal("9"), 0, True),    # >90% drawdown
        (Decimal("100"), Decimal("95"), 0, False),  # minor drawdown
        (Decimal("100"), Decimal("100"), 86400 + 1, True),  # TTL expired
        (Decimal("100"), Decimal("0"), 86400 + 1, True),    # both conditions
    ],
)
def test_should_exit_matrix(monkeypatch, size, balance, age_offset, expected):
    # Reload to ensure default TTL_SECONDS and MIRROR_RATIO
    monkeypatch.delenv("TTL_SECONDS", raising=False)
    importlib.reload(risk)
    # Freeze time to controlled value
    now = 1_000_000.0
    monkeypatch.setattr(risk.time, "time", lambda: now + age_offset)
    pos = Position(
        wallet="w",
        token="t",
        size=size,
        avg_price=Decimal("1"),
        opened_at=int(now),
        last_update=int(now),
        origin_tx="tx",
    )
    result = risk.should_exit(pos, balance)
    assert result is expected


def test_invalid_env_vars(monkeypatch):
    # Invalid MIRROR_RATIO
    monkeypatch.setenv("MIRROR_RATIO", "not_a_decimal")
    with pytest.raises(ValueError):
        importlib.reload(risk)
    # Invalid TTL_SECONDS
    monkeypatch.delenv("MIRROR_RATIO", raising=False)
    monkeypatch.setenv("TTL_SECONDS", "not_an_int")
    with pytest.raises(ValueError):
        importlib.reload(risk)
