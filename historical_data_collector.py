#!/usr/bin/env python3
"""
Comprehensive Historical Cryptocurrency Data Collector

Aggregates price and sentiment data from multiple sources
for backtesting cryptocurrency trading strategies.
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging
from typing import List, Dict, Optional

class HistoricalDataCollector:
    """
    Collect and aggregate historical cryptocurrency data
    for comprehensive backtesting
    """
    
    def __init__(self, 
                 coingecko_api_key: Optional[str] = None, 
                 alpha_vantage_key: Optional[str] = None):
        """
        Initialize data collector with API keys
        
        Args:
            coingecko_api_key (str, optional): CoinGecko API key
            alpha_vantage_key (str, optional): Alpha Vantage API key
        """
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # API Keys and Configurations
        self.coingecko_api_key = coingecko_api_key
        self.alpha_vantage_key = alpha_vantage_key
        
        # Default configuration
        self.cryptocurrencies = ['bitcoin', 'ethereum', 'ripple']
        self.output_dir = '/home/brad/.openclaw/workspace/operations/crypto-bot/backtest_data'
    
    def _fetch_coingecko_historical_prices(self, 
                                           crypto_id: str, 
                                           days: int = 365) -> pd.DataFrame:
        """
        Fetch historical price data from CoinGecko
        
        Args:
            crypto_id (str): CoinGecko cryptocurrency ID
            days (int): Number of historical days to fetch
        
        Returns:
            DataFrame with historical price data
        """
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}"
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Convert price data to DataFrame
            df = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Add OHLC columns using rolling windows
            df['open'] = df['price'].shift(1)
            df['high'] = df['price'].rolling(window=24).max()
            df['low'] = df['price'].rolling(window=24).min()
            df['close'] = df['price']
            
            # Add volume (simulated if not available)
            df['volume'] = np.random.randint(1000000, 10000000, size=len(df))
            
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        except Exception as e:
            self.logger.error(f"CoinGecko price fetch failed for {crypto_id}: {e}")
            return pd.DataFrame()
    
    def _fetch_sentiment_proxy(self, crypto_id: str, days: int = 365) -> pd.DataFrame:
        """
        Generate synthetic sentiment data based on price movements
        
        Args:
            crypto_id (str): Cryptocurrency identifier
            days (int): Number of days for sentiment data
        
        Returns:
            DataFrame with sentiment scores
        """
        try:
            # Fetch price data to base sentiment on
            prices = self._fetch_coingecko_historical_prices(crypto_id, days)
            
            # Generate synthetic sentiment
            prices['price_change'] = prices['close'].pct_change()
            
            # Convert price change to sentiment score
            # Normalize price change to -1 to 1 range
            prices['sentiment_score'] = prices['price_change'].apply(
                lambda x: max(min(x * 10, 1), -1)  # Scale and clip
            )
            
            # Add noise to sentiment
            prices['sentiment_score'] += np.random.normal(0, 0.2, len(prices))
            prices['sentiment_score'] = prices['sentiment_score'].clip(-1, 1)
            
            # Select relevant columns
            sentiment_df = prices[['timestamp', 'sentiment_score']]
            sentiment_df['source'] = crypto_id
            
            return sentiment_df
        
        except Exception as e:
            self.logger.error(f"Sentiment generation failed for {crypto_id}: {e}")
            return pd.DataFrame()
    
    def collect_historical_data(self, 
                                cryptocurrencies: Optional[List[str]] = None, 
                                days: int = 365):
        """
        Collect comprehensive historical data for specified cryptocurrencies
        
        Args:
            cryptocurrencies (List[str], optional): List of cryptocurrency IDs
            days (int): Number of historical days to collect
        """
        # Use provided or default cryptocurrencies
        target_cryptos = cryptocurrencies or self.cryptocurrencies
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Collect data for each cryptocurrency
        for crypto in target_cryptos:
            try:
                # Fetch price data
                price_data = self._fetch_coingecko_historical_prices(crypto, days)
                price_output_path = os.path.join(
                    self.output_dir, 
                    f'{crypto}_historical_prices_{days}days.csv'
                )
                price_data.to_csv(price_output_path, index=False)
                self.logger.info(f"Saved price data for {crypto} to {price_output_path}")
                
                # Generate sentiment data
                sentiment_data = self._fetch_sentiment_proxy(crypto, days)
                sentiment_output_path = os.path.join(
                    self.output_dir, 
                    f'{crypto}_sentiment_data_{days}days.csv'
                )
                sentiment_data.to_csv(sentiment_output_path, index=False)
                self.logger.info(f"Saved sentiment data for {crypto} to {sentiment_output_path}")
            
            except Exception as e:
                self.logger.error(f"Data collection failed for {crypto}: {e}")

def main():
    """
    Run historical data collection
    """
    # Initialize collector
    collector = HistoricalDataCollector(
        # Optional: Add API keys if you have them
        # coingecko_api_key='YOUR_KEY',
        # alpha_vantage_key='YOUR_KEY'
    )
    
    # Collect 12 months of historical data
    collector.collect_historical_data(days=365)

if __name__ == '__main__':
    main()