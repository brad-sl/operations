#!/usr/bin/env python3
"""
Rebalance Event Logger

Lightweight, append-only logging for rebalance events.

Design goals for future scale:
- One JSONL file per portfolio_id (avoids giant single files)
- Minimal fields (easy to extend or migrate to DB later)
- Fast appends, efficient tail reads for dashboards
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

REBALANCE_LOG_DIR = Path("/home/brad/projects/crypto-trading-bot/data/state/rebalance_history")


def get_log_path(portfolio_id: str = "default") -> Path:
    """Return the path to the JSONL file for a given portfolio."""
    REBALANCE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return REBALANCE_LOG_DIR / f"{portfolio_id}.jsonl"


def log_rebalance_event(
    event: Dict[str, Any],
    portfolio_id: str = "default"
) -> None:
    """
    Append a rebalance event to the portfolio's log.

    Expected minimal fields:
        timestamp, pairs_before, pairs_after, capital_deployed_usd,
        new_pairs, reason, cooldown_blocked, mode
    """
    if "timestamp" not in event:
        event["timestamp"] = datetime.now(timezone.utc).isoformat()

    event["portfolio_id"] = portfolio_id

    log_path = get_log_path(portfolio_id)
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")


def get_recent_rebalances(
    portfolio_id: str = "default",
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Return the most recent rebalance events (tail read)."""
    log_path = get_log_path(portfolio_id)
    if not log_path.exists():
        return []

    events = []
    with open(log_path, "r") as f:
        lines = f.readlines()[-limit:]
        for line in lines:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return events[::-1]  # most recent first


if __name__ == "__main__":
    # Quick test
    test_event = {
        "pairs_before": 2,
        "pairs_after": 5,
        "capital_deployed_usd": 487.50,
        "new_pairs": ["ADA-USD", "DOGE-USD", "AVAX-USD"],
        "reason": "emergency_recovery",
        "cooldown_blocked": ["XRP-USD"],
        "mode": "live"
    }
    log_rebalance_event(test_event)
    print("Logged test event")
    print(get_recent_rebalances(limit=5))