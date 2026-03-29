#!/usr/bin/env python3
"""
Backtest: Last 3 days, RSI-only (no sentiment), static thresholds
================================================================
Validates whether RSI signals should have triggered trades in last 72 hours.
"""

import requests
import json
from datetime import datetime, timedelta
from statistics import mean

# Parameters
now = datetime.utcnow()
start = now - timedelta(days=3)
BTC_THRESHOLDS = {"buy": 30, "sell": 70}
XRP_THRESHOLDS = {"buy": 35, "sell": 65}

print(f"\n{'='*70}")
print(f"RSI-ONLY BACKTEST: Last 3 Days")
print(f"{'='*70}")
print(f"Start: {start.isoformat()}")
print(f"End:   {now.isoformat()}")
print(f"RSI Thresholds: BTC 30/70 | XRP 35/65")
print(f"{'='*70}\n")

def get_candles(pair, granule_seconds, limit):
    """Fetch candles from Coinbase public API."""
    url = f"https://api.exchange.coinbase.com/products/{pair}/candles"
    params = {
        "granularity": granule_seconds,
        "limit": limit
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error fetching {pair}: {e}")
    return []

def calculate_rsi(prices):
    """RSI calculation (14-period)."""
    if len(prices) < 15:
        return 50.0
    
    recent = prices[-14:]
    gains = sum(max(0, recent[i] - recent[i-1]) for i in range(1, len(recent))) / 14
    losses = sum(max(0, recent[i-1] - recent[i]) for i in range(1, len(recent))) / 14
    
    if losses == 0:
        return 100.0 if gains > 0 else 0.0
    
    rs = gains / losses
    return 100 - (100 / (1 + rs))

results = {}

for pair in ["BTC-USD", "XRP-USD"]:
    print(f"📊 {pair}")
    print(f"{'-'*70}")
    
    # Fetch 5-minute candles (72 hours = 864 candles)
    candles = get_candles(pair, 300, 900)
    
    if not candles or len(candles) < 20:
        print(f"⚠️  Insufficient data: {len(candles) if candles else 0} candles")
        print()
        continue
    
    # Extract prices
    prices = [float(c[4]) for c in candles]  # Close price is index 4
    
    # Simulate trading
    trades = []
    entry_signal = None
    entry_price = None
    entry_rsi = None
    entry_idx = None
    
    thresholds = BTC_THRESHOLDS if pair == "BTC-USD" else XRP_THRESHOLDS
    
    for i in range(14, len(prices)):
        # Calculate RSI on current 14-period window
        rsi = calculate_rsi(prices[:i+1])
        
        # ENTRY LOGIC
        if not entry_signal:
            if rsi < thresholds["buy"]:
                entry_signal = "BUY"
                entry_price = prices[i]
                entry_rsi = rsi
                entry_idx = i
            elif rsi > thresholds["sell"]:
                entry_signal = "SELL"
                entry_price = prices[i]
                entry_rsi = rsi
                entry_idx = i
        
        # EXIT LOGIC
        elif entry_signal == "BUY":
            if rsi > thresholds["sell"]:
                exit_price = prices[i]
                pnl = exit_price - entry_price
                is_win = pnl > 0
                trades.append({
                    "type": "BUY",
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "entry_rsi": round(entry_rsi, 2),
                    "exit_rsi": round(rsi, 2),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 2),
                    "win": is_win
                })
                entry_signal = None
        
        elif entry_signal == "SELL":
            if rsi < thresholds["buy"]:
                exit_price = prices[i]
                pnl = entry_price - exit_price
                is_win = pnl > 0
                trades.append({
                    "type": "SELL",
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "entry_rsi": round(entry_rsi, 2),
                    "exit_rsi": round(rsi, 2),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 2),
                    "win": is_win
                })
                entry_signal = None
    
    # Summary
    wins = sum(1 for t in trades if t["win"])
    total_pnl = sum(t["pnl"] for t in trades)
    
    results[pair] = {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": (wins / len(trades) * 100) if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl_per_trade": round(total_pnl / len(trades), 2) if trades else 0,
        "trades_detail": trades[:10]  # First 10 for inspection
    }
    
    print(f"  Trades Completed: {len(trades)}")
    print(f"  Wins: {wins} | Losses: {len(trades) - wins}")
    if trades:
        print(f"  Win Rate: {wins / len(trades) * 100:.1f}%")
        print(f"  Total P&L: ${total_pnl:.2f}")
        print(f"  Avg P&L/Trade: ${total_pnl / len(trades):.2f}")
        print(f"\n  First 5 trades:")
        for j, t in enumerate(trades[:5]):
            status = "✅" if t["win"] else "❌"
            print(f"    {j+1}. {t['type']} @ RSI {t['entry_rsi']} (${t['entry_price']}) → " + 
                  f"RSI {t['exit_rsi']} (${t['exit_price']}) {status} ${t['pnl']}")
    else:
        print(f"  ⚠️  No trades triggered")
    
    print()

# Cross-pair summary
print(f"{'='*70}")
print(f"COMBINED SUMMARY")
print(f"{'='*70}")
total_trades = sum(r["trades"] for r in results.values())
total_wins = sum(r["wins"] for r in results.values())
total_pnl = sum(r["total_pnl"] for r in results.values())

print(f"Total Trades: {total_trades}")
print(f"Total Wins: {total_wins}")
if total_trades > 0:
    print(f"Overall Win Rate: {total_wins / total_trades * 100:.1f}%")
print(f"Total P&L: ${total_pnl:.2f}")

# Save results
with open("BACKTEST_3DAY_RSI.json", "w") as f:
    json.dump({
        "period": f"3 days ({start.isoformat()} to {now.isoformat()})",
        "thresholds": {"BTC-USD": BTC_THRESHOLDS, "XRP-USD": XRP_THRESHOLDS},
        "results": results,
        "summary": {
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_trades - total_wins,
            "win_rate_pct": (total_wins / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": round(total_pnl, 2)
        }
    }, f, indent=2)

print(f"\n💾 Results saved to BACKTEST_3DAY_RSI.json")
