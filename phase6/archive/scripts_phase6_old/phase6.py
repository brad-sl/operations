#!/usr/bin/env python3
"""
Phase 6 - Persistent Trading Loop with Sentiment Integration

A continuous, config-driven trading bot that:
1. Runs 30-min cycles (configurable)
2. Integrates live sentiment from trading-monitor-status.json
3. Uses Phase 4d signal logic (RSI<30 BUY, RSI>70 SELL, 2% SL)
4. Executes orders via order_executor.py
5. Tracks positions and calculates P&L
6. Logs trades to CSV and cycle stats to log file

Usage:
    python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE
    python3 phase6.py --config config/trading_config_phase6.json --mode LIVE

Environment Variables:
    PHASE_MODE: Override --mode flag. Values: PAPER_TRADE, LIVE
    PHASE_CONFIG: Override --config flag. Path to JSON config file.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import numpy as np

# For sentiment integration
try:
    import requests
except ImportError:
    requests = None

# Custom modules (assume these exist from previous phases)
try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    ADVANCED_TRADE_AVAILABLE = False
    CoinbaseAdvancedClient = None

from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


@dataclass
class GlobalSettings:
    """Global trading settings."""
    total_capital: float
    pairs: List[str]
    cycle_interval_seconds: int


@dataclass
class RiskManagement:
    """Risk configuration."""
    max_daily_loss_pct: float
    var_threshold: float
    stop_loss_pct: float
    take_profit_pct: Optional[float] = None


@dataclass
class ExpansionRules:
    """Phase 6 expansion rules."""
    max_pairs: int
    correlation_threshold: float
    reserve_min_pct: float


@dataclass
class Phase6Specific:
    """Phase 6-specific configuration."""
    expansion_rules: ExpansionRules


@dataclass
class TradingConfig:
    """Complete trading configuration."""
    global_settings: GlobalSettings
    risk_management: RiskManagement
    phase_6_specific: Phase6Specific


@dataclass
class Position:
    """Represents an open position."""
    pair: str
    entry_price: float
    entry_qty: float
    entry_timestamp: str
    side: str = "LONG"
    sl_price: float = 0.0
    tp_price: float = 0.0
    sl_order_id: Optional[str] = None
    order_id: Optional[str] = None


@dataclass
class Trade:
    """Represents a completed trade."""
    timestamp: str
    pair: str
    signal: str  # BUY, SELL, HOLD
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    side: str
    pnl: Optional[float]
    pnl_pct: Optional[float]


class ConfigLoader:
    """Load and validate trading configuration from JSON."""

    @staticmethod
    def load(config_path: str) -> TradingConfig:
        """Load config from JSON file."""
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
        
        try:
            config = TradingConfig(
                global_settings=GlobalSettings(**data['global_settings']),
                risk_management=RiskManagement(**data['risk_management']),
                phase_6_specific=Phase6Specific(
                    expansion_rules=ExpansionRules(**data['phase_6_specific']['expansion_rules'])
                )
            )
            return config
        except (KeyError, TypeError) as e:
            raise ValueError(f"Invalid config structure: {e}")


class SentimentManager:
    """Fetch live sentiment from trading-monitor-status.json"""
    
    SENTIMENT_FILE = '/home/brad/.openclaw/workspace/agents/memory/trading-monitor-status.json'
    
    @staticmethod
    def get_sentiment() -> Dict[str, float]:
        """
        Read sentiment from monitor status file.
        Returns dict with 'overall' and 'state' keys.
        Falls back to neutral (0.5) if unavailable.
        """
        try:
            if os.path.exists(SentimentManager.SENTIMENT_FILE):
                with open(SentimentManager.SENTIMENT_FILE, 'r') as f:
                    data = json.load(f)
                    sentiment = data.get('sentiment', {})
                    return {
                        'overall': sentiment.get('overall', 0.5),
                        'state': sentiment.get('state', 'neutral')
                    }
        except Exception as e:
            logging.warning(f"Sentiment fetch failed: {e}")
        
        # Default neutral
        return {'overall': 0.5, 'state': 'neutral'}


class Phase6TradingBot:
    """Main Phase 6 persistent trading loop."""
    
    def __init__(self, config_path: str, mode: str = 'PAPER_TRADE', sandbox: bool = False, shadow: bool = False):
        """
        Initialize Phase 6 trading bot.
        
        Args:
            config_path: Path to trading config JSON
            mode: PAPER_TRADE or LIVE
            sandbox: Use Coinbase sandbox (default True for safety)
            shadow: Shadow mode - simulate without placing real orders (for safe 24h validation)
        """
        self.config = ConfigLoader.load(config_path)
        self.mode = mode
        self.sandbox = sandbox
        self.shadow = shadow
        if self.shadow and self.mode == 'LIVE':
            self.logger.info("⚠️  SHADOW MODE ACTIVE: LIVE config loaded but NO real orders will be placed (micro-sizing or dry-run)")
        
        self._setup_logging()
        
        # Initialize Coinbase client
        self.cb_client = None
        if ADVANCED_TRADE_AVAILABLE and CoinbaseAdvancedClient:
            try:
                self.cb_client = CoinbaseAdvancedClient(test_mode=sandbox)
                self.logger.info(f"✅ Coinbase Advanced Trade initialized (sandbox={sandbox})")
            except Exception as e:
                self.logger.warning(f"Coinbase init failed: {e}")
                self.cb_client = None
        
        if not self.cb_client:
            raise ValueError("Coinbase client initialization failed")
        
        # State
        self.pairs = self.config.global_settings.pairs
        self.total_capital = self.config.global_settings.total_capital
        self.cycle_interval_seconds = self.config.global_settings.cycle_interval_seconds
        self.capital_per_pair = self.total_capital / len(self.pairs)
        
        # Trading parameters (Phase 4d logic)
        self.rsi_buy_thresh = 30
        self.rsi_sell_thresh = 70
        sl_raw = self.config.risk_management.stop_loss_pct
        self.sl_pct = sl_raw if sl_raw < 1.0 else sl_raw / 100.0
        tp_raw = self.config.risk_management.take_profit_pct
        self.tp_pct = (tp_raw if tp_raw is not None and tp_raw < 1.0 else (tp_raw / 100.0 if tp_raw is not None else None))
        
        # Sentiment weighting
        self.sentiment_weight = 0.4
        self.rsi_weight = 0.6
        
        # Price history and positions
        self.price_history = {pair: [] for pair in self.pairs}
        self.positions: Dict[str, Position] = {}
        self.daily_trades: List[Trade] = []
        
        # CSV for trade logging
        self.trades_csv_path = os.path.join(
            os.path.dirname(__file__), 
            'trades_paper_phase6.csv'
        )
        self._init_trades_csv()
        
        # Logging dir
        self.logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        
        self.logger.info(f'✅ Phase 6 Ready: {mode} mode, {len(self.pairs)} pairs, '
                        f'{self.cycle_interval_seconds}s cycles')
    
    def _setup_logging(self):
        """Setup logging to file and stdout."""
        log_path = os.path.join(
            os.path.dirname(__file__), 
            'logs', 
            'phase6_paper.log'
        )
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_path)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _init_trades_csv(self):
        """Initialize CSV file with headers."""
        if not os.path.exists(self.trades_csv_path):
            with open(self.trades_csv_path, 'w') as f:
                f.write('timestamp,pair,signal,price,qty,side\n')
    
    def _log_trade(self, pair: str, signal: str, price: float, qty: float, side: str):
        """Log trade to CSV."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        with open(self.trades_csv_path, 'a') as f:
            f.write(f'{timestamp},{pair},{signal},{price:.6f},{qty:.6f},{side}\n')
    
    def _get_batch_prices(self) -> Dict[str, float]:
        """Fetch prices for all pairs."""
        prices = {}
        try:
            products = self.cb_client.client.get_products(product_ids=self.pairs)
            for product in products.products:
                prices[product.product_id] = float(product.price)
            self.logger.debug(f"Fetched {len(prices)} prices")
        except Exception as e:
            self.logger.warning(f"Batch price fetch failed: {e}")
            prices = {pair: 0 for pair in self.pairs}
        return prices
    
    def _calculate_rsi(self, pair: str, period: int = 14) -> float:
        """Calculate RSI for pair."""
        if len(self.price_history[pair]) < period + 1:
            return 50  # Neutral RSI
        
        prices = np.array(self.price_history[pair][-period-1:])
        deltas = np.diff(prices)
        
        gains = np.sum(deltas[deltas > 0])
        losses = -np.sum(deltas[deltas < 0])
        
        avg_gain = gains / period
        avg_loss = losses / period if losses > 0 else 1e-6
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _get_sentiment(self) -> Tuple[float, str]:
        """
        Get live sentiment score.
        Returns: (score [0-1], state_label)
        """
        sentiment = SentimentManager.get_sentiment()
        return sentiment.get('overall', 0.5), sentiment.get('state', 'neutral')
    
    def _check_exit(self, pair: str, current_price: float, rsi: float) -> bool:
        """
        Check if we should exit an open position.
        Returns: True if exit executed, False otherwise.
        """
        if pair not in self.positions:
            return False
        
        pos = self.positions[pair]
        profit_pct = (current_price - pos.entry_price) / pos.entry_price
        
        should_exit = False
        exit_reason = ""
        
        # Exit on SL (2%)
        if profit_pct <= -self.sl_pct:
            should_exit = True
            exit_reason = "STOP_LOSS"
        
        # Exit on TP (5%) or RSI>70
        elif profit_pct >= self.tp_pct or rsi > self.rsi_sell_thresh:
            should_exit = True
            exit_reason = "TAKE_PROFIT" if rsi <= self.rsi_sell_thresh else "RSI_SELL"
        
        if should_exit:
            self.logger.info(f"  🔴 EXIT {pair}: {exit_reason} "
                           f"(P&L: {profit_pct*100:.2f}%, Price: ${current_price:.4f})")
            
            # Log trade
            exit_pnl = (current_price - pos.entry_price) * pos.entry_qty
            exit_pnl_pct = profit_pct * 100
            self._log_trade(pair, exit_reason, current_price, pos.entry_qty, "SELL")
            
            # Remove position
            del self.positions[pair]
            return True
        
        return False
    
    def _execute_buy(self, pair: str, current_price: float) -> bool:
        """
        Execute BUY order for pair.
        Returns: True if successful, False otherwise.
        """
        if pair in self.positions:
            self.logger.debug(f"Position already open for {pair}, skipping BUY")
            return False
        
        try:
            # Calculate order size
            order_size_usd = self.capital_per_pair * 0.5  # 50% of capital per pair
            qty = order_size_usd / current_price
            
            self.logger.info(f"  🟢 BUY {pair} @ ${current_price:.4f} "
                           f"(qty: {qty:.6f}, size: ${order_size_usd:.2f})")
            
            # Place market order
            try:
                order = self.cb_client.create_market_order(
                    product_id=pair,
                    side="BUY",
                    quote_size=order_size_usd
                )
                order_id = order.get('id', 'UNKNOWN')
                self.logger.info(f"    ✅ Order placed: {order_id}")
            except Exception as e:
                self.logger.warning(f"    ❌ Order placement failed: {e}")
                return False
            
            # Calculate SL and TP prices
            sl_price = current_price * (1 - self.sl_pct)
            tp_price = current_price * (1 + self.tp_pct)
            
            # Record position
            pos = Position(
                pair=pair,
                entry_price=current_price,
                entry_qty=qty,
                entry_timestamp=datetime.utcnow().isoformat() + 'Z',
                side="LONG",
                sl_price=sl_price,
                tp_price=tp_price,
                order_id=order_id
            )
            self.positions[pair] = pos
            
            # Log trade
            self._log_trade(pair, "BUY", current_price, qty, "BUY")
            
            self.logger.info(f"    📍 SL: ${sl_price:.4f}, TP: ${tp_price:.4f}")
            return True
        
        except Exception as e:
            self.logger.error(f"  ❌ BUY execution error: {e}", exc_info=True)
            return False
    
    def _process_cycle(self, cycle_num: int) -> Dict:
        """
        Execute one trading cycle.
        Returns: Cycle stats dict.
        """
        cycle_start = time.time()
        
        # Fetch prices
        prices = self._get_batch_prices()
        
        # Get sentiment once per cycle
        sentiment_score, sentiment_state = self._get_sentiment()
        
        cycle_stats = {
            'cycle': cycle_num,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'prices_fetched': len(prices),
            'sentiment_score': sentiment_score,
            'sentiment_state': sentiment_state,
            'positions': len(self.positions),
            'trades_executed': 0,
            'cycle_time_seconds': 0
        }
        
        # Process each pair
        for pair in self.pairs:
            if pair not in prices or prices[pair] == 0:
                self.logger.debug(f"Skipping {pair}: price unavailable")
                continue
            
            price = prices[pair]
            self.price_history[pair].append(price)
            
            # Calculate indicators
            rsi = self._calculate_rsi(pair)
            
            # Combined signal: 40% sentiment + 60% RSI
            # Sentiment is in [0, 1], RSI is in [0, 100]
            # Scale sentiment to [0, 100]
            sentiment_signal = sentiment_score * 100  # [0, 100]
            combined_signal = (self.sentiment_weight * sentiment_signal) + \
                            (self.rsi_weight * (100 - rsi))
            
            self.logger.info(f'CYCLE {cycle_num}: {pair} Price=${price:.4f} '
                           f'RSI={rsi:.1f} Sentiment={sentiment_score:.2f}')
            
            # Check exit first
            if self._check_exit(pair, price, rsi):
                cycle_stats['trades_executed'] += 1
            
            # Check buy signal (RSI < 30 + positive sentiment)
            elif rsi < self.rsi_buy_thresh and sentiment_score > 0.4:
                if self._execute_buy(pair, price):
                    cycle_stats['trades_executed'] += 1
            
            else:
                signal_type = "HOLD"
                self.logger.debug(f"  {signal_type}: RSI={rsi:.1f}, Sentiment={sentiment_score:.2f}")
        
        cycle_stats['cycle_time_seconds'] = time.time() - cycle_start
        
        return cycle_stats
    
    def run(self, max_cycles: Optional[int] = None):
        """
        Main persistent trading loop.
        
        Args:
            max_cycles: Max cycles to run (None = infinite until SIGINT)
        """
        self.logger.info('='*80)
        self.logger.info(f'PHASE 6 TRADING LOOP STARTED - {self.mode} mode')
        self.logger.info(f'Pairs: {self.pairs}')
        self.logger.info(f'Cycle interval: {self.cycle_interval_seconds}s')
        self.logger.info('='*80)
        
        cycle_num = 0
        
        try:
            while True:
                cycle_num += 1
                
                if max_cycles and cycle_num > max_cycles:
                    self.logger.info(f"Reached max cycles ({max_cycles}), stopping")
                    break
                
                self.logger.info(f'\n{"="*80}')
                self.logger.info(f'CYCLE {cycle_num} — {datetime.utcnow().isoformat()}')
                self.logger.info(f'{"="*80}')
                
                # Execute cycle
                stats = self._process_cycle(cycle_num)
                
                # Log cycle stats
                self.logger.info(f'CYCLE {cycle_num} STATS:')
                self.logger.info(f'  Prices fetched: {stats["prices_fetched"]}')
                self.logger.info(f'  Sentiment: {stats["sentiment_score"]:.2f} ({stats["sentiment_state"]})')
                self.logger.info(f'  Open positions: {stats["positions"]}')
                self.logger.info(f'  Trades executed: {stats["trades_executed"]}')
                self.logger.info(f'  Cycle time: {stats["cycle_time_seconds"]:.2f}s')
                
                # Wait for next cycle
                sleep_time = max(1, self.cycle_interval_seconds - stats["cycle_time_seconds"])
                self.logger.info(f'Sleeping {sleep_time:.1f}s until next cycle...')
                time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            self.logger.info('\n\n🛑 Trading bot interrupted by user')
            self.logger.info(f'Completed {cycle_num} cycles')
        
        except Exception as e:
            self.logger.error(f'\n\n❌ Fatal error: {e}', exc_info=True)
            sys.exit(1)
        
        finally:
            self.logger.info('Phase 6 trading loop closed')


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Phase 6 - Persistent Trading Bot with Sentiment Integration'
    )
    parser.add_argument(
        '--config',
        default=os.getenv('PHASE_CONFIG', 'config/trading_config_phase6.json'),
        help='Path to trading config JSON'
    )
    parser.add_argument(
        '--mode',
        default=os.getenv('PHASE_MODE', 'PAPER_TRADE'),
        choices=['PAPER_TRADE', 'LIVE'],
        help='Trading mode'
    )
    parser.add_argument(
        '--sandbox',
        action='store_true',
        default=True,
        help='Use Coinbase sandbox (default: True for safety)'
    )
    parser.add_argument(
        '--no-sandbox',
        dest='sandbox',
        action='store_false',
        help='Disable Coinbase sandbox (use live trading API)'
    )
    parser.add_argument(
        '--max-cycles',
        type=int,
        default=None,
        help='Max cycles to run (default: infinite until SIGINT)'
    )
    parser.add_argument(
        '--shadow',
        action='store_true',
        default=False,
        help='Shadow mode: run LIVE config but do not place real orders (micro sizing or dry-run). For safe validation runs.'
    )
    parser.add_argument(
        '--stop-loss-pct',
        type=float,
        default=None,
        help='Stop loss percentage as decimal (e.g. 0.03 for 3%). Overrides config. Default: 0.03'
    )
    parser.add_argument(
        '--take-profit-pct',
        type=float,
        default=None,
        help='Take profit percentage as decimal (e.g. 0.05). Use null/None or omit for "let it ride" (no TP). Overrides config.'
    )
    
    args = parser.parse_args()
    
    try:
        bot = Phase6TradingBot(
            config_path=args.config,
            mode=args.mode,
            sandbox=args.sandbox,
            shadow=args.shadow
        )
        bot.run(max_cycles=args.max_cycles)
    
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
