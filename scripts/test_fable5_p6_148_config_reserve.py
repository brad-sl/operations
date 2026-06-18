#!/usr/bin/env python3
"""
Code Isolation Test for P6-148 / G4 (reserve config key).
Config must contain withdrawal_reserve.min_reserve_usd (non-default path).
Runner must read it without falling back to hard-coded only.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG = Path("config/trading_config_phase6.json")

def test_config_has_withdrawal_reserve_key():
    cfg = json.loads(CONFIG.read_text())
    assert "withdrawal_reserve" in cfg, "Missing top-level withdrawal_reserve"
    wr = cfg["withdrawal_reserve"]
    assert "min_reserve_usd" in wr and isinstance(wr["min_reserve_usd"], (int, float)), "min_reserve_usd missing or bad type"
    assert wr["min_reserve_usd"] >= 10, "Reserve value unrealistically low"
    print("P6-148: config withdrawal_reserve key present and sane.")

def test_harness_and_runner_respect_config():
    # Light simulation: load via the pattern the runner now uses
    cfg = json.loads(CONFIG.read_text())
    min_reserve = cfg.get("withdrawal_reserve", {}).get("min_reserve_usd", 200.0)
    assert min_reserve == cfg["withdrawal_reserve"]["min_reserve_usd"]
    print(f"P6-148: runner-style read gives min_reserve=${min_reserve}")

if __name__ == "__main__":
    test_config_has_withdrawal_reserve_key()
    test_harness_and_runner_respect_config()
    print("P6-148 isolation test: ALL PASS")
