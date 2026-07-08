# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Performance Calculator
Calculates multi-period P&L from trade history.
Designed to work with synthetic/backtest data for safe testing.
Never used directly against live trading accounts.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Trade:
    timestamp: datetime
    pair: str
    side: str          # BUY / SELL
    qty: float
    price: float
    usd_value: float


class PerformanceCalculator:
    def __init__(self, trades: List[Trade]):
        self.trades = sorted(trades, key=lambda t: t.timestamp)
        self.realized_pnl = 0.0
        self._precompute()

    def _precompute(self):
        """Basic pre-computation for realized P&L (FIFO matching)."""
        buys = {}
        realized = 0.0

        for trade in self.trades:
            if trade.side.upper() == "BUY":
                if trade.pair not in buys:
                    buys[trade.pair] = []
                buys[trade.pair].append(trade)
            elif trade.side.upper() == "SELL":
                if trade.pair in buys and buys[trade.pair]:
                    buy = buys[trade.pair].pop(0)
                    realized += (trade.price - buy.price) * trade.qty
        self.realized_pnl = realized

    def get_pnl_for_period(self, days: int) -> Dict[str, Any]:
        """Calculate P&L for the last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        period_trades = [t for t in self.trades if t.timestamp >= cutoff]

        if not period_trades:
            return {"period_days": days, "pnl": 0.0, "trades": 0}

        # Simple P&L approximation for testing
        pnl = sum(
            (t.price * t.qty) if t.side.upper() == "SELL" else -(t.price * t.qty)
            for t in period_trades
        )

        return {
            "period_days": days,
            "pnl": round(pnl, 2),
            "trades": len(period_trades),
            "start_date": cutoff.isoformat(),
        }

    def get_all_periods(self) -> Dict[str, Any]:
        """Return P&L for standard periods."""
        return {
            "1d": self.get_pnl_for_period(1),
            "7d": self.get_pnl_for_period(7),
            "30d": self.get_pnl_for_period(30),
            "90d": self.get_pnl_for_period(90),
            "365d": self.get_pnl_for_period(365),
            "realized_total": round(self.realized_pnl, 2),
        }
