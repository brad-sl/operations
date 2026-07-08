#!/usr/bin/env python3
"""Isolation: per-scenario date_range override (ANALYST-20260708-004)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.research.run_scenario_leaderboard import load_pack


def test_pack_has_bear_window_scenarios():
    pack_path = Path(__file__).resolve().parents[1] / "research/scenarios/r2_defensive_sharpe_gate.json"
    pack = load_pack(pack_path)
    bear = [s for s in pack["scenarios"] if s.get("date_range")]
    assert len(bear) >= 2, bear
    for s in bear:
        dr = s["date_range"]
        assert dr["start"] < dr["end"]
    print(f"r2 pack scenarios={len(pack['scenarios'])} bear_window={len(bear)} OK")


if __name__ == "__main__":
    test_pack_has_bear_window_scenarios()
    print("[ANALYST-004] scenario pack isolation PASSED")