#!/usr/bin/env python3
"""
Phase 6 Trade Ledger
Persistent trade logging (JSONL + daily CSV)
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional


class TradeLedger:
    """Handles persistent trade logging for Phase 6."""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).parent.parent.parent
        self.trades_dir = self.base_dir / "trades"
        self.trades_dir.mkdir(parents=True, exist_ok=True)

        # Main JSONL log (append-only)
        self.jsonl_path = self.trades_dir / "phase6_trades.jsonl"

        # Daily CSV (rotated)
        self.current_csv_date = None
        self.csv_path = None

    def _get_daily_csv_path(self) -> Path:
        """Get (or create) today's CSV file."""
        today = date.today().isoformat()
        if today != self.current_csv_date:
            self.current_csv_date = today
            self.csv_path = self.trades_dir / f"phase6_trades_{today}.csv"
            # Write header if new file
            if not self.csv_path.exists():
                header = "timestamp,pair,side,qty,entry_price,exit_price,pnl,pnl_pct,signal_source\n"
                self.csv_path.write_text(header)
        return self.csv_path

    def log_trade(self, trade: Dict[str, Any]) -> None:
        """
        Log a completed trade.

        Expected keys:
            pair, side (BUY/SELL), qty, entry_price, exit_price,
            pnl, pnl_pct, signal_source (optional)
        """
        # Add timestamp if missing
        if "timestamp" not in trade:
            trade["timestamp"] = datetime.utcnow().isoformat()

        # Write to JSONL (append)
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(trade) + "\n")

        # Write to daily CSV
        csv_path = self._get_daily_csv_path()
        line = (
            f"{trade.get('timestamp')},"
            f"{trade.get('pair')},"
            f"{trade.get('side')},"
            f"{trade.get('qty')},"
            f"{trade.get('entry_price')},"
            f"{trade.get('exit_price')},"
            f"{trade.get('pnl')},"
            f"{trade.get('pnl_pct')},"
            f"{trade.get('signal_source', 'unknown')}\n"
        )
        with open(csv_path, "a") as f:
            f.write(line)

    def get_recent_trades(self, limit: int = 20) -> list:
        """Return the most recent trades from the JSONL file."""
        if not self.jsonl_path.exists():
            return []

        trades = []
        with open(self.jsonl_path, "r") as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    trades.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return trades


if __name__ == "__main__":
    # Quick test
    ledger = TradeLedger()
    test_trade = {
        "pair": "BTC-USD",
        "side": "BUY",
        "qty": 0.001,
        "entry_price": 65000.0,
        "exit_price": None,
        "pnl": 0,
        "pnl_pct": 0,
        "signal_source": "rsi"
    }
    ledger.log_trade(test_trade)
    print(f"Trade logged to {ledger.jsonl_path}")
    print("Recent trades:", ledger.get_recent_trades(5))
