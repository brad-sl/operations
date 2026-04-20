#!/usr/bin/env python3
"""
6-month backtest: Phase 4d (DynamicRSI) vs Grok's StochRSI rule
All 4 pairs (BTC, XRP, DOGE, ETH) — Jan 1 to Apr 6, 2026
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# ── Setup ────────────────────────────────────────────────────────────────────
PAIRS = ['BTC/USD', 'XRP/USD', 'DOGE/USD', 'ETH/USD']
START = datetime(2026, 1, 1)
END = datetime(2026, 4, 6)
CAPITAL_PER_PAIR = 250.0
TP_PCT = 0.05
SL_PCT_PHASE4D = -0.02
ATR_PERIOD = 14
RSI_PERIOD = 14

exchange = ccxt.coinbase()

def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 0.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

def compute_stochrsi(prices, rsi_period=14, k_period=3, d_period=3):
    """StochRSI: %K = (RSI - min_RSI) / (max_RSI - min_RSI) * 100"""
    if len(prices) < rsi_period + k_period:
        return 50.0, 50.0
    rsi = compute_rsi(prices[-rsi_period-k_period:], rsi_period)
    rsi_vals = [compute_rsi(prices[max(0, i-rsi_period):i+1], rsi_period) 
                for i in range(len(prices)-k_period, len(prices))]
    if not rsi_vals:
        return 50.0, 50.0
    min_rsi = min(rsi_vals)
    max_rsi = max(rsi_vals)
    if max_rsi == min_rsi:
        k = 50.0
    else:
        k = ((rsi - min_rsi) / (max_rsi - min_rsi)) * 100
    d = np.mean([compute_rsi(prices[max(0, i-rsi_period):i+1], rsi_period) 
                 for i in range(max(0, len(prices)-d_period), len(prices))])
    return k, d

def compute_atr(df, period=14):
    df['tr'] = np.maximum(
        df['h'] - df['l'],
        np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1)))
    )
    df['atr'] = df['tr'].rolling(period).mean()
    return df['atr'].iloc[-1] if len(df) > period else df['h'].iloc[-1] - df['l'].iloc[-1]

def backtest_pair(pair, data_df):
    """Run both strategies on same data"""
    trades_4d = []
    trades_sr = []
    
    position = None
    prices = list(data_df['c'])
    closes = prices[-min(200, len(prices)):]
    
    for i in range(RSI_PERIOD, len(data_df)):
        candle = data_df.iloc[i]
        closes.append(candle['c'])
        closes = closes[-RSI_PERIOD-20:]
        
        # ── Phase 4d Entry ──────────────────────────────────────────────────
        rsi = compute_rsi(closes, RSI_PERIOD)
        buy_signal_4d = rsi < 30
        
        if not position and buy_signal_4d:
            position = {
                'strategy': '4d',
                'entry_price': candle['c'],
                'entry_idx': i,
                'entry_time': candle['t']
            }
        
        # ── StochRSI Entry ──────────────────────────────────────────────────
        k, d = compute_stochrsi(closes, RSI_PERIOD, 3, 3)
        buy_signal_sr = k > d and k < 20
        
        if not position and buy_signal_sr:
            position = {
                'strategy': 'sr',
                'entry_price': candle['c'],
                'entry_idx': i,
                'entry_time': candle['t']
            }
        
        # ── Exit Logic ──────────────────────────────────────────────────────
        if position:
            pnl_pct = (candle['c'] - position['entry_price']) / position['entry_price']
            
            # TP or SL
            exit_reason = None
            if pnl_pct >= TP_PCT:
                exit_reason = 'TP'
            elif position['strategy'] == '4d' and pnl_pct <= SL_PCT_PHASE4D:
                exit_reason = 'SL'
            elif position['strategy'] == 'sr':
                atr = compute_atr(data_df.iloc[max(0, i-ATR_PERIOD):i+1], ATR_PERIOD)
                sl_sr = -2 * atr / position['entry_price']
                if pnl_pct <= sl_sr:
                    exit_reason = 'SL'
            
            if exit_reason:
                trade = {
                    'pair': pair,
                    'entry': position['entry_price'],
                    'exit': candle['c'],
                    'pnl': candle['c'] - position['entry_price'],
                    'pnl_pct': pnl_pct,
                    'reason': exit_reason
                }
                if position['strategy'] == '4d':
                    trades_4d.append(trade)
                else:
                    trades_sr.append(trade)
                position = None
    
    return trades_4d, trades_sr

def calc_sharpe(trades, capital):
    if not trades:
        return 0.0, 0.0, 0.0, 0.0
    pnls = [t['pnl'] for t in trades]
    returns = np.array(pnls) / capital
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0.0
    win_pct = sum(1 for t in trades if t['pnl'] > 0) / len(trades) * 100
    total_pnl = sum(pnls)
    max_dd = min(pnls) if pnls else 0.0
    return sharpe, win_pct, total_pnl, max_dd

# ── Main ──────────────────────────────────────────────────────────────────────
logger.info("Fetching 6-month data from Coinbase...")
all_trades_4d = []
all_trades_sr = []

for pair in PAIRS:
    logger.info(f"Backtesting {pair}...")
    try:
        start_ts = int(START.timestamp() * 1000)
        end_ts = int(END.timestamp() * 1000)
        
        ohlcv = exchange.fetch_ohlcv(pair, '1h', since=start_ts, limit=4320)
        if len(ohlcv) < RSI_PERIOD:
            logger.warning(f"{pair}: Insufficient data")
            continue
        
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        
        trades_4d, trades_sr = backtest_pair(pair, df)
        all_trades_4d.extend(trades_4d)
        all_trades_sr.extend(trades_sr)
        
        sharpe_4d, win_4d, pnl_4d, dd_4d = calc_sharpe(trades_4d, CAPITAL_PER_PAIR)
        sharpe_sr, win_sr, pnl_sr, dd_sr = calc_sharpe(trades_sr, CAPITAL_PER_PAIR)
        
        delta_sharpe = ((sharpe_sr - sharpe_4d) / sharpe_4d * 100) if sharpe_4d > 0 else 0
        flag = "✅ PHASE 5" if delta_sharpe >= 8 else "❌ KEEP 4D"
        
        print(f"\n{pair}")
        print(f"Phase 4d:  Sharpe={sharpe_4d:.2f} | Win%={win_4d:.1f}% | PnL=${pnl_4d:.2f} | Trades={len(trades_4d)}")
        print(f"StochRSI:  Sharpe={sharpe_sr:.2f} | Win%={win_sr:.1f}% | PnL=${pnl_sr:.2f} | Trades={len(trades_sr)}")
        print(f"Δ Sharpe: {delta_sharpe:+.1f}% {flag}")
        
    except Exception as e:
        logger.error(f"{pair}: {e}")

# ── Aggregate ────────────────────────────────────────────────────────────────
sharpe_4d_agg, win_4d_agg, pnl_4d_agg, dd_4d_agg = calc_sharpe(all_trades_4d, CAPITAL_PER_PAIR * 4)
sharpe_sr_agg, win_sr_agg, pnl_sr_agg, dd_sr_agg = calc_sharpe(all_trades_sr, CAPITAL_PER_PAIR * 4)
delta_agg = ((sharpe_sr_agg - sharpe_4d_agg) / sharpe_4d_agg * 100) if sharpe_4d_agg > 0 else 0
rec = "✅ DEPLOY PHASE 5" if delta_agg >= 8 else "❌ KEEP PHASE 4D"

print(f"\n{'='*70}")
print(f"AGGREGATE (ALL 4 PAIRS)")
print(f"{'='*70}")
print(f"Phase 4d:  Sharpe={sharpe_4d_agg:.2f} | Win%={win_4d_agg:.1f}% | PnL=${pnl_4d_agg:.2f} | Trades={len(all_trades_4d)}")
print(f"StochRSI:  Sharpe={sharpe_sr_agg:.2f} | Win%={win_sr_agg:.1f}% | PnL=${pnl_sr_agg:.2f} | Trades={len(all_trades_sr)}")
print(f"\nΔ Sharpe: {delta_agg:+.1f}%")
print(f"\nRECOMMENDATION: {rec}")
print(f"{'='*70}")

logger.info("Backtest complete.")
