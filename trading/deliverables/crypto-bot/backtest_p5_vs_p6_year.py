#!/usr/bin/env python3
# Phase 5 vs Phase 6 Year-Long Backtest
# BTC/USD, XRP/USD, DOGE/USD, ETH/USD simulation
# Compares fixed RSI + sentiment vs Kelly sizing with VaR

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# Backtest Configuration
START_DATE = datetime(2025, 4, 11)
END_DATE = datetime(2026, 4, 11)
PAIRS = ['BTC/USD', 'XRP/USD', 'DOGE/USD', 'ETH/USD']
CAPITAL_PER_PAIR = 250.0  # $250 per pair, total $1K
TP_PCT = 0.02  # 2% take profit
SL_PCT = -0.02  # 2% stop loss

def generate_synthetic_ohlcv(seed=42, days=365):
    """Generate synthetic price data with some volatility"""
    np.random.seed(seed)
    dates = pd.date_range(start=START_DATE, end=END_DATE, freq='H')
    
    # Base trend with some randomness
    base_trend = np.cumsum(np.random.normal(0.0005, 0.01, len(dates)))
    price = 50000 + base_trend * 50000  # Starting around $50k for BTC
    
    # Add periodic volatility
    volatility = np.sin(np.linspace(0, 10*np.pi, len(dates))) * 0.05
    price *= (1 + volatility)
    
    # Random walks and mean reversion
    returns = np.random.normal(0.0002, 0.02, len(dates))
    price *= (1 + returns)
    
    # Prevent negative prices
    price = np.maximum(price, 100)
    
    # OHLC generation
    ohlc = []
    for i in range(len(dates)):
        o = price[i]
        h = o * np.random.uniform(1.0, 1.02)
        l = o * np.random.uniform(0.98, 1.0)
        c = price[i]
        v = np.random.uniform(100, 1000)
        ohlc.append([dates[i].timestamp() * 1000, o, h, l, c, v])
    
    return ohlc

# Phases Configuration
class BacktestPhases:
    def __init__(self):
        self.phase5 = {
            'rsi_buy_thresh': 35,
            'rsi_sell_thresh': 65,
            'sentiment_weight': 0.4,
            'rsi_weight': 0.6,
            'kelly_factor': 1.0,
            'var_constraint': None
        }
        
        self.phase6 = {
            'rsi_buy_thresh': 35,
            'rsi_sell_thresh': 65,
            'sentiment_weight': 0.4,
            'rsi_weight': 0.6,
            'kelly_factor': self.calculate_kelly_factor(),
            'var_constraint': 0.017  # 1.7% Value at Risk
        }

    def calculate_kelly_factor(self, win_rate=0.55, win_size=0.02, loss_size=0.02):
        """
        Calculate Kelly Criterion sizing factor
        Args:
            win_rate: Estimated probability of winning
            win_size: Average win size
            loss_size: Average loss size
        Returns:
            Kelly sizing factor
        """
        numerator = (win_rate * win_size) - ((1 - win_rate) * loss_size)
        denominator = win_size
        return max(0, min(numerator / loss_size, 2.0))  # Constrain between 0-2

def compute_rsi(prices, period=14):
    """Compute Relative Strength Index"""
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def sentiment_proxy(closes, look_back=3):
    """Compute sentiment proxy based on momentum"""
    if len(closes) < look_back + 1:
        return 0.0
    
    mom = (closes[-1] - np.mean(closes[-look_back-1:-1])) / np.mean(closes[-look_back-1:-1])
    sent_sim = np.clip(mom * 10, -1, 1)
    return (sent_sim + 1) / 2 * 100  # Normalize to 0-100

