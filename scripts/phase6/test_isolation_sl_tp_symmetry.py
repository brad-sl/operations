#!/usr/bin/env python3
"""Isolation: SL/TP economic symmetry floor.

Design (2026-08-23 UNI force re-entry):
  Adaptive SL tightened to ~2.2% while live trail arm needs +4% before any
  profit path helps. Floor when live TP is on so SL is not inverted vs TP.

Rules under test:
  - live_tp OFF → adaptive unchanged (legacy path; no regression)
  - live_tp ON + never_tighter_than_base → floor at base_pct
  - live_tp ON + trail arm → floor at max(base, arm * frac)
  - symmetry disabled → no floor
  - result always clamped to [min, max]
  - StopLossManager wires config + force overrides for tests
  - UNI-shaped HIGH risk + live TP is not sub-base

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/test_isolation_sl_tp_symmetry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.sl_risk_scorer import (  # noqa: E402
    DEFAULT_SL_TP_SYMMETRY,
    apply_sl_tp_symmetry,
    get_adaptive_sl_pct,
)
from phase6.core.stop_loss_manager import StopLossManager  # noqa: E402


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def test_live_tp_off_unchanged():
    # Pure floor: live off → clamp only
    out = apply_sl_tp_symmetry(
        0.0225,
        base_pct=0.03,
        min_pct=0.015,
        max_pct=0.05,
        live_tp_active=False,
        trail_arm_pct=0.04,
    )
    assert _approx(out, 0.0225), out

    # Adaptive HIGH without live TP stays tight (legacy)
    high = {"level": "HIGH", "risk_score": 0.65}
    pct = get_adaptive_sl_pct(
        "UNI-USD",
        base_pct=0.03,
        regime_bias=0.5,
        risk_data=high,
        live_tp_active=False,
        trail_arm_pct=0.04,
    )
    assert pct < 0.03, f"expected legacy tighten, got {pct}"
    assert pct >= 0.015
    print(f"  live_tp OFF HIGH adaptive={pct} (tightened, ok)")


def test_live_tp_floor_base_and_arm():
    # 2.25% adaptive + live + base floor → at least 3%
    out = apply_sl_tp_symmetry(
        0.0225,
        base_pct=0.03,
        min_pct=0.015,
        max_pct=0.05,
        live_tp_active=True,
        trail_arm_pct=None,  # base only
        symmetry={"never_tighter_than_base_when_live_tp": True, "min_sl_frac_of_trail_arm": 0.85},
    )
    assert _approx(out, 0.03), out

    # arm 4% * 0.85 = 3.4% dominates base 3%
    out2 = apply_sl_tp_symmetry(
        0.0225,
        base_pct=0.03,
        min_pct=0.015,
        max_pct=0.05,
        live_tp_active=True,
        trail_arm_pct=0.04,
        symmetry={"never_tighter_than_base_when_live_tp": True, "min_sl_frac_of_trail_arm": 0.85},
    )
    assert _approx(out2, 0.034), out2
    print(f"  live_tp ON floors: base-only={out} arm*0.85={out2}")


def test_disabled_and_clamp():
    out = apply_sl_tp_symmetry(
        0.0225,
        base_pct=0.03,
        min_pct=0.015,
        max_pct=0.05,
        live_tp_active=True,
        trail_arm_pct=0.04,
        symmetry={"enabled": False},
    )
    assert _approx(out, 0.0225), out

    # arm floor cannot exceed max
    out_hi = apply_sl_tp_symmetry(
        0.02,
        base_pct=0.03,
        min_pct=0.015,
        max_pct=0.04,
        live_tp_active=True,
        trail_arm_pct=0.10,  # 0.10*0.85=0.085 → clamp 0.04
        symmetry={"min_sl_frac_of_trail_arm": 0.85},
    )
    assert _approx(out_hi, 0.04), out_hi
    print(f"  disabled={out} clamp_max={out_hi}")


def test_uni_shaped_high_with_live_tp():
    """Reproduce UNI force ticket shape: HIGH risk + live trail arm 4%."""
    high = {"level": "HIGH", "risk_score": 0.65, "reason": "test"}
    legacy = get_adaptive_sl_pct(
        "UNI-USD",
        base_pct=0.03,
        risk_data=high,
        live_tp_active=False,
    )
    fixed = get_adaptive_sl_pct(
        "UNI-USD",
        base_pct=0.03,
        risk_data=high,
        live_tp_active=True,
        trail_arm_pct=0.04,
        symmetry=dict(DEFAULT_SL_TP_SYMMETRY),
    )
    assert legacy < 0.03, legacy
    assert fixed >= 0.03, fixed
    # arm*0.85 = 0.034 should bind when legacy is tighter
    assert fixed >= 0.034 - 1e-9, fixed
    assert fixed <= 0.05
    print(f"  UNI-shaped HIGH: legacy={legacy} live_sym={fixed}")


def test_manager_wires_overrides():
    cfg = {
        "risk_management": {
            "stop_loss_pct": 0.03,
            "sl_base_pct": 0.03,
            "sl_min_pct": 0.015,
            "sl_max_pct": 0.05,
            "adaptive_sl": True,
            "sl_tp_symmetry": {
                "enabled": True,
                "never_tighter_than_base_when_live_tp": True,
                "min_sl_frac_of_trail_arm": 0.85,
                "force_live_tp_active": True,
                "trail_arm_pct": 0.04,
            },
        }
    }
    m = StopLossManager(exchange_client=None, config=cfg, mode="shadow")
    live, arm = m._live_tp_context()
    assert live is True
    assert _approx(arm, 0.04), arm
    high = {"level": "HIGH", "risk_score": 0.65}
    pct = m.get_sl_pct("UNI-USD", risk_data=high)
    assert pct >= 0.034 - 1e-9, pct
    print(f"  manager get_sl_pct HIGH live-forced={pct}")

    # force live off → legacy tighten again
    m.sl_tp_symmetry["force_live_tp_active"] = False
    pct2 = m.get_sl_pct("UNI-USD", risk_data=high)
    assert pct2 < 0.03, pct2
    print(f"  manager get_sl_pct HIGH live-forced-off={pct2}")


def test_low_risk_not_widened_beyond_adaptive():
    """Symmetry is a floor, not a widen-beyond-adaptive when already wider."""
    low = {"level": "LOW", "risk_score": 0.2}
    # risk-on bias can widen above base
    wide = get_adaptive_sl_pct(
        "BTC-USD",
        base_pct=0.03,
        regime_bias=0.8,
        risk_data=low,
        live_tp_active=True,
        trail_arm_pct=0.04,
    )
    # Should be >= arm floor 0.034 but not forced down
    assert wide >= 0.034 - 1e-9, wide
    print(f"  LOW risk-on with live TP={wide} (floor, not cap)")


def main() -> int:
    print("=== test_isolation_sl_tp_symmetry ===")
    tests = [
        test_live_tp_off_unchanged,
        test_live_tp_floor_base_and_arm,
        test_disabled_and_clamp,
        test_uni_shaped_high_with_live_tp,
        test_manager_wires_overrides,
        test_low_risk_not_widened_beyond_adaptive,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
            import traceback

            traceback.print_exc()
    print("=== RESULT", "PASS" if failed == 0 else f"FAIL ({failed})", "===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
