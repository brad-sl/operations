#!/usr/bin/env python3
"""
Phase 5 Minimal Logging Version
Only logs: Trades, Errors, Startup/Shutdown, Status every N cycles
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from random import uniform
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Custom modules
from price_wrapper import PublicExchangePriceWrapper
try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    ADVANCED_TRADE_AVAILABLE = False
    CoinbaseAdvancedClient = None

try:
    from phase5_order_executor_wrapper import OrderExecutorWrapper
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = True
except ImportError:
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = False
    OrderExecutorWrapper = None

# Suppress verbose library logging
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

MAX_BATCH_SIZE = 20
STATUS_LOG_INTERVAL = 100  # Log status every 100 cycles

class Phase5MinimalLogger:
    """Minimal logging - only important events"""
    
    def __init__(self, log_file):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Only file handler - no console spam
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        
        # Suppress verbose library logging
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    def trade(self, msg):
        """Log trades"""
        self.logger.info(f"🔴 TRADE: {msg}")
    
    def error(self, msg):
        """Log errors"""
        self.logger.error(f"❌ ERROR: {msg}")
    
    def status(self, msg):
        """Log status updates"""
        self.logger.info(f"📊 STATUS: {msg}")
    
    def startup(self, msg):
        """Log startup events"""
        self.logger.info(f"🚀 STARTUP: {msg}")
    
    def shutdown(self, msg):
        """Log shutdown events"""
        self.logger.info(f"🛑 SHUTDOWN: {msg}")


class Phase5Harness:
    def __init__(self, config_path=None):
        load_dotenv()
        
        # Setup minimal logging
        log_file = os.path.join(os.path.dirname(__file__), 'logs', 'phase5_live.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        self.logger = Phase5MinimalLogger(log_file)
        
        # Load configuration
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), 
            'config', 
            'trading_config_phase5.json'
        )
        self.config = self._load_config()
        
        # Initialize components
        self.sandbox = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'
        self.price_wrapper = PublicExchangePriceWrapper()
        self.cb_client = None
        
        if ADVANCED_TRADE_AVAILABLE:
            try:
                self.cb_client = CoinbaseAdvancedClient(test_mode=self.sandbox)
                self.logger.startup(f"Coinbase Advanced Trade API (sandbox={self.sandbox})")
            except Exception as e:
                self.logger.error(f"Advanced Trade API init failed: {e}")
                self.cb_client = None
        
        self.pairs = self.config.get('global_settings', {}).get('pairs', [])
        self.total_capital = self.config.get('global_settings', {}).get('total_capital', 1000)
        self.order_size_usd = self.config.get('global_settings', {}).get('order_size_usd', 25.0)
        self.sandbox_trading = os.getenv('SANDBOX_TRADING', 'True').lower() == 'true'
        
        self.executor_wrapper = None
        if ORDER_EXECUTOR_WRAPPER_AVAILABLE and self.sandbox_trading:
            try:
                self.executor_wrapper = OrderExecutorWrapper(
                    cb_client=self.cb_client,
                    sandbox_mode=self.sandbox_trading,
                    order_size_usd=self.order_size_usd,
                    logger=self.logger.logger
                )
                self.logger.startup(f"Phase 6 OrderExecutor (order_size=${self.order_size_usd})")
            except Exception as e:
                self.logger.error(f"OrderExecutor init failed: {e}")
        
        # Initialize price history
        self.price_history = {pair: [] for pair in self.pairs}
        self.sentiment_cache_file = os.path.join(os.path.dirname(__file__), 'sentiment_cache.json')
        self.cycle_count = 0
        
        self.logger.startup(f"Phase 5 Ready: {len(self.pairs)} pairs, ${self.total_capital} capital")
    
    def _load_config(self):
        """Load trading configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Could not load config: {e}")
            return {'global_settings': {'pairs': ['BTC-USD'], 'total_capital': 1000}}
    
    def get_sentiment(self, pair):
        """Load sentiment from cache"""
        try:
            if os.path.exists(self.sentiment_cache_file):
                with open(self.sentiment_cache_file, 'r') as f:
                    cache = json.load(f)
                    return cache.get('sentiments', {}).get(pair, 0.0)
        except Exception:
            pass
        return 0.0
    
    def get_batch_prices(self, pairs):
        """Fetch prices for batch of pairs"""
        prices = {}
        try:
            if self.cb_client:
                prices = self.cb_client.get_batch_prices(pairs)
            else:
                # Fallback to price wrapper
                for pair in pairs:
                    prices[pair] = self.price_wrapper.get_price(pair)
        except Exception as e:
            self.logger.error(f"Batch price fetch failed: {e}")
        
        return prices
    
    def calculate_rsi(self, pair, period=14):
        """Calculate RSI for a pair"""
        prices = self.price_history.get(pair, [])
        if len(prices) < period + 1:
            return 50  # Neutral
        
        deltas = np.diff(prices[-period-1:])
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        return 100 - 100 / (1 + rs) if rs != 0 else 50
    
    def run(self):
        """Main trading loop"""
        try:
            while True:
                self.cycle_count += 1
                
                # Fetch prices
                prices = self.get_batch_prices(self.pairs)
                if not prices:
                    continue
                
                # Update price history and check for signals
                for pair in self.pairs:
                    if pair not in prices:
                        continue
                    
                    price = prices[pair]
                    self.price_history[pair].append(price)
                    
                    # Keep only last 100 prices
                    if len(self.price_history[pair]) > 100:
                        self.price_history[pair].pop(0)
                    
                    # Calculate indicators
                    rsi = self.calculate_rsi(pair)
                    sentiment = self.get_sentiment(pair)
                    
                    # Trading signals
                    if rsi < 30 and sentiment > 0:
                        self.logger.trade(f"BUY {pair} @ ${price:.2f} (RSI={rsi:.1f}, Sentiment={sentiment:.2f})")
                        if self.executor_wrapper:
                            self.executor_wrapper.place_order(pair, 'BUY', self.order_size_usd)
                    
                    elif rsi > 70 and sentiment < 0:
                        self.logger.trade(f"SELL {pair} @ ${price:.2f} (RSI={rsi:.1f}, Sentiment={sentiment:.2f})")
                        if self.executor_wrapper:
                            self.executor_wrapper.place_order(pair, 'SELL', self.order_size_usd)
                
                # Log status periodically
                if self.cycle_count % STATUS_LOG_INTERVAL == 0:
                    price_str = " | ".join([f"{p}=${prices.get(p, 0):.2f}" for p in self.pairs[:3]])
                    self.logger.status(f"Cycle {self.cycle_count}: {price_str}")
                
                time.sleep(5)  # 5-second intervals
        
        except KeyboardInterrupt:
            self.logger.shutdown("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            raise


if __name__ == '__main__':
    harness = Phase5Harness()
    harness.run()
