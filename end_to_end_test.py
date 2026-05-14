#!/usr/bin/env python3
"""
End-to-End Sentiment-Driven Trading Workflow Test
Demonstrates complete pipeline: Fetch > Aggregate > Apply > Trade Decision > Log
"""

import os
import sys
import json
import os
import sys
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from datetime import datetime
from typing import List, Dict, Any
import sqlite3

# Ensure the crypto-bot directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from x_sentiment_fetcher import XSentimentFetcher
from sentiment_aggregator import SentimentAggregator
from signal_generator import SignalGenerator

class EndToEndWorkflowTest:
    def __init__(self, bearer_token: str, database_path: str):
        """
        Initialize the end-to-end workflow test
        
        :param bearer_token: X API bearer token
        :param database_path: Path to SQLite trades database
        """
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(os.path.join(os.path.dirname(__file__), 'end_to_end_test.log'))
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.sentiment_fetcher = XSentimentFetcher(bearer_token)
        self.sentiment_aggregator = SentimentAggregator()
        # Placeholder data for SignalGenerator initialization
        dummy_rsi_data = [50.0, 55.0, 60.0]
        dummy_sentiment_data = [0.1, 0.2, 0.3]
        self.trading_strategy = SignalGenerator(dummy_rsi_data, dummy_sentiment_data)
        
        # Database connection
        self.database_path = database_path
        self.conn = sqlite3.connect(database_path)
        self.cursor = self.conn.cursor()
        
        # Ensure trades table exists with sentiment columns
        self._setup_trades_table()
    
    def _setup_trades_table(self):
        """
        Ensure trades table has required sentiment columns
        """
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY,
                    pair TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    sentiment_score REAL,
                    sentiment_tweet_count INTEGER,
                    sentiment_source_ids TEXT,
                    sentiment_cached BOOLEAN,
                    trade_timestamp DATETIME
                )
            ''')
            self.conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to setup trades table: {e}")
            raise
    
    def run_workflow(self, pairs: List[str]):
        """
        Execute complete sentiment-driven trading workflow
        
        :param pairs: List of cryptocurrency pairs to process
        :return: Dictionary of trading results
        """
        workflow_results = {}
        
        for pair in pairs:
            try:
                # 1. Fetch Sentiment
                sentiment_data = self.sentiment_fetcher.fetch_sentiment(pair)
                self.logger.info(f"Sentiment for {pair}: {sentiment_data}")
                
                # 2. Aggregate Sentiment
                # Use placeholder data if process_sentiment method doesn't exist
                try:
                    aggregated_sentiment = self.sentiment_aggregator.process_sentiment(sentiment_data)
                except AttributeError:
                    aggregated_sentiment = sentiment_data
                    self.logger.warning("process_sentiment not found, using raw sentiment data")
                
                # 3. Apply Trading Strategy
                signals = self.trading_strategy.generate_all_signals()
                trade_decision = self.trading_strategy.get_signal_summary(signals)
                
                pair = sentiment_data.get('pair', 'Unknown')
                sentiment_score = sentiment_data.get('sentiment_score', 0.0)
                
                # 4. Log Trade
                # Modify trade decision logic to use signal summary
                buy_percentage = trade_decision.get('buy_percentage', 0)
                if buy_percentage > 50:  # More than 50% buy signals
                    self._log_trade(
                        pair=pair,
                        sentiment_data=sentiment_data,
                        trade_details=trade_decision
                    )
                
                # Store workflow results
                workflow_results[pair] = {
                    'sentiment': sentiment_data,
                    'trade_decision': trade_decision
                }
            
            except Exception as e:
                self.logger.error(f"Workflow failed for {pair}: {e}")
                workflow_results[pair] = {
                    'error': str(e)
                }
        
        return workflow_results
    
    def _log_trade(self, pair: str, sentiment_data: dict, trade_details: dict):
        """
        Log trade details to SQLite database
        
        :param pair: Cryptocurrency pair
        :param sentiment_data: Sentiment information
        :param trade_details: Trading decision details
        """
        try:
            # Convert source tweet IDs to JSON string
            source_tweet_ids = json.dumps(sentiment_data.get('source_tweet_ids', []))
            
            self.cursor.execute('''
                INSERT INTO trades (
                    pair, 
                    entry_price, 
                    sentiment_score, 
                    sentiment_tweet_count, 
                    sentiment_source_ids, 
                    sentiment_cached, 
                    trade_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                pair,
                trade_details.get('entry_price', 0.0),
                sentiment_data.get('sentiment_score', 0.0),
                sentiment_data.get('tweet_count', 0),
                source_tweet_ids,
                sentiment_data.get('cached', False),
                datetime.utcnow().isoformat()
            ))
            
            self.conn.commit()
            self.logger.info(f"Trade logged for {pair}")
        
        except Exception as e:
            self.logger.error(f"Failed to log trade for {pair}: {e}")
            self.conn.rollback()
    
    def generate_report(self):
        """
        Generate a comprehensive report of trades
        
        :return: Dictionary with trade summary
        """
        try:
            self.cursor.execute('''
                SELECT 
                    pair, 
                    COUNT(*) as total_trades, 
                    AVG(sentiment_score) as avg_sentiment,
                    SUM(CASE WHEN sentiment_score > 0 THEN 1 ELSE 0 END) as positive_sentiment_trades
                FROM trades
                GROUP BY pair
            ''')
            
            report = {}
            for row in self.cursor.fetchall():
                pair, total_trades, avg_sentiment, positive_sentiment_trades = row
                report[pair] = {
                    'total_trades': total_trades,
                    'average_sentiment': avg_sentiment,
                    'positive_sentiment_trades': positive_sentiment_trades,
                    'positive_sentiment_percentage': (positive_sentiment_trades / total_trades * 100) if total_trades > 0 else 0
                }
            
            return report
        
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            return {}
    
    def __del__(self):
        """
        Ensure database connection is closed
        """
        if hasattr(self, 'conn'):
            self.conn.close()

def main():
    # Load bearer token from environment
    bearer_token = os.getenv('X_API_TOKEN') or open('x_bearer_token.txt').read().strip()
    print(f"Token Loaded: {bearer_token[:20]}...")
    if not bearer_token:
        print("❌ Error: Token not found.")
        sys.exit(1)
    
    # Database path
    db_path = os.path.join(os.path.dirname(__file__), 'trades.db')
    
    # Initialize end-to-end test
    e2e_test = EndToEndWorkflowTest(bearer_token, db_path)
    
    # Run workflow for multiple pairs
    pairs_to_test = ['BTC-USD', 'XRP-USD']
    workflow_results = e2e_test.run_workflow(pairs_to_test)
    
    # Generate and print report
    trade_report = e2e_test.generate_report()
    
    # Output results
    print("\nWorkflow Results:")
    print(json.dumps(workflow_results, indent=2))
    
    print("\nTrade Report:")
    print(json.dumps(trade_report, indent=2))

if __name__ == '__main__':
    main()