#!/usr/bin/env python3
"""
Simple comparison runner for Phase 6 backtest harness (Phase 1)

Runs Baseline mode and prints a basic report.
"""

from datetime import date
from phase6.backtest.backtest_engine import BacktestConfig, BacktestEngine
from phase6.backtest.metrics import collect_metrics, calculate_sharpe, calculate_max_drawdown
from phase6.backtest.report import generate_comparison_report


def main():
    print("=== Phase 6 Backtest Harness (Phase 2) ===\n")

    # Baseline configuration
    baseline_cfg = BacktestConfig(
        start_date=date(2025, 4, 20),
        end_date=date(2026, 4, 19),
        initial_capital=1000.0,
        enable_pair_expansion=False,
        rebalance_frequency_days=7
    )

    # Expanded configuration
    expanded_cfg = BacktestConfig(
        start_date=date(2025, 4, 20),
        end_date=date(2026, 4, 19),
        initial_capital=1000.0,
        enable_pair_expansion=True,
        candidate_universe=["AVAX-USD", "LINK-USD", "NEAR-USD", "ARB-USD"],
        rebalance_frequency_days=7
    )

    print("--- Running Baseline ---")
    engine = BacktestEngine(baseline_cfg)
    result = engine.run()

    # Enhance metrics
    result.max_drawdown_pct = calculate_max_drawdown(result.equity_curve)
    result.sharpe_ratio = calculate_sharpe(result.equity_curve)

    baseline_metrics = collect_metrics(result)

    print("Baseline Run Metrics:")
    for k, v in baseline_metrics.items():
        print(f"  {k}: {v}")

    print("\n--- Running Expanded ---")
    engine2 = BacktestEngine(expanded_cfg)
    result2 = engine2.run()
    result2.max_drawdown_pct = calculate_max_drawdown(result2.equity_curve)
    result2.sharpe_ratio = calculate_sharpe(result2.equity_curve)
    expanded_metrics = collect_metrics(result2)

    print(f"\nExpanded trades: {len(result2.trades)}")
    for t in result2.trades:
        print(f"  {t}")

    print("\n" + generate_comparison_report(baseline_metrics, expanded_metrics))


if __name__ == "__main__":
    main()