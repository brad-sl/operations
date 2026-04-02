#!/usr/bin/env python3
"""
Seed Sentiment — Pre-populate sentiment_schedule table with UTC-hour fallback values.
Ensures sentiment data exists before trading test starts (no X API required).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / 'phase4_trades_test.db'

def seed_sentiment():
    """Seed BTC-USD and XRP-USD sentiment using UTC-hour deterministic fallback"""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    cursor = conn.cursor()
    
    # Create sentiment_schedule table if not exists
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
    
    # UTC-hour deterministic sentiment
    utc_hour = datetime.now(timezone.utc).hour
    
    if 14 <= utc_hour < 21:  # US market hours
        sentiment = 0.3
        mood = "BULLISH"
    elif 0 <= utc_hour < 7:   # Asian session
        sentiment = -0.1
        mood = "BEARISH"
    else:                       # Pre-US
        sentiment = -0.2
        mood = "NEUTRAL_DOWN"
    
    fetch_time = datetime.now(timezone.utc).isoformat()
    
    # Seed BTC-USD
    cursor.execute('''
        INSERT INTO sentiment_schedule 
        (pair, sentiment_score, positive_tweets, negative_tweets, total_tweets, 
         cached, fetch_timestamp, age_minutes, source, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'BTC-USD',
        sentiment,
        0, 0, 0,
        True,
        fetch_time,
        0,
        'UTC_HOUR_FALLBACK',
        f'Seeded sentiment for BTC-USD (UTC {utc_hour}:00, {mood})'
    ))
    
    # Seed XRP-USD
    cursor.execute('''
        INSERT INTO sentiment_schedule 
        (pair, sentiment_score, positive_tweets, negative_tweets, total_tweets, 
         cached, fetch_timestamp, age_minutes, source, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'XRP-USD',
        sentiment,
        0, 0, 0,
        True,
        fetch_time,
        0,
        'UTC_HOUR_FALLBACK',
        f'Seeded sentiment for XRP-USD (UTC {utc_hour}:00, {mood})'
    ))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Seeded sentiment for both pairs: BTC-USD={sentiment:+.3f}, XRP-USD={sentiment:+.3f}")
    print(f"   Mood: {mood} (UTC {utc_hour}:00)")
    print(f"   Database: {DB_PATH}")

if __name__ == '__main__':
    seed_sentiment()
