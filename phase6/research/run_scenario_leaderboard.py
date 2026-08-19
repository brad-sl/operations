#!/usr/bin/env python3
"""
ANALYST-OPT: Run a scenario pack and emit a ranked leaderboard.

Engines per scenario (or pack `default_engine`):
  - simple  → Path A BacktestEngine
  - arch4   → Path B ARCH-4 isolation harness (promotion-eligible stack)

Real OHLCV only (backtests/data/backtest_historical_ohlcv_*.json).

Usage:
  python3 phase6/research/run_scenario_leaderboard.py
  python3 phase6/research/run_scenario_leaderboard.py --pack phase6/research/scenarios/r1_arch4_smoke_three.json
  python3 phase6/research/run_scenario_leaderboard.py --compare-production --record-learning

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

from phase6.backtest.backtest_engine import BacktestEngine
from phase6.backtest.metrics import calculate_max_drawdown, calculate_sharpe, collect_metrics
from phase6.research.arch4_scenario_runner import run_arch4_scenario
from phase6.research.production_period_baseline import (
    compare_to_production,
    compute_production_metrics,
    compute_since_go_live,
)
from phase6.research.scenario_knobs import ScenarioKnobs


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def _rank_key(primary: str, metrics: dict) -> float:
    if primary == "max_drawdown_pct":
        return -float(metrics.get(primary, 999))
    val = metrics.get(primary)
    if val is None:
        return -9999.0
    return float(val)


def load_pack(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def run_scenario(pack: dict, scenario: dict) -> dict:
    knobs = ScenarioKnobs.from_scenario(scenario, pack)
    dr = scenario.get("date_range") or pack["date_range"]
    pack_dr = pack.get("date_range") or {}
    if scenario.get("date_range") and pack_dr.get("start") and pack_dr.get("end"):
        ps, pe = _parse_date(pack_dr["start"]), _parse_date(pack_dr["end"])
        ss, se = _parse_date(dr["start"]), _parse_date(dr["end"])
        if ss < ps or se > pe:
            print(
                f"[WARN] scenario {scenario.get('id')} date_range {dr} extends outside pack {pack_dr}",
                file=sys.stderr,
            )
    w_start, w_end = _parse_date(dr["start"]), _parse_date(dr["end"])

    if knobs.engine == "arch4":
        out = run_arch4_scenario(knobs, w_start, w_end)
        return {
            "id": scenario["id"],
            "label": scenario.get("label", scenario["id"]),
            "engine": "arch4",
            "metrics": out["metrics"],
            "basket_size": len(out.get("basket") or []),
            "simulation_window": out.get("simulation_window"),
        }

    cfg = knobs.to_backtest_config(w_start, w_end)
    engine = BacktestEngine(cfg)
    result = engine.run()
    result.max_drawdown_pct = calculate_max_drawdown(result.equity_curve)
    result.sharpe_ratio = calculate_sharpe(result.equity_curve)
    metrics = collect_metrics(result)
    metrics["engine"] = "simple"
    return {
        "id": scenario["id"],
        "label": scenario.get("label", scenario["id"]),
        "engine": "simple",
        "metrics": metrics,
    }


def append_learning(
    learnings_path: Path,
    pack_id: str,
    run_id: str,
    winner: dict,
    baseline: dict,
    engine_mode: str,
    production_since: dict | None,
) -> None:
    data = {"schema_version": 1, "last_updated": "", "learnings": []}
    if learnings_path.exists():
        with open(learnings_path) as f:
            data = json.load(f)
    cycle = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    thesis = f"Scenario pack {pack_id} ({engine_mode}) should improve {winner.get('primary_metric', 'sharpe')} vs baseline and vs production."
    prod_note = ""
    if production_since and (production_since.get("metrics") or {}).get("total_return_pct") is not None:
        prod_note = f" production_return_pct={production_since['metrics'].get('total_return_pct')};"
    outcome = (
        f"run_id={run_id} winner={winner['id']} engine={winner.get('engine')} "
        f"sharpe={winner['metrics'].get('sharpe_ratio')} "
        f"return_pct={winner['metrics'].get('total_return_pct')} "
        f"max_dd={winner['metrics'].get('max_drawdown_pct')}; "
        f"baseline sharpe={baseline['metrics'].get('sharpe_ratio')};{prod_note}"
    )
    note = (
        "Path B arch4 + production comparison; promotion requires gap matrix gates + shadow."
        if engine_mode == "arch4"
        else "Path A simple only; not promotion-eligible."
    )
    entry = {
        "cycle": cycle,
        "thesis": thesis,
        "outcome": outcome,
        "evolution_note": note,
        "date": datetime.now(timezone.utc).isoformat(),
    }
    data["learnings"].append(entry)
    data["last_updated"] = entry["date"]
    learnings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(learnings_path, "w") as f:
        json.dump(data, f, indent=2)


def pack_engine_mode(pack: dict) -> str:
    de = pack.get("default_engine")
    if de:
        return de
    engines = {ScenarioKnobs.from_scenario(sc, pack).engine for sc in pack.get("scenarios", [])}
    if len(engines) == 1:
        return next(iter(engines))
    return "mixed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pack",
        default=str(ROOT / "phase6/research/scenarios/r0_smoke_three.json"),
    )
    parser.add_argument("--record-learning", action="store_true")
    parser.add_argument(
        "--compare-production",
        action="store_true",
        help="Attach live production metrics (overlap + since go-live) and vs_production deltas",
    )
    parser.add_argument(
        "--skip-live-param-audit-gate",
        action="store_true",
        help="Bypass P6 param confidence gate (dev/smoke only)",
    )
    parser.add_argument(
        "--strict-live-param-audit",
        action="store_true",
        help="Hard-fail (exit 3) when live param gate fails; default is soft-fail so weekly OPT still produces leaderboard",
    )
    parser.add_argument(
        "--refresh-param-audit",
        action="store_true",
        help="Re-run P6 param audit before scenario pack",
    )
    args = parser.parse_args()

    from phase6.research.live_param_audit_gate import (
        attach_live_param_audit_to_leaderboard,
        require_live_param_confidence_for_opt,
    )

    if not args.skip_live_param_audit_gate:
        ok, live = require_live_param_confidence_for_opt(refresh=args.refresh_param_audit)
        if not ok:
            print(
                "ANALYST-OPT: live param confidence gate failed "
                "(scenarios continue; promotion remains blocked unless gate passes)",
                file=sys.stderr,
            )
            for f in live.failures:
                print(f"  - {f}", file=sys.stderr)
            if args.strict_live_param_audit:
                print("ANALYST-OPT blocked: --strict-live-param-audit", file=sys.stderr)
                return 3
    else:
        from phase6.research.live_param_audit_gate import evaluate_live_param_confidence

        live = evaluate_live_param_confidence()

    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = ROOT / pack_path
    pack = load_pack(pack_path)
    primary = pack["primary_metric"]
    baseline_id = pack["baseline_scenario_id"]
    engine_mode = pack_engine_mode(pack)
    dr = pack["date_range"]

    results = []
    for sc in pack["scenarios"]:
        results.append(run_scenario(pack, sc))

    results.sort(key=lambda r: _rank_key(primary, r["metrics"]), reverse=True)
    ranking = [r["id"] for r in results]
    baseline_row = next((r for r in results if r["id"] == baseline_id), results[-1])
    winner = results[0]

    production = None
    since_go_live = None
    vs_production = []
    if args.compare_production:
        production = compute_production_metrics(dr["start"], dr["end"])
        since_go_live = compute_since_go_live()
        vs_production = compare_to_production(results, production, primary)

    run_id = f"OPT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    leaderboard = {
        "run_id": run_id,
        "pack_id": pack["pack_id"],
        "engine_mode": engine_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_metric": primary,
        "baseline_scenario_id": baseline_id,
        "pack_date_range": dr,
        "ranking": ranking,
        "scenarios": results,
    }
    if args.compare_production:
        leaderboard["production"] = production
        leaderboard["production_since_go_live"] = since_go_live
        leaderboard["vs_production"] = vs_production

    leaderboard = attach_live_param_audit_to_leaderboard(leaderboard, live)

    state_dir = ROOT / "data/state"
    state_dir.mkdir(parents=True, exist_ok=True)
    latest_path = state_dir / "analyst_scenario_leaderboard_latest.json"
    with open(latest_path, "w") as f:
        json.dump(leaderboard, f, indent=2)

    jsonl_path = state_dir / "analyst_scenario_runs.jsonl"
    ledger_line = {**leaderboard, "data_fingerprint": {
        "source": "backtests/data/backtest_historical_ohlcv_*",
        "pack_path": str(pack_path.relative_to(ROOT)),
    }}
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(ledger_line) + "\n")

    print(f"ANALYST-OPT OK run_id={run_id} pack={pack['pack_id']} engine_mode={engine_mode}")
    print(f"primary_metric={primary} winner={winner['id']}")
    for r in results:
        m = r["metrics"]
        print(
            f"  {r['id']} ({r.get('engine')}): sharpe={m.get('sharpe_ratio')} "
            f"return_pct={m.get('total_return_pct')} max_dd={m.get('max_drawdown_pct')}"
        )
    if args.compare_production and since_go_live:
        sm = (since_go_live.get("metrics") or {})
        print(
            f"production since go-live: return_pct={sm.get('total_return_pct')} "
            f"equity=${sm.get('end_equity_usd')} trades={sm.get('trade_count')}"
        )
        if production:
            print(f"production overlap coverage={production.get('coverage')} window={production.get('overlap_window')}")
        for c in vs_production:
            print(
                f"  vs prod {c['scenario_id']}: delta={c.get('delta')} beats={c.get('beats_production')}"
            )
    print(f"wrote {latest_path}")

    if args.record_learning:
        append_learning(
            state_dir / "analyst_learnings.json",
            pack["pack_id"],
            run_id,
            {**winner, "primary_metric": primary},
            baseline_row,
            engine_mode,
            since_go_live,
        )
        print("appended analyst_learnings.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())