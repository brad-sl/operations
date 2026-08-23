#!/usr/bin/env python3
"""Isolation: vol risk scalar math + velocity dampen (no network)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import vol_risk_scalar_shadow as m  # noqa: E402
from phase6.core.vol_risk_scalar_shadow import (  # noqa: E402
    VolRiskConfig,
    clip,
    ewma_variance,
    hourly_var_to_daily_vol,
    log_returns,
)


def test_math() -> None:
    closes = [100.0]
    for i in range(200):
        closes.append(
            closes[-1] * (1.0 + 0.001 * math.sin(i / 7) + (0.002 if i % 17 else -0.001))
        )
    rets = log_returns(closes)
    assert len(rets) >= 100
    var = ewma_variance(rets, span=36)
    assert var is not None and var > 0
    dvol = hourly_var_to_daily_vol(var)
    assert 0.0001 < dvol < 0.5

    cfg = VolRiskConfig()
    high = m.vol_scalar(0.08, cfg, 0.03)
    assert high["s_vol"] < 0.5
    assert high["vol_regime"] == "high"

    low = m.vol_scalar(0.01, cfg, 0.03)
    assert low["s_vol"] <= cfg.s_max + 1e-9
    assert low["vol_regime"] == "low"

    s_calm = m.velocity_scalar(0.0, cfg)
    assert abs(s_calm - 1.0) < 1e-9
    s_hot = m.velocity_scalar(1.5, cfg)
    assert cfg.velocity_v_min - 1e-9 <= s_hot < s_calm

    vst = m.velocity_stress(
        {
            "summary": {"open_tracks": 10},
            "nominations": [
                {"pair": "FOO-USD", "rvol_1h": 4.0},
                {"pair": "BTC-USD", "rvol_1h": 2.5},
            ],
        },
        cfg,
    )
    assert vst["stress"] > 0.5

    shadow = m.apply_shadow_sizes(0.7, {"rebalance_cap_usd_internal": 100.0})
    assert shadow["would_reduce"] is True
    assert shadow["would_cap_usd"] == 70.0
    assert "Not a trader-facing" in (shadow.get("note") or "")

    assert clip(2.0, 0.35, 1.15) == 1.15
    print("  vol_risk_scalar math OK")


if __name__ == "__main__":
    test_math()
    print("test_isolation_vol_risk_scalar_shadow PASS")
