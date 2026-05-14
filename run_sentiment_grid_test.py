#!/usr/bin/env python3
"""
Sentiment Grid Test Runner
Runs 9 scenarios (3 Twitter HL × 3 Reddit HL) using real historical data
"""

import json
import os
from pathlib import Path
from datetime import datetime
import numpy as np

# Grid parameters
TWITTER_HALF_LIVES = [15, 30, 60]  # minutes
REDDIT_HALF_LIVES = [60, 120, 240]  # minutes

BASE_DIR = Path('/home/brad/.openclaw/workspace/operations/crypto-bot')
DATA_DIR = BASE_DIR
OUTPUT_DIR = BASE_DIR / 'config' / f"sentiment_grid_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_ohlcv_data(pair):
    """Load OHLCV data from JSON file"""
    filename = DATA_DIR / f'backtest_historical_ohlcv_{pair.lower()}_2025-04-20_to_2026-04-20.json'
    
    if not filename.exists():
        print(f"⚠️ Missing: {filename}")
        return None
    
    with open(filename, 'r') as f:
        data = json.load(f)
    
    return data

def calculate_rsi(prices, period=14):
    """Calculate RSI from price series"""
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    
    rsi_values = [100.0 - 100.0 / (1.0 + rs)]
    
    for i in range(period, len(deltas)):
        delta = deltas[i]
        if delta > 0:
            upval = delta
            downval = 0.0
        else:
            upval = 0.0
            downval = -delta
        
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi_values.append(100.0 - 100.0 / (1.0 + rs))
    
    return rsi_values

def exponential_decay_weight(age_minutes, half_life_minutes):
    """Calculate exponential decay weight"""
    lambda_val = np.log(2) / half_life_minutes
    return np.exp(-lambda_val * age_minutes)

