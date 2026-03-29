#!/usr/bin/env python3
"""
Phase 4 v4 — Parallel Strategy Test Harness
============================================
Runs 3 minimum-profit strategies simultaneously on the same market data.
Logs all trades per strategy and compares performance metrics.

Strategies:
1. FIXED: min_profit_pct = 1.0% (baseline)
2. FEE_AWARE: min_profit_pct = (entry_fee + exit_fee) * safety_margin
3. PAIR_SPECIFIC: per-pair overrides (BTC 0.5%, XRP 1.5%)

All 3 run in parallel, sharing the same entry signals but with different exit rules.

Author: Brad / Strategy Comparison Framework
Date: 2026-03-29
"""

import json
import sqlite3
import requests
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional
import statistics

# ============================================================================
# CONFIG & SETUP
# ============================================================================

COINBASE_API_BASE = "https://api.exchange.coinbase.com"
PAIRS = ["BTC-USD", "XRP-USD"]
POLL_INTERVAL_SEC = 300  # 5 minutes
SANDBOX = True

@dataclass
class StrategyConfig:
    """Strategy-specific settings."""
    name: str  # 'fixed', 'fee_aware', 'pair_specific'
    min_profit_pct: float
    entry_fee_pct: float = 0.1
    exit_fee_pct: float = 0.1
    fee_safety_margin: float = 1.5
    per_pair_overrides: Dict[str, float] = None  # {pair: min_pnl_pct}

@dataclass
class TradeResult:
    """Single trade outcome."""
    strategy: str
    pair: str
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    result: str  # 'WIN' or 'LOSS'
    entry_time: str
    exit_time: str

