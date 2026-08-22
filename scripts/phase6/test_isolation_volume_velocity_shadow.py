#!/usr/bin/env python3
"""Isolation tests for volume_velocity_shadow (no network required for unit parts)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.volume_velocity_shadow import (  # noqa: E402
    rvol_from_vols,
    rvol_burst_nh,
    daily_vols_from_hourly,
    synthetic_gate_check,
    VelocityConfig,
    telegram_summary,
)


def test_rvol():
    vols = [10.0] * 20 + [40.0]
    r = rvol_from_vols(vols, 20, use_last=True)
    assert r is not None and abs(r - 4.0) < 1e-9, r
    # penultimate: [10]*20 + [40, 5] → bar 40 vs mean 10
    vols2 = [10.0] * 20 + [40.0, 5.0]
    r2 = rvol_from_vols(vols2, 20, use_last=False)
    assert r2 is not None and abs(r2 - 4.0) < 1e-9, r2
    assert rvol_from_vols([1, 2], 20) is None
    # 3h burst: prior 20h @10, last 3h @40 → (40)/10 = 4
    vols3 = [10.0] * 20 + [40.0, 40.0, 40.0, 1.0]
    b = rvol_burst_nh(vols3, 3, 20)
    assert b is not None and abs(b - 4.0) < 1e-9, b


def test_daily_agg():
    # two hours same day + one next day
    base = 1_700_000_000
    candles = [
        [base, 1, 2, 1, 1.5, 100],
        [base + 3600, 1, 2, 1, 1.6, 50],
        [base + 86400, 1, 2, 1, 1.7, 80],
    ]
    d = daily_vols_from_hourly(candles)
    assert len(d) == 2
    assert d[0] == 150
    assert d[1] == 80


def test_gate_lqhv():
    cfg = VelocityConfig()
    g = synthetic_gate_check(
        pair="FOO-USD",
        ret_24h=0.05,
        mom_3d=0.04,
        mom_7d=0.1,
        rvol_1h=3.0,
        vol_quote_24h=400_000,
        quality_row={"quality_score": 0.2, "pass_gate": False},
        in_contenders=False,
        promote_eligible=False,
        proposed_add=False,
        cfg=cfg,
    )
    assert g["low_qualified_high_velocity"] is True
    assert g["would_clear_legacy_funnel"] is False
    assert any("below_discovery" in x for x in g["fails"])


def test_telegram_empty_when_idle():
    assert telegram_summary({"nominations_this_run": 0, "open_tracks": 0}) == ""
    body = telegram_summary(
        {
            "nominations_this_run": 2,
            "open_tracks": 3,
            "low_qualified_high_velocity_n": 1,
            "ever_promote_eligible_n": 0,
            "never_selected_n": 3,
            "perf_all_open": {"mean_mark_r": 0.01},
            "perf_lqhv": {"mean_mark_r": 0.02},
            "perf_never_selected": {"mean_mark_r": 0.015},
            "nominations": [{"pair": "AAA-USD", "bucket": "early_coil", "rvol_1h": 2.5}],
        }
    )
    assert "VELOCITY shadow" in body
    assert "AAA-USD" in body


def main() -> int:
    test_rvol()
    test_daily_agg()
    test_gate_lqhv()
    test_telegram_empty_when_idle()
    print("OK test_isolation_volume_velocity_shadow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
