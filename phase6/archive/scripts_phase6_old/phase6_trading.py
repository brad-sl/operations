#!/usr/bin/env python3
"""
Phase 6 Trading Loop - Paper Trading Implementation

Architecture:
- Async persistent trading loop (30min cycles)
- Paper trading mode only (SANDBOX_TRADING=True)
- Phase 4d signal logic (RSI<30 BUY, RSI>70 SELL, 2% SL)
- Sentiment integration from trading-monitor cache
- Position management with open position tracking
- Trade logging to CSV with entry/exit prices and PnL
- 6 pairs: BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD, ADA-USD
- $1000 capital across all pairs

Usage:
    python3 phase6_trading.py --config config/trading_config_phase6.json --mode PAPER_TRADE

Requirements:
    - SANDBOX_MODE=True
    - SANDBOX_TRADING=True
    - PAPER_MODE=True
    - Environment variables for Coinbase credentials (sandbox)
"""

import os
import sys
import json
import csv
import time
import logging
import asyncio
import argparse
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from scripts.phase6.trade_ledger import TradeLedger
from scripts.phase6.logging_config import setup_phase6_logging
from scripts.phase6.telegram_alerts import TelegramAlerter
from scripts.phase6.anomaly_detector import AnomalyDetector


# Verify paper trading mode
SANDBOX_MODE = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'
SANDBOX_TRADING = os.getenv('SANDBOX_TRADING', 'True').lower() == 'true'
PAPER_MODE = os.getenv('PAPER_MODE', 'True').lower() == 'true'

if not (SANDBOX_MODE and SANDBOX_TRADING and PAPER_MODE):
    raise RuntimeError(
        f"Paper trading mode not enabled!\n"
        f"  SANDBOX_MODE={SANDBOX_MODE}\n"
        f"  SANDBOX_TRADING={SANDBOX_TRADING}\n"
        f"  PAPER_MODE={PAPER_MODE}"
    )


class Logger:
    """Simple logger wrapper"""
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
        )
    
    def info(self, msg):
        self.logger.info(msg)
    
    def error(self, msg):
        self.logger.error(msg)
    
    def warning(self, msg):
        self.logger.warning(msg)
    
    def debug(self, msg):
        self.logger.debug(msg)


