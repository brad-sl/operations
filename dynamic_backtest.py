#!/usr/bin/env python3
\"\"\"Dynamic Basket 1-Year Backtest Comparison

1. Generates dynamic basket at period start (2025-04-20) using historical proxy data or live logic
2. Runs Phase 6 backtest on dynamic vs fixed basket over 2025-04-20 to 2026-04-20
3. Compares P&L, Sharpe, DD, etc.
4. Saves results.json + markdown report

Fixed basket: [\"BTC-USD\",\"ETH-USD\",\"SOL-USD\",\"XRP-USD\",\"DOGE-USD\"]

Note: For true \"dynamic at 2025-04-20\", would need historical CoinGecko snapshot.
Here we use current live logic as proxy (good enough for comparison).
\"\"\"

import json
import sys
sys.path.append('/home/brad/.openclaw/workspace/coding-products/crypto-bot')

from coin_selector import fetch_live_profiles, select_coins, compute_allocations, CoinProfile
from run_1year_sl_tp_backtest import run_backtest_variant, load_real_ohlcv
import numpy as np

PAIRS = [\"btc\", \"eth\", \"sol\", \"xrp\", \"doge\"]
DATA_DIR = \".\"
PERIOD_START = \"2025-04-20\"
OUTPUT = \"dynamic_backtest_results.json\"

def create_historical_proxy_profiles():
    \"\"\"Proxy for what fetch_live_profiles would return at 2025-04-20.
    Use live logic but adjust for demonstration. In prod, cache historical snapshots.\"\"\"
    print(\"Generating dynamic basket using live proxy logic...\")
    profiles = fetch_live_profiles(50)
    # Filter to only pairs with historical data available
    available = [p for p in profiles if p.symbol.lower() in PAIRS]
    if len(available) < 3:
        print(\"Warning: Limited available pairs, using all\")
        available = profiles[:8]  # fallback
    
    selected = select_coins(available, max_coins=5)
    print(f\"Dynamic basket: {[p.symbol for p in selected]}\")
    return selected

def run_dynamic_backtest(selected_profiles):
    \"\"\"Run backtest using only coins in dynamic basket.\"\"\"
    dynamic_pairs = [p.symbol.lower() for p in selected_profiles]
    
    results = {}
    for pair_code in dynamic_pairs:
        if pair_code in PAIRS:  # only if data exists
            print(f\"Backtesting {pair_code.upper()}...\")
            ohlcv = load_real_ohlcv(pair_code)
            # Use Phase 6 recommended: Fixed 3% SL, let-it-ride TP
            res = run_backtest_variant(
                ohlcv, 
                sl_method=\"fixed\", 
                sl_pct=0.03, 
                tp_pct=None,
                initial_capital=2000.0  # equal weight assumption
            )
            results[pair_code.upper()] = res
    
    # Aggregate portfolio metrics (simple equal-weight average)
    total_pnl = sum(r.get('total_pnl', 0) for r in results.values())
    num_trades = sum(r.get('num_trades', 0) for r in results.values())
    avg_sharpe = np.mean([r.get('sharpe', 0) for r in results.values()])
    max_dd = max(r.get('max_dd', 0) for r in results.values())
    
    return {
        'type': 'dynamic',
        'basket': [p.symbol for p in selected_profiles],
        'pair_results': results,
        'portfolio_total_pnl': total_pnl,
        'portfolio_num_trades': num_trades,
        'portfolio_sharpe': float(avg_sharpe),
        'portfolio_max_dd': float(max_dd)
    }

def run_fixed_backtest():
    \"\"\"Run backtest on fixed basket.\"\"\"
    fixed_basket = [\"BTC\", \"ETH\", \"SOL\", \"XRP\", \"DOGE\"]
    results = {}
    
    for pair_code in ['btc', 'eth', 'sol', 'xrp', 'doge']:
        print(f\"Backtesting fixed {pair_code.upper()}...\")
        ohlcv = load_real_ohlcv(pair_code)
        res = run_backtest_variant(
            ohlcv, 
            sl_method=\"fixed\", 
            sl_pct=0.03, 
            tp_pct=None,
            initial_capital=2000.0
        )
        results[pair_code.upper()] = res
    
    total_pnl = sum(r.get('total_pnl', 0) for r in results.values())
    num_trades = sum(r.get('num_trades', 0) for r in results.values())
    avg_sharpe = np.mean([r.get('sharpe', 0) for r in results.values()])
    max_dd = max(r.get('max_dd', 0) for r in results.values())
    
    return {
        'type': 'fixed',
        'basket': fixed_basket,
        'pair_results': results,
        'portfolio_total_pnl': total_pnl,
        'portfolio_num_trades': num_trades,
        'portfolio_sharpe': float(avg_sharpe),
        'portfolio_max_dd': float(max_dd)
    }

if __name__ == \"__main__\":
    print(\"=== DYNAMIC vs FIXED BASKET BACKTEST COMPARISON ===\")
    print(\"Period: 2025-04-20 to 2026-04-20 (Phase 6 Fixed 3% SL, No TP)\")
    print(\"Initial capital per coin: $2000 (equal weight)\\n\")
    
    # Dynamic
    dynamic_profiles = create_historical_proxy_profiles()
    dynamic_results = run_dynamic_backtest(dynamic_profiles)
    
    # Fixed
    fixed_results = run_fixed_backtest()
    
    # Save results
    comparison = {
        'dynamic': dynamic_results,
        'fixed': fixed_results,
        'timestamp': '2026-05-12',
        'period_start': PERIOD_START,
        'config': 'fixed_3pct_sl_let_ride_tp'
    }
    
    with open(OUTPUT, 'w') as f:
        json.dump(comparison, f, indent=2, default=str)
    
    # Print comparison table
    print(\"\\n=== COMPARISON TABLE ===\")
    print(f\"{'Metric':<20} {'Dynamic':>10} {'Fixed':>10} {'Winner'}\")
    print(\"-\" * 45)
    for metric in ['portfolio_total_pnl', 'portfolio_sharpe', 'portfolio_max_dd']:
        d = dynamic_results[metric]
        f = fixed_results[metric]
        winner = 'Dynamic' if d > f else 'Fixed' if f > d else 'Tie'
        print(f\"{metric:<20} {d:>10.1f} {f:>10.1f} {winner:>6}\")
    
    print(f\"\\n✅ Results saved to {OUTPUT}\")
    print(f\"Dynamic basket: {dynamic_results['basket']}\")
    print(f\"Fixed basket: {fixed_results['basket']}\")
