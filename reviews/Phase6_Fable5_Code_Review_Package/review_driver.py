#!/usr/bin/env python3
"""
Phase 6 Fable 5 Review Driver
Helps prepare clean, labelled file bundles for a targeted expensive-model review.

Usage (on this machine or in the review chat):
  python3 reviews/Phase6_Fable5_Code_Review_Package/review_driver.py --batch 1
  python3 ... --batch 2 --output /tmp/batch2.txt
  python3 ... --list-batches
  python3 ... --manifest   # show the tier list again

It prints (or writes) files with clear === headers so you can copy-paste directly
into a Fable 5 (or Claude/Grok high-context) conversation with low confusion risk.
"""

import argparse
import os
from pathlib import Path

REPO_ROOT = Path("/home/brad/projects/crypto-trading-bot")
PKG = REPO_ROOT / "reviews/Phase6_Fable5_Code_Review_Package"

# Exact tiers (kept in sync with MANIFEST.md)
TIERS = {
    0: [
        "phase6/core/phase6_runner.py",
        "phase6/scripts/deploy_capital.py",
        "phase6/core/signal_generator.py",
    ],
    1: [
        "phase6/core/stop_loss_manager.py",
        "phase6/core/stop_loss_coordinator.py",
        "phase6/core/rebalancing/hybrid_rebalancer.py",
        "phase6/core/order_executor.py",
        "phase6/core/exchange_client.py",
        "phase6/core/risk/atr_calculator.py",
        "phase6/core/risk/correlation_circuit_breaker.py",
        "phase6/core/risk/regime_detector.py",
        "phase6/core/risk/rolling_correlation.py",
        "phase6/core/risk/test_shadow_integration.py",
    ],
    2: [
        "phase6/core/sentiment_scorer.py",
        "phase6/core/sentiment/sentiment_scorer.py",
        "run_full_sentiment_v3.py",
        "phase6/scripts/generate_trading_intelligence_report.py",
        "phase6/core/price_history_manager.py",
        "phase6/core/sentiment/direct_reddit_fetcher.py",
        "phase6/core/sentiment/fetch_reddit_sentiment.py",
        "phase6/core/sentiment/fetch_x_sentiment.py",
        "phase6/core/sentiment/praw_reddit_fetcher.py",
    ],
    3: [
        "phase6/core/allocation_engine.py",
        "phase6/core/allocation/enhanced_allocation_engine.py",
        "phase6/scripts/capital_deployment_runner.py",
        "phase6/scripts/real_capital_event_monitor.py",
        "phase6/core/rebalance_logger.py",
        "phase6/core/trade_ledger.py",
    ],
    4: [
        "phase6/core/config_loader.py",
        "phase6/core/error_notifier.py",
        "phase6/core/performance_api.py",
        "phase6/core/performance_calculator.py",
        "serve_live_8501.py",
        "phase6/scripts/phase6_live_harness.py",
        "scripts/monitor_canonical_sentiment.py",
        "phase6/core/live_portfolio_manager.py",
    ],
    5: [
        "phase6/backtest/backtest_engine.py",
        "phase6/backtest/data_loader.py",
        "phase6/backtest/metrics.py",
        "phase6/backtest/pair_selector.py",
        "phase6/backtest/report.py",
        "phase6/backtest/run_comparison.py",
        "phase6/backtest/experiments/recovery_backtest.py",
        "scripts/validate_canonical_sentiment_paper.py",
        "phase6/scripts/phase6_live_harness.py",
    ],
    6: [
        "docs/MASTER_TASK_TRACKING.md",
        "docs/PHASE6.md",
        "docs/PHASE_6_REBALANCING.md",
        "docs/AGENTS.md",
        "phase6/README.md",
    ],
}

def read_file_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR READING {p}: {e}"

def emit_batch(batch_num: int, outfile: Path = None):
    files = TIERS.get(batch_num, [])
    if not files:
        print(f"No files registered for Batch {batch_num}")
        return

    lines = []
    lines.append(f"=== PHASE 6 FABLE 5 REVIEW — BATCH {batch_num} (Tier {batch_num}) ===\n")
    lines.append(f"Repo root: {REPO_ROOT}")
    lines.append("Constraints reminder (real data only, Fresh Start = bootstrap-only, sticky holdings, sentiment aging, withdrawal reserve, Code Isolation Testing, durable tracking).\n")

    for rel in files:
        full = REPO_ROOT / rel
        content = read_file_safe(full)
        header = f"\n\n=== FILE: {rel} (size ~{len(content)} chars) ===\n"
        lines.append(header)
        lines.append(content)

    output = "\n".join(lines)
    if outfile:
        outfile.write_text(output, encoding="utf-8")
        print(f"Wrote Batch {batch_num} → {outfile}")
    else:
        print(output)

def list_batches():
    print("Registered batches / tiers:")
    for b, files in sorted(TIERS.items()):
        print(f"  Batch {b}: {len(files)} files")
        for f in files[:3]:
            print(f"    - {f}")
        if len(files) > 3:
            print(f"    ... +{len(files)-3} more")

def show_manifest():
    print((PKG / "MANIFEST.md").read_text())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, help="Emit a specific batch (0-6)")
    ap.add_argument("--output", type=Path, help="Write to file instead of stdout")
    ap.add_argument("--list-batches", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    args = ap.parse_args()

    if args.list_batches:
        list_batches()
    elif args.manifest:
        show_manifest()
    elif args.batch is not None:
        emit_batch(args.batch, args.output)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
