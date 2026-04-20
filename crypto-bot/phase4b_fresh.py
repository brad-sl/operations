#!/usr/bin/env python3
"""
Phase 4b Fresh Runner — 24h paper trade test (fresh data repo)

This script:
- Backs up existing phase4 data files
- Resets in-memory data structures and logs to fresh state
- Runs a 24-hour paper-trade cycle (5-minute cadence) with robust price/sentiment handling
- Logs activity and trades to PHASE4_ACTIVITY_LOG.json and PHASE4_TRADES.json
- Avoids DB schema dependencies for sentiment; uses a deterministic fallback if needed

Usage:
  - Normal run: python3 phase4b_fresh.py
  - Quick validation: FAST_VALIDATION=1 python3 phase4b_fresh.py
"""

import json
import time
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
import requests

BASE = Path("/home/brad/.openclaw/workspace/operations/crypto-bot")
PHASE4_ACTIVITY_LOG = BASE / "PHASE4_ACTIVITY_LOG.json"
PHASE4_TRADES_JSON = BASE / "PHASE4_TRADES.json"
PHASE4_ACTIVITY_FILE = BASE / "PHASE4_ACTIVITY.log"

# Logging config (also logs to PHASE4_ACTIVITY.log for long-term tracing)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(PHASE4_ACTIVITY_FILE)),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

SENTIMENT_CACHE = BASE / "x_sentiment_cache.json"

class FreshPhase4bRunner:
    def __init__(self, duration_hours=24, fast=False):
        self.duration_hours = duration_hours
        self.fast = fast
        self.start_time = datetime.utcnow()
        self.cycle_count = 0
        self.pairs = ["BTC-USD", "XRP-USD"]
        self.activity_log = []
        self.positions = {p: {"active": False, "entry_price": None, "signal": None} for p in self.pairs}
        self.prices = {"BTC-USD": 67500.0, "XRP-USD": 2.50}
        self.th = {
            "BTC-USD": {"buy": 30, "sell": 70},
            "XRP-USD": {"buy": 35, "sell": 65}
        }
        self._backup_existing()
        self._reset_logs()
        logger.info("✅ Phase 4b Fresh Runner Started (24h)" )
        logger.info(f"  Pairs: {self.pairs}")
        logger.info(f"  Duration: {self.duration_hours} hours")
        self._log_banner()

    def _backup_existing(self):
        # Create backups of existing data to avoid mixing old/new runs
        backups = []
        if PHASE4_TRADES_JSON.exists():
            bak = PHASE4_TRADES_JSON.with_suffix(
                ".bak.{}".format(int(time.time()))
            )
            shutil.copy2(PHASE4_TRADES_JSON, bak)
            backups.append(str(bak))
        if PHASE4_ACTIVITY_LOG.exists():
            bak2 = PHASE4_ACTIVITY_LOG.with_suffix(
                ".bak.{}".format(int(time.time()))
            )
            shutil.copy2(PHASE4_ACTIVITY_LOG, bak2)
            backups.append(str(bak2))
        if backups:
            logger.info(f"🔒 Backed up old data: {', '.join(backups)}")

    def _reset_logs(self):
        # Reset in-memory logs to a clean state
        self.activity = []
        self.trades = []
        # Create empty JSON files for fresh run
        with open(PHASE4_ACTIVITY_LOG, 'w') as f:
            json.dump([], f, indent=2)
        with open(PHASE4_TRADES_JSON, 'w') as f:
            json.dump([], f, indent=2)
        # Ensure initial log files exist
        PHASE4_ACTIVITY_LOG.touch(exist_ok=True)
        PHASE4_TRADES_JSON.touch(exist_ok=True)

    def _log_banner(self):
        logger.info("Phase 4 fresh run initialized. 24h window. 5-min cadence.")

    def fetch_price(self, pair):
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                return float(data.get('price', 0.0))
        except Exception as e:
            logger.warning(f"Price fetch error for {pair}: {e}")
        # Fallbacks
        return {"BTC-USD": 67500.0, "XRP-USD": 2.50}.get(pair, 100.0)

    def get_sentiment(self, pair):
        # Prefer cached sentiment if available
        try:
            if SENTIMENT_CACHE.exists():
                with open(SENTIMENT_CACHE, 'r') as f:
                    cache = json.load(f)
                    if pair in cache:
                        return float(cache[pair].get("sentiment", 0.0))
        except Exception:
            pass
        # Deterministic fallback by hour (sandbox-safe)
        hour = datetime.utcnow().hour
        if 14 <= hour < 21:
            return 0.3
        if 0 <= hour < 7:
            return -0.1
        return -0.2

    def calculate_rsi(self, pair):
        # Robust RSI with minimal external calls
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/candles"
            r = requests.get(url, params={"granularity": 300, "limit": 100}, timeout=10)
            if r.status_code == 200:
                candles = r.json()
                closes = [float(c[4]) for c in candles[-14:]]
                gains = []
                losses = []
                for i in range(1, len(closes)):
                    delta = closes[i] - closes[i-1]
                    if delta >= 0:
                        gains.append(delta)
                        losses.append(0.0)
                    else:
                        gains.append(0.0)
                        losses.append(abs(delta))
                avg_gain = sum(gains) / len(gains)
                avg_loss = sum(losses) / len(losses)
                if avg_loss == 0:
                    return 100.0
                rs = avg_gain / avg_loss
                return