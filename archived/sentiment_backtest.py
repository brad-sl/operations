#!/usr/bin/env python3
"""
Cryptocurrency Trading Strategy Backtesting Framework

Supports multi-strategy comparison with:
- Sentiment-based trading
- RSI-based trading
- Combined Sentiment + RSI strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import json
import os
from datetime import datetime, timedelta

class TradingStrategyBacktest:
    """
    Comprehensive backtesting framework for cryptocurrency trading strategies
    """
    
    def __init__(self, 
                 initial_capital: float = 10000, 
                 fee_rate: float = 0.001,  # 0.1% trading fee
                 risk_per_trade: float = 0.02):  # 2% risk per trade
        """
        Initialize backtesting environment
        
        Args:
            initial_capital (float): Starting capital for the backtest
            fee_rate (float): Trading fee rate per transaction
            risk_per_trade (float): Maximum risk percentage per trade
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.risk_per_trade = risk_per_trade
        
        # Performance tracking
        self.trades: List[Dict] = []
        self.portfolio_history: List[Dict] = []
    
    def load_price_data(self, csv_path: str) -> pd.DataFrame:
        """
        Load historical price data
        
        Args:
            csv_path (str): Path to CSV with price data
        
        Returns:
            DataFrame with price information
        """
        df = pd.read_csv(csv_path)
        
        # Ensure required columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"CSV must contain columns: {required_cols}")
        
        # Convert timestamp if needed
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Sort by timestamp
        return df.sort_values('timestamp')
    
    def calculate_rsi(self, prices: pd.Series, window: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            prices (Series): Closing prices
            window (int): RSI calculation window
        
        Returns:
            Series with RSI values
        """
        delta = prices.diff()
        
        # Separate gains and losses
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Calculate average gains and losses
        avg_gain = gain.rolling(window=window).mean()
        avg_loss = loss.rolling(window=window).mean()
        
        # Calculate relative strength
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi
    
    def sentiment_strategy(self, 
                           sentiment_data: pd.DataFrame, 
                           rsi: pd.Series,
                           prices: pd.DataFrame) -> List[Dict]:
        """
        Trading strategy based on sentiment and optional RSI
        
        Args:
            sentiment_data (DataFrame): Sentiment scores
            rsi (Series): RSI values
            prices (DataFrame): Price data
        
        Returns:
            List of trades
        """
        trades = []
        position = None
        entry_price = None
        
        for i in range(len(prices)):
            # Current data point
            current_price = prices.iloc[i]['close']
            current_timestamp = prices.iloc[i]['timestamp']
            
            # Match sentiment to current timestamp
            matching_sentiment = sentiment_data[
                sentiment_data['timestamp'] <= current_timestamp
            ].iloc[-1] if not sentiment_data[sentiment_data['timestamp'] <= current_timestamp].empty else None
            
            # Sentiment and RSI conditions
            sentiment_score = matching_sentiment['sentiment_score'] if matching_sentiment is not None else 0
            current_rsi = rsi.iloc[i] if not pd.isna(rsi.iloc[i]) else 50
            
            # Trading logic
            buy_signal = (sentiment_score > 0.5 and current_rsi < 30) or (sentiment_score > 0.7)
            sell_signal = (sentiment_score < -0.5 and current_rsi > 70) or (sentiment_score < -0.7)
            
            # Position management
            if position is None and buy_signal:
                # Open long position
                position = 'long'
                entry_price = current_price
                trades.append({
                    'type': 'buy',
                    'timestamp': current_timestamp,
                    'price': current_price,
                    'sentiment_score': sentiment_score,
                    'rsi': current_rsi
                })
            
            elif position == 'long' and (sell_signal or current_price <= entry_price * 0.95):
                # Close long position (stop loss or sell signal)
                position = None
                trades.append({
                    'type': 'sell',
                    'timestamp': current_timestamp,
                    'price': current_price,
                    'sentiment_score': sentiment_score,
                    'rsi': current_rsi
                })
        
        return trades
    
    def calculate_performance(self, trades: List[Dict], initial_capital: float) -> Dict:
        """
        Calculate performance metrics for a trading strategy
        
        Args:
            trades (List[Dict]): List of trades
            initial_capital (float): Starting capital
        
        Returns:
            Performance metrics dictionary
        """
        capital = initial_capital
        trades_count = len(trades) // 2  # Buy and sell pairs
        
        # Tracking for performance
        profits = []
        max_drawdown = 0
        peak_capital = initial_capital
        
        # Calculate returns
        for i in range(0, len(trades), 2):
            if i + 1 < len(trades):
                buy_trade = trades[i]
                sell_trade = trades[i + 1]
                
                # Calculate trade profit
                trade_profit = (sell_trade['price'] - buy_trade['price']) / buy_trade['price']
                
                # Apply fees
                trade_profit -= self.fee_rate * 2  # Entry and exit fees
                
                capital *= (1 + trade_profit)
                profits.append(trade_profit)
                
                # Drawdown calculation
                max_drawdown = min(max_drawdown, (capital - peak_capital) / peak_capital)
                peak_capital = max(peak_capital, capital)
        
        return {
            'final_capital': capital,
            'total_return': (capital - initial_capital) / initial_capital,
            'trades_count': trades_count,
            'avg_return_per_trade': np.mean(profits) if profits else 0,
            'max_drawdown': max_drawdown
        }
    
    def run_backtest(self, 
                     price_data_path: str, 
                     sentiment_data_path: str) -> Dict:
        """
        Run comprehensive backtest with multiple strategies
        
        Args:
            price_data_path (str): Path to price data CSV
            sentiment_data_path (str): Path to sentiment data CSV
        
        Returns:
            Comparative performance metrics
        """
        # Load data
        prices = self.load_price_data(price_data_path)
        sentiment_data = pd.read_csv(sentiment_data_path)
        
        # Calculate RSI
        prices['rsi'] = self.calculate_rsi(prices['close'])
        
        # Convert timestamp to datetime for both datasets
        sentiment_data['timestamp'] = pd.to_datetime(sentiment_data['timestamp'])
        
        # Run strategies
        strategies = {
            'sentiment_only': self.sentiment_strategy(sentiment_data, 
                                                     pd.Series(50, index=prices.index), 
                                                     prices),
            'rsi_only': self.sentiment_strategy(pd.DataFrame({'timestamp': prices['timestamp'], 'sentiment_score': 0.5}), 
                                                prices['rsi'], 
                                                prices),
            'sentiment_rsi_combined': self.sentiment_strategy(sentiment_data, 
                                                             prices['rsi'], 
                                                             prices)
        }
        
        # Calculate performance for each strategy
        performance = {}
        for strategy_name, strategy_trades in strategies.items():
            performance[strategy_name] = self.calculate_performance(strategy_trades, self.initial_capital)
        
        return performance

def main():
    """
    Run backtest with example data
    """
    # Initialize backtest
    backtest = TradingStrategyBacktest()
    
    # Paths to input data (you'll need to generate/provide these)
    price_data_path = '/home/brad/.openclaw/workspace/operations/crypto-bot/backtest_data/btc_historical_prices.csv'
    sentiment_data_path = '/home/brad/.openclaw/workspace/operations/crypto-bot/backtest_data/btc_sentiment_data.csv'
    
    # Run backtest
    results = backtest.run_backtest(price_data_path, sentiment_data_path)
    
    # Print results
    print("Backtesting Results:")
    for strategy, metrics in results.items():
        print(f"\n{strategy.replace('_', ' ').title()} Strategy:")
        for metric, value in metrics.items():
            print(f"{metric.replace('_', ' ').title()}: {value * 100:.2f}%")

if __name__ == '__main__':
    main()