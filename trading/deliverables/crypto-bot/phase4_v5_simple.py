#!/usr/bin/env python3
"""
Phase 4 v5 — Simplified Strategy Test Harness
Runs 3 strategies with robust DB handling & 0.25% corrected Coinbase fees.
"""

import json
import sqlite3
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional
import time

COINBASE_API_BASE = "https://api.exchange.coinbase.com"
PAIRS = ["BTC-USD", "XRP-USD"]
POLL_INTERVAL_SEC = 300  # 5 minutes

class StrategyTester:
    def __init__(self, trader_id="brad"):
        self.trader_id = trader_id
        self.cycle_count = 0
        self.start_time = datetime.now(timezone.utc)
        
        # Per-strategy results
        self.results = {
            'fixed': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0},
            'fee_aware': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0},
            'pair_specific': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
        }
        
        print(f"🧪 Strategy Tester v5 initialized for {trader_id}")
        print(f"   Strategies: FIXED (1.0%), FEE_AWARE (0.75%), PAIR_SPECIFIC (0.5/1.5%)")
        print(f"   Fee rates: 0.25% Coinbase maker (corrected)")
        
    def _fetch_config(self, pair: str, strategy: str) -> Optional[Dict]:
        """Load strategy config from DB (fresh connection)."""
        try:
            conn = sqlite3.connect('phase4_trades.db', timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trader_configs 
                WHERE trader_id = ? AND pair = ? AND strategy = ?
            ''', (self.trader_id, pair, strategy))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            print(f"   ⚠️  Config load error {pair}/{strategy}: {e}")
            return None
    
    def _fetch_price(self, pair: str) -> Optional[float]:
        """Get current price from Coinbase."""
        try:
            url = f"{COINBASE_API_BASE}/products/{pair}/ticker"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return float(resp.json()['price'])
        except Exception as e:
            pass
        return None
    
    def _get_min_profit_pct(self, strategy: str, pair: str, cfg: Dict) -> float:
        """Calculate min profit threshold per strategy."""
        if strategy == 'fixed':
            return 1.0
        elif strategy == 'fee_aware':
            # (0.25% entry + 0.25% exit) * 1.5 safety margin = 0.75%
            return 0.75
        elif strategy == 'pair_specific':
            # Use override if set, else fallback
            return cfg.get('min_profit_pct_override', 1.0) if cfg.get('min_profit_pct_override') else \
                   (0.5 if pair == 'BTC-USD' else 1.5)
        return 1.0
    
    def run_cycle(self):
        """Run one polling cycle."""
        self.cycle_count += 1
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        
        print(f"\n🔄 Cycle {self.cycle_count} | {elapsed:.1f}h elapsed")
        
        for pair in PAIRS:
            price = self._fetch_price(pair)
            if not price:
                print(f"  ⚠️  {pair}: price fetch failed")
                continue
            
            # Mock entry (simulate RSI signal + random P&L)
            import random
            entry_price = price * (1 + random.uniform(-0.01, 0.01))
            current_price = entry_price * (1 + random.uniform(-0.02, 0.05))
            pnl = current_price - entry_price
            pnl_pct = (pnl / entry_price) * 100
            
            # Test each strategy
            for strategy in ['fixed', 'fee_aware', 'pair_specific']:
                cfg = self._fetch_config(pair, strategy)
                if not cfg:
                    continue
                
                min_pnl = self._get_min_profit_pct(strategy, pair, cfg)
                should_exit = pnl_pct >= min_pnl
                
                if should_exit:
                    # Trade executed
                    self.results[strategy]['trades'] += 1
                    if pnl > 0:
                        self.results[strategy]['wins'] += 1
                    else:
                        self.results[strategy]['losses'] += 1
                    self.results[strategy]['pnl'] += pnl
                    
                    status = "✅" if pnl > 0 else "❌"
                    print(f"  {status} {strategy:15} {pair:8} P&L {pnl_pct:+6.2f}% (min {min_pnl:.1f}%) → +${pnl:.2f}")
                    
                    # Log to DB (fresh connection)
                    try:
                        conn = sqlite3.connect('phase4_trades.db', timeout=10.0)
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO trades 
                            (pair, signal, entry_price, exit_price, pnl, pnl_pct, result, 
                             entry_time, exit_time, timestamp, regime)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (pair, f'{strategy}_signal', entry_price, current_price, pnl, pnl_pct,
                              'WIN' if pnl > 0 else 'LOSS', 
                              datetime.now(timezone.utc).isoformat(),
                              datetime.now(timezone.utc).isoformat(),
                              datetime.now(timezone.utc).isoformat(),
                              'TEST'))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        print(f"   ⚠️  DB write error: {e}")
                else:
                    print(f"  ⏳ {strategy:15} {pair:8} P&L {pnl_pct:+6.2f}% (need {min_pnl:.1f}%)")
        
        self._print_summary()
    
    def _print_summary(self):
        """Print running summary for all strategies."""
        print("\n📊 Strategy Summary:")
        for strat in ['fixed', 'fee_aware', 'pair_specific']:
            r = self.results[strat]
            if r['trades'] == 0:
                print(f"  {strat:15} — No trades yet")
            else:
                win_rate = (r['wins'] / r['trades'] * 100) if r['trades'] else 0
                avg_pnl = r['pnl'] / r['trades'] if r['trades'] else 0
                print(f"  {strat:15} | Trades: {r['trades']:3} | W/L: {r['wins']}/{r['losses']} | "
                      f"Win%: {win_rate:5.1f}% | Total P&L: ${r['pnl']:+8.2f} | Avg: ${avg_pnl:+7.2f}")

if __name__ == '__main__':
    tester = StrategyTester(trader_id='brad')
    
    print("\n" + "="*80)
    print("TRADE THROTTLE TEST — 3 Exit Strategies Comparison")
    print("="*80)
    
    # Run cycles
    try:
        cycle_limit = 288  # 48 hours @ 5-min intervals
        while tester.cycle_count < cycle_limit:
            tester.run_cycle()
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        print("\n\n✅ Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
