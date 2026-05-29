#!/usr/bin/env python3
"""
Self-contained reliable paper trading launcher.
Handles Python path and provides standalone minimal simulation.
"""

import sys
import os
import argparse
import random
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src", "core"))


class SimplePaperPortfolio:
    """Reliable minimal paper trading portfolio."""
    def __init__(self, cash=10000.0):
        self.cash = cash
        self.positions = {}
        self.trade_log = []

    def buy(self, symbol, price, usd_amount):
        qty = usd_amount / price
        avg = self.positions.get(symbol, {}).get("avg", price)
        tot_qty = self.positions.get(symbol, {}).get("qty", 0) + qty
        self.positions[symbol] = {
            "qty": tot_qty,
            "avg": ((avg * (tot_qty - qty)) + (price * qty)) / tot_qty
        }
        self.cash -= usd_amount
        trade = {"ts": datetime.now().isoformat(), "action": "BUY",
                 "symbol": symbol, "qty": round(qty, 6), "price": price, "usd": round(usd_amount, 2)}
        self.trade_log.append(trade)
        return trade

    def get_value(self, prices=None):
        value = self.cash
        prices = prices or {}
        for sym, pos in self.positions.items():
            px = prices.get(sym, pos["avg"])
            value += pos["qty"] * px
        return round(value, 2)

    def summary(self):
        return {
            "cash": round(self.cash, 2),
            "positions": {k: {**v, "qty": round(v["qty"], 6)} for k, v in self.positions.items()},
            "trades": len(self.trade_log)
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    print("\n" + "="*60)
    print("📊 PAPER TRADING LAUNCHER - SELF CONTAINED")
    print(f"⏰ {datetime.now().isoformat()}")
    print("="*60 + "\n")

    portfolio = SimplePaperPortfolio(10000.0)
    symbols = ["BTC-USD", "ETH-USD"]

    for cycle in range(args.cycles):
        print(f"Cycle {cycle + 1}")
        for sym in symbols:
            # Fake realistic prices
            price = 67000 + random.randint(-400, 800) if "BTC" in sym else 2400 + random.randint(-50, 70)
            print(f"  {sym}: ${price:,.2f}")

            # Execute 1-2 demo trades total
            if len(portfolio.trade_log) < 2:
                amount = 500.0
                trade = portfolio.buy(sym, price, amount)
                print(f"    📈 BUY {trade['qty']} {sym} @ ${price}")

    final_val = portfolio.get_value()
    print("\n" + "="*60)
    print(f"✅ Finished | Trades recorded: {len(portfolio.trade_log)}")
    print(f"💼 Final simulated portfolio value: ${final_val:,.2f}")
    print(f"📋 Full trade log: {portfolio.trade_log}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
