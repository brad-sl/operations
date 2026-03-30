#!/usr/bin/env python3
"""
X-Sentiment Scheduler — Fetch sentiment on a schedule (every 1 hour)
Runs as a daemon or cron job to keep sentiment cache fresh
Logs sentiment fetches to sentiment_log.jsonl for audit trail
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import sqlite3

# Import sentiment fetcher
from x_sentiment_fetcher import XSentimentFetcher

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sentiment_scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load .env
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

DB_PATH = Path(__file__).parent / 'phase4_trades.db'
SENTIMENT_LOG = Path(__file__).parent / 'sentiment_log.jsonl'


class SentimentScheduler:
    """Scheduled sentiment fetcher with database logging"""
    
    def __init__(self, cache_dir: str = "."):
        self.fetcher = XSentimentFetcher(cache_dir)
        self.cache_dir = Path(cache_dir)
        
    def _init_sentiment_table(self):
        """Create sentiment_schedule table if not exists"""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sentiment_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    sentiment_score REAL,
                    positive_tweets INTEGER,
                    negative_tweets INTEGER,
                    total_tweets INTEGER,
                    cached BOOLEAN DEFAULT 0,
                    fetch_timestamp TEXT NOT NULL,
                    age_minutes INTEGER,
                    source TEXT,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("✅ sentiment_schedule table initialized")
        except Exception as e:
            logger.error(f"Failed to init sentiment table: {e}")
    
    def _log_sentiment_fetch(self, pair: str, sentiment: float, metadata: dict):
        """Log sentiment fetch to sentiment_log.jsonl for audit trail"""
        try:
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'pair': pair,
                'sentiment_score': sentiment,
                'metadata': metadata
            }
            with open(SENTIMENT_LOG, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
            logger.debug(f"Logged sentiment fetch for {pair}")
        except Exception as e:
            logger.error(f"Failed to log sentiment fetch: {e}")
    
    def _store_sentiment_in_db(self, pair: str, sentiment: float, metadata: dict):
        """Store sentiment fetch in sentiment_schedule table"""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sentiment_schedule 
                (pair, sentiment_score, positive_tweets, negative_tweets, total_tweets, 
                 cached, fetch_timestamp, age_minutes, source, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pair,
                sentiment,
                metadata.get('positive_tweets', 0),
                metadata.get('negative_tweets', 0),
                metadata.get('total_tweets', 0),
                metadata.get('cached', False),
                metadata.get('fetch_time'),
                metadata.get('age_minutes', 0),
                metadata.get('source', 'X API'),
                metadata.get('note', '')
            ))
            conn.commit()
            conn.close()
            logger.info(f"✅ Stored {pair} sentiment in DB: {sentiment:.2f}")
        except Exception as e:
            logger.error(f"Failed to store sentiment in DB: {e}")
    
    def fetch_all_pairs(self):
        """Fetch sentiment for BTC and XRP"""
        logger.info("=" * 60)
        logger.info("🔄 SENTIMENT SCHEDULER RUN")
        logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        logger.info("=" * 60)
        
        # Ensure table exists
        self._init_sentiment_table()
        
        pairs = ['BTC-USD', 'XRP-USD']
        results = {}
        
        for pair in pairs:
            try:
                logger.info(f"\n📊 Fetching sentiment for {pair}...")
                sentiment, metadata = self.fetcher.get_sentiment(pair, force_refresh=False)
                
                results[pair] = {
                    'sentiment': sentiment,
                    'metadata': metadata
                }
                
                # Log to JSONL
                self._log_sentiment_fetch(pair, sentiment, metadata)
                
                # Store in DB
                self._store_sentiment_in_db(pair, sentiment, metadata)
                
                logger.info(f"✅ {pair}: {sentiment:+.3f} ({metadata.get('source')})")
                
            except Exception as e:
                logger.error(f"❌ Failed to fetch sentiment for {pair}: {e}")
                results[pair] = {'error': str(e)}
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ SCHEDULER RUN COMPLETE")
        logger.info("=" * 60)
        
        return results
    
    def get_latest_sentiment(self, pair: str) -> dict:
        """Get the latest sentiment for a pair from the database.
        Falls back to UTC-hour deterministic sentiment if DB fetch fails."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Try to fetch with created_at; fall back to ROWID if column doesn't exist
            try:
                cursor.execute('''
                    SELECT * FROM sentiment_schedule
                    WHERE pair = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (pair,))
            except sqlite3.OperationalError as oe:
                if "no such column: created_at" in str(oe):
                    logger.warning(f"created_at column missing; using ROWID fallback for {pair}")
                    cursor.execute('''
                        SELECT * FROM sentiment_schedule
                        WHERE pair = ?
                        ORDER BY ROWID DESC
                        LIMIT 1
                    ''', (pair,))
                else:
                    raise
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            else:
                logger.warning(f"No sentiment data found for {pair}; using UTC-hour fallback")
                return self._utc_hour_fallback_sentiment(pair)
        except Exception as e:
            logger.error(f"Failed to fetch sentiment from DB ({e}); using UTC-hour fallback")
            return self._utc_hour_fallback_sentiment(pair)
    
    def _utc_hour_fallback_sentiment(self, pair: str) -> dict:
        """UTC-hour deterministic sentiment fallback.
        Repeats every 24h, simulates market mood patterns."""
        from datetime import datetime, timezone
        
        utc_hour = datetime.now(timezone.utc).hour
        
        # Market moods by UTC hour (consistent 24-hour cycle)
        # US market hours (14:30-21:00 UTC): bullish (+0.3)
        # Asian session (00:00-07:00 UTC): bearish (-0.1)
        # Pre-US (07:00-14:30 UTC): slightly bearish (-0.2)
        
        if 14 <= utc_hour < 21:  # US market hours
            sentiment = 0.3
            mood = "BULLISH"
        elif 0 <= utc_hour < 7:   # Asian session
            sentiment = -0.1
            mood = "BEARISH"
        else:                       # Pre-US
            sentiment = -0.2
            mood = "NEUTRAL_DOWN"
        
        return {
            'pair': pair,
            'sentiment_score': sentiment,
            'source': 'UTC_HOUR_FALLBACK',
            'mood': mood,
            'utc_hour': utc_hour,
            'note': f'Fallback sentiment for {pair} (UTC {utc_hour}:00)',
            'cached': True,
            'age_minutes': 0
        }


def main():
    """Run scheduler once (call from cron every 1 hour)"""
    scheduler = SentimentScheduler('.')
    results = scheduler.fetch_all_pairs()
    
    # Print summary
    print("\n📈 SENTIMENT SUMMARY:")
    for pair, data in results.items():
        if 'error' in data:
            print(f"  {pair}: ERROR - {data['error']}")
        else:
            sentiment = data['sentiment']
            direction = "🟢" if sentiment > 0.1 else "🔴" if sentiment < -0.1 else "⚪"
            print(f"  {direction} {pair}: {sentiment:+.3f}")


if __name__ == '__main__':
    main()