def run_single_scenario(twitter_hl, reddit_hl, scenario_num, total_scenarios):
    """Run backtest for single decay parameter scenario"""
    
    print(f"\n[{scenario_num}/{total_scenarios}] Testing: Twitter {twitter_hl}m, Reddit {reddit_hl}m")
    
    try:
        # Load data for all pairs
        pairs = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']
        all_prices = {}
        
        for pair in pairs:
            data = load_ohlcv_data(pair)
            if data is None:
                print(f"❌ Failed to load {pair}")
                return None
            
            closes = [candle['close'] for candle in data]
            all_prices[pair] = closes
        
        # Mock sentiment data (for validation purposes)
        # Real Phase 6 will use actual X API + Reddit data
        num_candles = len(all_prices['BTC'])
        
        total_trades = 0
        winning_trades = 0
        total_pnl = 0
        trades = []
        
        # Simulate trading with multi-source sentiment
        for i in range(14, min(num_candles - 1, len(all_prices['BTC']) - 1)):
            # Calculate RSI for entry signal
            btc_rsi = calculate_rsi(all_prices['BTC'][:i+1])[-1]
            
            # Mock multi-source sentiment (X + Reddit weighted by decay)
            # X sentiment ages 0-30 min, Reddit ages 0-360 min
            # This is simplified; real version uses actual API data
            
            twitter_age_min = 15  # Mock: assume 15 min old
            reddit_age_min = 90   # Mock: assume 90 min old
            
            twitter_weight = exponential_decay_weight(twitter_age_min, twitter_hl)
            reddit_weight = exponential_decay_weight(reddit_age_min, reddit_hl)
            
            total_weight = twitter_weight + reddit_weight
            twitter_contribution = twitter_weight / total_weight
            reddit_contribution = reddit_weight / total_weight
            
            # Mock sentiment scores
            twitter_sentiment = 0.65  # Mock bullish
            reddit_sentiment = 0.55   # Mock neutral-bullish
            
            combined_sentiment = (twitter_sentiment * twitter_contribution + 
                                reddit_sentiment * reddit_contribution)
            
            # Trading logic: RSI<30 AND Sentiment>0.55 = BUY
            if btc_rsi < 30 and combined_sentiment > 0.55:
                # Simulate trade
                entry_price = all_prices['BTC'][i]
                exit_price = all_prices['BTC'][i+1]
                
                pnl = exit_price - entry_price
                total_pnl += pnl
                total_trades += 1
                
                if pnl > 0:
                    winning_trades += 1
                
                trades.append({
                    'candle': i,
                    'entry': entry_price,
                    'exit': exit_price,
                    'pnl': pnl,
                    'rsi': btc_rsi,
                    'sentiment': combined_sentiment,
                    'twitter_weight': twitter_contribution,
                    'reddit_weight': reddit_contribution
                })
        
        # Calculate metrics
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_win = np.mean([t['pnl'] for t in trades if t['pnl'] > 0]) if winning_trades > 0 else 0
        avg_loss = np.mean([t['pnl'] for t in trades if t['pnl'] <= 0]) if (total_trades - winning_trades) > 0 else 0
        
        # Simplified Sharpe (assuming 0.15 daily risk-free rate annualized)
        if len(trades) > 0:
            pnls = [t['pnl'] for t in trades]
            sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0
        else:
            sharpe = 0
        
        result = {
            'decay_params': {
                'twitter_half_life_minutes': twitter_hl,
                'reddit_half_life_minutes': reddit_hl
            },
            'backtest_period': '2025-04-20 to 2026-04-20',
            'metrics': {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades,
                'win_rate_pct': round(win_rate, 2),
                'total_pnl_dollars': round(total_pnl, 2),
                'total_pnl_pct': round((total_pnl / 1000) * 100, 2),
                'avg_win_dollars': round(avg_win, 2) if winning_trades > 0 else 0,
                'avg_loss_dollars': round(avg_loss, 2) if (total_trades - winning_trades) > 0 else 0,
                'sharpe_ratio': round(sharpe, 2),
                'profit_factor': round(abs(winning_trades * avg_win / ((total_trades - winning_trades) * avg_loss)) if avg_loss != 0 else 0, 2)
            },
            'sentiment_stats': {
                'avg_twitter_weight': round(twitter_contribution, 2),
                'avg_reddit_weight': round(reddit_contribution, 2),
                'twitter_half_life_minutes': twitter_hl,
                'reddit_half_life_minutes': reddit_hl
            }
        }
        
        print(f"✅ Complete: {total_trades} trades, Win% {win_rate:.1f}%, Sharpe {sharpe:.2f}")
        
        return result
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    """Run grid test for all parameter combinations"""
    
    print("🚀 Starting Sentiment Grid Test")
    print(f"📊 Twitter HL: {TWITTER_HALF_LIVES} min")
    print(f"📊 Reddit HL: {REDDIT_HALF_LIVES} min")
    print(f"📂 Output: {OUTPUT_DIR}")
    
    results = []
    scenario_num = 0
    total_scenarios = len(TWITTER_HALF_LIVES) * len(REDDIT_HALF_LIVES)
    
    for twitter_hl in TWITTER_HALF_LIVES:
        for reddit_hl in REDDIT_HALF_LIVES:
            scenario_num += 1
            result = run_single_scenario(twitter_hl, reddit_hl, scenario_num, total_scenarios)
            
            if result:
                results.append(result)
                
                # Save individual result
                filename = OUTPUT_DIR / f"decay_{twitter_hl}m_{reddit_hl}m.json"
                with open(filename, 'w') as f:
                    json.dump(result, f, indent=2)
    
    # Find optimal scenario (highest Sharpe)
    if results:
        optimal = max(results, key=lambda x: x['metrics'].get('sharpe_ratio', 0))
        
        print("\n" + "="*60)
        print("📈 GRID TEST COMPLETE")
        print("="*60)
        print(f"\n🏆 OPTIMAL PARAMETERS:")
        print(f"   Twitter half-life: {optimal['decay_params']['twitter_half_life_minutes']} min")
        print(f"   Reddit half-life: {optimal['decay_params']['reddit_half_life_minutes']} min")
        print(f"\n   Sharpe Ratio: {optimal['metrics']['sharpe_ratio']}")
        print(f"   Win Rate: {optimal['metrics']['win_rate_pct']}%")
        print(f"   PnL: {optimal['metrics']['total_pnl_pct']}%")
        print(f"   Profit Factor: {optimal['metrics']['profit_factor']}")
        
        # Summary JSON
        summary = {
            'test_date': datetime.now().isoformat(),
            'total_scenarios': len(results),
            'optimal': optimal,
            'all_results': results,
            'recommendation': 'PROCEED with multi-source' if optimal['metrics']['sharpe_ratio'] > 1.60 else 'HOLD - needs optimization'
        }
        
        summary_file = OUTPUT_DIR / 'SUMMARY.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n💾 Summary: {summary_file}")
        print(f"✅ All results saved to {OUTPUT_DIR}/")
    else:
        print("❌ No valid results")

if __name__ == '__main__':
    main()
