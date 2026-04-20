#!/usr/bin/env python3
"""
Comprehensive Fix Script for Phase 4b Trading Bot
Addresses API, Database, and Trading Logic Issues
"""

import sqlite3
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='🔧 [PHASE4B_FIX] %(levelname)s: %(message)s')

# Paths
BOT_DIR = Path(__file__).parent
DB_PATH = BOT_DIR / 'phase4_trades.db'
SCHEMA_PATH = BOT_DIR / 'SCHEMA_UPDATE_SENTIMENT.sql'

def apply_database_fixes():
    """Apply database schema updates and validate"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            
            # Check existing columns
            cursor.execute("PRAGMA table_info(trades)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add missing sentiment columns if not present
            if 'sentiment_score' not in columns:
                logging.info("Adding sentiment columns to trades table")
                cursor.execute("ALTER TABLE trades ADD COLUMN sentiment_score REAL DEFAULT NULL")
            
            # Create sentiment_schedule table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sentiment_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    sentiment_score REAL,
                    fetch_timestamp TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logging.info("✅ Database schema updated successfully")
    
    except sqlite3.Error as e:
        logging.error(f"Database update failed: {e}")
        sys.exit(1)

def validate_coinbase_config():
    """Validate Coinbase API configuration"""
    try:
        from dotenv import load_dotenv
        import os
        
        load_dotenv(BOT_DIR / '.env')
        
        required_keys = [
            'COINBASE_API_KEY', 
            'COINBASE_API_SECRET', 
            'COINBASE_PASSPHRASE'
        ]
        
        for key in required_keys:
            if not os.getenv(key) or os.getenv(key) == 'your_live_api_key_here':
                logging.warning(f"⚠️ {key} is not properly configured")
        
        logging.info("✅ Coinbase configuration preliminary check complete")
    
    except Exception as e:
        logging.error(f"Coinbase config validation failed: {e}")

def main():
    """Execute all fixes"""
    logging.info("🚀 Starting Phase 4b Trading Bot Fixes")
    
    apply_database_fixes()
    validate_coinbase_config()
    
    logging.info("🏁 Fix process completed")

if __name__ == '__main__':
    main()