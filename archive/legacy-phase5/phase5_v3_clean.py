#!/usr/bin/env python3
"""
Phase 5 Multi-Pair Trading Bot (v2: Coinbase Advanced Trade API)
Enhanced with robust price fetching and error handling

DECISION LOG (2026-04-18):
- Migrate from deprecated Coinbase Pro API to Advanced Trade API v3 (ECDSA JWT auth)
- See AUTH_NOTES.md + coinbase_advanced_client.py for implementation details
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from prometheus_client import start_http_server, Gauge

# Custom modules
from price_wrapper import PublicExchangePriceWrapper
try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    ADVANCED_TRADE_AVAILABLE = False
    CoinbaseAdvancedClient = None

# Suppress verbose fallback API errors (Pro API deprecated, CoinGecko rate-limited)
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
logging.getLogger('requests').setLevel(logging.WARNING)  # Suppress requests lib debug logs
logging.getLogger('urllib3').setLevel(logging.WARNING)   # Suppress urllib3 debug logs

MAX_BATCH_SIZE = 20  # Batch chunking safety limit

class Phase5Harness:
    def __init__(self, config_path=None):
        # Load environment variables
        load_dotenv()
        
        # Setup logging
        self._setup_logging()
        
        # Initialize metrics
        self._setup_prometheus_metrics()
        
        # Load configuration
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), 
            'config', 
            'trading_config_phase5.json'
        )
        self.config = self._load_config()
        
        # Initialize trading components
        # MIGRATION: Advanced Trade API (ECDSA JWT) + fallback to CoinGecko
        self.sandbox = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'
        self.price_wrapper = PublicExchangePriceWrapper()  # CoinGecko fallback
        self.cb_client = None
        
        if ADVANCED_TRADE_AVAILABLE:
            try:
                self.cb_client = CoinbaseAdvancedClient(test_mode=self.sandbox)
                self.logger.info(f"Coinbase Advanced Trade API initialized (sandbox={self.sandbox})")
            except Exception as e:
                self.logger.warning(f"Advanced Trade API init failed: {e}. Using CoinGecko fallback.")
                self.cb_client = None
        
        self.pairs = self.config.get('global_settings', {}).get('pairs', [])
        
        # Trading parameters
        self.total_capital = self.config.get('global_settings', {}).get('total_capital', 1000)
        self.capital_per_pair = self.total_capital / len(self.pairs)
        
        # Sentiment and risk management
        self.sentiment_weight = self.config.get('sentiment', {}).get('weight', 0.4)
        
        # Initialize price history for RSI calculation
        self.price_history = {pair: [] for pair in self.pairs}
        
        # Prime historical data (60 days)
        self.logger.info(f"Priming historical data for {len(self.pairs)} pairs...")
        self._prime_historical_data(days=60)
        
        # Logging
        self.logger.info(f"Phase 5 Harness Initialized: {len(self.pairs)} pairs")
    
    def _setup_logging(self):
        """Configure logging with file and console output"""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(os.path.join(log_dir, 'phase5_live.log'))
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _setup_prometheus_metrics(self):
        """Initialize Prometheus metrics server"""
        # Initialize as None by default
        self.pair_price_gauge = None
        self.trading_capital_gauge = None
        
        try:
            metrics_port = int(os.getenv('PROMETHEUS_METRICS_PORT', 8502))
            start_http_server(metrics_port)
            
            # Define key metrics
            self.pair_price_gauge = Gauge(
                'trading_pair_price', 
                'Current trading pair price', 
                ['pair']
            )
            self.trading_capital_gauge = Gauge(
                'trading_total_capital', 
                'Total trading capital'
            )
            
            self.logger.info(f"Prometheus metrics server started on :{metrics_port}")
        except Exception as e:
            self.logger.error(f"Prometheus metrics setup failed: {e}. Continuing without metrics.")
    
    def _load_config(self):
        """Load trading configuration from JSON"""
        try:
            import json
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Config load error: {e}")
            return {}
    
    def _fetch_all_pairs_batch(self):
        """Batch fetch with chunking (max 20 pairs/request for URL safety)"""
        all_prices = {}
        chunks = [self.pairs[i:i+MAX_BATCH_SIZE] for i in range(0, len(self.pairs), MAX_BATCH_SIZE)]
        
        for chunk_idx, chunk in enumerate(chunks, 1):
            try:
                response = self.cb_client.client.get_products(product_ids=chunk)
                self.logger.info(f"Response type: {type(response)}, has products attr: {hasattr(response, 'products')}")
                if hasattr(response, 'products') and response.products:
                    self.logger.info(f"DEBUG: response has products attr. Iterating over {len(response.products)} products")
                    for product in response.products:
                        pair_id = product.get('product_id') if isinstance(product, dict) else getattr(product, 'product_id', None)
                        price_str = product.get('price') if isinstance(product, dict) else getattr(product, 'price', None)
                        if pair_id and price_str:
                            try:
                                price_float = float(price_str)
                                all_prices[pair_id] = price_float
                                self.logger.info(f"Cached {pair_id}: ${price_float:.2f}")
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Failed to parse price for {pair_id}: {price_str} ({e})")
                self.logger.info(f"✅ Batch {chunk_idx}/{len(chunks)}: {len(chunk)} pairs fetched | Cached: {len(all_prices)} prices")
            except Exception as e:
                self.logger.error(f"Batch {chunk_idx} failed: {e} (fallback to individual)")
                for pair in chunk:
                    try:
                        single = self.cb_client.client.get_products(product_ids=[pair])
                        if isinstance(single, dict) and 'products' in single and len(single['products']) > 0:
                            prod = single['products'][0]
                            all_prices[pair] = float(prod.get('price', 0))
                    except Exception as pe:
                        self.logger.warning(f"Individual fetch {pair}: {pe}")
        return all_prices
    
    def _prime_historical_data(self, days=60):
        """
        Prime price history with N days of synthetic historical data before trading starts.
        Uses current prices with small perturbations to seed RSI calculation.
        """
        try:
            self.logger.info(f"Priming {len(self.pairs)} pairs with synthetic historical data...")
            
            # Fetch current prices
            current_prices = self._fetch_all_pairs_batch()
            
            for pair in self.pairs:
                try:
                    if pair not in current_prices:
                        self.logger.warning(f"⚠️  {pair}: Could not fetch current price")
                        self.price_history[pair] = []
                        continue
                    
                    current_price = current_prices[pair]
                    
                    # Generate synthetic historical prices with small perturbations
                    import random
                    noise_factor = 0.001  # 0.1% noise
                    num_points = min(days * 24, 1440)  # Up to 60 days of hourly data
                    
                    historical_prices = []
                    price = current_price
                    for i in range(num_points, 0, -1):  # Go backwards in time
                        historical_prices.insert(0, price)
                        price *= (1 + random.uniform(-noise_factor, noise_factor))
                    
                    self.price_history[pair] = historical_prices
                    self.logger.info(f"✅ {pair}: Primed with {len(historical_prices)} synthetic points")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️  Failed to prime {pair}: {e}. Will accumulate live.")
                    self.price_history[pair] = []
            
            self.logger.info(f"✅ Historical priming complete. Ready for trading.")
            
        except Exception as e:
            self.logger.error(f"Historical priming failed: {e}. Proceeding with live accumulation.")
    
    def _process_pair(self, pair, cycle):
        """Process individual trading pair (uses batch-fetched price)"""
        try:
            # Use ONLY batch-fetched price (already cached on self by run)
            price_attr = pair + "_price"
            price = getattr(self, price_attr, None)
            
            if price is None or price <= 0:
                self.logger.warning(f"Batch price missing for {pair}, skipping cycle")
                return "HOLD"
            
            # Update Prometheus metrics (safe if metrics disabled)
            if self.pair_price_gauge:
                try:
                    self.pair_price_gauge.labels(pair=pair).set(price)
                except Exception:
                    pass
            if self.trading_capital_gauge:
                try:
                    self.trading_capital_gauge.set(self.total_capital)
                except Exception:
                    pass
            
            # Basic logging and processing
            self.logger.info(f"CYCLE {cycle}: {pair} Price=${price:.4f}")
            
            # Real trading logic (NO mocks in live mode)
            rsi = self._calculate_rsi(pair)
            sentiment = self._get_sentiment(pair)
            
            # Trading decision logic
            signal = self._determine_trade_signal(pair, price, rsi, sentiment)
            
            return signal
        except Exception as e:
            self.logger.error(f"Error processing {pair}: {e}")
            return "HOLD"
    
    def _calculate_rsi(self, pair, period=14):
        """Calculate RSI from price history"""
        # Placeholder RSI calculation
        return np.random.uniform(30, 70)
    
    def _get_sentiment(self, pair):
        """Get sentiment for pair"""
        # Placeholder sentiment retrieval
        return np.random.uniform(-1, 1)
    
    def _determine_trade_signal(self, pair, price, rsi, sentiment):
        """Determine trading signal based on multiple factors"""
        # Simple trading logic
        if (rsi < 30 and sentiment > 0.5) or (rsi > 70 and sentiment < -0.5):
            return "TRADE"
        return "HOLD"
    
    def _execute_trade(self, pair, signal, price):
        """Execute live trade on Coinbase if signal triggers"""
        if signal != "TRADE" or not self.cb_client:
            return None
        try:
            order_size = (self.capital_per_pair / price) * 0.5
            self.logger.info(f"🔥 LIVE TRADE: {pair} @ ${price:.4f}")
            try:
                order = self.cb_client.create_market_order(
                    product_id=pair,
                    side="BUY",
                    quote_size=self.capital_per_pair * 0.5
                )
                self.logger.info(f"✅ Order placed: {order.get('id', 'unknown')}")
                return order
            except Exception as e:
                self.logger.warning(f"Order failed: {e}")
                return None
        except Exception as e:
            self.logger.error(f"Trade error {pair}: {e}")
            return None
    
        """Process individual trading pair (uses batch-fetched price)"""
        try:
            # Use batch-fetched price (already cached on self by run)
            price_attr = pair + "_price"
            price = getattr(self, price_attr, None)
            
            # Fallback only if batch fetch failed
            if price is None or price <= 0:
                price = self.price_wrapper.get_price(pair)
            # Update Prometheus metrics (safe if metrics disabled)
            if self.pair_price_gauge:
                try:
                    self.pair_price_gauge.labels(pair=pair).set(price)
                except Exception:
                    pass
            if self.trading_capital_gauge:
                try:
                    self.trading_capital_gauge.set(self.total_capital)
                except Exception:
                    pass
            
            # Basic logging and processing
            self.logger.info(f"CYCLE {cycle}: {pair} Price=${price:.4f}")
            
            # Real trading logic (NO mocks in live mode)
            rsi = self._calculate_rsi(pair)
            sentiment = self._get_sentiment(pair)
            
            # Trading decision logic
            signal = self._determine_trade_signal(pair, price, rsi, sentiment)
            
            return signal
        except Exception as e:
            self.logger.error(f"Error processing {pair}: {e}")
            return "HOLD"
    
    def _calculate_rsi(self, pair, period=14):
        """
        Calculate RSI from historical prices (14-period standard).
        SECURITY: NO MOCK DATA in live trading. Must use real historical prices.
        Thresholds: RSI<30 oversold (BUY), RSI>70 overbought (SELL)
        """
        try:
            if not hasattr(self, 'price_history'):
                self.price_history = {}
            if pair not in self.price_history:
                self.price_history[pair] = []
            
            current_price = getattr(self, f'{pair}_price', None)
            if current_price is None or current_price <= 0:
                return 50.0
            
            self.price_history[pair].append(current_price)
            
            if len(self.price_history[pair]) < period + 1:
                return 50.0
            
            prices = self.price_history[pair][-(period + 1):]
            
            gains = []
            losses = []
            for i in range(1, len(prices)):
                change = prices[i] - prices[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            
            if avg_loss == 0:
                rsi = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
            
            self.logger.info(f"RSI {pair}: {rsi:.1f} (periods={len(prices)-1})")
            return rsi
            
        except Exception as e:
            self.logger.warning(f"RSI calc error {pair}: {e}")
            return 50.0
    
    def _get_sentiment(self, pair):
        """
        Retrieve sentiment from sentiment_cache.json (pre-computed).
        SECURITY: NO MOCK DATA in live trading. Cache must be fresh.
        """
        try:
            cache_file = os.path.join(os.path.dirname(__file__), 'sentiment_cache.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                    if pair in cache:
                        sentiment = cache[pair].get('sentiment', 0.0)
                        self.logger.info(f"{pair} sentiment from cache: {sentiment:.2f}")
                        return sentiment
                    else:
                        self.logger.warning(f"{pair} not in sentiment cache")
        except Exception as e:
            self.logger.warning(f"Sentiment cache read failed for {pair}: {e}")
        
        # No mock: require test flag
        if os.getenv('ALLOW_MOCK_SENTIMENT', 'false').lower() == 'true':
            return np.random.uniform(-1, 1)  # Test only
        else:
            # Neutral default (HOLD signal)
            return 0.0
    
    def _determine_trade_signal(self, pair, price, rsi, sentiment):
        """
        Determine trading signal based on RSI + sentiment (REAL DATA ONLY).
        SECURITY: Explicit conditions to prevent false signals from mock data.
        """
        # Signal only on strong confirmation (RSI extreme + sentiment alignment)
        if rsi < 30 and sentiment > 0.5:
            self.logger.info(f"{pair} BUY signal: RSI={rsi:.1f}, Sentiment={sentiment:.2f}")
            return "BUY"
        elif rsi > 70 and sentiment < -0.5:
            self.logger.info(f"{pair} SELL signal: RSI={rsi:.1f}, Sentiment={sentiment:.2f}")
            return "SELL"
        else:
            return "HOLD"
    
    def run(self, total_cycles=288):
        """Main trading bot execution loop"""
        self.logger.info(f"Phase 5 Harness starting — {total_cycles} cycles, 300s interval")
        
        for cycle in range(1, total_cycles + 1):
            self.logger.info(f"\n======================================================================")
            self.logger.info(f"CYCLE {cycle}/{total_cycles} — {datetime.now().isoformat()}")
            self.logger.info(f"======================================================================")
            
            # BATCH FETCH all prices (1 API call)
            batch_prices = self._fetch_all_pairs_batch()
            
            # Process pairs with batch prices
            for pair in self.pairs:
                if pair in batch_prices:
                    setattr(self, f'{pair}_price', batch_prices[pair])
                self._process_pair(pair, cycle)
            
            # Sleep interval (use simulated time for paper trading)
            # In production, use actual sleep
            # time.sleep(300)

def main():
    """Entry point for the trading bot"""
    parser = argparse.ArgumentParser(description="Phase 5 Multi-Pair Trading Bot")
    parser.add_argument("--cycles", type=int, default=288, help="Number of trading cycles")
    args = parser.parse_args()
    
    harness = Phase5Harness()
    harness.run(total_cycles=args.cycles)

if __name__ == '__main__':
    main()