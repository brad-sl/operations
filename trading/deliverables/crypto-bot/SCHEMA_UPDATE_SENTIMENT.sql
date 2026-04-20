-- Schema Update for X-Sentiment Integration
-- Run this to add sentiment columns to trades table and create sentiment_schedule table

-- 1. Add sentiment columns to trades table
ALTER TABLE trades ADD COLUMN sentiment_score REAL DEFAULT NULL;
ALTER TABLE trades ADD COLUMN sentiment_fetch_time TEXT DEFAULT NULL;
ALTER TABLE trades ADD COLUMN sentiment_cached BOOLEAN DEFAULT 0;

-- 2. Create sentiment_schedule table for scheduler logging
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
);

-- 3. Index on pair + created_at for fast lookups by Phase 4b
CREATE INDEX IF NOT EXISTS idx_sentiment_pair_time 
ON sentiment_schedule(pair, created_at DESC);

-- 4. Index on pair for latest sentiment lookup
CREATE INDEX IF NOT EXISTS idx_sentiment_pair 
ON sentiment_schedule(pair);

-- Execute this in sqlite3:
-- sqlite3 phase4_trades.db < SCHEMA_UPDATE_SENTIMENT.sql
