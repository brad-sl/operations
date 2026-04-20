#!/usr/bin/env python3
"""
Phase 4 v1 — Fixed with Activity Logging
==========================================
Adds detailed price/sentiment logging every 30 minutes + trade execution logs.
"""

import json
import time
import logging
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/PHASE4_ACTIVITY.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE = Path("/home/brad/.openclaw/workspace/operations/crypto-bot")

class ActivityMonitor:
    """Logs prices, sentiment, RSI every 30 minutes."""
    
    def __init__(self):
        self.log_file = BASE / "PHASE4_ACTIVITY_LOG.json"
        self.last_log = None
        self.activity_log = []
    
    def should_log(self):
        """Log every 30 minutes."""
        now = datetime.utcnow()
        if not self.last_log:
            self.last_log = now
            return True
        
        if (now - self.last_log).total_seconds() >= 1800:  # 30 min
            self.last_log = now
            return True
        
        return False
    
    def log_activity(self, pair, price, rsi, sentiment, regime):
        """Log market snapshot."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "price": round(price, 2),
            "rsi": round(rsi, 2),
            "sentiment": round(sentiment, 3),
            "regime": regime
        }
        self.activity_log.append(entry)
        logger.info(f"📊 ACTIVITY: {pair} | Price: ${entry['price']} | RSI: {entry['rsi']} | Sentiment: {entry['sentiment']} | Regime: {regime}")
        
        # Write to JSON
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.activity_log[-1000:], f, indent=2)  # Keep last 1000
        except:
            pass

class TradeLogger:
    """Logs all trade executions."""
    
    def __init__(self):
        self.trade_file = BASE / "PHASE4_TRADES.json"
        self.trades = []
    
    def log_entry(self, pair, signal, price, rsi, sentiment):
        """Log entry signal."""
        entry = {
            "type": "ENTRY",
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "signal": signal,
            "entry_price": round(price, 2),
            "entry_rsi": round(rsi, 2),
            "entry_sentiment": round(sentiment, 3)
        }
        self.trades.append(entry)
        logger.warning(f"🟢 ENTRY: {pair} {signal} @ ${entry['entry_price']} (RSI: {entry['entry_rsi']})")
        self._save()
    
    def log_exit(self, pair, exit_price, exit_rsi, pnl):
        """Log exit."""
        exit_entry = {
            "type": "EXIT",
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "exit_price": round(exit_price, 2),
            "exit_rsi": round(exit_rsi, 2),
            "pnl": round(pnl, 2)
        }
        self.trades.append(exit_entry)
        status = "✅" if pnl > 0 else "❌"
        logger.warning(f"🔴 EXIT: {pair} @ ${exit_entry['exit_price']} (RSI: {exit_entry['exit_rsi']}) {status} P&L: ${pnl}")
        self._save()
    
    def _save(self):
        try:
            with open(self.trade_file, 'w') as f:
                json.dump(self.trades, f, indent=2)
        except:
            pass

class DynamicRSIOrchestrator:
    """Main orchestrator with detailed logging."""
    
    def __init__(self):
        self.pairs = ["BTC-USD", "XRP-USD"]
        self.start_time = datetime.utcnow()
        self.duration_hours = 72
        self.cycle_count = 0
        
        self.activity_monitor = ActivityMonitor()
        self.trade_logger = TradeLogger()
        
        # Thresholds
        self.thresholds = {
            "BTC-USD": {"buy": 30, "sell": 70},
            "XRP-USD": {"buy": 35, "sell": 65}
        }
        
        # Positions
        self.positions = {pair: {"active": False, "entry_price": None, "signal": None} for pair in self.pairs}
        
        logger.info("✅ Phase 4 Orchestrator Started")
        logger.info(f"   Duration: {self.duration_hours} hours")
        logger.info(f"   Pairs: {self.pairs}")
        logger.info(f"   Activity Log: PHASE4_ACTIVITY_LOG.json (every 30 min)")
        logger.info(f"   Trade Log: PHASE4_TRADES.json (per trade)")
    
    def fetch_price(self, pair):
        """Get real price from Coinbase."""
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return float(r.json()['price'])
        except:
            pass
        
        return {"BTC-USD": 67500, "XRP-USD": 2.45}.get(pair, 100)
    
    def get_sentiment(self, pair):
        """Get X API sentiment."""
        cache_file = BASE / "x_sentiment_cache.json"
        try:
            if cache_file.exists():
                with open(cache_file) as f:
                    cache = json.load(f)
                    if pair in cache:
                        return cache[pair].get("sentiment", 0)
        except:
            pass
        
        # Fallback: deterministic based on hour
        hour = datetime.utcnow().hour
        if 14 <= hour < 21:
            return 0.3
        elif 0 <= hour < 7:
            return -0.1
        return -0.2
    
    def calculate_rsi(self, pair):
        """Fetch candles and calculate RSI."""
        try:
            url = f"https://api.exchange.coinbase.com/products/{pair}/candles"
            r = requests.get(url, params={"granularity": 300, "limit": 100}, timeout=10)
            
            if r.status_code == 200:
                candles = r.json()
                prices = [float(c[4]) for c in candles[-14:]]
                
                gains = sum(max(0, prices[i] - prices[i-1]) for i in range(1, len(prices))) / len(prices)
                losses = sum(max(0, prices[i-1] - prices[i]) for i in range(1, len(prices))) / len(prices)
                
                if losses == 0:
                    return 100.0 if gains > 0 else 0.0
                
                rs = gains / losses
                return 100 - (100 / (1 + rs))
        except:
            pass
        
        return 50.0
    
    def run_cycle(self):
        """Execute one trading cycle."""
        self.cycle_count += 1
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        
        if elapsed > self.duration_hours * 3600:
            logger.info(f"✅ Duration complete ({self.duration_hours}h)")
            return False
        
        logger.debug(f"\n🔄 Cycle {self.cycle_count}")
        
        for pair in self.pairs:
            price = self.fetch_price(pair)
            rsi = self.calculate_rsi(pair)
            sentiment = self.get_sentiment(pair)
            regime = "NORMAL"  # Simplified
            
            # Log every 30 min
            if self.activity_monitor.should_log():
                self.activity_monitor.log_activity(pair, price, rsi, sentiment, regime)
            
            # Trading logic
            thresholds = self.thresholds[pair]
            position = self.positions[pair]
            
            # Entry
            if not position["active"]:
                if rsi < thresholds["buy"]:
                    position["active"] = True
                    position["entry_price"] = price
                    position["signal"] = "BUY"
                    self.trade_logger.log_entry(pair, "BUY", price, rsi, sentiment)
                
                elif rsi > thresholds["sell"]:
                    position["active"] = True
                    position["entry_price"] = price
                    position["signal"] = "SELL"
                    self.trade_logger.log_entry(pair, "SELL", price, rsi, sentiment)
            
            # Exit
            elif position["signal"] == "BUY" and rsi > thresholds["sell"]:
                pnl = price - position["entry_price"]
                self.trade_logger.log_exit(pair, price, rsi, pnl)
                position["active"] = False
            
            elif position["signal"] == "SELL" and rsi < thresholds["buy"]:
                pnl = position["entry_price"] - price
                self.trade_logger.log_exit(pair, price, rsi, pnl)
                position["active"] = False
        
        return True
    
    def run(self):
        """Main loop."""
        logger.info("🚀 Starting Phase 4 Trading")
        
        while self.run_cycle():
            time.sleep(300)  # 5 min
        
        logger.info("✅ Phase 4 Complete")

if __name__ == "__main__":
    orchestrator = DynamicRSIOrchestrator()
    orchestrator.run()
