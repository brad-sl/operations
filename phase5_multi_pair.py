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
from random import uniform
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

try:
    from phase5_order_executor_wrapper import OrderExecutorWrapper
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = True
except ImportError:
    ORDER_EXECUTOR_WRAPPER_AVAILABLE = False
    OrderExecutorWrapper = None

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
        
        # Phase 6: Sandbox trading via OrderExecutor
        self.order_size_usd = self.config.get('global_settings', {}).get('order_size_usd', 25.0)
        self.sandbox_trading = os.getenv('SANDBOX_TRADING', 'True').lower() == 'true'
        self.executor_wrapper = None
        
        if ORDER_EXECUTOR_WRAPPER_AVAILABLE and self.sandbox_trading:
            try:
                self.executor_wrapper = OrderExecutorWrapper(
                    cb_client=self.cb_client,
                    sandbox_mode=self.sandbox_trading,
                    order_size_usd=self.order_size_usd,
                    logger=self.logger
                )
                self.logger.info(f"✅ Phase 6 OrderExecutor initialized (sandbox={self.sandbox_trading}, order_size=${self.order_size_usd})")
            except Exception as e:
                self.logger.warning(f"Phase 6 initialization failed: {e}. Running Phase 5 only.")
                self.executor_wrapper = None
        else:
            self.logger.info("⚠️  Phase 6 OrderExecutor unavailable (Phase 5 manual trading only)")
        
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
            level=logging.WARNING,
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
        """
        Batch fetch prices for all trading pairs using price wrapper.
        
        DESIGN: Uses PublicExchangePriceWrapper.get_prices_batch() to fetch
        all pairs in ONE request to CoinGecko, avoiding rate limits and API errors.
        
        RETURNS: Dict mapping each pair to its current price
        """
        try:
            # Single efficient batch request (1 API call for all 6 pairs)
            prices = self.price_wrapper.get_prices_batch(self.pairs)
            
            # Verify we got all pairs
            successful = len([p for p in prices.values() if p > 0])
            self.logger.info(f"✅ Batch price fetch: {successful}/{len(self.pairs)} prices")
            
            return prices
        except Exception as e:
            self.logger.error(f"Batch fetch error: {e}. Falling back to individual requests.")
            # Fallback: fetch individually
            prices = {}
            for pair in self.pairs:
                try:
                    prices[pair] = self.price_wrapper.get_price(pair)
                except Exception as pair_e:
                    self.logger.warning(f"Failed to fetch {pair}: {pair_e}")
                    prices[pair] = 0.0
            return prices
    
    def _prime_historical_data(self, days=60):
        """
        Prime price history with REAL historical OHLCV data from backtest files.
        No synthetic/random data. Uses close prices for accurate RSI(11).
        """
        import json
        import os
        try:
            self.logger.info(f"Priming {len(self.pairs)} pairs with REAL historical data...")
            data_dir = os.path.dirname(__file__)
            pair_map = {
                'BTC-USD': 'backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json',
                'ETH-USD': 'backtest_historical_ohlcv_eth_2025-04-20_to_2026-04-20.json',
                'SOL-USD': 'backtest_historical_ohlcv_sol_2025-04-20_to_2026-04-20.json',
                'XRP-USD': 'backtest_historical_ohlcv_xrp_2025-04-20_to_2026-04-20.json',
                'DOGE-USD': 'backtest_historical_ohlcv_doge_2025-04-20_to_2026-04-20.json',
            }
            for pair in self.pairs:
                try:
                    fname = pair_map.get(pair)
                    if fname:
                        fpath = os.path.join(data_dir, fname)
                        if os.path.exists(fpath):
                            with open(fpath) as f:
                                hist = json.load(f)
                            closes = [float(c['close']) for c in hist if 'close' in c][:1440]  # up to ~60d hourly
                            self.price_history[pair] = closes
                            self.logger.info(f"✅ {pair}: Primed with {len(closes)} REAL points from {fname}")
                            continue
                    # fallback to empty, will accumulate live
                    self.price_history[pair] = []
                    self.logger.warning(f"⚠️  {pair}: No real data file, will accumulate live")
                except Exception as e:
                    self.logger.warning(f"⚠️  Failed to prime {pair}: {e}. Will accumulate live.")
                    self.price_history[pair] = []
            self.logger.info(f"✅ Real historical priming complete. RSI will be accurate.")
        except Exception as e:
            self.logger.error(f"Historical priming failed: {e}. Proceeding with live accumulation.")
    
    def _process_pair(self, pair, cycle):
        """Process individual trading pair (uses batch-fetched price)"""
        try:
            # Get price directly from wrapper
            price = self.price_wrapper.get_price(pair)
            
            if price is None or price <= 0:
                self.logger.warning(f"Price fetch failed for {pair}, skipping cycle")
                return "HOLD"
            
            # Update real price history for RSI(11) calc (append live close)
            if pair not in self.price_history:
                self.price_history[pair] = []
            self.price_history[pair].append(price)
            if len(self.price_history[pair]) > 2000:  # cap memory
                self.price_history[pair] = self.price_history[pair][-2000:]
            
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
            
            # Phase 6: Execute via OrderExecutorWrapper (sandbox paper trading)
            if self.executor_wrapper and signal != "HOLD":
                try:
                    results = self.executor_wrapper.execute_signal(
                        pair=pair,
                        signal=signal,
                        price=price,
                        rsi=rsi,
                        sentiment=sentiment,
                        cycle=cycle
                    )
                    if results:
                        self.logger.info(f"✅ {pair} {signal}: {len(results)} order(s) executed (LIVE TRADING)")
                except Exception as e:
                    self.logger.error(f"Phase 6 execution error: {e}")
            
            return signal
        except Exception as e:
            self.logger.error(f"Error processing {pair}: {e}")
            return "HOLD"
    
    def _calculate_rsi(self, pair, period=11):
        """Calculate real RSI(11) from price history using Wilder's smoothing.
        Uses proper historical price data (no random/placeholder).
        """
        try:
            if pair not in self.price_history or len(self.price_history[pair]) < period + 1:
                return 50.0  # neutral start
            prices = np.array(self.price_history[pair][-period-1:])
            deltas = np.diff(prices)
            if len(deltas) == 0:
                return 50.0
            # Initial average gain/loss
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[:period]) if period > 0 else 0
            avg_loss = np.mean(losses[:period]) if period > 0 else 1e-10
            rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
            rsi = 100 - 100 / (1 + rs)
            # Continue with remaining deltas for full period
            for delta in deltas[period:]:
                if delta > 0:
                    avg_gain = (avg_gain * (period - 1) + delta) / period
                    avg_loss = (avg_loss * (period - 1)) / period
                else:
                    avg_gain = (avg_gain * (period - 1)) / period
                    avg_loss = (avg_loss * (period - 1) - delta) / period
                rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
                rsi = 100 - 100 / (1 + rs)
            return float(np.clip(rsi, 0, 100))
        except Exception:
            return 50.0
    
    def _get_sentiment(self, pair):
        """Get sentiment for pair"""
        # Placeholder sentiment retrieval
        return np.random.uniform(-1, 1)
    
    def _determine_trade_signal(self, pair, price, rsi, sentiment):
        """Determine trading signal based on multiple factors"""
        # Simple trading logic
        # TEMP: Lowered sentiment threshold from ±0.5 to ±0.0 to test trade execution (2026-04-21)
        # TODO: Restore to 0.5 threshold after verifying execution works with stronger signals
        # See: https://github.com/openclaw/crypto-bot/issues/phase6-sentiment-threshold
        if (rsi < 30 and sentiment > 0.0) or (rsi > 70 and sentiment < -0.0):
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
            
            # Phase 6: Execute via OrderExecutorWrapper (sandbox paper trading)
            if self.executor_wrapper and signal != "HOLD":
                try:
                    results = self.executor_wrapper.execute_signal(
                        pair=pair,
                        signal=signal,
                        price=price,
                        rsi=rsi,
                        sentiment=sentiment,
                        cycle=cycle
                    )
                    if results:
                        self.logger.info(f"✅ {pair} {signal}: {len(results)} order(s) executed (LIVE TRADING)")
                except Exception as e:
                    self.logger.error(f"Phase 6 execution error: {e}")
            
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
                    cache_data = json.load(f)
                    # Handle both old format (direct pair keys) and new format (wrapped in 'sentiments')
                    if 'sentiments' in cache_data:
                        sentiments = cache_data['sentiments']
                    else:
                        sentiments = cache_data
                    
                    if pair in sentiments:
                        sentiment_data = sentiments[pair]
                        # Extract value if it's a dict (old format), otherwise use directly
                        if isinstance(sentiment_data, dict):
                            sentiment = sentiment_data.get('sentiment', 0.0)
                        else:
                            sentiment = sentiment_data
                        self.logger.info(f"{pair} sentiment from cache: {sentiment:.4f}")
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
        # TEMP: Lowered threshold from 0.5 to 0.0 (see line 313 comment)
        if rsi < 30 and sentiment > 0.0:
            self.logger.info(f"{pair} BUY signal: RSI={rsi:.1f}, Sentiment={sentiment:.2f}")
            return "BUY"
        elif rsi > 70 and sentiment < -0.0:
            self.logger.info(f"{pair} SELL signal: RSI={rsi:.1f}, Sentiment={sentiment:.2f}")
            return "SELL"
        else:
            return "HOLD"
    
    def _rebalance_if_needed(self, cycle_number):
        """
        Weekly rebalancing: Every 7 cycles (~7 min), rebalance portfolio based on correlation.
        
        ALGORITHM:
        1. Calculate correlation matrix from 30-cycle price history
        2. Detect high-correlation pairs (avg_corr > 0.7)
        3. Shift 50% of high-corr allocations to reserve
        4. Re-deploy from reserve based on sentiment weighting
        """
        if cycle_number % 7 != 0:
            return  # Only rebalance every 7 cycles
        
        try:
            # Initialize allocations tracking
            if not hasattr(self, 'allocations'):
                self.allocations = {pair: self.capital_per_pair for pair in self.pairs}
                self.reserve = 0.0
            
            # Build price matrix (pairs × 30 cycles)
            price_matrix = []
            for pair in self.pairs:
                if pair in self.price_history and len(self.price_history[pair]) >= 30:
                    pair_prices = self.price_history[pair][-30:]  # Last 30 cycles
                    price_matrix.append(pair_prices)
                else:
                    # Fallback: use current price repeated
                    current_price = getattr(self, f'{pair}_price', 0)
                    if current_price > 0:
                        price_matrix.append([current_price] * 30)
                    else:
                        self.logger.warning(f"⚠️  {pair}: Insufficient price data for correlation")
                        continue
            
            if len(price_matrix) < 2:
                self.logger.warning("Not enough pairs with price history for correlation")
                return
            
            # Calculate correlation matrix
            price_matrix = np.array(price_matrix)
            corr_matrix = np.corrcoef(price_matrix)
            
            # Get average correlation (excluding diagonal self-correlations)
            corr_values = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
            avg_correlation = np.mean(corr_values) if len(corr_values) > 0 else 0
            
            self.logger.info(f"🔄 REBALANCING TRIGGER (Cycle {cycle_number})")
            self.logger.info(f"📊 Average Correlation: {avg_correlation:.3f}")
            
            # Rebalance if high correlation detected
            if avg_correlation > 0.7:
                self.logger.info(f"⚠️  High correlation ({avg_correlation:.3f}). Initiating rebalancing...")
                
                # Identify high-correlation pairs
                high_corr_pairs = []
                for i, pair in enumerate(self.pairs):
                    if i < len(corr_matrix):
                        pair_corrs = corr_matrix[i]
                        avg_pair_corr = np.mean(pair_corrs)
                        if avg_pair_corr > 0.7:
                            high_corr_pairs.append((pair, avg_pair_corr))
                
                self.logger.info(f"High-correlation pairs: {high_corr_pairs}")
                
                # Save state before rebalancing
                allocations_before = dict(self.allocations)
                reserve_before = self.reserve
                
                # Shift 50% of high-corr pairs to reserve
                for pair, pair_corr in high_corr_pairs:
                    if pair in self.allocations:
                        shift_amount = self.allocations[pair] * 0.5
                        self.allocations[pair] -= shift_amount
                        self.reserve += shift_amount
                        self.logger.info(f"  {pair} (corr={pair_corr:.2f}): Shifted ${shift_amount:.2f} to reserve")
                
                # Log rebalancing summary
                self.logger.info(f"Allocations BEFORE: {allocations_before}")
                self.logger.info(f"Allocations AFTER:  {self.allocations}")
                self.logger.info(f"Reserve: ${reserve_before:.2f} → ${self.reserve:.2f}")
                
            else:
                self.logger.info(f"✅ Correlation healthy ({avg_correlation:.3f}). No rebalancing needed.")
            
            # Log final portfolio state
            total_allocated = sum(self.allocations.values())
            self.logger.info(f"📈 Portfolio State: ${total_allocated:.2f} allocated + ${self.reserve:.2f} reserve")
            
        except Exception as e:
            self.logger.error(f"❌ Rebalancing error: {e}", exc_info=True)
    
    def run(self, total_cycles=None):
        """Main trading bot execution loop"""
        if total_cycles is None:
            total_cycles = float('inf')
        self.logger.info(f"Phase 5 Harness starting — {'INFINITE' if total_cycles == float('inf') else total_cycles} cycles, 300s interval")
        
        cycle = 1
        while cycle <= total_cycles:
            self.logger.info(f"\n======================================================================")
            cycle_display = '∞' if total_cycles == float('inf') else f"{cycle}/{total_cycles}"
            self.logger.info(f"CYCLE {cycle_display} — {datetime.now().isoformat()}")
            self.logger.info(f"======================================================================")
            
            # BATCH FETCH all prices (1 API call for all pairs)
            batch_prices = self._fetch_all_pairs_batch()
            
            # Cache batch prices for use in _process_pair
            for pair in self.pairs:
                if pair in batch_prices:
                    setattr(self, f'{pair}_price', batch_prices[pair])
            
            # Process pairs using cached batch prices
            for pair in self.pairs:
                self._process_pair(pair, cycle)
            
            # Weekly rebalancing (every 7 cycles)
            self._rebalance_if_needed(cycle)
            
            cycle += 1
            
            # Sleep interval: 600 seconds = 10 minutes between cycles (reduced from 5 min to ease API rate limits)
            time.sleep(600)

def main():
    """Entry point for the trading bot"""
    parser = argparse.ArgumentParser(description="Phase 5 Multi-Pair Trading Bot")
    parser.add_argument("--cycles", type=int, default=None, help="Number of trading cycles (default: infinite)")
    args = parser.parse_args()
    
    harness = Phase5Harness()
    harness.run(total_cycles=args.cycles)

if __name__ == '__main__':
    main()