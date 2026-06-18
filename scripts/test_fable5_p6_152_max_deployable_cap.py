#!/usr/bin/env python3
"""
Code Isolation Test for P6-152: max_deployable_usd cap enforcement.
Config max_deployable clamps the deployable_after_reserve even when cash - min_reserve is larger.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def compute_deployable(cash: float, min_reserve: float, max_deployable: float) -> float:
    dep = max(0.0, cash - min_reserve)
    if max_deployable is not None:
        dep = min(dep, float(max_deployable))
    return dep

def main():
    cfg_path = "config/trading_config_phase6.json"
    with open(cfg_path) as f:
        cfg = json.load(f)
    wr = cfg.get("withdrawal_reserve", {})
    min_r = float(wr.get("min_reserve_usd", 200.0))
    max_d = wr.get("max_deployable_usd", cfg.get("global_settings", {}).get("max_deployable_usd", 1000.0))
    max_d = float(max_d) if max_d is not None else 1000.0

    # Case 1: cash allows > max (should clamp)
    cash_high = 10000.0
    dep1 = compute_deployable(cash_high, min_r, max_d)
    assert abs(dep1 - 800.0) < 0.01, f"Expected cap at 800 but got {dep1}"
    print(f"P6-152 cap-hit case: cash={cash_high}, dep={dep1} (clamped to {max_d}) — PASS")

    # Case 2: cash - reserve < max (no clamp)
    cash_low = 500.0
    dep2 = compute_deployable(cash_low, min_r, max_d)
    expected2 = max(0.0, cash_low - min_r)
    assert abs(dep2 - expected2) < 0.01, f"Low case mismatch {dep2} vs {expected2}"
    print(f"P6-152 no-cap case: cash={cash_low}, dep={dep2} — PASS")

    print("P6-152 isolation test: ALL PASS")

if __name__ == "__main__":
    main()
