#!/usr/bin/env python3
"""
combined_strategy_backtest.py
Ablation harness for TEST-COMBINED-INDICATOR-ABLATION-2026-08

Real BTC-USD daily data (yfinance, 2021-01-01 to present).
Long-only, 95% equity sizing.
Fees: 5 bps/side baseline (also report 10 bps).

Entry (A0 baseline):
  MACD bullish cross (no look-ahead) AND RSI(14) < 30 AND Stoch %K(14,3,3) < 20 AND Close <= BB lower(20,2)

Exit: ANY of
  MACD bearish cross OR RSI > 70 OR Stoch %K > 80 OR Close >= BB upper

ARMS:
A0: full stack (MACD + RSI + Stoch + BB)
A1: drop Stoch
A2: drop RSI
A3: drop BB touch
A4: MACD + (RSI OR Stoch) + BB
A5: MACD + RSI only
A6: RSI + BB only
A7: A0 entry + ATR(14)*2 trailing stop
A8: A0 entry + fixed -8% SL +16% TP
A9: best simplified + ATR trail + MACD bearish emergency

Metrics per arm: N, win rate, avg win/loss %, expectancy, total return, max DD, Sharpe, bars held, exit-reason mix, delta vs A0.
Flag N<15 inconclusive.

Deliverables: console table + data/state/trials/TEST_COMBINED_INDICATOR_ABLATION_2026-08.json
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date
import json
import os

def download_data(ticker="BTC-USD", start="2021-01-01", end=None):
    if end is None:
        end = date.today().isoformat()
    df = yf.download(ticker, start=start, end=end, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    df.index = pd.to_datetime(df.index)
    return df

def compute_indicators(df):
    df = df.copy()
    # MACD
    df['ema12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # RSI(14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Stochastic %K(14,3,3)
    low14 = df['Low'].rolling(14).min()
    high14 = df['High'].rolling(14).max()
    df['stoch_k'] = 100 * (df['Close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    
    # Bollinger Bands (20,2)
    df['bb_mid'] = df['Close'].rolling(20).mean()
    bb_std = df['Close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    
    # ATR(14) for trailing
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    df = df.dropna()
    return df

def backtest_arm(df, arm='A0', fee_bps=5, initial_equity=10000.0):
    df = df.copy()
    position = 0.0
    entry_price = 0.0
    equity = initial_equity
    trades = []
    equity_curve = [equity]
    exit_reasons = {'MACD_bear': 0, 'RSI_high': 0, 'Stoch_high': 0, 'BB_upper': 0, 'TRAIL': 0, 'SL': 0, 'TP': 0, 'EOD': 0}
    
    fee = fee_bps / 10000.0
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Entry conditions (A0 baseline)
        macd_bull = (prev['macd'] < prev['macd_signal']) and (row['macd'] > row['macd_signal'])
        rsi_low = row['rsi'] < 30
        stoch_low = row['stoch_k'] < 20
        bb_touch = row['Close'] <= row['bb_lower']
        
        entry_cond = macd_bull and rsi_low and stoch_low and bb_touch
        
        # Arm modifications to entry
        if arm == 'A1':  # drop Stoch
            entry_cond = macd_bull and rsi_low and bb_touch
        elif arm == 'A2':  # drop RSI
            entry_cond = macd_bull and stoch_low and bb_touch
        elif arm == 'A3':  # drop BB
            entry_cond = macd_bull and rsi_low and stoch_low
        elif arm == 'A4':  # MACD + (RSI OR Stoch) + BB
            entry_cond = macd_bull and (rsi_low or stoch_low) and bb_touch
        elif arm == 'A5':  # MACD + RSI only
            entry_cond = macd_bull and rsi_low
        elif arm == 'A6':  # RSI + BB only
            entry_cond = rsi_low and bb_touch
        
        exit_cond = False
        reason = None
        
        if position > 0:
            # Base exits
            macd_bear = (prev['macd'] > prev['macd_signal']) and (row['macd'] < row['macd_signal'])
            rsi_high = row['rsi'] > 70
            stoch_high = row['stoch_k'] > 80
            bb_upper = row['Close'] >= row['bb_upper']
            
            if macd_bear:
                exit_cond = True
                reason = 'MACD_bear'
            elif rsi_high:
                exit_cond = True
                reason = 'RSI_high'
            elif stoch_high:
                exit_cond = True
                reason = 'Stoch_high'
            elif bb_upper:
                exit_cond = True
                reason = 'BB_upper'
            
            # Arm-specific exits
            if arm == 'A7':  # ATR trailing
                trail_stop = entry_price - (2 * row['atr'])  # simplified trailing
                if row['Close'] < trail_stop:
                    exit_cond = True
                    reason = 'TRAIL'
            if arm == 'A8':  # fixed SL/TP
                if row['Close'] <= entry_price * 0.92:
                    exit_cond = True
                    reason = 'SL'
                elif row['Close'] >= entry_price * 1.16:
                    exit_cond = True
                    reason = 'TP'
            if arm == 'A9':  # simplified + ATR + MACD emergency
                if macd_bear:
                    exit_cond = True
                    reason = 'MACD_bear'
        
        # Execute
        if position == 0 and entry_cond:
            position = (equity * 0.95) / row['Close']
            entry_price = row['Close']
            equity -= position * row['Close'] * fee  # entry fee on notional
            trades.append({'entry_date': row.name, 'entry_price': entry_price, 'shares': position})
        
        elif position > 0 and exit_cond:
            exit_price = row['Close']
            pnl = (exit_price - entry_price) * position
            equity += pnl - (position * exit_price * fee)
            trades[-1].update({
                'exit_date': row.name,
                'exit_price': exit_price,
                'pnl': pnl,
                'equity_after': equity,
                'reason': reason
            })
            if reason in exit_reasons:
                exit_reasons[reason] += 1
            position = 0.0
            entry_price = 0.0
        
        # Mark to market
        if position > 0:
            mtm = equity + (position * row['Close']) - (position * row['Close'] * fee)  # rough
            equity_curve.append(mtm)
        else:
            equity_curve.append(equity)
    
    # Close any open at end
    if position > 0:
        last_price = df['Close'].iloc[-1]
        pnl = (last_price - entry_price) * position
        equity += pnl
        trades[-1].update({
            'exit_date': df.index[-1],
            'exit_price': last_price,
            'pnl': pnl,
            'equity_after': equity,
            'reason': 'EOD'
        })
        exit_reasons['EOD'] += 1
    
    # Metrics
    if not trades:
        return {'N': 0, 'arm': arm}
    
    n = len(trades)
    wins = [t for t in trades if t.get('pnl', 0) > 0]
    win_rate = len(wins) / n if n > 0 else 0
    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    losses = [t for t in trades if t.get('pnl', 0) <= 0]
    avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss) if n > 0 else 0
    
    total_return = (equity - initial_equity) / initial_equity
    equity_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(equity_arr)
    dd = (equity_arr - peak) / peak
    max_dd = np.min(dd) if len(dd) > 0 else 0
    
    returns = np.diff(equity_arr) / equity_arr[:-1]
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0
    
    bars_held = [ (t.get('exit_date') - t.get('entry_date')).days for t in trades if 'exit_date' in t ]
    avg_bars = np.mean(bars_held) if bars_held else 0
    
    metrics = {
        'arm': arm,
        'N': n,
        'win_rate': round(win_rate, 4),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'expectancy': round(expectancy, 2),
        'total_return': round(total_return, 4),
        'max_dd': round(max_dd, 4),
        'sharpe': round(sharpe, 4),
        'avg_bars_held': round(avg_bars, 1),
        'exit_reasons': exit_reasons,
        'final_equity': round(equity, 2)
    }
    return metrics, trades, equity_curve

def run_ablation():
    print("Downloading BTC-USD data...")
    df = download_data()
    print(f"Data: {len(df)} bars from {df.index[0].date()} to {df.index[-1].date()}")
    
    df = compute_indicators(df)
    
    arms = ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9']
    results = {}
    all_trades = {}
    
    for arm in arms:
        print(f"Backtesting arm {arm}...")
        m, trades, curve = backtest_arm(df, arm=arm, fee_bps=5)
        results[arm] = m
        all_trades[arm] = trades
        # Also run 10bps for report
        m10, _, _ = backtest_arm(df, arm=arm, fee_bps=10)
        results[arm]['fee_10bps_total_return'] = m10.get('total_return')
    
    # Delta vs A0
    a0_return = results['A0']['total_return']
    for arm in arms:
        results[arm]['delta_vs_A0'] = round(results[arm]['total_return'] - a0_return, 4)
        if results[arm]['N'] < 15:
            results[arm]['note'] = 'N<15 inconclusive'
    
    # Print table
    print("\n=== ABLATION RESULTS (5bps fees) ===")
    print(f"{'Arm':<4} {'N':>5} {'Win%':>7} {'Exp':>8} {'TotRet':>8} {'MaxDD':>8} {'Sharpe':>7} {'DeltaA0':>8}")
    for arm in arms:
        r = results[arm]
        print(f"{arm:<4} {r['N']:>5} {r['win_rate']*100:>6.1f}% {r['expectancy']:>8.2f} {r['total_return']:>7.2%} {r['max_dd']:>7.2%} {r['sharpe']:>7.2f} {r['delta_vs_A0']:>8.2%}")
    
    # Save
    os.makedirs('data/state/trials', exist_ok=True)
    out = {
        'task_id': 'TEST-COMBINED-INDICATOR-ABLATION-2026-08',
        'date': datetime.now().isoformat(),
        'data_range': [str(df.index[0].date()), str(df.index[-1].date())],
        'results': results,
        'notes': 'Real yfinance BTC-USD daily. A0 baseline + 9 arms. 5/10bps fees. Long-only 95% equity.'
    }
    with open('data/state/trials/TEST_COMBINED_INDICATOR_ABLATION_2026-08.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)
    
    print("\nSaved: data/state/trials/TEST_COMBINED_INDICATOR_ABLATION_2026-08.json")
    return results

if __name__ == "__main__":
    run_ablation()
