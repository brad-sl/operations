#!/usr/bin/env python3
"""
Trading Intelligence Report Generator

Generates a human-readable trading intelligence report with:
- RSI values + interpretation labels
- Sentiment scores + interpretation labels
- Portfolio snapshot

Designed to be called by cron jobs (e.g. twice-daily-trading-intelligence)
and supports future multi-trader / multi-account usage.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.sentiment_scorer import (
    load_sentiment_scores,
    format_rsi_for_report,
    format_sentiment_for_report,
)

# Paths
PHASE6_ROOT = Path("/home/brad/projects/crypto-trading-bot")
LIVE_STATE = PHASE6_ROOT / "data" / "state" / "phase6_live_state.json"


def load_live_state():
    if not LIVE_STATE.exists():
        return {}
    try:
        with open(LIVE_STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def generate_report() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    state = load_live_state()
    rsi_values = state.get("rsi", {})
    sentiment_scores = load_sentiment_scores()

    # Portfolio snapshot
    total = state.get("total_usd", 0)
    cash = state.get("cash_usd", 0)
    holdings_value = state.get("total_holdings_value", 0)
    positions = state.get("positions", [])

    # Build report
    lines = [
        "📊 Trading Intelligence Report",
        f"🕒 Generated: {now}",
        "",
        "📉 RSI Values:",
        format_rsi_for_report(rsi_values) if rsi_values else "No RSI data available",
        "",
        "💬 Sentiment:",
        format_sentiment_for_report(sentiment_scores) if sentiment_scores else "No sentiment data available",
        "",
        "💼 Portfolio Snapshot:",
        f"Total: ${total:,.2f} | Cash: ${cash:,.2f} | Holdings: ${holdings_value:,.2f}",
        f"Active Positions: {len(positions)}",
        "",
        "No rebalance signals generated." if not positions else "",
    ]

    return "\n".join(lines).strip()


def main():
    report = generate_report()
    print(report)


if __name__ == "__main__":
    main()