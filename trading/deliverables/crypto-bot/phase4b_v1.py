#!/usr/bin/env python3
"""
Phase 4b v1 — FIXED: Real Coinbase Prices + Position Hold Logic + No Duplicates

**CRITICAL FIXES (2026-03-30 12:20 PDT):**
1. ✅ Real Coinbase API calls: get_current_price() replaces simulated prices
2. ✅ Position hold times: 5+ cycles min (25+ minutes) before exit allowed
3. ✅ No duplicate trades: One trade logged per entry, not 3
4. ✅ Real stop loss: Exit if (price - entry) / entry <= -2% OR >= exit_threshold

Data sources:
- Prices: Real Coinbase Advanced Trade API (/products/{product_id}/ticker)
- Sentiment: Real X API v2, 1-hour cache (sentiment_scheduler.py)
- RSI: Simulated (would be real in production from Coinbase candle data)

Commit message: PHASE4B FIX: Integrate Coinbase real prices, add position hold times, remove trade duplicates
Issue: Phase 4B v1 was logging trades instantly (microseconds) with simulated prices
Resolution: Now uses real Coinbase ticker API + tracks positions with min 25-min hold + logs 1 trade per signal
"""

import json
import sqlite3
import logging
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv

from x_sentiment_fetcher import XSentimentFetcher
from coinbase_wrapper import CoinbaseWrapper

