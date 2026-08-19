#!/usr/bin/env python3
"""Isolation: rebalance quality gate (connectivity + signal_freshness_enforced)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rebalance_quality_gate import (  # noqa: E402
    assess_data_readiness,
    should_mark_slot_complete,
    signal_freshness_enforced,
)


class _Runner:
    config_dict = {"global_settings": {"signal_freshness_enforced": True}}


def test_enforced_blocks_stale():
    r = _Runner()
    assert signal_freshness_enforced(r) is True
    ok, reasons = assess_data_readiness(
        r,
        {"complete": False, "stale_rsi": ["BTC-USD"], "stale_sentiment": []},
    )
    assert ok is False
    assert "incomplete_coverage" in reasons
    print("enforced_blocks_stale OK")


def test_slot_not_burned_on_outage():
    assert (
        should_mark_slot_complete(
            connectivity_ok=False,
            data_ready=False,
            executed=0,
            skipped=[],
            enforced=True,
        )
        is False
    )
    assert (
        should_mark_slot_complete(
            connectivity_ok=True,
            data_ready=True,
            executed=4,
            skipped=[],
            enforced=True,
        )
        is True
    )
    assert (
        should_mark_slot_complete(
            connectivity_ok=True,
            data_ready=True,
            executed=0,
            skipped=[{"reason": "network unreachable"}],
            enforced=True,
        )
        is False
    )
    print("slot_not_burned_on_outage OK")


if __name__ == "__main__":
    test_enforced_blocks_stale()
    test_slot_not_burned_on_outage()
    print("[REBALANCE-QUALITY-GATE] PASSED")