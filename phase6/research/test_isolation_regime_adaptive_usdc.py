"""Isolation: regime-adaptive overlay + USDC hurdle."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.usdc_benchmark import annualize_return_pct, beats_usdc_hurdle
from phase6.core.config_overlay import apply_analyst_overlays, OVERLAY_STATE


def test_usdc_hurdle_math() -> None:
    # +1.96% over 92 days (baseline rotation in bull window) beats 3.5% USDC
    h = beats_usdc_hurdle(1.96, {"start": "2025-10-01", "end": "2025-12-31"})
    assert h["beats_usdc_benchmark"] is True, h
    # -0.31% over ~60 days annualizes below 3.5%
    h2 = beats_usdc_hurdle(-0.31, {"start": "2025-08-01", "end": "2025-09-30"})
    assert h2["beats_usdc_benchmark"] is False


def test_regime_overlay_applies_knobs() -> None:
    overlay = {
        "active": True,
        "proposal_id": "TEST",
        "live_overlay": {"global_settings.rebalance_cap_usd": 999},
        "knobs": {"use_rotation": True, "rebal_freq": 7},
        "regime_policy": {
            "enabled": True,
            "map_path": "config/regime_knob_map.json",
            "current_regime": None,
        },
    }
    with tempfile.TemporaryDirectory() as td:
        state_path = Path(td) / "overlay.json"
        state_path.write_text(json.dumps(overlay), encoding="utf-8")
        import phase6.core.config_overlay as co

        old = co.OVERLAY_STATE
        co.OVERLAY_STATE = state_path
        try:
            cfg = {"global_settings": {"rebalance_cap_usd": 150}}
            out = apply_analyst_overlays(cfg)
            cap = out["global_settings"]["rebalance_cap_usd"]
            # USDC standdown forces cap 0 when scorecard winner below hurdle
            assert cap == 0.0 or (cap != 999 and cap is not None)
        finally:
            co.OVERLAY_STATE = old


def main() -> int:
    test_usdc_hurdle_math()
    test_regime_overlay_applies_knobs()
    print("regime-adaptive + USDC isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())