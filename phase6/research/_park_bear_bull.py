#!/usr/bin/env python3
"""Park BEAR/BULL strategy plans until live regime or historical-backtest unlock."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "state" / "trials" / "TEST_STRATEGY.json"
NOW = datetime.now(timezone.utc).isoformat()
DAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

PARK = {
    "PLAN-BEAR-PARK-001": {
        "emit_only_when_regime": "bear",
        "allow_historical_backtest": True,
        "parked": True,
        "park_reason": (
            f"{DAY}: Park until live regime=bear (clear transition) OR Brad unlocks "
            "historical bear-tape backtest via "
            "`analyst_test_strategy.py emit --allow-historical-backtest PLAN-BEAR-PARK-001`. "
            "Not closed — real test design retained."
        ),
        "emit_gate_note": (
            "PARKED: auto-emit only when live=bear. Historical backtest requires explicit "
            "CLI unlock. Primary window remains bear_historical_slices."
        ),
    },
    "PLAN-BULL-KNOBS-002": {
        "emit_only_when_regime": "bull",
        "allow_historical_backtest": True,
        "parked": True,
        "park_reason": (
            f"{DAY}: Park until live regime=bull (detector bull / BTC 30d ≥ +15%) OR Brad unlocks "
            "historical bull-tape backtest via "
            "`analyst_test_strategy.py emit --allow-historical-backtest PLAN-BULL-KNOBS-002`. "
            "Layered re-entry stays paper-only. Not closed — real successor to zombie 001."
        ),
        "emit_gate_note": (
            "PARKED: auto-emit only when live=bull. Historical backtest requires explicit "
            "CLI unlock. Primary window bull_windows."
        ),
    },
}


def main() -> None:
    s = json.loads(PATH.read_text())
    for plan in s.get("roadmap") or []:
        pid = plan.get("plan_id")
        if pid not in PARK:
            continue
        u = PARK[pid]
        plan.update(u)
        # keep regimen fields
        plan["regimen_ready"] = True
        print("PARKED", pid, "regime=", u["emit_only_when_regime"])
    s.setdefault("notes", []).append(
        f"{DAY}: Brad park bear+bull until clear live transition OR explicit historical "
        f"backtest unlock. METHOD-ROTATION remains next ungated offline candidate when capacity free."
    )
    s["updated_at"] = NOW
    PATH.write_text(json.dumps(s, indent=2) + "\n")
    print("OK", PATH)


if __name__ == "__main__":
    main()
