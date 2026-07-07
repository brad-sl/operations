"""
ANALYST-OPT R3: Promotion gates for scenario winners → proposals.

Shadow-trial proposals only; live config changes still require MASTER + user approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


MAX_DD_SLACK_PP = 5.0
MIN_PRIMARY_DELTA_SHARPE = 0.0  # must strictly beat baseline on primary when sharpe


@dataclass
class GateResult:
    passed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    winner_id: Optional[str] = None
    baseline_id: Optional[str] = None


def _row_by_id(scenarios: List[dict], sid: str) -> Optional[dict]:
    return next((s for s in scenarios if s.get("id") == sid), None)


def _metric(row: dict, key: str) -> Optional[float]:
    if not row:
        return None
    v = (row.get("metrics") or {}).get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate_promotion_gates(leaderboard: Dict[str, Any]) -> GateResult:
    """
    Gates for ingesting an optimization winner as a shadow-trial proposal.
    """
    result = GateResult(passed=False)
    primary = leaderboard.get("primary_metric", "sharpe_ratio")
    baseline_id = leaderboard.get("baseline_scenario_id")
    ranking = leaderboard.get("ranking") or []
    scenarios = leaderboard.get("scenarios") or []
    engine_mode = leaderboard.get("engine_mode", "")

    if not ranking or not baseline_id:
        result.failures.append("missing ranking or baseline_scenario_id")
        return result

    winner_id = ranking[0]
    winner = _row_by_id(scenarios, winner_id)
    baseline = _row_by_id(scenarios, baseline_id)
    result.winner_id = winner_id
    result.baseline_id = baseline_id

    if engine_mode != "arch4":
        result.failures.append(f"engine_mode={engine_mode} (Path B arch4 required for promotion proposals)")

    if not winner or not baseline:
        result.failures.append("winner or baseline row missing")
        return result

    if (winner.get("metrics") or {}).get("simulation_skipped"):
        result.failures.append(f"winner {winner_id} simulation_skipped")

    w_primary = _metric(winner, primary)
    b_primary = _metric(baseline, primary)
    if w_primary is None or b_primary is None:
        result.failures.append(f"primary metric {primary} missing on winner or baseline")
    elif primary == "max_drawdown_pct":
        if w_primary > b_primary + MAX_DD_SLACK_PP:
            result.failures.append(
                f"max_dd {w_primary}% worse than baseline {b_primary}% + slack {MAX_DD_SLACK_PP}pp"
            )
    else:
        if w_primary <= b_primary + MIN_PRIMARY_DELTA_SHARPE:
            result.failures.append(
                f"{primary} winner={w_primary} does not beat baseline={b_primary}"
            )

    w_dd = _metric(winner, "max_drawdown_pct")
    b_dd = _metric(baseline, "max_drawdown_pct")
    if w_dd is not None and b_dd is not None and w_dd > b_dd + MAX_DD_SLACK_PP:
        result.failures.append(f"max_drawdown_pct {w_dd} > baseline {b_dd} + slack")

    w_sharpe = _metric(winner, "sharpe_ratio")
    if w_sharpe is not None and w_sharpe < 0:
        result.failures.append(f"winner sharpe {w_sharpe} < 0 (no promotion on losing risk-adjusted profile)")

    prod = leaderboard.get("production") or {}
    cov = prod.get("coverage")
    if cov and cov != "none":
        comparisons = leaderboard.get("vs_production") or []
        win_cmp = next((c for c in comparisons if c.get("scenario_id") == winner_id), None)
        if win_cmp and win_cmp.get("beats_production") is False:
            result.failures.append("winner does not beat production on overlap window")
    else:
        result.warnings.append(
            "no production calendar overlap — regime scorecard (bear/flat) required before live knobs"
        )

    # Documented Path B gaps — warn, do not auto-live
    result.warnings.append(
        "Path B sentiment/RSI proxy vs live cache — see BACKTEST_LIVE_GAP_MATRIX.md"
    )

    # Regime scorecard (bear/flat stress) when scorecard file exists
    scorecard_path = Path(__file__).resolve().parents[2] / "data/state/analyst_regime_scorecard_latest.json"
    if scorecard_path.exists():
        import json

        with open(scorecard_path) as f:
            sc = json.load(f)
        regimes = sc.get("regimes") or []
        stress = [r for r in regimes if r.get("regime") in ("bear", "flat")]
        stress_pass = sum(1 for r in stress if r.get("beats_baseline"))
        if stress_pass < 1:
            result.failures.append(
                "regime scorecard: no bear/flat window beats baseline (bull-only risk)"
            )
        elif stress_pass < 2 and len(stress) >= 2:
            result.warnings.append("regime scorecard: only one of bear/flat beats baseline")
    else:
        result.warnings.append(
            "run run_regime_scorecard.py before promotion — see REGIME_SCENARIO_PROCEDURE.md"
        )

    result.passed = len(result.failures) == 0
    return result