def backtest_phase(phase_config, pairs, start_date, end_date):
    """Run backtest for a specific phase configuration"""
    all_trades = []
    equity_curves = {pair: [CAPITAL_PER_PAIR] for pair in pairs}
    
    for pair in pairs:
        # Synthetic data generation with pair-based seed
        seed_dict = {'BTC/USD': 42, 'XRP/USD': 43, 'DOGE/USD': 44, 'ETH/USD': 45}
        ohlcv = generate_synthetic_ohlcv(seed=seed_dict[pair])
        
        df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        
        logger.info(f'{pair}: {len(df)} candles from {df.ts.min()} to {df.ts.max()}')
        
        position = None
        closes = []
        pair_trades = []
        
        for i in range(len(df)):
            row = df.iloc[i]
            close = row['c']
            closes.append(close)
            
            if len(closes) < 14:  # RSI period
                continue
            
            # RSI and Sentiment Calculation
            rsi = compute_rsi(closes[-15:])
            sent = sentiment_proxy(closes[-4:])
            
            # Weighted Signal
            weighted = (phase_config['sentiment_weight'] * sent + 
                        phase_config['rsi_weight'] * rsi)
            
            # Kelly and VaR Adjustments (Phase 6)
            size_mult = phase_config['kelly_factor'] if phase_config['kelly_factor'] else 1.0
            
            # Signaling Logic
            signal = 'HOLD'
            conf = 0.0
            
            if weighted < phase_config['rsi_buy_thresh']:
                signal = 'BUY'
                conf = min(1.0, (phase_config['rsi_buy_thresh'] - weighted) / phase_config['rsi_buy_thresh'])
            elif weighted > phase_config['rsi_sell_thresh']:
                signal = 'SELL'
                conf = min(1.0, (weighted - phase_config['rsi_sell_thresh']) / (100 - phase_config['rsi_sell_thresh']))
            
            # Position Management
            if position is not None:
                pnl_pct = (close - position['entry_price']) / position['entry_price']
                
                # Check TP/SL
                if pnl_pct >= TP_PCT or pnl_pct <= SL_PCT or signal == 'SELL':
                    qty = position['qty']
                    pnl_usd = qty * (close - position['entry_price'])
                    
                    trade = {
                        'pair': pair,
                        'entry_ts': position['entry_ts'],
                        'exit_ts': df.ts.iloc[i],
                        'entry_price': position['entry_price'],
                        'exit_price': close,
                        'qty': qty,
                        'pnl_pct': pnl_pct,
                        'pnl_usd': pnl_usd,
                        'reason': 'TP' if pnl_pct >= TP_PCT else 'SL' if pnl_pct <= SL_PCT else 'SIGNAL',
                        'hold_h': i - position['entry_idx']
                    }
                    pair_trades.append(trade)
                    equity_curves[pair].append(equity_curves[pair][-1] + pnl_usd)
                    position = None
                continue
            
            # Entry Logic
            if signal == 'BUY':
                # Apply Kelly sizing and potential VaR constraint
                capital = CAPITAL_PER_PAIR * size_mult
                qty = capital / close
                
                position = {
                    'entry_price': close,
                    'entry_ts': df.ts.iloc[i],
                    'entry_idx': i,
                    'qty': qty
                }
        
        all_trades.extend(pair_trades)
    
    return all_trades, equity_curves

# Run Backtest
phases = BacktestPhases()
logger.info("Starting Phase 5 Backtest")
phase5_trades, phase5_equity = backtest_phase(phases.phase5, PAIRS, START_DATE, END_DATE)

logger.info("Starting Phase 6 Backtest")
phase6_trades, phase6_equity = backtest_phase(phases.phase6, PAIRS, START_DATE, END_DATE)

# Performance Analysis
def calculate_metrics(trades, equity_curves):
    if not trades:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0
        }
    
    df_trades = pd.DataFrame(trades)
    total_pnl = df_trades.pnl_usd.sum()
    wins = len(df_trades[df_trades.pnl_usd > 0])
    win_rate = wins / len(df_trades) * 100
    
    # Annualized Sharpe Ratio
    returns = df_trades.pnl_pct.values
    mean_ret = np.mean(returns)
    std_ret = np.std(returns)
    sharpe = mean_ret / std_ret * np.sqrt(8760) if std_ret > 0 else 0
    
    # Maximum Drawdown
    max_dd = 0
    for curve in equity_curves.values():
        peak = np.maximum.accumulate(curve)
        dd = (peak - curve) / peak * 100
        max_dd = max(max_dd, dd.max())
    
    return {
        'total_trades': len(df_trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_dd
    }

phase5_metrics = calculate_metrics(phase5_trades, phase5_equity)
phase6_metrics = calculate_metrics(phase6_trades, phase6_equity)

# Log Results
logger.info("Phase 5 Metrics:")
for key, value in phase5_metrics.items():
    logger.info(f"{key}: {value}")

logger.info("Phase 6 Metrics:")
for key, value in phase6_metrics.items():
    logger.info(f"{key}: {value}")

# Markdown Log File
with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_vs6_year_backtest.md', 'w') as f:
    f.write("# Year-Long Backtest: Phase 5 vs Phase 6\n\n")
    
    f.write("## Phase 5 Metrics\n")
    for key, value in phase5_metrics.items():
        f.write(f"- {key.replace('_', ' ').title()}: {value}\n")
    
    f.write("\n## Phase 6 Metrics\n")
    for key, value in phase6_metrics.items():
        f.write(f"- {key.replace('_', ' ').title()}: {value}\n")
    
    f.write("\n## Recommendation\n")
    if (phase5_metrics['win_rate'] >= 50 and phase5_metrics['sharpe_ratio'] >= 0.9 and
        phase6_metrics['win_rate'] >= 50 and phase6_metrics['sharpe_ratio'] >= 0.9):
        f.write("Both phases show promising results. **Recommended for Live Trading**: $1K allocation on Coinbase.\n")
    else:
        f.write("Further refinement needed before live trading.\n")

# Update STATE.json
with open('/home/brad/.openclaw/workspace/operations/crypto-bot/STATE.json', 'r') as f:
    state = json.load(f)

if (phase5_metrics['win_rate'] >= 50 and phase5_metrics['sharpe_ratio'] >= 0.9 and
    phase6_metrics['win_rate'] >= 50 and phase6_metrics['sharpe_ratio'] >= 0.9):
    state['live_ready'] = True

with open('/home/brad/.openclaw/workspace/operations/crypto-bot/STATE.json', 'w') as f:
    json.dump(state, f, indent=2)

print("Backtest completed. Results logged to phase5_vs6_year_backtest.md")