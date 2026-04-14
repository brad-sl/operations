#!/usr/bin/env python3
"""
Phase 4b Real Data Only — 24h paper trade test with EXPLICIT data sourcing

THIS IS A LIVE TEST. NO SYNTHETIC DATA.

Requirements before launch:
- Real Coinbase API access (production endpoint)
- Real X sentiment data (via x_sentiment_cache.json OR X API bearer token in .env)

If either data source is unavailable, the bot FAILS LOUDLY rather than falling back to fake data.

This ensures end-to-end functionality testing with real market conditions.
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
SENTIMENT_CACHE = BASE / "x_sentiment_cache.json"

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(PHASE4_ACTIVITY_FILE)),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

class RealDataOnlyPhase4bRunner:
    def __init__(self, duration_hours=24):
        self.duration_hours = duration_hours
        self.start_time = datetime.utcnow()
        self.cycle_count = 0
        self.pairs = ["BTC-USD", "XRP-USD"]
        self.activity_log = []
        self.positions = {p: {"active": False, "entry_price": None, "signal": None} for p in self.pairs}
        self.prices = {"BTC-USD": None, "XRP-USD": None}
        self.th = {
            "BTC-USD": {"buy": 30, "sell": 70},
            "XRP-USD": {"buy": 35, "sell": 65}
        }
        
        # Verify real data is available BEFORE starting
        self._verify_data_sources()
        
        self._backup_existing()
        self._reset_logs()
        logger.info("✅ Phase 4b REAL DATA ONLY Runner Started (24h paper trade)")
        logger.info(f"  Pairs: {self.pairs}")
        logger.info(f"  Duration: {self.duration_hours} hours")
        logger.info("  Data sources: Coinbase API (prices), X Sentiment Cache (sentiment)")
        logger.info("  Fallback policy: FAIL LOUDLY if real data unavailable")

    def _verify_data_sources(self):
        """Verify that real data sources are available BEFORE we start."""
        logger.info("🔍 Verifying data sources...")
        
        # Check sentiment cache exists
        if not SENTIMENT_CACHE.exists():
            logger.error(f"❌ FATAL: Sentiment cache not found at {SENTIMENT_CACHE}")
            logger.error("   To run live test, populate x_sentiment_cache.json with real X sentiment data")
            logger.error("   Format: {'BTC-USD': {'sentiment': 0.5}, 'XRP-USD': {'sentiment': -0.2}}")
            raise RuntimeError("Missing sentiment cache. Cannot proceed without real sentiment data.")
        
        # Verify sentiment cache has required pairs
        try:
            with open(SENTIMENT_CACHE, 'r') as f:
                cache = json.load(f)
                for pair in self.pairs:
                    if pair not in cache:
                        logger.error(f"❌ FATAL: {pair} not in sentiment cache")
                        raise RuntimeError(f"Sentiment cache missing {pair}. Aborting.")
                logger.info(f"✅ Sentiment cache verified: {list(cache.keys())}")
        except Exception as e:
            logger.error(f"❌ FATAL: Failed to read sentiment cache: {e}")
            raise RuntimeError(f"Sentiment cache error: {e}")
        
        # Test Coinbase API connectivity
        try:
            url = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                logger.info("✅ Coinbase API connectivity verified")
            else:
                raise RuntimeError(f"Coinbase API returned {r.status_code}")
        except Exception as e:
            logger.error(f"❌ FATAL: Coinbase API unreachable: {e}")
            raise RuntimeError(f"Coinbase API error: {e}")

    def _backup_existing(self):
        """Backup old data to avoid mixing runs."""
        backups = []
        if PHASE4_TRADES_JSON.exists():
            bak = PHASE4_TRADES_JSON.with_suffix(f".bak.{int(time.time())}")
            shutil.copy2(PHASE4_TRADES_JSON, bak)
            backups.append(str(bak))
        if PHASE4_ACTIVITY_LOG.exists():
            bak2 = PHASE4_ACTIVITY_LOG.with_suffix(f".bak.{int(time.time())}")
            shutil.copy2(PHASE4_ACTIVITY_LOG, bak2)
            backups.append(str(bak2))
        if backups:
            logger.info(f"🔒 Backed up old data: {', '.join(backups)}")

    def _reset_logs(self):
        """Reset logs to fresh state."""
        self.activity = []
        self.trades = []
        with open(PHASE4_ACTIVITY_LOG, 'w') as f:
            json.dump([], f, indent=2)
        with open(PHASE4_TRADES_JSON, 'w') as f:
            json.dump([], f, indent=2)
        PHASE4_ACTIVITY_LOG.touch(exist_ok=True)
        PHASE4_TRADES_JSON.touch(exist_ok=True)

    def fetch_price(self, pair):
        """Fetch REAL price from Coinbase API. No fallback."""
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                price = float(data.get('price', 0.0))
                if price > 0:
                    logger.debug(f"🔗 Price fetch SUCCESS: {pair} = ${price}")
                    return price
        except Exception as e:
            logger.error(f"❌ Price fetch FAILED for {pair}: {e}")
        
        # NO FALLBACK — fail explicitly
        raise RuntimeError(f"Cannot fetch real price for {pair}. Data source unavailable.")

    def get_sentiment(self, pair):
        """Fetch REAL sentiment from cache. No synthetic fallback."""
        try:
            if SENTIMENT_CACHE.exists():
                with open(SENTIMENT_CACHE, 'r') as f:
                    cache = json.load(f)
                    if pair in cache and 'sentiment' in cache[pair]:
                        sentiment = float(cache[pair]['sentiment'])
                        logger.debug(f"📊 Sentiment fetch SUCCESS: {pair} = {sentiment}")
                        return sentiment
        except Exception as e:
            logger.error(f"❌ Sentiment cache read error: {e}")
        
        # NO FALLBACK — fail explicitly
        raise RuntimeError(f"Cannot fetch real sentiment for {pair}. Cache unavailable or invalid.")

    def calculate_rsi(self, pair):
        """Fetch REAL RSI from Coinbase candles. No synthetic fallback."""
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/candles"
            r = requests.get(url, params={"granularity": 300, "limit": 100}, timeout=10)
            if r.status_code == 200:
                candles = r.json()
                if len(candles) >= 14:
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
                        rsi = 100.0
                    else:
                        rs = avg_gain / avg_loss
                        rsi = 100.0 - (100.0 / (1.0 + rs))
                    logger.debug(f"📈 RSI fetch SUCCESS: {pair} = {rsi:.1f}")
                    return rsi
        except Exception as e:
            logger.error(f"❌ RSI calculation FAILED for {pair}: {e}")
        
        # NO FALLBACK — fail explicitly
        raise RuntimeError(f"Cannot calculate real RSI for {pair}. API error.")

    def run_cycle(self):
        """Execute one trading cycle with REAL data only."""
        self.cycle_count += 1
        now = datetime.utcnow()
        cycle_data = {
            "cycle": self.cycle_count,
            "timestamp": now.isoformat(),
            "pairs": {},
            "data_sources": {}
        }
        
        try:
            for pair in self.pairs:
                # Fetch price (REAL ONLY)
                try:
                    price = self.fetch_price(pair)
                    self.prices[pair] = price
                except RuntimeError as e:
                    logger.error(f"CYCLE {self.cycle_count} ABORTED: {e}")
                    raise
                
                # Calculate RSI (REAL ONLY)
                try:
                    rsi = self.calculate_rsi(pair)
                except RuntimeError as e:
                    logger.error(f"CYCLE {self.cycle_count} ABORTED: {e}")
                    raise
                
                # Get sentiment (REAL ONLY)
                try:
                    sentiment = self.get_sentiment(pair)
                except RuntimeError as e:
                    logger.error(f"CYCLE {self.cycle_count} ABORTED: {e}")
                    raise
                
                # Check entry/exit signals
                threshold = self.th[pair]
                position = self.positions[pair]
                
                pair_data = {
                    "pair": pair,
                    "price": price,
                    "rsi": rsi,
                    "sentiment": sentiment,
                    "position": position["active"],
                    "signals": []
                }
                
                # Entry logic
                if not position["active"]:
                    if rsi < threshold["buy"] and sentiment > -0.2:
                        pair_data["signals"].append("BUY_SIGNAL")
                        position["active"] = True
                        position["entry_price"] = price
                        position["signal"] = "BUY"
                        logger.info(f"✅ ENTRY: {pair} @ ${price:.2f} (RSI={rsi:.1f}, sentiment={sentiment:.2f})")
                
                # Exit logic
                if position["active"]:
                    if rsi > threshold["sell"]:
                        pair_data["signals"].append("SELL_SIGNAL")
                        profit_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                        position["active"] = False
                        logger.info(f"✅ EXIT: {pair} @ ${price:.2f} (P&L={profit_pct:+.2f}%)")
                
                cycle_data["pairs"][pair] = pair_data
        
        except RuntimeError as e:
            logger.error(f"🛑 CYCLE {self.cycle_count} FAILED — stopping runner")
            raise
        
        # Log cycle to JSON
        self.activity.append(cycle_data)
        with open(PHASE4_ACTIVITY_LOG, 'w') as f:
            json.dump(self.activity, f, indent=2)
        
        logger.info(f"📊 Cycle {self.cycle_count} COMPLETE: BTC=${self.prices['BTC-USD']:.2f}, XRP=${self.prices['XRP-USD']:.4f}")

    def run(self):
        """Run 24-hour test with REAL data only."""
        logger.info("🚀 Starting Phase 4b REAL DATA ONLY 24-hour test loop...")
        cycle_interval = 300  # 5 minutes per cycle
        max_cycles = (self.duration_hours * 3600) // cycle_interval
        
        try:
            for cycle in range(max_cycles):
                self.run_cycle()
                elapsed = (datetime.utcnow() - self.start_time).total_seconds()
                if elapsed > (self.duration_hours * 3600):
                    logger.info(f"✅ 24-hour window complete. Total cycles: {self.cycle_count}")
                    break
                time.sleep(cycle_interval)
        except KeyboardInterrupt:
            logger.info("⏹️ User interrupt. Saving logs...")
        except RuntimeError as e:
            logger.error(f"❌ FATAL ERROR: {e}")
            logger.error("Test terminated due to data source failure.")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        finally:
            logger.info(f"📝 Activity log: {PHASE4_ACTIVITY_LOG}")
            logger.info(f"📊 Trades log: {PHASE4_TRADES_JSON}")

if __name__ == "__main__":
    runner = RealDataOnlyPhase4bRunner(duration_hours=24)
    runner.run()