class StrategyTester:
    """Run 3 strategies in parallel."""
    
    def __init__(self, trader_id="brad"):
        self.trader_id = trader_id
        self.db = self._init_db()
        self.cycle_count = 0
        self.start_time = datetime.now(timezone.utc)
        
        # Load configs from DB
        self.configs = self._load_strategies()
        
        # Track results per strategy
        self.results: Dict[str, List[TradeResult]] = {
            'fixed': [],
            'fee_aware': [],
            'pair_specific': []
        }
        
        print(f"🧪 Strategy Tester initialized for {trader_id}")
        print(f"   Running {len(self.configs)} strategies")
        
    def _init_db(self):
        """Connect to trades database."""
        conn = sqlite3.connect('phase4_trades.db')
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_strategies(self) -> List[StrategyConfig]:
        """Load strategy configs from trader_configs table."""
        cursor = self.db.execute('''
            SELECT DISTINCT strategy FROM trader_configs WHERE trader_id = ?
        ''', (self.trader_id,))
        
        strategies = []
        for row in cursor.fetchall():
            strategy_name = row['strategy']
            
            if strategy_name == 'fixed':
                strategies.append(StrategyConfig(
                    name='fixed',
                    min_profit_pct=1.0
                ))
            elif strategy_name == 'fee_aware':
                strategies.append(StrategyConfig(
                    name='fee_aware',
                    min_profit_pct=0.0,  # Calculated per trade
                    entry_fee_pct=0.25,  # Actual Coinbase maker fee (Advanced 1+ tier)
                    exit_fee_pct=0.25,   # Actual Coinbase maker fee (Advanced 1+ tier)
                    fee_safety_margin=1.5
                ))
            elif strategy_name == 'pair_specific':
                overrides = {}
                cursor2 = self.db.execute('''
                    SELECT pair, min_profit_pct_override FROM trader_configs 
                    WHERE trader_id = ? AND strategy = ? AND min_profit_pct_override IS NOT NULL
                ''', (self.trader_id, 'pair_specific'))
                for r in cursor2.fetchall():
                    overrides[r['pair']] = r['min_profit_pct_override']
                
                strategies.append(StrategyConfig(
                    name='pair_specific',
                    min_profit_pct=1.0,  # Fallback
                    per_pair_overrides=overrides or {}
                ))
        
        return strategies
    
    def _get_min_profit_pct(self, strategy: StrategyConfig, pair: str) -> float:
        """Calculate minimum profit % for given strategy & pair."""
        if strategy.name == 'fixed':
            return strategy.min_profit_pct
        
        elif strategy.name == 'fee_aware':
            total_fee = (strategy.entry_fee_pct + strategy.exit_fee_pct) / 100.0
            return (total_fee * strategy.fee_safety_margin) * 100
        
        elif strategy.name == 'pair_specific':
            if strategy.per_pair_overrides and pair in strategy.per_pair_overrides:
                return strategy.per_pair_overrides[pair]
            return strategy.min_profit_pct
        
        return strategy.min_profit_pct
    
    def _fetch_price(self, pair: str) -> Optional[float]:
        """Get current price from Coinbase."""
        try:
            url = f"{COINBASE_API_BASE}/products/{pair}/ticker"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return float(resp.json()['price'])
        except Exception as e:
            print(f"   ⚠️  Error fetching {pair}: {e}")
        return None
    
    def _get_or_create_entry(self, pair: str) -> Optional[Dict]:
        """Get oldest open trade (entry) for pair, or create mock entry."""
        cursor = self.db.execute('''
            SELECT id, entry_price, entry_time FROM trades 
            WHERE pair = ? AND exit_price IS NULL AND (exit_time IS NULL OR exit_time = '')
            ORDER BY id DESC LIMIT 1
        ''', (pair,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        # Create mock entry
        price = self._fetch_price(pair)
        if not price:
            return None
        
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO trades (pair, signal, entry_price, entry_time, timestamp, regime)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pair, 'TEST_BUY', price, now, now, 'SIDEWAYS'))
        self.db.commit()
        
        return {
            'id': cursor.lastrowid,
            'entry_price': price,
            'entry_time': now,
            'timestamp': now
        }
    
    def _should_exit(self, entry_price: float, current_price: float, 
                     strategy: StrategyConfig, pair: str) -> bool:
        """Check if P&L exceeds strategy's minimum threshold."""
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        min_pnl = self._get_min_profit_pct(strategy, pair)
        
        return pnl_pct >= min_pnl
    
    def run_cycle(self):
        """Run one polling cycle across all pairs & strategies."""
        self.cycle_count += 1
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        
        print(f"\n🔄 Cycle {self.cycle_count} | {elapsed:.1f}h elapsed")
        
        for pair in PAIRS:
            entry = self._get_or_create_entry(pair)
            if not entry:
                continue
            
            current_price = self._fetch_price(pair)
            if not current_price:
                continue
            
            pnl = current_price - entry['entry_price']
            pnl_pct = (pnl / entry['entry_price']) * 100
            
            # Test each strategy
            for strategy in self.configs:
                min_pnl = self._get_min_profit_pct(strategy, pair)
                should_exit = pnl_pct >= min_pnl
                
                if should_exit:
                    now = datetime.now(timezone.utc).isoformat()
                    result = TradeResult(
                        strategy=strategy.name,
                        pair=pair,
                        entry_price=entry['entry_price'],
                        exit_price=current_price,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        result='WIN' if pnl > 0 else 'LOSS',
                        entry_time=entry['entry_time'],
                        exit_time=now
                    )
                    self.results[strategy.name].append(result)
                    
                    # Log to DB
                    cursor = self.db.execute('''
                        INSERT INTO strategy_backtest 
                        (trader_id, pair, strategy, total_trades, wins, losses)
                        VALUES (?, ?, ?, 1, ?, ?)
                    ''', (self.trader_id, pair, strategy.name, 
                          1 if result.result == 'WIN' else 0,
                          1 if result.result == 'LOSS' else 0))
                    self.db.commit()
                    
                    print(f"  ✅ {strategy.name:15} {pair:8} P&L {pnl_pct:+6.2f}% (min {min_pnl:.1f}%)")
                else:
                    print(f"  ⏳ {strategy.name:15} {pair:8} P&L {pnl_pct:+6.2f}% (need {min_pnl:.1f}%)")
        
        self._print_summary()
    
    def _print_summary(self):
        """Print running stats for all strategies."""
        print("\n📊 Strategy Comparison:")
        
        for strat_name in ['fixed', 'fee_aware', 'pair_specific']:
            trades = self.results[strat_name]
            if not trades:
                print(f"  {strat_name:15} — No trades yet")
                continue
            
            wins = sum(1 for t in trades if t.result == 'WIN')
            losses = len(trades) - wins
            win_rate = (wins / len(trades) * 100) if trades else 0
            total_pnl = sum(t.pnl for t in trades)
            avg_pnl = total_pnl / len(trades) if trades else 0
            
            print(f"  {strat_name:15} | Trades: {len(trades):3} | W/L: {wins}/{losses} | "
                  f"Win%: {win_rate:5.1f}% | Total P&L: ${total_pnl:+8.2f} | Avg: ${avg_pnl:+7.2f}")

if __name__ == '__main__':
    tester = StrategyTester(trader_id='brad')
    
    print("\n" + "="*80)
    print("PARALLEL STRATEGY TEST — 3 Exit Strategies, Same Entry Signals")
    print("="*80)
    print("\nStrategies:")
    for cfg in tester.configs:
        print(f"  • {cfg.name:15} min_profit = {cfg.min_profit_pct:.1f}%")
    
    # Run cycles
    import time
    while True:
        try:
            tester.run_cycle()
            time.sleep(POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n\n✅ Test stopped by user")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
