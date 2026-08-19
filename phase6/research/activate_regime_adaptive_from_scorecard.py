#!/usr/bin/env python3
"""
Activate regime-adaptive shadow overlay from scorecard-filled regime_knob_map.json.

Uses per-regime winners (not a single pack winner). Runner swaps knobs when
detect_regime() changes. USDC APY hurdle may stand down deploy per regime.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.regime_detector import detect_regime
from phase6.research.shadow_overlay_store import load_state, save_state, _snapshot_to_git

KNOB_MAP = ROOT / "config/regime_knob_map.json"
BASE_CONFIG = ROOT / "config/trading_config_phase6.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Replace existing active overlay")
    args = ap.parse_args()

    state = load_state()
    if state.get("active") and not args.force:
        print(
            f"overlay already active ({state.get('proposal_id')}); rollback first or use --force",
            file=sys.stderr,
        )
        return 1

    if not KNOB_MAP.exists():
        print(f"missing {KNOB_MAP}; run apply_regime_knob_map_from_scorecard.py", file=sys.stderr)
        return 1

    knob_map = json.loads(KNOB_MAP.read_text(encoding="utf-8"))
    det = detect_regime()
    regime = det.get("regime", "unknown")
    regimes = knob_map.get("regimes") or {}
    entry = regimes.get(regime)
    if not entry and regime == "unknown":
        entry = regimes.get("transition") or regimes.get("flat")
        regime = "transition" if regimes.get("transition") else "flat"
    if not entry:
        print(f"no knob map entry for regime={regime}", file=sys.stderr)
        return 1

    live = dict(entry.get("live_overlay") or {})
    if entry.get("usdc_benchmark", {}).get("beats_usdc_benchmark") is False:
        from phase6.core.usdc_benchmark import usdc_standdown_overlay

        live = {**live, **usdc_standdown_overlay()}

    proposal_id = "REGIME-ADAPTIVE-SCORECARD"
    payload = {
        "active": True,
        "mode": "shadow",
        "proposal_id": proposal_id,
        "source_run_id": knob_map.get("scorecard_generated_at"),
        "scenario_id": entry.get("scenario_id"),
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_equity_usd": None,
        "predicted": entry.get("usdc_benchmark"),
        "knobs": entry.get("arch4_params") or {},
        "live_overlay": live,
        "gap_flags": ["regime_adaptive_scorecard", "btc_proxy_regime"],
        "regime_policy": {
            "enabled": True,
            "map_path": "config/regime_knob_map.json",
            "current_regime": regime,
            "last_regime_change_at": det.get("as_of"),
            "detected": det,
            "usdc_benchmark": entry.get("usdc_benchmark"),
        },
    }
    snap = _snapshot_to_git(proposal_id, payload)
    payload["config_snapshot_path"] = snap

    new_state = {
        "active": True,
        **payload,
        "history": (state.get("history") or [])[-20:],
    }
    save_state(new_state)

    print(f"REGIME-ADAPTIVE shadow ACTIVE regime={regime} scenario={entry.get('scenario_id')}")
    print(f"  live_overlay cap={live.get('global_settings.rebalance_cap_usd')}")
    print(f"  usdc_benchmark={entry.get('usdc_benchmark')}")
    print(f"  snapshot={snap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())