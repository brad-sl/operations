#!/usr/bin/env python3
"""
Phase 6 Basic Anomaly Detector
- Drawdown monitoring
- Repeated failure detection
"""

from typing import List, Dict, Any
from collections import defaultdict


class AnomalyDetector:
    """Lightweight anomaly detection for Phase 6 trading."""

    def __init__(self, max_drawdown_pct: float = 5.0, max_failures: int = 3):
        self.max_drawdown_pct = max_drawdown_pct
        self.max_failures = max_failures
        self.trade_history: List[Dict] = []
        self.failures_by_pair = defaultdict(int)
        self.peak_equity = 0.0
        self.current_equity = 0.0

    def update_equity(self, equity: float):
        """Track equity for drawdown calculation."""
        self.current_equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity

    def record_trade(self, trade: Dict[str, Any]):
        """Record a trade and check for anomalies."""
        self.trade_history.append(trade)

        if trade.get("pnl", 0) < 0:
            self.failures_by_pair[trade.get("pair")] += 1
        else:
            self.failures_by_pair[trade.get("pair")] = 0  # reset on success

    def check_drawdown(self) -> bool:
        """Return True if drawdown exceeds threshold."""
        if self.peak_equity == 0:
            return False
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100
        return drawdown >= self.max_drawdown_pct

    def check_repeated_failures(self) -> List[str]:
        """Return list of pairs with too many consecutive failures."""
        bad_pairs = []
        for pair, count in self.failures_by_pair.items():
            if count >= self.max_failures:
                bad_pairs.append(pair)
        return bad_pairs

    def get_alerts(self) -> List[str]:
        """Return list of current anomaly alerts."""
        alerts = []
        if self.check_drawdown():
            alerts.append(f"⚠️ Drawdown exceeded {self.max_drawdown_pct}%")
        bad = self.check_repeated_failures()
        if bad:
            alerts.append(f"⚠️ Repeated failures on: {', '.join(bad)}")
        return alerts


if __name__ == "__main__":
    detector = AnomalyDetector()
    detector.update_equity(1000)
    detector.record_trade({"pair": "BTC-USD", "pnl": -50})
    detector.record_trade({"pair": "BTC-USD", "pnl": -30})
    print(detector.get_alerts())
