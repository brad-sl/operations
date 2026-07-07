"""ANALYST-OPT R4 isolation: regime detect + drift monitor (read-only / temp state)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.regime_detector import detect_regime
from phase6.research.shadow_drift_monitor import evaluate_drift
from phase6.core.config_overlay import apply_analyst_overlays


def test_regime_detect() -> None:
    r = detect_regime()
    assert "regime" in r
    assert r["regime"] in ("bull", "bear", "flat", "transition", "unknown")
    print(f"regime={r['regime']} btc_return={r.get('btc_return_pct')}")


def test_overlay_inactive_passthrough() -> None:
    cfg = {"global_settings": {"rebalance_cap_usd": 150}}
    out = apply_analyst_overlays(cfg)
    assert out["global_settings"]["rebalance_cap_usd"] == 150


def test_drift_inactive() -> None:
    rep = evaluate_drift()
    assert rep.get("status") == "inactive"


def main() -> int:
    test_regime_detect()
    test_overlay_inactive_passthrough()
    test_drift_inactive()
    print("ANALYST-OPT R4 isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())