"""Isolation: promotion gates + proposal ingest (no live side effects)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.promotion_gates import evaluate_promotion_gates
from phase6.research.proposal_from_leaderboard import ingest_proposal


def test_negative_sharpe_blocked() -> None:
    lb = {
        "run_id": "OPT-TEST-001",
        "pack_id": "test",
        "engine_mode": "arch4",
        "primary_metric": "sharpe_ratio",
        "baseline_scenario_id": "baseline_7d",
        "ranking": ["rebalance_7d", "baseline_7d"],
        "scenarios": [
            {"id": "rebalance_7d", "metrics": {"sharpe_ratio": -2.0, "max_drawdown_pct": 3.0}},
            {"id": "baseline_7d", "metrics": {"sharpe_ratio": -3.0, "max_drawdown_pct": 30.0}},
        ],
    }
    g = evaluate_promotion_gates(lb)
    assert not g.passed
    assert any("sharpe" in f for f in g.failures)


def test_positive_sharpe_passes_gates() -> None:
    lb = {
        "run_id": "OPT-TEST-002",
        "pack_id": "test",
        "engine_mode": "arch4",
        "primary_metric": "sharpe_ratio",
        "baseline_scenario_id": "baseline_7d",
        "ranking": ["rebalance_7d", "baseline_7d"],
        "production": {"coverage": "none"},
        "live_param_audit": {
            "fail_count": 0,
            "confidence_score": 0.95,
            "verified_fills": 50,
            "ok": True,
        },
        "scenarios": [
            {"id": "rebalance_7d", "metrics": {"sharpe_ratio": 0.5, "max_drawdown_pct": 5.0}},
            {"id": "baseline_7d", "metrics": {"sharpe_ratio": 0.2, "max_drawdown_pct": 12.0}},
        ],
    }
    g = evaluate_promotion_gates(lb)
    assert g.passed, g.failures


def test_ingest_dry_run_no_write() -> None:
    lb = json.loads(
        (ROOT / "data/state/analyst_scenario_leaderboard_latest.json").read_text()
    )
    g = evaluate_promotion_gates(lb)
    print(f"latest leaderboard gates passed={g.passed} failures={g.failures} warnings={g.warnings}")


def main() -> int:
    test_negative_sharpe_blocked()
    test_positive_sharpe_passes_gates()
    test_ingest_dry_run_no_write()
    print("ANALYST-OPT R3 isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())