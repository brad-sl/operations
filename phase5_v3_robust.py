#!/usr/bin/env python3
"""Phase 5 v3 Robust: Safety-First Multi-Pair Trading Bot"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
import numpy as np
from dotenv import load_dotenv
from prometheus_client import start_http_server, Gauge

# Local modules
from position_state_manager import PositionStateManager
from price_wrapper import PublicExchangePriceWrapper

# Try to import Coinbase Advanced Client
try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    ADVANCED_TRADE_AVAILABLE = False
    CoinbaseAdvancedClient = None

load_dotenv()

class Phase5V3Robust:
    def __init__(self, config_path=None, sandbox=True):
        # Logging
        self._setup_logging()
        
        # Config
        config_path = config_path or os.path.join(
            os.path.dirname(__file__), 'config', 'trading_config_phase5.json'
        )
        self.config = self._load_config(config_path)
        self.pairs = self.config['global_settings']['pairs']
        self.total_capital = self.config['global_settings']['total_capital']
        self.capital_per_pair = self.total_capital / len(self.pairs)
        self.sl_pct = self.config['risk_management']['stop_loss_pct'] / 100  # 0.02
        
        # Clients - use proven CoinbaseWrapper
        self.sandbox = sandbox
        api_key = os.getenv('COINBASE_API_KEY')
        private_key = os.getenv('COINBASE_API_SECRET')
        if not api_key or not private_key:
            raise ValueError("Missing COINBASE_API_KEY or COINBASE_API_SECRET")
        self.cb_client = CoinbaseWrapper(api_key, private_key, sandbox=sandbox)
        self.state_manager = PositionStateManager()
        self.state_manager.sl_pct = self.sl_pct
        
        # Metrics
        self._setup_prometheus()
        
        # Price history for RSI
        self.price_history = {p: [] for p in self.pairs}
        
        # Startup validation
        self.logger.info('=== STARTUP VALIDATION ===')
        validation = self.state_manager.validate_all(self.cb_client)
        self.logger.info(f'Validation complete: {validation}')
        
        # Prime history
        #self._prime_history()  # Disabled for sandbox test
        
        self.logger.info(f'Phase 5 v3 Robust ready: {len(self.pairs)} pairs, sandbox={sandbox}')
    
    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(log_dir, 'phase5_v3.log'))]
        )
        self.logger = logging.getLogger(__name__)
    
    def _setup_prometheus(self):
        try:
            start_http_server(8503)
            self.metrics = {
                'price': Gauge('pair_price', 'Price', ['pair']),
                'capital': Gauge('total_capital', 'Capital')
            }
        except:
            self.metrics = {}
    
    def _load_config(self, path):
        with open(path) as f:
            return json.load(f)
    
    def _prime_history(self, periods=100):
        prices = self.cb_client.get_batch_prices(self.pairs)
        for pair in self.pairs:
            if pair in prices:
                price = prices[pair]
                # Synthetic backward walk
                hist = [price]
                for _ in range(1, periods):
                    hist.insert(0, price * (1 + np.random.uniform(-0.001, 0.001)))
                self.price_history[pair] = hist
                if self.metrics.get('price'):
                    self.metrics['price'].labels(pair=pair).set(price)
    
    def _get_batch_prices(self):
        return self.cb_client.get_batch_prices(self.pairs)
    
    def _validate_single(self, pair):
        """Quick single-pair validation before trade."""

        pos = self.state_manager.get_position(pair)
        if not pos:
            return True  # No position: safe to BUY
        
        base_asset = pair.split('-')[0]
        balances = self.cb_client.get_account_balances()
        actual_qty = balances.get(base_asset, {}).get('available', 0.0)
        expected_qty = pos['entry_qty']
        
        mismatch = abs(actual_qty - expected_qty) / expected_qty > 0.01
        if mismatch:
            self.logger.warning(f'{pair}: Qty mismatch exp={expected_qty:.6f} act={actual_qty:.6f}')
            # Adjust or clear based on actual
            if actual_qty < expected_qty * 0.01:
                self.state_manager.clear_position(pair)
                self.logger.info(f'{pair}: Cleared ghost position')
            else:
                # Update expected to actual (dust/fees)
                pos['entry_qty'] = actual_qty
                self.state_manager._save_state()
        
        # Quick SL check
        if self.cb_client.get_order(pos['sl_order_id'])['order']['status'] == 'FILLED':
            self.state_manager.clear_position(pair)
        
        return True  # Proceed after sync
    
    def _calculate_rsi(self, pair, period=14):
        hist = self.price_history[pair]
        if len(hist) < period + 1:
            return 50.0
        
        deltas = np.diff(hist[-period-1:])
        gains = deltas[deltas > 0].sum() / period
        losses = -deltas[deltas < 0].sum() / period
        rs = gains / losses if losses != 0 else 0
        rsi = 100 - 100 / (1 + rs)
        return rsi
    
    def _get_sentiment(self, pair):
        # Placeholder: load from cache in prod
        cache_file = os.path.join(os.path.dirname(__file__), 'sentiment_cache.json')
        try:
            if os.path.exists(cache_file):
                with open(cache_file) as f:
                    return json.load(f).get(pair, {}).get('sentiment', 0.0)
        except:
            pass
        return 0.0  # Neutral
    
    def _trade_signal(self, pair, price):
        rsi = self._calculate_rsi(pair)
        sentiment = self._get_sentiment(pair)
        pos = self.state_manager.get_position(pair)
        
        has_position = bool(pos)
        
        if not has_position and rsi < 30 and sentiment > 0.5:
            return 'BUY'
        elif has_position and rsi > 70 and sentiment < -0.5:
            return 'SELL'
        return 'HOLD'
    
    def _execute_buy(self, pair, quote_size):
        """Execute BUY + SL."""

        order = self.cb_client.place_market_order(pair, side='BUY', funds_or_size=quote_size)
        if not order:
            return
        
        order_id = order['order']['id']
        status = self.cb_client.poll_order_status(order_id)
        if status != 'FILLED':
            self.logger.warning(f'{pair} BUY not filled: {status}')
            return
        
        # Get fills for avg price/qty
        fills = self.cb_client.get_fills_for_order(pair, order_id)
        if not fills:
            self.logger.warning(f'{pair} No fills found')
            return
        
        total_base = sum(float(f['filled_base_size']) for f in fills)
        total_quote = sum(float(f['filled_quote_size']) for f in fills)
        avg_price = total_quote / total_base
        
        # Place SL
        sl_price = avg_price * (1 - self.sl_pct)
        limit_price = f'{sl_price * 0.995:.2f}'  # 0.5% slippage
        sl_order = self.cb_client.place_stop_limit_sell(pair, f'{total_base:.8f}', f'{sl_price:.2f}', limit_price)
        
        if sl_order:
            sl_id = sl_order['order']['id']
            self.state_manager.update_position(pair, avg_price, total_base, sl_id, sl_price, datetime.now().isoformat())
            self.logger.info(f'{pair} BUY+SL: qty={total_base:.6f} @${avg_price:.2f} SL=${sl_price:.2f} [{sl_id}]')
    
    def _execute_sell(self, pair):
        """Execute SELL + clear."""

        pos = self.state_manager.get_position(pair)
        if not pos:
            return
        
        base_size = f'{pos["entry_qty"]:.8f}'
        order = self.cb_client.place_market_order(pair, side='SELL', funds_or_size=float(base_size))
        if not order:
            return
        
        order_id = order['order']['id']
        status = self.cb_client.poll_order_status(order_id)
        if status == 'FILLED':
            self.state_manager.clear_position(pair)
            self.logger.info(f'{pair} SELL filled + cleared')
    
    def process_pair(self, pair, price, cycle):
        """Full per-pair cycle."""

        self.logger.info(f'CYCLE {cycle}: {pair} ${price:.4f}')
        
        # Update history + metrics
        self.price_history[pair].append(price)
        if len(self.price_history[pair]) > 200:
            self.price_history[pair] = self.price_history[pair][-200:]
        if self.metrics.get('price'):
            self.metrics['price'].labels(pair=pair).set(price)
        
        # Validate
        self._validate_single(pair)
        
        # Signal
        signal = self._trade_signal(pair, price)
        if signal == 'HOLD':
            return
        
        # Execute
        pos = self.state_manager.get_position(pair)
        has_pos = bool(pos)
        
        if signal == 'BUY' and not has_pos:
            self._execute_buy(pair, self.capital_per_pair * 0.5)
        elif signal == 'SELL' and has_pos:
            self._execute_sell(pair)
    
    def run(self, cycles=10, cycle_interval=300):
        """Main loop."""

        self.logger.info(f'Starting {cycles} cycles ({cycle_interval}s interval)')
        full_validate_cycle = 0
        
        for cycle in range(1, cycles + 1):
            self.logger.info(f'\\n=== CYCLE {cycle}/{cycles} ===')
            
            prices = self._get_batch_prices()
            full_validate_cycle = (full_validate_cycle + 1) % 5
            if full_validate_cycle == 0:
                self.state_manager.validate_all(self.cb_client)
            
            for pair in self.pairs:
                price = prices.get(pair)
                if price:
                    self.process_pair(pair, price, cycle)
            
            if cycle < cycles:
                time.sleep(cycle_interval)
        
        self.logger.info('Run complete')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cycles', type=int, default=10)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    
    bot = Phase5V3Robust(sandbox=not args.live)
    bot.run(cycles=args.cycles)

if __name__ == '__main__':
    main()