class PriceCache:
    """Simple in-memory price cache with fallback to CoinGecko"""
    def __init__(self, logger):
        self.logger = logger
        self.prices = {}
        self.history = {}  # Track price history for RSI
    
    async def fetch_prices(self, pairs: List[str]) -> Dict[str, float]:
        """
        Fetch current prices for all pairs
        Uses CoinGecko public API (no auth needed)
        """
        try:
            import requests
            
            # Map pairs to CoinGecko IDs
            coin_map = {
                'BTC-USD': 'bitcoin',
                'ETH-USD': 'ethereum',
                'SOL-USD': 'solana',
                'XRP-USD': 'ripple',
                'DOGE-USD': 'dogecoin',
                'ADA-USD': 'cardano'
            }
            
            coin_ids = ','.join(coin_map.get(p, p.split('-')[0].lower()) for p in pairs)
            
            url = 'https://api.coingecko.com/api/v3/simple/price'
            params = {
                'ids': coin_ids,
                'vs_currencies': 'usd',
                'include_market_cap': 'false',
                'include_24hr_vol': 'false',
                'include_change': 'false'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Map back to pair format
            prices = {}
            for pair in pairs:
                coin_id = coin_map.get(pair, pair.split('-')[0].lower())
                if coin_id in data and 'usd' in data[coin_id]:
                    price = float(data[coin_id]['usd'])
                    prices[pair] = price
                    
                    # Update history for RSI
                    if pair not in self.history:
                        self.history[pair] = []
                    self.history[pair].append(price)
                    
                    # Keep only last 100 prices for RSI
                    if len(self.history[pair]) > 100:
                        self.history[pair] = self.history[pair][-100:]
                    
                    self.logger.debug(f"{pair}: ${price:.2f}")
            
            self.prices = prices
            return prices
            
        except Exception as e:
            self.logger.error(f"Price fetch error: {e}")
            # Return cached prices if available
            return self.prices


class SentimentCache:
    """Load sentiment from trading-monitor JSON cache"""
    def __init__(self, logger):
        self.logger = logger
        self.cache_file = Path('/home/brad/.openclaw/workspace/coding-products/crypto-bot/sentiment_cache.json')
        self.sentiments = {}
    
    async def load_sentiments(self) -> Dict[str, float]:
        """Load sentiments from cache file"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.sentiments = data.get('sentiments', {})
                    self.logger.debug(f"Loaded sentiments: {len(self.sentiments)} pairs")
            else:
                self.logger.warning(f"Sentiment cache not found at {self.cache_file}")
                self.sentiments = {}
            
            return self.sentiments
        except Exception as e:
            self.logger.error(f"Sentiment load error: {e}")
            return {}
    
    def get(self, pair: str, default: float = 0.0) -> float:
        """Get sentiment for a pair"""
        return self.sentiments.get(pair, default)


class RSICalculator:
    """Calculate RSI from price history"""
    def __init__(self, logger):
        self.logger = logger
    
    def calculate(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate RSI using standard formula
        
        RSI = 100 - (100 / (1 + RS))
        where RS = average gain / average loss
        """
        if len(prices) < period + 1:
            return 50.0  # Return neutral RSI if insufficient data
        
        try:
            # Calculate price changes
            deltas = []
            for i in range(1, len(prices)):
                deltas.append(prices[i] - prices[i-1])
            
            # Separate gains and losses
            gains = [max(d, 0) for d in deltas]
            losses = [abs(min(d, 0)) for d in deltas]
            
            # Calculate average gain and loss (using simple average for first calc)
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            
            # Avoid division by zero
            if avg_loss == 0:
                return 100.0 if avg_gain > 0 else 50.0
            
            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
        except Exception as e:
            self.logger.error(f"RSI calculation error: {e}")
            return 50.0


class PositionManager:
    """Manage open positions and track PnL"""
    def __init__(self, logger):
        self.logger = logger
        self.positions = {}  # pair -> {'qty': float, 'entry_price': float, 'entry_time': str}
        self.trades_log = []  # All trades (open and closed)
    
    def has_position(self, pair: str) -> bool:
        """Check if we have an open position"""
        return pair in self.positions and self.positions[pair]['qty'] > 0
    
    def open_position(self, pair: str, qty: float, entry_price: float, signal: str):
        """Open a new position"""
        self.positions[pair] = {
            'qty': qty,
            'entry_price': entry_price,
            'entry_time': datetime.utcnow().isoformat(),
            'signal': signal
        }
        self.logger.info(f"Opened {signal} position: {pair} x{qty:.6f} @ ${entry_price:.2f}")
    
    def close_position(self, pair: str, exit_price: float) -> Optional[Dict]:
        """Close an open position and calculate PnL"""
        if pair not in self.positions:
            return None
        
        pos = self.positions[pair]
        qty = pos['qty']
        entry_price = pos['entry_price']
        signal = pos['signal']
        
        # Calculate PnL
        if signal == 'BUY':
            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:  # SELL
            pnl = (entry_price - exit_price) * qty
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        
        trade = {
            'pair': pair,
            'signal': signal,
            'qty': qty,
            'entry_price': entry_price,
            'entry_time': pos['entry_time'],
            'exit_price': exit_price,
            'exit_time': datetime.utcnow().isoformat(),
            'pnl': pnl,
            'pnl_pct': pnl_pct
        }
        
        self.trades_log.append(trade)
        del self.positions[pair]
        
        self.logger.info(
            f"Closed {signal} position: {pair} | "
            f"Entry: ${entry_price:.2f}, Exit: ${exit_price:.2f} | "
            f"PnL: ${pnl:.2f} ({pnl_pct:.2f}%)"
        )
        
        return trade


class Phase6TradingBot:
    """Phase 6 Paper Trading Bot"""
    
    def __init__(self, config_path: str, logger: Logger):
        self.logger = logger
        self.config = self._load_config(config_path)
        
        # Trading parameters
        self.pairs = self.config['global_settings']['pairs']
        self.total_capital = self.config['global_settings']['total_capital']
        self.capital_per_pair = self.total_capital / len(self.pairs)
        self.cycle_interval = self.config['global_settings']['cycle_interval_seconds']
        
        # Risk management
        self.stop_loss_pct = self.config['risk_management']['stop_loss_pct']
        self.take_profit_pct = self.config['risk_management']['take_profit_pct']
        
        # Initialize components
        self.price_cache = PriceCache(logger)
        self.sentiment_cache = SentimentCache(logger)
        self.rsi_calc = RSICalculator(logger)
        self.position_manager = PositionManager(logger)

        # Initialize Phase 6 observability components
        self.trade_ledger = TradeLedger()
        self.alerter = TelegramAlerter()
        self.anomaly_detector = AnomalyDetector(max_drawdown_pct=5.0, max_failures=3)
        
        # Setup structured logging
        self.structured_logger = setup_phase6_logging()
        
        # Trade logging
        self.trades_csv_path = Path(os.path.dirname(__file__)) / 'trades_paper_phase6.csv'
        self._init_trades_csv()
        
        # Paper portfolio P&L persistence
        self.portfolio_state_path = Path('/home/brad/projects/crypto-trading-bot/data/state/paper_portfolio.json')
        
        self.cycle_count = 0
        
        self.logger.info(f"Phase 6 Trading Bot initialized:")
        self.logger.info(f"  Pairs: {', '.join(self.pairs)}")
        self.logger.info(f"  Total capital: ${self.total_capital:.2f}")
        self.logger.info(f"  Capital per pair: ${self.capital_per_pair:.2f}")
        self.logger.info(f"  Cycle interval: {self.cycle_interval}s")
        self.logger.info(f"  Trade log: {self.trades_csv_path}")
        # Send launch notification via Telegram
        if hasattr(self, "alerter"):
            try:
                status = {
                    "capital": self.total_capital,
                    "pairs": self.pairs,
                    "mode": "LIVE" if not PAPER_MODE else "PAPER",
                    "open_positions": len(getattr(self.position_manager, "positions", {}))
                }
                self.alerter.send_launch_overview(status)
            except Exception as e:
                self.logger.error(f"Failed to send launch alert: {e}")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            self.logger.info(f"Configuration loaded: {config_path}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise
    
    def _init_trades_csv(self):
        """Initialize trades CSV with headers"""
        try:
            # Write header if file doesn't exist
            if not self.trades_csv_path.exists():
                with open(self.trades_csv_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'timestamp', 'pair', 'signal', 'entry_price', 'qty', 
                        'exit_price', 'pnl', 'pnl_pct'
                    ])
                    writer.writeheader()
                self.logger.info(f"Trades CSV initialized: {self.trades_csv_path}")
        except Exception as e:
            self.logger.error(f"Failed to init trades CSV: {e}")
    
    async def run(self):
        """Main trading loop"""
        self.logger.info("Starting Phase 6 trading loop (PAPER MODE)")
        
        try:
            while True:
                self.cycle_count += 1
                await self._run_cycle()
                
                # Wait for next cycle
                self.logger.info(f"Waiting {self.cycle_interval}s until next cycle...")
                await asyncio.sleep(self.cycle_interval)
        
        except KeyboardInterrupt:
            self.logger.info("Trading loop interrupted by user")
            await self._shutdown()
        except Exception as e:
            self.logger.error(f"Trading loop error: {e}")
            await self._shutdown()
            raise
    
    async def _run_cycle(self):
        """Execute one trading cycle"""
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"CYCLE {self.cycle_count} - {datetime.utcnow().isoformat()}")
        self.logger.info(f"{'='*80}")
        
        try:
            # 1. Fetch prices
            prices = await self.price_cache.fetch_prices(self.pairs)
            if not prices:
                self.logger.warning("No prices fetched, skipping cycle")
                return
            
            # 2. Load sentiments
            await self.sentiment_cache.load_sentiments()
            
            # 3. Process each pair
            for pair in self.pairs:
                if pair not in prices:
                    self.logger.warning(f"{pair}: No price available")
                    continue
                
                try:
                    await self._process_pair(pair, prices[pair])
                except Exception as e:
                    self.logger.error(f"{pair}: Processing error: {e}")
            
            # 4. Log cycle summary
            self._log_cycle_summary()
        
        except Exception as e:
            self.logger.error(f"Cycle {self.cycle_count} error: {e}")
    
    async def _process_pair(self, pair: str, current_price: float):
        """Process one pair (check signals, manage positions)"""
        
        # Get technical indicators
        prices = self.price_cache.history.get(pair, [])
        if not prices:
            self.logger.warning(f"{pair}: No price history")
            return
        
        rsi = self.rsi_calc.calculate(prices)
        sentiment = self.sentiment_cache.get(pair, 0.0)
        
        self.logger.info(
            f"{pair}: Price=${current_price:.4f}, RSI={rsi:.1f}, Sentiment={sentiment:.4f}"
        )
        
        # Check if we have an open position
        if self.position_manager.has_position(pair):
            await self._check_exit_conditions(pair, current_price, rsi)
        else:
            # No open position, check entry signals
            signal = self._generate_signal(pair, rsi, sentiment)
            if signal in ['BUY', 'SELL']:
                await self._enter_position(pair, signal, current_price)
    
    def _generate_signal(self, pair: str, rsi: float, sentiment: float) -> str:
        """
        Generate trading signal (Phase 4d logic)
        
        BUY:  RSI < 30 (oversold)
        SELL: RSI > 70 (overbought)
        HOLD: Otherwise
        """
        if rsi < 30:
            self.logger.info(f"{pair}: Signal=BUY (RSI={rsi:.1f} < 30)")
            return 'BUY'
        elif rsi > 70:
            self.logger.info(f"{pair}: Signal=SELL (RSI={rsi:.1f} > 70)")
            return 'SELL'
        else:
            self.logger.debug(f"{pair}: Signal=HOLD (RSI={rsi:.1f})")
            return 'HOLD'
    
    async def _enter_position(self, pair: str, signal: str, entry_price: float):
        """Enter a new position"""
        try:
            qty = self.capital_per_pair / entry_price
            self.position_manager.open_position(pair, qty, entry_price, signal)
            
            # Log to CSV
            self._log_trade(pair, signal, entry_price, qty, None, None, None)
            
        except Exception as e:
            self.logger.error(f"{pair}: Failed to enter position: {e}")
    
    async def _check_exit_conditions(self, pair: str, current_price: float, rsi: float):
        """Check if we should exit an open position"""
        pos = self.position_manager.positions[pair]
        entry_price = pos['entry_price']
        signal = pos['signal']
        qty = pos['qty']
        
        # Calculate SL and TP levels
        if signal == 'BUY':
            sl_price = entry_price * (1 - self.stop_loss_pct / 100)
            tp_price = entry_price * (1 + self.take_profit_pct / 100)
            
            # Exit conditions
            if current_price <= sl_price:
                self.logger.warning(
                    f"{pair}: STOP LOSS hit! Price=${current_price:.4f} <= SL=${sl_price:.4f}"
                )
                trade = self.position_manager.close_position(pair, current_price)
                self._log_trade_closed(trade)
            elif current_price >= tp_price:
                self.logger.info(
                    f"{pair}: TAKE PROFIT hit! Price=${current_price:.4f} >= TP=${tp_price:.4f}"
                )
                trade = self.position_manager.close_position(pair, current_price)
                self._log_trade_closed(trade)
        
        else:  # SELL signal
            sl_price = entry_price * (1 + self.stop_loss_pct / 100)
            tp_price = entry_price * (1 - self.take_profit_pct / 100)
            
            if current_price >= sl_price:
                self.logger.warning(
                    f"{pair}: STOP LOSS hit! Price=${current_price:.4f} >= SL=${sl_price:.4f}"
                )
                trade = self.position_manager.close_position(pair, current_price)
                self._log_trade_closed(trade)
            elif current_price <= tp_price:
                self.logger.info(
                    f"{pair}: TAKE PROFIT hit! Price=${current_price:.4f} <= TP=${tp_price:.4f}"
                )
                trade = self.position_manager.close_position(pair, current_price)
                self._log_trade_closed(trade)
    
    def _log_trade(self, pair: str, signal: str, entry_price: float, qty: float,
                   exit_price: Optional[float], pnl: Optional[float], pnl_pct: Optional[float]):
        """Log a trade entry to CSV"""
        try:
            with open(self.trades_csv_path, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'pair', 'signal', 'entry_price', 'qty',
                    'exit_price', 'pnl', 'pnl_pct'
                ])
                writer.writerow({
                    'timestamp': datetime.utcnow().isoformat(),
                    'pair': pair,
                    'signal': signal,
                    'entry_price': entry_price,
                    'qty': qty,
                    'exit_price': exit_price or '',
                    'pnl': pnl or '',
                    'pnl_pct': pnl_pct or ''
                })
        except Exception as e:
            self.logger.error(f"Failed to log trade: {e}")
    
    def _log_trade_closed(self, trade: Dict):
        """Update CSV with closed trade info"""
        try:
            with open(self.trades_csv_path, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'pair', 'signal', 'entry_price', 'qty',
                    'exit_price', 'pnl', 'pnl_pct'
                ])
                writer.writerow({
                    'timestamp': datetime.utcnow().isoformat(),
                    'pair': trade['pair'],
                    'signal': f"{trade['signal']}_CLOSED",
                    'entry_price': trade['entry_price'],
                    'qty': trade['qty'],
                    'exit_price': trade['exit_price'],
                    'pnl': f"{trade['pnl']:.4f}",
                    'pnl_pct': f"{trade['pnl_pct']:.2f}"
                })
        except Exception as e:
            self.logger.error(f"Failed to log closed trade: {e}")
            # Also write to new TradeLedger
            if hasattr(self, "trade_ledger"):
                ledger_trade = {
                    "pair": trade.get("pair"),
                    "side": trade.get("signal"),
                    "qty": trade.get("qty"),
                    "entry_price": trade.get("entry_price"),
                    "exit_price": trade.get("exit_price"),
                    "pnl": trade.get("pnl"),
                    "pnl_pct": trade.get("pnl_pct"),
                    "signal_source": "phase6"
                }
                self.trade_ledger.log_trade(ledger_trade)
                self.anomaly_detector.record_trade(ledger_trade)
    
    def _log_cycle_summary(self):
        """Log summary of current positions"""
        open_count = len(self.position_manager.positions)
        closed_count = len(self.position_manager.trades_log)
        
        self.logger.info(f"Cycle {self.cycle_count} Summary:")
        self.logger.info(f"  Open positions: {open_count}")
        self.logger.info(f"  Closed trades: {closed_count}")
        
        if self.position_manager.positions:
            self.logger.info("  Open positions:")
            for pair, pos in self.position_manager.positions.items():
                self.logger.info(
                    f"    {pair}: {pos['signal']} x{pos['qty']:.6f} @ ${pos['entry_price']:.2f}"
                )
    
    async def _shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down...")
        
        # Log final summary
        self.logger.info(f"\nFinal Summary (Cycle {self.cycle_count}):")
        self.logger.info(f"  Total closed trades: {len(self.position_manager.trades_log)}")
        
        if self.position_manager.trades_log:
            total_pnl = sum(t['pnl'] for t in self.position_manager.trades_log)
            avg_pnl_pct = np.mean([t['pnl_pct'] for t in self.position_manager.trades_log])
            
            self.logger.info(f"  Total PnL: ${total_pnl:.2f}")
            self.logger.info(f"  Avg PnL%: {avg_pnl_pct:.2f}%")
            self.logger.info(f"  Trade log: {self.trades_csv_path}")
        # Send launch notification via Telegram
        if hasattr(self, "alerter"):
            try:
                status = {
                    "capital": self.total_capital,
                    "pairs": self.pairs,
                    "mode": "LIVE" if not PAPER_MODE else "PAPER",
                    "open_positions": len(getattr(self.position_manager, "positions", {}))
                }
                self.alerter.send_launch_overview(status)
            except Exception as e:
                self.logger.error(f"Failed to send launch alert: {e}")


async def main():
    """Entry point"""
    parser = argparse.ArgumentParser(description='Phase 6 Paper Trading Bot')
    parser.add_argument('--config', default='config/trading_config_phase6.json',
                        help='Configuration file path')
    parser.add_argument('--mode', default='PAPER_TRADE', help='Trading mode')
    args = parser.parse_args()
    
    logger = Logger('phase6_trading')
    
    # Verify paper trading mode is enabled
    logger.info(f"Mode: {args.mode}")
    logger.info(f"SANDBOX_MODE: {SANDBOX_MODE}")
    logger.info(f"SANDBOX_TRADING: {SANDBOX_TRADING}")
    logger.info(f"PAPER_MODE: {PAPER_MODE}")
    
    if args.mode != 'PAPER_TRADE':
        logger.error(f"Invalid mode: {args.mode}. Only PAPER_TRADE supported.")
        sys.exit(1)
    
    # Create and run bot
    bot = Phase6TradingBot(args.config, logger)
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())
