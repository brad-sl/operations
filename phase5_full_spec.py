#!/usr/bin/env python3
"""
Phase 5 Full Specification Implementation
Implements StochRSI(14,3,3) crossover + adaptive 2×ATR stops (as per spec)

Entry: %K > %D crossover while StochRSI < 0.2 (oversold)
Exit: +5% TP OR 2×ATR SL
Sentiment: 40% weight for confidence boost
"""

import os
import sys
import json
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Custom modules
from price_wrapper import PublicExchangePriceWrapper
from position_state_manager import PositionStateManager
from indicators.stochrsi_strategy import StochRSISignalCalculator

try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    ADVANCED_TRADE_AVAILABLE = False

load_dotenv()
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

class Phase5FullSpec:
    def __init__(self, sandbox=True):
        load_dotenv()
        self._setup_logging()
        
        self.sandbox = sandbox
        self.price_wrapper = PublicExchangePriceWrapper()
        self.cb_client = None
        
        if ADVANCED_TRADE_AVAILABLE:
            try:
                self.cb_client = CoinbaseAdvancedClient(test_mode=sandbox)
                self.logger.info(f"✅ Coinbase Advanced Trade API initialized (sandbox={sandbox})")
            except Exception as e:
                self.logger.warning(f"Advanced Trade API init failed: {e}")
                self.cb_client = None
        
        # Position management
        self.POSITION_MANAGER = PositionStateManager()
        
        # StochRSI calculator
        self.stochrsi_calc = StochRSISignalCalculator(
            rsi_period=14,
            k_smooth=3,
            d_smooth=3,
            oversold_threshold=0.2,
            sentiment_weight=0.4
        )
        
        # Configuration (from spec)
        self.pairs = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD', 'ADA-USD']
        self.total_capital = 1000
        self.capital_per_pair = self.total_capital / len(self.pairs)
        
        # Trading parameters from spec
        self.tp_pct = 0.05  # 5% take profit (from spec)
        self.atr_multiple = 2.0  # 2×ATR for stop loss
        self.atr_period = 14
        self.sentiment_weight = 0.4
        
        # Price/ATR history
        self.price_history = {pair: [] for pair in self.pairs}
        self.atr_history = {pair: [] for pair in self.pairs}
        
        self.logger.info(f'✅ Phase 5 Full Spec initialized: {len(self.pairs)} pairs')
    
    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(os.path.join(log_dir, 'phase5_full_spec.log'))
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _calculate_atr(self, pair, highs, lows, closes, period=14):
        """Calculate Average True Range"""
        if len(closes) < period:
            return None
        
        trs = []
        for i in range(len(closes)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )
            trs.append(tr)
        
        atr = np.mean(trs[-period:])
        return atr
    
    def _get_sentiment(self, pair):
        """Get sentiment score (0-1)"""
        try:
            cache_file = os.path.join(os.path.dirname(__file__), 'sentiment_cache.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    sentiment_data = json.load(f)
                    return sentiment_data.get(pair, {'score': 0.5}).get('score', 0.5)
        except Exception as e:
            self.logger.warning(f"Sentiment fetch failed: {e}")
        
        return 0.5  # Neutral default
    
    def run_backtest(self, pair, closes, highs, lows):
        """Run backtest on real price data"""
        trades = []
        positions = {}
        pnl = 0
        
        # Build price/ATR history
        for i in range(self.atr_period, len(closes)):
            price = closes[i]
            high_window = highs[max(0, i-self.atr_period):i+1]
            low_window = lows[max(0, i-self.atr_period):i+1]
            close_window = closes[max(0, i-self.atr_period):i+1]
            
            # Calculate ATR
            atr = self._calculate_atr(pair, high_window, low_window, close_window, self.atr_period)
            
            # Price history for StochRSI
            price_slice = closes[max(0, i-50):i+1]
            
            # Get StochRSI signal
            k, d, stochrsi = self.stochrsi_calc.compute_stochrsi(price_slice)
            
            # Get sentiment
            sentiment = self._get_sentiment(pair)
            
            # Exit logic
            if pair in positions:
                pos = positions[pair]
                entry_price = pos['entry_price']
                profit_pct = (price - entry_price) / entry_price
                
                should_exit = False
                exit_reason = ""
                
                # Exit on +5% TP
                if profit_pct >= self.tp_pct:
                    should_exit = True
                    exit_reason = "TP"
                
                # Exit on 2×ATR SL
                if atr and profit_pct <= -(self.atr_multiple * atr / entry_price):
                    should_exit = True
                    exit_reason = "SL"
                
                if should_exit:
                    trade_pnl = (price - entry_price) * pos['entry_qty']
                    pnl += trade_pnl
                    
                    trades.append({
                        'entry_price': entry_price,
                        'exit_price': price,
                        'pnl': trade_pnl,
                        'pnl_pct': profit_pct * 100,
                        'reason': exit_reason
                    })
                    
                    del positions[pair]
            
            # Entry logic: %K > %D crossover AND StochRSI < 0.2 AND sentiment > 0.5
            if pair not in positions:
                k_prev = self.stochrsi_calc.last_k
                d_prev = self.stochrsi_calc.last_d
                
                # Crossover detection
                is_crossover = (k_prev and d_prev and k_prev <= d_prev and k > d)
                
                if is_crossover and stochrsi < 0.2 and sentiment > 0.5:
                    qty = self.capital_per_pair / price
                    positions[pair] = {
                        'entry_price': price,
                        'entry_qty': qty,
                        'atr': atr,
                    }
            
            # Update StochRSI state for next iteration
            self.stochrsi_calc.last_k = k
            self.stochrsi_calc.last_d = d
        
        # Close remaining positions
        if pair in positions:
            pos = positions[pair]
            final_pnl = (closes[-1] - pos['entry_price']) * pos['entry_qty']
            pnl += final_pnl
            trades.append({
                'entry_price': pos['entry_price'],
                'exit_price': closes[-1],
                'pnl': final_pnl,
                'pnl_pct': ((closes[-1] - pos['entry_price']) / pos['entry_price']) * 100,
                'reason': 'END'
            })
        
        return trades, pnl
    
    def get_metrics(self, trades, capital):
        """Calculate backtest metrics"""
        if not trades:
            return None
        
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] <= 0]
        
        return {
            'total_trades': len(trades),
            'winning': len(winning),
            'losing': len(losing),
            'win_rate': (len(winning) / len(trades) * 100) if trades else 0,
            'total_pnl': trades_df['pnl'].sum(),
            'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
            'avg_loss': losing['pnl'].mean() if len(losing) > 0 else 0,
            'max_win': winning['pnl'].max() if len(winning) > 0 else 0,
            'max_loss': losing['pnl'].min() if len(losing) > 0 else 0,
        }

# For testing
if __name__ == '__main__':
    print("Phase 5 Full Spec module loaded")
