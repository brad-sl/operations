#!/usr/bin/env python3
"""
ANALYST-OPT R0: Run a scenario pack through BacktestEngine and emit a ranked leaderboard.

Real OHLCV only (backtests/data/backtest_historical_ohlcv_*.json).

Usage:
  python3 phase6/research/run_scenario_leaderboard.py
  python3 phase6/research/run_scenario_leaderboard.py --pack phase6/research/scenarios/r0_smoke_three.json
  python3 phase6/research/run_scenario_leaderboard.py --record-learning

Isolation test: exit 0 + leaderboard JSON + jsonl append.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.backtest.backtest_engine import BacktestConfig, BacktestEngine
from phase6.backtest.metrics import calculate_max_drawdown, calculate_sharpe, collect_metrics
from phase6.research.scenario_knobs import ScenarioKnobs


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def _rank_key(primary: str, metrics: dict) -> float:
    if primary == "max_drawdown_pct":
        return -float(metrics.get(primary, 999))
    return float(metrics.get(primary, -999))


def load_pack(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def run_scenario(pack: dict, scenario: dict) -> dict:
    dr = pack["date_range"]
    knobs = ScenarioKnobs.from_scenario(scenario)
    cfg = knobs.to_backtest_config(_parse_date(dr["start"]), _parse_date(dr["end"]))
    engine = BacktestEngine(cfg)
    result = engine.run()
    result.max_drawdown_pct = calculate_max_drawdown(result.equity_curve)
    result.sharpe_ratio = calculate_sharpe(result.equity_curve)
    metrics = collect_metrics(result)
    return {
        "id": scenario["id"],
        "label": scenario.get("label", scenario["id"]),
        "metrics": metrics,
    }


def append_learning(learnings_path: Path, pack_id: str, run_id: str, winner: dict, baseline: dict) -> None:
    data = {"schema_version": 1, "last_updated": "", "learnings": []}
    if learnings_path.exists():
        with open(learnings_path) as f:
            data = json.load(f)
    cycle = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    thesis = f"Scenario pack {pack_id} should improve {winner.get('primary_metric', 'sharpe')} vs baseline."
    outcome = (
        f"run_id={run_id} winner={winner['id']} "
        f"sharpe={winner['metrics'].get('sharpe_ratio')} "
        f"return_pct={winner['metrics'].get('total_return_pct')} "
        f"max_dd={winner['metrics'].get('max_drawdown_pct')}; "
        f"baseline sharpe={baseline['metrics'].get('sharpe_ratio')}."
    )
    entry = {
        "cycle": cycle,
        "thesis": thesis,
        "outcome": outcome,
        "evolution_note": "R0 harness only; R1 must align knobs with live allocator before promotion.",
        "date": datetime.now(timezone.utc).isoformat(),
    }
    data["learnings"].append(entry)
    data["last_updated"] = entry["date"]
    learnings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(learnings_path, "w") as f:
        json.dump(data, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pack",
        default=str(ROOT / "phase6/research/scenarios/r0_smoke_three.json"),
    )
    parser.add_argument("--record-learning", action="store_true")
    args = parser.parse_args()

    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = ROOT / pack_path
    pack = load_pack(pack_path)
    primary = pack["primary_metric"]
    baseline_id = pack["baseline_scenario_id"]

    results = []
    for sc in pack["scenarios"]:
        results.append(run_scenario(pack, sc))

    results.sort(key=lambda r: _rank_key(primary, r["metrics"]), reverse=True)
    ranking = [r["id"] for r in results]
    baseline_row = next((r for r in results if r["id"] == baseline_id), results[-1])
    winner = results[0]

    run_id = f"OPT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    leaderboard = {
        "run_id": run_id,
        "pack_id": pack["pack_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_metric": primary,
        "baseline_scenario_id": baseline_id,
        "ranking": ranking,
        "scenarios": results,
    }

    state_dir = ROOT / "data/state"
    state_dir.mkdir(parents=True, exist_ok=True)
    latest_path = state_dir / "analyst_scenario_leaderboard_latest.json"
    with open(latest_path, "w") as f:
        json.dump(leaderboard, f, indent=2)

    jsonl_path = state_dir / "analyst_scenario_runs.jsonl"
    ledger_line = {
        "run_id": run_id,
        "pack_id": pack["pack_id"],
        "started_at": leaderboard["generated_at"],
        "data_fingerprint": {
            "source": "backtests/data/backtest_historical_ohlcv_*",
            "pack_path": str(pack_path.relative_to(ROOT)),
        },
        "baseline_scenario_id": baseline_id,
        "primary_metric": primary,
        "ranking": ranking,
        "scenarios": results,
    }
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(ledger_line) + "\n")

    print(f"ANALYST-OPT R0 OK run_id={run_id} pack={pack['pack_id']}")
    print(f"primary_metric={primary} winner={winner['id']}")
    for r in results:
        m = r["metrics"]
        print(
            f"  {r['id']}: sharpe={m.get('sharpe_ratio')} "
            f"return_pct={m.get('total_return_pct')} max_dd={m.get('max_drawdown_pct')}"
        )
    print(f"wrote {latest_path}")

    if args.record_learning:
        append_learning(
            state_dir / "analyst_learnings.json",
            pack["pack_id"],
            run_id,
            {**winner, "primary_metric": primary},
            baseline_row,
        )
        print("appended analyst_learnings.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())