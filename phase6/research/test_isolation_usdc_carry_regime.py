"""USDC carry + regime optimizer isolation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.usdc_carry_backtest import usdc_carry_metrics, usdc_window_total_return_pct
from phase6.research.regime_strategy_optimizer import pick_optimal_strategy


def test_usdc_carry_window() -> None:
    dr = {"start": "2026-01-01", "end": "2026-03-31"}
    m = usdc_carry_metrics(dr, apy_pct=3.5)
    assert m["max_drawdown_pct"] == 0.0
    assert m["total_trades"] == 0
    assert 0 < m["total_return_pct"] < 1.0  # ~89 days at 3.5%
    assert abs(m["annualized_return_pct"] - 3.5) < 0.1


def test_pick_optimal_usdc_wins() -> None:
    dr = {"start": "2026-01-01", "end": "2026-03-31"}
    rows = [
        {
            "id": "rebalance_7d",
            "metrics": {"total_return_pct": -0.12, "max_drawdown_pct": 1.0},
        },
        {
            "id": "usdc_hold",
            "metrics": usdc_carry_metrics(dr),
        },
    ]
    opt = pick_optimal_strategy(rows, dr)
    assert opt["optimal_strategy_id"] == "usdc_hold"
    assert opt["optimal_is_usdc"] is True
    assert opt["alt_beats_usdc_carry"] is False


def test_pick_optimal_alt_wins() -> None:
    dr = {"start": "2025-10-01", "end": "2025-12-31"}
    usdc_m = usdc_carry_metrics(dr)
    rows = [
        {
            "id": "baseline_7d",
            "metrics": {"total_return_pct": 1.96, "max_drawdown_pct": 6.0},
        },
        {"id": "usdc_hold", "metrics": usdc_m},
    ]
    opt = pick_optimal_strategy(rows, dr)
    assert opt["optimal_strategy_id"] == "baseline_7d"
    assert opt["alt_beats_usdc_carry"] is True


def main() -> int:
    test_usdc_carry_window()
    test_pick_optimal_usdc_wins()
    test_pick_optimal_alt_wins()
    print("usdc_carry + regime optimizer isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())