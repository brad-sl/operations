#!/usr/bin/env python3
"""
Sentiment seeder — Initialize sentiment_schedule.db with seed data for testing.
This runs before the main sentiment scheduler to ensure BTC-USD and XRP-USD have initial sentiment values.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SENTIMENT_DB_PATH = Path(__file__).parent / 'sentiment_schedule.db'

def seed_sentiment():
    """Initialize sentiment data for both trading pairs."""
    try:
        conn = sqlite3.connect(str(SENTIMENT_DB_PATH), timeout=10.0)
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                sentiment_score REAL,
                fetched_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Seed initial sentiment for both pairs
        pairs_and_sentiment = [
            ('BTC-USD', 0.3),    # Start bullish for BTC
            ('XRP-USD', 0.1),    # Start neutral for XRP
        ]
        
        now = datetime.now(timezone.utc).isoformat()
        
        for pair, sentiment in pairs_and_sentiment:
            cursor.execute('''
                INSERT INTO sentiment_schedule 
                (pair, sentiment_score, fetched_at)
                VALUES (?, ?, ?)
            ''', (pair, sentiment, now))
            logger.info(f"✅ Seeded {pair}: sentiment_score={sentiment:+.3f}")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Sentiment database seeded successfully")
        return True
    
    except Exception as e:
        logger.error(f"❌ Failed to seed sentiment: {e}")
        return False

if __name__ == '__main__':
    seed_sentiment()
