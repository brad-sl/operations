#!/usr/bin/env python3
"""
phase5_multi_pair.py — Phase 5 Multi-Pair Trading Harness
StochRSI crossover + 2×ATR adaptive stops
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# ── Path setup ──────────────────────────────────────────────────────────────
BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(BOT_DIR))

from dotenv import load_dotenv
load_dotenv(BOT_DIR / '.env')

# ── Imports ─────────────────────────────────────────────────────────────────
from indicators.stochrsi_strategy import StochRSISignalCalculator, ATRStopCalculator, compute_atr
from x_sentiment_fetcher import XSentimentFetcher
from test_price_wrapper import get_price_wrapper
from prometheus_client import Gauge, start_http_server

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
CONFIG_PATH = BOT_DIR / 'config' / 'trading_config_phase5.json'
DB_PATH = BOT_DIR / 'phase4_trades.db'

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

PAIRS = CONFIG['pairs']
CYCLE_INTERVAL = CONFIG['cycle_interval_seconds']
STOCHRSI_CFG = CONFIG['stochrsi']
ATR_CFG = CONFIG['atr']
EXIT_CFG = CONFIG['exit']
RISK_CFG = CONFIG['risk']

# ── Database Setup ──────────────────────────────────────────────────────────
def init_db():
    """Ensure trades table exists"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            strategy TEXT DEFAULT 'phase5_stochrsi',
            sentiment_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_trade(pair: str, entry_price: float, exit_price: Optional[float], 
              pnl: Optional[float], pnl_pct: Optional[float], 
              entry_time: str, exit_time: Optional[str], sentiment: Optional[float]):
    """Log trade to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (pair, entry_price, exit_price, pnl, pnl_pct, 
                           entry_time, exit_time, strategy, sentiment_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pair, entry_price, exit_price, pnl, pnl_pct, 
          entry_time, exit_time, 'phase5_stochrsi', sentiment))
    conn.commit()
    conn.close()

# ── Main Trading Loop ──────────────────────────────────────────────────────
class Phase5Harness:
    def __init__(self):
        self.positions = {}  # {pair: {'entry_price', 'entry_time', 'atr_sl', 'sentiment'}}
        self.daily_pnl = defaultdict(float)
        self.price_wrapper = get_price_wrapper()
        self.sentiment_fetcher = XSentimentFetcher()
        
        # Initialize StochRSI & ATR calculators per pair
        self.stochrsi_calcs = {
            pair: StochRSISignalCalculator(
                rsi_period=STOCHRSI_CFG['rsi_period'],
                k_smooth=STOCHRSI_CFG['k_smooth'],
                d_smooth=STOCHRSI_CFG['d_smooth'],
                oversold_threshold=STOCHRSI_CFG['oversold_threshold'],
                sentiment_weight=STOCHRSI_CFG['sentiment_weight']
            )
            for pair in PAIRS
        }
        self.atr_calc = ATRStopCalculator(
            atr_multiple=ATR_CFG['multiple'],
            min_sl_pct=ATR_CFG['min_sl_pct'],
            max_sl_pct=ATR_CFG['max_sl_pct']
        )
        self.price_history = {pair: [] for pair in PAIRS}
        
        start_http_server(8502)
        logger.info("Prometheus metrics server started on :8502")
        
        self.cycles_total = Gauge('crypto_cycles_total', 'Total trading cycles completed')
        self.pnl_usd = Gauge('crypto_pnl_usd', 'PnL USD', ['pair'])
        self.unrealized_pnl = Gauge('crypto_unrealized_pnl_usd', 'Unrealized PnL USD', ['pair'])
        self.hold_time = Gauge('crypto_hold_time_seconds', 'Hold time in seconds', ['pair'])
        self.positions_open = Gauge('crypto_positions_open', 'Open positions (1 or 0)', ['pair'])
    
    def run(self, cycles: int = 288):
        """Run trading harness for N cycles"""
        init_db()
        logger.info(f"Phase 5 Harness starting — {cycles} cycles, {CYCLE_INTERVAL}s interval")
        
        for cycle in range(1, cycles + 1):
            logger.info(f"\n{'='*70}")
            logger.info(f"CYCLE {cycle}/{cycles} — {datetime.now(timezone.utc).isoformat()}")
            logger.info(f"{'='*70}")
            
            for pair in PAIRS:
                try:
                    self._process_pair(pair, cycle)
                except Exception as e:
                    logger.error(f"Error processing {pair}: {e}", exc_info=True)
            
            self.cycles_total.inc()
            
            # Reset daily PnL at midnight
            if datetime.now().hour == 0 and datetime.now().minute < 5:
                self.daily_pnl.clear()
                logger.info("Daily PnL reset")
            
            logger.info(f"Cycle {cycle} complete. Sleeping {CYCLE_INTERVAL}s...")
            time.sleep(CYCLE_INTERVAL)
    
    def _process_pair(self, pair: str, cycle: int):
        """Process single pair: fetch price, signal, execute"""
        
        # ── Fetch price ─────────────────────────────────────────────────────
        price = self.price_wrapper.get_price(pair)
        logger.info(f"PRICE_FETCH: {pair}={float(price):.4f} [exchange public]")
        
        # Build price history
        self.price_history[pair].append(price)
        self.price_history[pair] = self.price_history[pair][-100:]  # Keep last 100
        
        # ── Fetch sentiment (cached) ────────────────────────────────────────
        sentiment = self.sentiment_fetcher.fetch_sentiment(pair)
        if sentiment is None:
            logger.warning(f"Sentiment unavailable for {pair}, proceeding without filter")
            sentiment_use = None
        else:
            sentiment_use = sentiment
        
        # ── Compute StochRSI signal ─────────────────────────────────────────
        calc = self.stochrsi_calcs[pair]
        signal, confidence = calc.detect_signal(self.price_history[pair], sentiment_use)
        
        ctx = calc.get_signal_context()
        logger.info(f"[{pair}] Signal={signal} (conf={confidence:.2f}) | "
                   f"StochRSI K={ctx['k']:.1f} D={ctx['d']:.1f}")
        
        # ── Entry Logic ─────────────────────────────────────────────────────
        if signal == 'BUY' and pair not in self.positions:
            # Compute ATR for adaptive stop
            if len(self.price_history[pair]) >= ATR_CFG['period']:
                # Simulate OHLCV: use close, high, low as close (for demo)
                import pandas as pd
                prices_arr = np.array(self.price_history[pair])
                df = pd.DataFrame({
                    'h': prices_arr * 1.001,  # Simulate wicks
                    'l': prices_arr * 0.999,
                    'c': prices_arr
                })
                atr = compute_atr(df, ATR_CFG['period'])
            else:
                atr = price * 0.02  # Default 2% if not enough data
            
            sl_pct = self.atr_calc.get_stop_loss_pct(price, atr)
            
            entry = {
                'entry_price': price,
                'entry_time': datetime.now(timezone.utc).isoformat(),
                'atr_sl_pct': sl_pct,
                'atr': atr,
                'sentiment': sentiment,
                'confidence': confidence
            }
            self.positions[pair] = entry
            logger.info(f"[{pair}] BUY @ {price:.4f} | ATR={atr:.4f} | SL={sl_pct*100:.1f}%")
            
            # Log entry
            log_trade(pair, price, None, None, None, entry['entry_time'], None, sentiment)
        
        # ── Exit Logic ──────────────────────────────────────────────────────
        if pair in self.positions:
            pos = self.positions[pair]
            entry_price = pos['entry_price']
            pnl_pct = (price - entry_price) / entry_price
            pnl = price - entry_price
            
            # Check TP
            if pnl_pct >= EXIT_CFG['take_profit_pct']:
                logger.info(f"[{pair}] CLOSE (TP) @ {price:.4f} | PnL={pnl:.2f} ({pnl_pct*100:.1f}%)")
                self._close_position(pair, price, pnl_pct, 'TP', pos)
            
            # Check SL
            elif pnl_pct <= pos['atr_sl_pct']:
                logger.info(f"[{pair}] CLOSE (SL) @ {price:.4f} | PnL={pnl:.2f} ({pnl_pct*100:.1f}%)")
                self._close_position(pair, price, pnl_pct, 'SL', pos)
            
            # Check daily cap
            if self.daily_pnl[pair] + pnl <= -RISK_CFG['daily_loss_cap_usd']:
                logger.warning(f"[{pair}] Daily loss cap hit! Pausing pair.")
                # In production: skip further trades for this pair today
            
            # Update Prometheus metrics
            if pair in self.positions:
                pos = self.positions[pair]
                entry_ts = datetime.fromisoformat(pos['entry_time'].replace('Z', '+00:00')).timestamp()
                hold_sec = time.time() - entry_ts
                unreal_pnl = price - pos['entry_price']
                self.hold_time.labels(pair).set(hold_sec)
                self.unrealized_pnl.labels(pair).set(unreal_pnl)
                self.positions_open.labels(pair).set(1)
                total_pnl = self.daily_pnl[pair] + unreal_pnl
                self.pnl_usd.labels(pair).set(total_pnl)
            else:
                self.hold_time.labels(pair).set(0)
                self.unrealized_pnl.labels(pair).set(0)
                self.positions_open.labels(pair).set(0)
                self.pnl_usd.labels(pair).set(self.daily_pnl[pair])
    
    def _close_position(self, pair: str, exit_price: float, pnl_pct: float, reason: str, pos: dict):
        """Close position and log trade"""
        pnl = (exit_price - pos['entry_price'])
        exit_time = datetime.now(timezone.utc).isoformat()
        
        self.daily_pnl[pair] += pnl
        
        log_trade(pair, pos['entry_price'], exit_price, pnl, pnl_pct, 
                 pos['entry_time'], exit_time, pos['sentiment'])
        
        del self.positions[pair]

# ── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 5 Multi-Pair Trading Harness')
    parser.add_argument('--cycles', type=int, default=288, help='Number of cycles to run')
    args = parser.parse_args()
    
    import numpy as np
    
    harness = Phase5Harness()
    harness.run(cycles=args.cycles)