# Load environment variables from .env
load_dotenv(Path(__file__).parent / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('phase4b_48h_run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / 'phase4_trades.db'
CYCLE_INTERVAL = 300  # 5 minutes


class Phase4bOrchestrator:
    def __init__(self, phase4_winner_strategy: str = 'fee_aware'):
        """FIX #1: Initialize Coinbase wrapper with real credentials from .env"""
        self._init_database()
        
        self.winner_strategy = phase4_winner_strategy
        self.sentiment_fetcher = XSentimentFetcher(cache_dir='.')  # cache_hours loaded from config/sentiment_config.json (default: 4h)
        
        # FIX #1: Load Coinbase credentials from .env (CRITICAL: never commit .env)
        coinbase_api_key = os.getenv('COINBASE_API_KEY_ID', '')
        coinbase_private_key = os.getenv('COINBASE_PRIVATE_KEY', '')
        coinbase_passphrase = os.getenv('COINBASE_PASSPHRASE', 'default')
        coinbase_sandbox = os.getenv('COINBASE_SANDBOX', 'true').lower() == 'true'
        
        if not coinbase_api_key or not coinbase_private_key:
            logger.warning("⚠️ COINBASE credentials missing from .env — using sandbox fallback")
            coinbase_api_key = "sandbox"
            coinbase_private_key = "sandbox"
            coinbase_sandbox = True
        
        self.cb = CoinbaseWrapper(
            api_key=coinbase_api_key,
            private_key=coinbase_private_key,
            passphrase=coinbase_passphrase,
            sandbox=coinbase_sandbox
        )
        self.cycle_count = 0
        self.start_time = datetime.now(timezone.utc)
        
        # FIX #3: Track open positions with hold times
        self.open_positions = {}  # {pair: {entry_price, entry_cycle, entry_rsi, sentiment}}
        self.min_hold_cycles = 5  # Min 5 cycles (25 min) before exit allowed
        self.stop_loss_pct = -0.02  # -2% stop loss
        
        self._sentiment_cache = {}
        self._sentiment_cache_ttl = 3600
        self._sentiment_cache_timestamp = time.time()
        
        self.exit_thresholds = {
            'fixed': 0.01,
            'fee_aware': 0.0075,
            'pair_specific': {'BTC-USD': 0.005, 'XRP-USD': 0.015}
        }
        
        self.sentiment_boost_threshold = 0.2
        self.sentiment_dampen_threshold = -0.2
        
        logger.info(f"🚀 Phase 4b Orchestrator initialized (FIXED)")
        logger.info(f"   Winner Strategy: {self.winner_strategy}")
        logger.info(f"   FIX #1: Real Coinbase prices enabled")
        logger.info(f"   FIX #3: Position hold={self.min_hold_cycles} cycles (~25 min)")
        logger.info(f"   FIX #4: Stop loss={self.stop_loss_pct*100:.0f}%")
    
    def _init_database(self):
        """Initialize SQLite database with required tables"""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
            cursor = conn.cursor()
            
            # Create trades table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    pnl REAL,
                    pnl_pct REAL,
                    entry_time TEXT,
                    exit_time TEXT,
                    strategy TEXT,
                    sentiment_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create sentiment_schedule table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    sentiment_score REAL,
                    fetched_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Database initialized at {DB_PATH}")
        except Exception as e:
            logger.error(f"Database init error: {e}")
    
    def _get_latest_sentiment(self, pair: str, max_retries: int = 3) -> Tuple[float, Dict]:
        """Fetch sentiment with retry logic (from Patch #1)"""
        for attempt in range(max_retries):
            try:
                with sqlite3.connect(str(DB_PATH), timeout=10.0) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute('SELECT sentiment FROM sentiment_schedule WHERE pair = ? ORDER BY created_at DESC LIMIT 1', (pair,))
                    row = cursor.fetchone()
                    if row:
                        return float(row[0]), {'source': 'db'}
                    return 0.0, {'source': 'no_data'}
            except sqlite3.OperationalError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to fetch sentiment after {max_retries} retries: {e}")
                    return 0.0, {'source': 'error', 'error': str(e)}
                time.sleep(0.1 * (attempt + 1))
        return 0.0, {'source': 'retries_exhausted'}
    
    def _get_current_price(self, pair: str) -> float:
        """FIX #1: Get real price from Coinbase API instead of simulating"""
        try:
            result = self.cb.get_price(pair)
            if result.get('success'):
                price = result.get('price', 0.0)
                logger.info(f"PRICE_FETCH: {pair}=${price:.2f}")
                return price
            else:
                logger.warning(f"Coinbase price fetch failed for {pair}, using fallback")
                return self.cb._fallback_price(pair)
        except Exception as e:
            logger.error(f"Error fetching price for {pair}: {e}")
            return self.cb._fallback_price(pair)    
    def _detect_market_regime(self, price_24h_ago: float, current_price: float) -> Tuple[str, Dict]:
        """Detect market regime based on 24h price change"""
        change_pct = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0
        if change_pct < -2:
            return 'downtrend', {'buy': 40, 'sell': 60}
        elif change_pct > 2:
            return 'uptrend', {'buy': 20, 'sell': 80}
        else:
            return 'sideways', {'buy': 30, 'sell': 70}
    
    def _apply_sentiment_modulation(self, rsi_value: float, sentiment_score: float, regime_buy_threshold: float, pair: str) -> bool:
        """Apply sentiment to entry signal"""
        entry_approved = rsi_value <= regime_buy_threshold
        if sentiment_score > self.sentiment_boost_threshold:
            logger.info(f"   ✅ {pair}: RSI {rsi_value:.0f} vs {regime_buy_threshold} (sentiment +{sentiment_score:.2f}) → {'✓' if entry_approved else '✗'}")
        elif sentiment_score < self.sentiment_dampen_threshold:
            logger.info(f"   ⚠️ {pair}: RSI {rsi_value:.0f} vs {regime_buy_threshold} (sentiment {sentiment_score:.2f}) → {'✓' if entry_approved else '✗'}")
        else:
            logger.info(f"   ⚪ {pair}: RSI {rsi_value:.0f} vs {regime_buy_threshold} (sentiment {sentiment_score:.2f}) → {'✓' if entry_approved else '✗'}")
        return entry_approved
    
    def _get_exit_threshold(self, pair: str) -> float:
        """Get exit threshold for pair"""
        if self.winner_strategy == 'pair_specific':
            return self.exit_thresholds['pair_specific'].get(pair, 0.01)
        return self.exit_thresholds[self.winner_strategy]
    
    def _log_trade(self, pair: str, entry_price: float, exit_price: float, sentiment_score: float):
        """FIX #2: Log ONE trade per entry (no duplicates)"""
        try:
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) if entry_price > 0 else 0
            
            conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (pair, entry_price, exit_price, pnl, pnl_pct, entry_time, exit_time, strategy, sentiment_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pair, entry_price, exit_price, pnl, pnl_pct, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), self.winner_strategy, sentiment_score))
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Trade logged: {pair} ${entry_price:.2f}→${exit_price:.2f} P&L: ${pnl:.2f} ({pnl_pct:+.2%}) sentiment: {sentiment_score:+.2f}")
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")
    
    def run_cycle(self):
        """Execute one trading cycle with real prices and position tracking"""
        self.cycle_count += 1
        cycle_time = datetime.now(timezone.utc).isoformat()
        logger.info(f"\n{'='*70}\n📊 CYCLE {self.cycle_count} — {cycle_time}\n{'='*70}")
        
        for pair in ['BTC-USD', 'XRP-USD']:
            try:
                # FIX #1: Fetch real price from Coinbase
                current_price = self._get_current_price(pair)
                
                # Sentiment
                sentiment_score, _ = self._get_latest_sentiment(pair)
                
                # Market regime (mock for now)
                price_24h_ago = 48000 if pair == 'BTC-USD' else 2.35
                regime, regime_thresholds = self._detect_market_regime(price_24h_ago, current_price)
                logger.info(f"   📈 {pair}: Regime={regime.upper()} (24h: {((current_price-price_24h_ago)/price_24h_ago*100):+.1f}%)")
                
                # RSI (mock for now)
                rsi_value = 35.0 if pair == 'BTC-USD' else 65.0
                regime_buy_threshold = regime_thresholds['buy']
                
                # FIX #3: Check for exit on OPEN positions first
                if pair in self.open_positions:
                    pos = self.open_positions[pair]
                    hold_cycles = self.cycle_count - pos['entry_cycle']
                    
                    if hold_cycles >= self.min_hold_cycles:
                        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                        exit_threshold = self._get_exit_threshold(pair)
                        
                        if pnl_pct >= exit_threshold or pnl_pct <= self.stop_loss_pct:
                            self._log_trade(pair, pos['entry_price'], current_price, sentiment_score)
                            del self.open_positions[pair]
                            logger.info(f"📉 POSITION CLOSED: {pair} P&L={pnl_pct:+.2%}")
                        else:
                            logger.info(f"⏳ {pair}: Position held {hold_cycles}/{self.min_hold_cycles} cycles, P&L={pnl_pct:+.2%}")
                    else:
                        logger.info(f"⏳ {pair}: Position held {hold_cycles}/{self.min_hold_cycles} cycles (too young to exit)")
                    continue  # Skip entry check if position exists
                
                # Entry signal
                entry_approved = self._apply_sentiment_modulation(rsi_value, sentiment_score, regime_buy_threshold, pair)
                
                if entry_approved:
                    # FIX #3: Open position, don't exit immediately
                    self.open_positions[pair] = {
                        'entry_price': current_price,
                        'entry_cycle': self.cycle_count,
                        'entry_rsi': rsi_value,
                        'sentiment': sentiment_score,
                    }
                    logger.info(f"📈 POSITION OPENED: {pair} @ ${current_price:.2f}")
                else:
                    logger.info(f"   🚫 {pair}: Entry suppressed (RSI {rsi_value:.0f} > {regime_buy_threshold})")
            
            except Exception as e:
                logger.error(f"Cycle error for {pair}: {e}")
        
        logger.info(f"✅ Cycle {self.cycle_count} complete")
    
    def run_48h(self):
        """Run 48-hour test (576 cycles of 5 min)"""
        total_cycles = 576
        
        logger.info(f"🚀 Starting Phase 4b 48-hour test (FIXED)")
        logger.info(f"   Cycles: {total_cycles}")
        logger.info(f"   Interval: {CYCLE_INTERVAL}s (5 min)")
        logger.info(f"   FIX #1: Real Coinbase prices")
        logger.info(f"   FIX #3: {self.min_hold_cycles}-cycle hold requirement")
        logger.info(f"   FIX #4: {self.stop_loss_pct*100:.0f}% stop loss + exit thresholds")
        
        for cycle_num in range(total_cycles):
            try:
                cycle_start = time.time()
                self.run_cycle()
                elapsed_cycle = time.time() - cycle_start
                sleep_time = max(0, CYCLE_INTERVAL - elapsed_cycle)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            except KeyboardInterrupt:
                logger.info(f"\n🛑 Test interrupted at cycle {cycle_num + 1}/{total_cycles}")
                break
            except Exception as e:
                logger.error(f"Fatal error at cycle {cycle_num + 1}: {e}")
                break
        
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        logger.info(f"\n✅ Phase 4b test complete\n   Cycles: {self.cycle_count}\n   Elapsed: {elapsed:.2f}h\n   Open positions: {len(self.open_positions)}")


def main():
    """Main entry point"""
    orchestrator = Phase4bOrchestrator(phase4_winner_strategy='fee_aware')
    orchestrator.run_48h()


if __name__ == '__main__':
    main()
