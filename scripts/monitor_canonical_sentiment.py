#!/usr/bin/env python3
"""
Production Monitor for Canonical Sentiment (48h deployment monitoring)

Checks:
- Freshness of the single canonical cache
- Loads aged scores
- Runs quick intelligence-like output
- Logs warnings if stale (>180 min)
- Can be run by cron every 30min

Deliver output to Telegram via cron delivery or direct.

Usage in cron: python scripts/monitor_canonical_sentiment.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import json

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.sentiment_scorer import (
    get_aged_sentiment_scores,
    get_sentiment_freshness_minutes,
    get_sentiment_timestamp,
    load_sentiment_scores,
    format_sentiment_for_report,
)
from phase6.scripts.generate_trading_intelligence_report import main as run_report  # reuse if possible, or inline

def main():
    print(f"=== Canonical Sentiment Production Monitor - {datetime.now(timezone.utc).isoformat()} ===")

    ts = get_sentiment_timestamp()
    age = get_sentiment_freshness_minutes()
    raw = load_sentiment_scores()
    aged = get_aged_sentiment_scores(half_life_minutes=60.0)

    print(f"Timestamp: {ts}")
    print(f"Age: {age} minutes")
    print(f"Raw scores: {raw}")
    print(f"Aged scores (60min HL): {aged}")
    print(f"Formatted (aged): {format_sentiment_for_report(aged)}")

    STALE_THRESHOLD_MIN = 180
    if age is not None and age > STALE_THRESHOLD_MIN:
        msg = f"⚠️ STALE SENTIMENT: Age {age}min > {STALE_THRESHOLD_MIN}min threshold. Trigger refresh or use conservative mode."
        print(msg)
        # In full cron, this would trigger alert
    else:
        print("✅ Sentiment freshness within threshold.")

    # Optional: trigger the full report for monitoring (it will use canonical)
    print("\n--- Quick Intelligence Report (canonical) ---")
    try:
        # Call the report generator function if it supports non-main, else just note
        print("(Full report would run here via cron; see twice-daily-trading-intelligence)")
    except Exception as e:
        print(f"Report note: {e}")

    # Write monitor state for dashboard or logs
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "age_min": age,
        "ts": ts,
        "raw": raw,
        "aged": aged,
        "stale": age > STALE_THRESHOLD_MIN if age else False
    }
    state_path = PROJECT_ROOT / "data" / "state" / "sentiment_monitor_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\nMonitor state written to {state_path}")

    return 0

if __name__ == "__main__":
    sys.exit(main())