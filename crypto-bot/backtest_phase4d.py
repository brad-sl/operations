#!/usr/bin/env python3
# Phase 4d 6-day backtest: hourly TP5% no-cap dynamic RSI + sentiment sim
# BTC/USD, XRP/USD, DOGE/USD, ETH/USD on Coinbase Mar 30 - Apr 5 2026
# Output trades table, PnL, Sharpe, win%, DD

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path('backtest_6day.log')
from datetime import timedelta
now = datetime.utcnow()
start_date = int((now - timedelta(hours=24)).timestamp() * 1000)
end_date = int(now.timestamp() * 1000)  # Last 24 hours
pairs = ['BTC/USD', 'XRP/USD', 'DOGE/USD', 'ETH/USD']
capital_per_pair = 250.0  # $250 per pair, total $1K
tp_pct = 0.05
sl_pct = -0.02
rsi_period = 14
regime_threshold_pct = 0.02
early_entry = True  # Phase 4d

def compute_rsi(prices, period=14):
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
    return 100 - 100 / (1 + rs)

def get_regime(pct_change_24h):
    if pct_change_24h > regime_threshold_pct:
        return 'UPTREND'
    elif pct_change_24h < -regime_threshold_pct:
        return 'DOWNTREND'
    return 'SIDEWAYS'

REGIME_THRESH = {
    'UPTREND': (20, 80),
    'DOWNTREND': (40, 60),
    'SIDEWAYS': (30, 70)
}
REGIME_SIZE_MULT = {'UPTREND': 1.2, 'DOWNTREND': 0.7, 'SIDEWAYS': 1.0}

exchange = ccxt.coinbase()
all_trades = []
equity_curves = {pair: [capital_per_pair] for pair in pairs}
total_capital = capital_per_pair * 4

for pair in pairs:
    logger.info(f'Fetching {pair} hourly data...')
    ohlcv = exchange.fetch_ohlcv(pair, '1h', since=start_date, limit=168)
    if len(ohlcv) < 24:
        logger.warning(f'Insufficient data for {pair}: {len(ohlcv)} candles')
        continue
    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    logger.info(f'{pair}: {len(df)} candles from {df.ts.min()} to {df.ts.max()}')

    position = None
    closes = []
    for i in range(len(df)):
        row = df.iloc[i]
        close = row['c']
        closes.append(close)

        if len(closes) < rsi_period:
            continue

        rsi = compute_rsi(closes[-rsi_period-1:], rsi_period)

        # Regime: 24h pct change
        pct24 = 0.0
        if i >= 24:
            close24 = df.iloc[i-24]['c']
            pct24 = (close - close24) / close24

        regime = get_regime(pct24)
        buy_th, sell_th = REGIME_THRESH[regime]
        size_mult = REGIME_SIZE_MULT[regime]

        # Sentiment sim: momentum proxy over last 3h
        sent_sim = 0.0
        if i >= 3:
            mom3 = (closes[-1] - np.mean(closes[-4:-1])) / np.mean(closes[-4:-1])
            sent_sim = np.clip(mom3 * 10, -1, 1)
        norm_sent = (sent_sim + 1) / 2 * 100
        weighted = 0.6 * norm_sent + 0.4 * rsi

        # Signal & conf
        if weighted < buy_th:
            signal = 'BUY'
            conf = min(1.0, (buy_th - weighted) / buy_th)
        elif weighted > sell_th:
            signal = 'SELL'
            conf = min(1.0, (weighted - sell_th) / (100 - sell_th))
        else:
            signal = 'HOLD'
            mid = (buy_th + sell_th) / 2
            conf = abs(weighted - mid) / (mid - buy_th + 1e-9) * 0.5

        # Early entry Phase 4d
        force_buy = False
        if early_entry and rsi < 40 and conf > 0.3 and signal != 'SELL':
            signal = 'BUY'
            size_mult *= 2.33
            force_buy = True
            logger.info(f'{pair} {df.ts.iloc[i]}: EARLY BUY rsi={rsi:.1f} conf={conf:.2f}')

        if position is not None:
            pnl_pct = (close - position['entry_price']) / position['entry_price']
            reason = None
            if pnl_pct >= tp_pct:
                reason = 'TP'
            elif pnl_pct <= sl_pct:
                reason = 'SL'
            elif signal == 'SELL':
                reason = 'SIGNAL'

            if reason:
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
                    'reason': reason,
                    'hold_h': i - position['entry_idx']
                }
                all_trades.append(trade)
                equity_curves[pair].append(equity_curves[pair][-1] + pnl_usd)
                position = None
                logger.info(f'{pair} CLOSE {reason}: PnL ${pnl_usd:.2f} ({pnl_pct:.2%})')
            continue

        # Entry
        if signal == 'BUY':
            qty = (capital_per_pair * size_mult) / close
            position = {
                'entry_price': close,
                'entry_ts': df.ts.iloc[i],
                'entry_idx': i,
                'qty': qty
            }
            logger.info(f'{pair} ENTRY BUY @${close:.4f} size_mult={size_mult:.2f} qty={qty:.6f}')

# Final metrics
if all_trades:
    df_trades = pd.DataFrame(all_trades)
    total_pnl = df_trades.pnl_usd.sum()
    wins = len(df_trades[df_trades.pnl_usd > 0])
    win_pct = wins / len(df_trades) * 100

    # Sharpe on trade returns (hourly)
    returns = df_trades.pnl_pct.values
    mean_ret = np.mean(returns)
    std_ret = np.std(returns)
    sharpe = mean_ret / std_ret * np.sqrt(8760) if std_ret > 0 else 0  # Annualized

    # DD per equity curve
    max_dd = 0
    for curve in equity_curves.values():
        peak = np.maximum.accumulate(curve)
        dd = (peak - curve) / peak * 100
        max_dd = max(max_dd, dd.max())
    max_dd = max_dd / 100  # pct to decimal? No, keep %

    print('\n=== TRADES TABLE ===')
    print(df_trades[['pair', 'entry_ts', 'exit_ts', 'entry_price', 'exit_price', 'pnl_pct', 'pnl_usd', 'reason', 'hold_h']].round(4).to_markdown(index=False))

    print(f'\n=== METRICS ===')
    print(f'Total PnL: ${total_pnl:.2f}')
    print(f'Win %: {win_pct:.1f}% ({wins}/{len(df_trades)})')
    print(f'Sharpe (ann.): {sharpe:.2f}')
    print(f'Max DD: {max_dd:.2%}')
else:
    print('No trades executed.')

print(f'\nLogged to {DB_PATH}')
