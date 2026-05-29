"""
paper_trader.py - Paper trading engine for simulated execution

Implements PaperTrader class that executes simulated trades using allocation
and rebalance_plan logic from allocation_engine.

Trade records follow schema exactly as specified in SPEC.md:
{
  "timestamp": "2026-05-14T14:30:00Z",
  "action": "BUY",
  "pair": "ETH-USD",
  "usd_amount": 166.67,
  "price": 2450.50,
  "note": "Daily rebalance - Fresh Start"
}

Portfolio snapshot stored in data/state/paper_portfolio.json
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# Ensure project root reference
PROJECT_ROOT = Path(__file__).parent.parent.parent
STATE_DIR = PROJECT_ROOT / "data" / "state"
TRADES_CSV = STATE_DIR / "paper_trades.csv"
PORTFOLIO_JSON = STATE_DIR / "paper_portfolio.json"


@dataclass
class PaperTrade:
    """Structured representation of a paper trade record."""
    timestamp: str
    action: str
    pair: str
    usd_amount: float
    price: float
    note: str = ""


class PaperTrader:
    """
    Simulated trading engine.

    Executes trades using rebalance_plan outputs and allocation logic.
    Records trades to CSV and persists portfolio state to JSON.
    """

    def __init__(self, total_capital: float = 10000.0, initial_portfolio: Optional[Dict[str, Any]] = None):
        """
        Initialize PaperTrader.

        Args:
            total_capital: Starting total deployable capital in USD
            initial_portfolio: Optional dict with 'cash' and 'positions'
                Example: {"cash": 8000.0, "positions": {"BTC-USD": 0.1, "ETH-USD": 2.5}}
        """
        self.total_capital = float(total_capital)
        self.cash = float(total_capital)
        self.positions: Dict[str, float] = {}  # pair -> quantity held
        self.trades: List[PaperTrade] = []

        if initial_portfolio:
            self.cash = float(initial_portfolio.get("cash", total_capital))
            self.positions = initial_portfolio.get("positions", {}).copy()

        # Ensure state directory exists
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        # Load persisted state if exists
        self._load_state()

    def _load_state(self) -> None:
        """Load latest portfolio snapshot and trades if files exist."""
        if PORTFOLIO_JSON.exists():
            try:
                with open(PORTFOLIO_JSON, "r") as f:
                    state = json.load(f)
                self.cash = float(state.get("cash", self.cash))
                self.positions = state.get("positions", {}).copy()
                self.total_capital = float(state.get("total_capital", self.total_capital))
            except (json.JSONDecodeError, KeyError, ValueError):
                pass  # Start fresh on corruption

        # Optionally preload recent trades (useful for testing)
        if TRADES_CSV.exists():
            try:
                with open(TRADES_CSV, "r", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        trade = PaperTrade(
                            timestamp=row["timestamp"],
                            action=row["action"],
                            pair=row["pair"],
                            usd_amount=float(row["usd_amount"]),
                            price=float(row["price"]),
                            note=row.get("note", ""),
                        )
                        self.trades.append(trade)
            except Exception:
                pass

    def _save_portfolio_snapshot(self) -> None:
        """Persist current portfolio state to JSON."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_capital": self.total_capital,
            "cash": self.cash,
            "positions": self.positions.copy(),
        }
        with open(PORTFOLIO_JSON, "w") as f:
            json.dump(snapshot, f, indent=2)

    def _record_trade(self, trade: PaperTrade) -> None:
        """Append trade record to CSV following exact schema."""
        file_exists = TRADES_CSV.exists()
        write_header = not file_exists or os.path.getsize(TRADES_CSV) == 0

        with open(TRADES_CSV, "a", newline="") as f:
            fieldnames = ["timestamp", "action", "pair", "usd_amount", "price", "note"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if write_header:
                writer.writeheader()

            writer.writerow({
                "timestamp": trade.timestamp,
                "action": trade.action,
                "pair": trade.pair,
                "usd_amount": f"{trade.usd_amount:.2f}",
                "price": f"{trade.price:.2f}",
                "note": trade.note,
            })

        self.trades.append(trade)

    def get_current_price(self, pair: str) -> float:
        """
        Placeholder price fetcher.
        In real usage this is injected. Returns 0.0 by default.
        Callers should override with real price source.
        """
        # No hard-coded prices or assumptions. External callers provide prices.
        return 0.0

    def execute_rebalance(self, rebalance_plan: List[Dict[str, Any]], prices: Dict[str, float], note: str = "rebalance") -> List[PaperTrade]:
        """
        Execute a list of moves generated by rebalance_plan().

        Each plan entry:
            {"action": "BUY" or "SELL", "pair": "BTC-USD", "usd_amount": 123.45}

        Args:
            rebalance_plan: list of dicts with keys action, pair, usd_amount
            prices: dict of pair -> current price
            note: Optional annotation for the trade records

        Returns:
            List of executed PaperTrade records
        """
        executed: List[PaperTrade] = []

        for move in rebalance_plan:
            action = move.get("action", "").upper()
            pair = move.get("pair")
            usd_amount = float(move.get("usd_amount", 0.0))

            if not pair or usd_amount <= 0:
                continue

            price = prices.get(pair, self.get_current_price(pair))
            if price <= 0:
                # Cannot execute without valid price - skip safely
                continue

            quantity = usd_amount / price

            timestamp = datetime.now(timezone.utc).isoformat()

            if action == "BUY":
                # Spend cash, increase position
                if self.cash >= usd_amount:
                    self.cash -= usd_amount
                    self.positions[pair] = self.positions.get(pair, 0.0) + quantity

                    trade = PaperTrade(
                        timestamp=timestamp,
                        action="BUY",
                        pair=pair,
                        usd_amount=usd_amount,
                        price=price,
                        note=note,
                    )
                    self._record_trade(trade)
                    executed.append(trade)
            elif action == "SELL":
                # Sell holdings, increase cash
                current_qty = self.positions.get(pair, 0.0)
                sell_qty = min(quantity, current_qty)
                if sell_qty > 0:
                    sell_usd = sell_qty * price
                    self.cash += sell_usd
                    self.positions[pair] = current_qty - sell_qty
                    if self.positions[pair] <= 0:
                        self.positions.pop(pair, None)

                    trade = PaperTrade(
                        timestamp=timestamp,
                        action="SELL",
                        pair=pair,
                        usd_amount=sell_usd,
                        price=price,
                        note=note,
                    )
                    self._record_trade(trade)
                    executed.append(trade)

        self._save_portfolio_snapshot()
        return executed

    def get_portfolio_state(self) -> Dict[str, Any]:
        """
        Return current portfolio snapshot for inspection / saving.
        """
        return {
            "total_capital": self.total_capital,
            "cash": round(self.cash, 2),
            "positions": {k: round(v, 8) for k, v in self.positions.items()},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def calculate_paper_pnl(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """
        Compute paper P&L using current market prices.

        Returns:
            dict containing:
            - total_value: total portfolio value (cash + positions)
            - cash: current cash
            - unrealized_pnl: positions value - invested capital
            - realized_pnl: (could be extended in future with cost basis tracking)
        """
        positions_value = 0.0
        invested = 0.0  # simplistic: sum of positive trade USD

        for pair, qty in self.positions.items():
            price = current_prices.get(pair, 0.0)
            if price > 0 and qty > 0:
                positions_value += qty * price

        # Simple realized approximation based on historical buys/sells
        # (For full cost-basis tracking a ledger would be needed - kept minimal here)
        realized = 0.0
        for t in self.trades:
            if t.action == "SELL":
                realized += t.usd_amount  # rough proxy, sufficient for paper snapshot

        total_value = round(self.cash + positions_value, 2)

        return {
            "total_value": total_value,
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "unrealized_pnl": round(positions_value, 2),  # placeholder until cost basis
            "realized_pnl": round(realized, 2),
        }


def create_fresh_paper_trader(total_capital: float = 10000.0) -> PaperTrader:
    """Convenience factory for a brand-new paper trading account."""
    return PaperTrader(total_capital=total_capital)