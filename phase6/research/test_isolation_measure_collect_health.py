#!/usr/bin/env python3
"""Isolation: measure_collect_health catches stuck meters (W2 class failure)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.research.measure_collect_health import (  # noqa: E402
    evaluate_all_streams,
    health_from_rows,
    health_w2_would_arm,
)


def test_stuck_hours_and_tryout_is_degenerate() -> None:
    rows = [
        {
            "pair": "LINK-USD",
            "held_usd": 48.0,
            "hours_held": 0.0,
            "has_tryout_lot": False,
            "mfe_pct": 0.0,
            "would_arm_3pct": False,
            "rule_id": "W1_default_wide",
        },
        {
            "pair": "SOL-USD",
            "held_usd": 72.0,
            "hours_held": 0.0,
            "has_tryout_lot": False,
            "mfe_pct": 0.0,
            "would_arm_3pct": False,
            "rule_id": "W3_never_tighten_after_green",
        },
    ]
    h = health_from_rows(
        rows,
        name="w2_test",
        required_row_fields=(
            "pair",
            "held_usd",
            "hours_held",
            "has_tryout_lot",
            "mfe_pct",
            "would_arm_3pct",
            "rule_id",
        ),
        stuck_defaults={"hours_held": 0.0, "has_tryout_lot": False},
        treatment_field="would_arm_3pct",
    )
    assert h.ok is False, h
    assert h.code == "sensor_degenerate", h
    assert h.collect_clock_ok is False
    assert h.go_packet_allowed is False
    print("ok stuck_hours_tryout → sensor_degenerate")


def test_core_only_all_false_tryout_not_degenerate() -> None:
    """Core-only book with has_tryout_lot=False is honest empty, not stuck meter."""
    rows = [
        {
            "pair": "BTC-USD",
            "held_usd": 200.0,
            "hours_held": 120.0,
            "has_tryout_lot": False,
            "mfe_pct": 0.02,
            "would_arm_3pct": False,
            "rule_id": "W1_default_wide",
        },
        {
            "pair": "ETH-USD",
            "held_usd": 150.0,
            "hours_held": 90.0,
            "has_tryout_lot": False,
            "mfe_pct": 0.01,
            "would_arm_3pct": False,
            "rule_id": "W1_default_wide",
        },
    ]
    h = health_from_rows(
        rows,
        name="w2_core_only",
        required_row_fields=(
            "pair",
            "held_usd",
            "hours_held",
            "has_tryout_lot",
            "mfe_pct",
            "would_arm_3pct",
            "rule_id",
        ),
        stuck_defaults={"hours_held": 0.0, "has_tryout_lot": False},
        treatment_field="would_arm_3pct",
    )
    assert h.ok is True, h
    assert h.collect_clock_ok is True, h
    assert h.code in ("sensor_ok", "collect_empty_book_ok"), h
    print(f"ok core_only → {h.code}")


def test_live_range_with_treatment_is_armed() -> None:
    rows = [
        {
            "pair": "ADA-USD",
            "held_usd": 25.0,
            "hours_held": 12.0,
            "has_tryout_lot": True,
            "mfe_pct": 0.005,
            "would_arm_3pct": True,
            "rule_id": "W2_tight_unproven_shell",
        },
        {
            "pair": "LINK-USD",
            "held_usd": 28.0,
            "hours_held": 8.5,
            "has_tryout_lot": True,
            "mfe_pct": 0.01,
            "would_arm_3pct": False,
            "rule_id": "W1_default_wide",
        },
        {
            "pair": "BTC-USD",
            "held_usd": 200.0,
            "hours_held": 100.0,
            "has_tryout_lot": False,
            "mfe_pct": 0.03,
            "would_arm_3pct": False,
            "rule_id": "W1_default_wide",
        },
    ]
    h = health_from_rows(
        rows,
        name="w2_armed",
        required_row_fields=(
            "pair",
            "held_usd",
            "hours_held",
            "has_tryout_lot",
            "mfe_pct",
            "would_arm_3pct",
            "rule_id",
        ),
        stuck_defaults={"hours_held": 0.0, "has_tryout_lot": False},
        treatment_field="would_arm_3pct",
    )
    assert h.ok is True, h
    assert h.code == "collect_armed", h
    assert h.collect_clock_ok is True
    print("ok live range + fire → collect_armed")


def test_w2_live_history_has_schema() -> None:
    """Live history health returns schema; live_meter preferred over contaminated hist."""
    h = health_w2_would_arm()
    assert h.get("schema") == "measure_collect_health_v1"
    assert "live_meter" in h or h.get("code")
    print(
        f"ok live W2 health code={h.get('code')} "
        f"live={((h.get('live_meter') or {}).get('code'))} "
        f"clock={h.get('collect_clock_ok')} "
        f"sensor_ok_days={h.get('sensor_ok_day_estimate')}"
    )


def test_rollup_has_streams() -> None:
    roll = evaluate_all_streams()
    assert roll.get("schema") == "measure_collect_health_rollup_v1"
    assert "w2_would_arm" in (roll.get("streams") or {})
    assert "bank_trail" in (roll.get("streams") or {})
    print(f"ok rollup n={roll.get('n_streams')} frozen={roll.get('frozen')}")


if __name__ == "__main__":
    test_stuck_hours_and_tryout_is_degenerate()
    test_core_only_all_false_tryout_not_degenerate()
    test_live_range_with_treatment_is_armed()
    test_w2_live_history_has_schema()
    test_rollup_has_streams()
    print("ALL measure_collect_health isolation PASSED")
