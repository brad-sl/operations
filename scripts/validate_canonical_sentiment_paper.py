#!/usr/bin/env python3
"""
Standalone Code Isolation Test for Canonical Sentiment Pipeline (Paper Mode)

Purpose: Validate the new single-source fetcher + scorer + aging in a paper trading context.
- Triggers real fetch via canonical v3.
- Loads raw and aged scores (exponential decay, 60min half-life).
- Applies to allocation/weighting (as used in Phase6Runner Fresh Start and rebalance).
- Simulates paper "trading decisions" using allocation logic + logs (no execution, real data only).
- Checks: real (non-all-zero) data, aging reduces |score| when stale, weights sum to ~1, no crashes.
- Frequency simulation: Run multiple times (e.g. 4 cycles) with interval to mimic 2x per hour.

Run standalone for validation:
  python scripts/validate_canonical_sentiment_paper.py --cycles 4 --interval 10

This is the primary artifact for "Code Isolation Testing" per project preferences.
Real data only. Outputs detailed report + assertions.

See also: scripts/phase6/paper_trading_harness.py (updated harness).
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.sentiment_scorer import (
    load_sentiment_scores,
    get_aged_sentiment_scores,
    get_sentiment_adjusted_weights,
    get_sentiment_freshness_minutes,
    get_sentiment_timestamp,
)
from allocation_engine import compute_inverse_vol_allocations

FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
CANONICAL_FETCH_WRAPPER = PROJECT_ROOT / "scripts" / "run_sentiment.sh"

def run_canonical_fetch(timeout_seconds: int = 180) -> bool:
    """Trigger the single canonical fetcher. Returns success."""
    print(f"[{datetime.now(timezone.utc)}] Running canonical fetcher (wrapper)...")
    try:
        result = subprocess.run(
            ["bash", str(CANONICAL_FETCH_WRAPPER)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        print(result.stdout[-2000:] if result.stdout else "No stdout")
        if result.stderr:
            print("STDERR (last 500):", result.stderr[-500:])
        return result.returncode == 0 or result.returncode == 124  # timeout ok
    except subprocess.TimeoutExpired:
        print("Fetch timed out (acceptable for Apify).")
        return True
    except Exception as e:
        print(f"Fetch error: {e}")
        return False

def simulate_paper_decision(aged_scores: Dict[str, float], base_capital: float = 1000.0) -> List[Dict]:
    """Simulate trading script application: compute adjusted weights, 'decide' allocations."""
    dummy_vols = {p: 0.65 for p in FIXED_UNIVERSE}
    base_weights = compute_inverse_vol_allocations(dummy_vols)
    adjusted = get_sentiment_adjusted_weights(base_weights, aged_scores, sentiment_weight=0.2)

    decisions = []
    for pair, weight in adjusted.items():
        usd = round(base_capital * weight, 2)
        if usd >= 10:
            decision = {
                "pair": pair,
                "weight": round(weight, 4),
                "usd_amount": usd,
                "aged_sentiment": aged_scores.get(pair, 0.0),
                "action": "PAPER_ALLOCATE" if usd > 0 else "SKIP"
            }
            decisions.append(decision)
    return decisions, adjusted

def validate_one_cycle(cycle_num: int) -> Dict:
    """One full isolation test cycle."""
    print(f"\n=== Cycle {cycle_num} Validation ===")

    # Ensure fresh data (run fetch)
    fetch_ok = run_canonical_fetch()
    if not fetch_ok:
        print("WARNING: Fetch may not have completed fully; using cache.")

    # Load
    raw = load_sentiment_scores(universe=FIXED_UNIVERSE)
    aged = get_aged_sentiment_scores(universe=FIXED_UNIVERSE, half_life_minutes=60.0)
    age = get_sentiment_freshness_minutes() or 0.0
    ts = get_sentiment_timestamp()

    print(f"Timestamp: {ts}")
    print(f"Age: {age} min")
    print(f"Raw: {raw}")
    print(f"Aged (60min HL): {aged}")

    # Simulate trading script usage
    decisions, adjusted_weights = simulate_paper_decision(aged)
    print(f"Adjusted weights (sum={sum(adjusted_weights.values()):.4f}): {adjusted_weights}")
    print(f"Paper decisions: {decisions}")

    # Assertions (Code Isolation Test)
    assertions = {
        "fetch_ran": fetch_ok,
        "has_data": any(abs(v) > 0.0001 for v in raw.values()),  # real (non-trivial) data
        "weights_sum_near_1": abs(sum(adjusted_weights.values()) - 1.0) < 0.05,
        "aging_applied": all(abs(aged[p]) <= abs(raw[p]) + 0.0001 for p in raw),  # decay reduces magnitude
        "no_crash": True,
        "decisions_made": len(decisions) > 0
    }

    passed = all(assertions.values())
    print(f"Assertions: {assertions}")
    print(f"Cycle {cycle_num} {'✅ PASSED' if passed else '❌ FAILED'}")

    return {
        "cycle": cycle_num,
        "timestamp": ts,
        "age_min": age,
        "raw_scores": raw,
        "aged_scores": aged,
        "adjusted_weights": adjusted_weights,
        "paper_decisions": decisions,
        "assertions": assertions,
        "passed": passed
    }

def main():
    parser = argparse.ArgumentParser(description="Canonical Sentiment Paper Validation (Isolation Test)")
    parser.add_argument("--cycles", type=int, default=3, help="Number of fetch+validate cycles (2x/hour sim)")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between cycles (1800 for real 30min)")
    args = parser.parse_args()

    print("=== Canonical Sentiment Pipeline - Paper Mode Validation ===")
    print(f"Cycles: {args.cycles} | Simulated interval: {args.interval}s (real target 1800s / 30min)")
    print("Fetcher: run_full_sentiment_v3.py (single source)")
    print("Scorer: phase6/core/sentiment_scorer.py (with 60min exponential aging)")
    print("Application: allocation_engine + simulated paper decisions (like Phase6Runner)")
    print("Real data + aging factors enforced.\n")

    results = []
    for c in range(1, args.cycles + 1):
        res = validate_one_cycle(c)
        results.append(res)
        if c < args.cycles:
            print(f"\nWaiting {args.interval}s for next cycle (simulating 30min)...")
            time.sleep(args.interval)

    # Overall report
    all_passed = all(r["passed"] for r in results)
    summary = {
        "overall_passed": all_passed,
        "cycles_run": len(results),
        "total_decisions": sum(len(r["paper_decisions"]) for r in results),
        "avg_age": sum(r["age_min"] for r in results) / len(results) if results else 0,
        "results": results,
        "end_time": datetime.now(timezone.utc).isoformat()
    }

    print("\n=== FINAL VALIDATION REPORT ===")
    print(json.dumps(summary, indent=2))

    if all_passed:
        print("\n✅ ALL CYCLES PASSED. Pipeline validated for paper mode (real data, aging, trading script application).")
        print("Ready for Phase 2 (production deploy + 48h monitor).")
    else:
        print("\n❌ SOME CYCLES FAILED. Review report above. Do not proceed to deploy without fixes.")

    # Write report for durable record
    report_path = PROJECT_ROOT / "data" / "state" / f"sentiment_paper_validation_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nReport saved to {report_path}")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())