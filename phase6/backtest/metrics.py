"""
Metrics Collector for Backtest Results

Collects performance and activity metrics for comparison reports.
"""

from typing import List, Dict

from phase6.backtest.backtest_engine import BacktestResult


def calculate_sharpe(equity_curve: List[float], risk_free_rate: float = 0.0) -> float:
    if len(equity_curve) < 2:
        return 0.0
    returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] 
               for i in range(1, len(equity_curve))]
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std = variance ** 0.5
    if std == 0:
        return 0.0
    return (mean_ret - risk_free_rate) / std * (252 ** 0.5)


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def collect_metrics(result: BacktestResult) -> Dict:
    """Extract key metrics from a BacktestResult."""
    return {
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 3),
        "total_trades": result.total_trades,
        "rebalance_count": result.rebalance_count,
        "avg_pairs_held": round(result.avg_pairs_held, 2),
    }


if __name__ == "__main__":
    print("Metrics module initialized (Phase 1)")