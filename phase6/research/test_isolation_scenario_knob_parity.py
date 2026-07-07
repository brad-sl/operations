#!/usr/bin/env python3
"""
ANALYST-OPT R1 isolation: scenario knob parity across Path A/B/C mappings.

Exit 0 when:
- Every scenario in default pack maps to BacktestConfig + arch4 params + live overlay
- ARCH-4 harness runs once using knobs from baseline_7d (real OHLCV, no network)

Run: python3 phase6/research/test_isolation_scenario_knob_parity.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.scenario_knobs import ScenarioKnobs, parity_report


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def test_pack_mappings(pack_path: Path) -> None:
    with open(pack_path) as f:
        pack = json.load(f)
    dr = pack["date_range"]
    start = _parse_date(dr["start"])
    end = _parse_date(dr["end"])

    for sc in pack["scenarios"]:
        knobs = ScenarioKnobs.from_scenario(sc, pack)
        cfg = knobs.to_backtest_config(start, end)
        assert cfg.rebalance_frequency_days == knobs.rebalance_frequency_days
        assert cfg.initial_capital == knobs.initial_capital
        arch = knobs.to_arch4_params()
        assert arch["rebal_freq"] == knobs.rebalance_frequency_days
        overlay = knobs.to_live_config_overlay()
        assert "global_settings.rebalance_cap_usd" in overlay
        gaps = knobs.gap_flags()
        assert "REBALANCE_CLOCK_vs_DAY_STRIDE" in gaps

    report = parity_report(pack)
    out = ROOT / "data/state/analyst_scenario_parity_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"parity mappings OK scenarios={len(pack['scenarios'])} wrote {out}")


def test_arch4_smoke_from_knobs(pack_path: Path) -> None:
    with open(pack_path) as f:
        pack = json.load(f)
    baseline_id = pack["baseline_scenario_id"]
    sc = next(s for s in pack["scenarios"] if s["id"] == baseline_id)
    knobs = ScenarioKnobs.from_scenario(sc, pack)
    params = knobs.to_arch4_params()

    from phase6.scripts.backtest_arch4_isolation_harness import (
        load_all_data,
        load_ohlcv,
        PAIR_MAP,
        run_arch4_backtest,
    )

    basket = []
    for short in ["btc", "eth", "sol", "xrp", "doge"]:
        p = PAIR_MAP.get(short)
        if p and load_ohlcv(p):
            basket.append(p)
    if len(basket) < 3:
        raise RuntimeError("insufficient OHLCV for arch4 smoke")

    data = load_all_data(basket)
    result = run_arch4_backtest(
        data,
        initial=params["initial_capital"],
        rebal_freq=params["rebal_freq"],
        use_rotation=params["use_rotation"],
    )
    if result.get("error"):
        raise RuntimeError(result["error"])
    metrics = result.get("metrics") or {}
    print(
        f"arch4 smoke OK scenario={baseline_id} "
        f"return_pct={metrics.get('return_pct')} max_dd={metrics.get('max_dd_pct')} "
        f"trades={metrics.get('trade_count')}"
    )


def test_r1b_arch4_leaderboard_one_scenario() -> None:
    from phase6.research.arch4_scenario_runner import run_arch4_scenario

    pack_path = ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json"
    with open(pack_path) as f:
        pack = json.load(f)
    sc = pack["scenarios"][0]
    knobs = ScenarioKnobs.from_scenario(sc, pack)
    assert knobs.engine == "arch4"
    out = run_arch4_scenario(knobs)
    assert out["metrics"]["engine"] == "arch4"
    assert "sharpe_ratio" in out["metrics"]
    print(f"r1b arch4 runner OK id={knobs.scenario_id} sharpe={out['metrics']['sharpe_ratio']}")


def main() -> int:
    pack = ROOT / "phase6/research/scenarios/r0_smoke_three.json"
    test_pack_mappings(pack)
    test_arch4_smoke_from_knobs(pack)
    test_pack_mappings(ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json")
    test_r1b_arch4_leaderboard_one_scenario()
    print("ANALYST-OPT R1 isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())