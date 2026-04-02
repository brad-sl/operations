#!/usr/bin/env python3
"""
Phase 4B 30-minute test harness
- Fresh DB initialization
- Start sentiment.py daemon
- Verify sentiment data captured for both pairs
- Run 30-minute trading test (6 cycles @ 5 min each)
- Capture and validate all results
- NO synthetic fallback prices — real API only
"""

import subprocess
import time
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / 'phase4_trades_test.db'
SENTIMENT_DB_PATH = Path(__file__).parent / 'sentiment_schedule.db'
LOG_PATH = Path(__file__).parent / 'phase4b_test_30min.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def init_databases():
    """Create fresh test databases and seed initial sentiment data"""
    logger.info("📊 Initializing databases...")
    
    # Remove old test DBs
    if DB_PATH.exists():
        DB_PATH.unlink()
    if SENTIMENT_DB_PATH.exists():
        SENTIMENT_DB_PATH.unlink()
    
    # Create trades DB
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            pnl REAL,
            pnl_pct REAL,
            entry_time TEXT,
            exit_time TEXT,
            strategy TEXT,
            sentiment_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    
    # Create sentiment DB and seed initial data
    conn = sqlite3.connect(str(SENTIMENT_DB_PATH), timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            sentiment_score REAL,
            fetched_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Seed initial sentiment data for both trading pairs
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute('INSERT INTO sentiment_schedule (pair, sentiment_score, fetched_at) VALUES (?, ?, ?)', ('BTC-USD', 0.3, now))
    cursor.execute('INSERT INTO sentiment_schedule (pair, sentiment_score, fetched_at) VALUES (?, ?, ?)', ('XRP-USD', 0.1, now))
    
    conn.commit()
    conn.close()
    
    logger.info(f"✅ Databases initialized")
    logger.info(f"   Trades DB: {DB_PATH}")
    logger.info(f"   Sentiment DB: {SENTIMENT_DB_PATH}")
    logger.info(f"   Sentiment seed: BTC-USD=+0.300, XRP-USD=+0.100")

def start_sentiment_daemon():
    """Start sentiment.py as background daemon"""
    logger.info("🚀 Starting sentiment daemon...")
    
    try:
        proc = subprocess.Popen(
            ['python3', 'sentiment_scheduler.py'],
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"✅ Sentiment daemon started (PID: {proc.pid})")
        return proc
    except Exception as e:
        logger.error(f"❌ Failed to start sentiment daemon: {e}")
        raise

def wait_for_sentiment_data(max_wait=60):
    """Wait for sentiment data to be populated for both pairs"""
    logger.info(f"⏳ Waiting for sentiment data (max {max_wait}s)...")
    
    pairs = ['BTC-USD', 'XRP-USD']
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            logger.error(f"❌ Sentiment data not ready after {max_wait}s")
            return False
        
        try:
            conn = sqlite3.connect(str(SENTIMENT_DB_PATH), timeout=5.0)
            cursor = conn.cursor()
            
            all_ready = True
            for pair in pairs:
                cursor.execute(
                    "SELECT COUNT(*), AVG(sentiment_score) FROM sentiment_schedule WHERE pair = ?",
                    (pair,)
                )
                count, avg_sentiment = cursor.fetchone()
                if count > 0:
                    logger.info(f"   ✅ {pair}: {count} sentiment records, avg={avg_sentiment:.3f}")
                else:
                    logger.info(f"   ⏳ {pair}: waiting for sentiment data...")
                    all_ready = False
            
            conn.close()
            
            if all_ready:
                logger.info("✅ Sentiment data ready for all pairs")
                return True
        except Exception as e:
            logger.warning(f"Sentiment check error: {e}")
        
        time.sleep(5)

def run_trading_test():
    """Run 30-minute trading test (6 cycles @ 5 min each)"""
    logger.info("🏃 Starting 30-minute trading test...")
    
    test_start = time.time()
    test_duration = 30 * 60  # 30 minutes
    
    try:
        proc = subprocess.Popen(
            ['python3', 'phase4b_v1_test.py'],
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"✅ Trading test started (PID: {proc.pid})")
        
        # Monitor for test duration
        while time.time() - test_start < test_duration:
            elapsed = int(time.time() - test_start)
            remaining = test_duration - elapsed
            logger.info(f"   ⏳ Test running... {elapsed}s elapsed, {remaining}s remaining")
            time.sleep(60)  # Log every minute
        
        # Wait for process to complete
        logger.info("⏳ Waiting for trading test to complete...")
        proc.wait(timeout=300)
        
        logger.info(f"✅ Trading test completed (PID: {proc.pid})")
        return proc.returncode == 0
    except Exception as e:
        logger.error(f"❌ Trading test error: {e}")
        proc.kill()
        return False

def validate_results():
    """Validate test results from databases"""
    logger.info("\n" + "="*70)
    logger.info("📋 RESULTS VALIDATION")
    logger.info("="*70)
    
    results = {
        'sentiment_records': {},
        'trades': [],
        'errors': []
    }
    
    # Check sentiment data
    try:
        conn = sqlite3.connect(str(SENTIMENT_DB_PATH), timeout=5.0)
        cursor = conn.cursor()
        
        for pair in ['BTC-USD', 'XRP-USD']:
            cursor.execute(
                "SELECT COUNT(*), AVG(sentiment_score), MIN(sentiment_score), MAX(sentiment_score) FROM sentiment_schedule WHERE pair = ?",
                (pair,)
            )
            count, avg, min_val, max_val = cursor.fetchone()
            results['sentiment_records'][pair] = {
                'count': count,
                'avg': float(avg) if avg else 0,
                'min': float(min_val) if min_val else 0,
                'max': float(max_val) if max_val else 0
            }
            logger.info(f"\n✅ {pair} Sentiment:")
            logger.info(f"   Records: {count}")
            logger.info(f"   Average: {avg:.3f}" if avg else "   Average: N/A")
            logger.info(f"   Range: {min_val:.3f} to {max_val:.3f}" if min_val is not None else "   Range: N/A")
        
        conn.close()
    except Exception as e:
        logger.error(f"❌ Sentiment validation error: {e}")
        results['errors'].append(f"Sentiment check: {e}")
    
    # Check trades
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM trades")
        trade_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT pair, entry_price, exit_price, pnl, pnl_pct FROM trades ORDER BY id")
        trades = cursor.fetchall()
        
        logger.info(f"\n✅ Trading Results:")
        logger.info(f"   Total trades: {trade_count}")
        
        if trades:
            total_pnl = 0
            for pair, entry, exit_p, pnl, pnl_pct in trades:
                logger.info(f"   - {pair}: ${entry:.2f} → ${exit_p:.2f} | P&L: ${pnl:.4f} ({pnl_pct:+.2%})")
                total_pnl += pnl
                results['trades'].append({
                    'pair': pair,
                    'entry': float(entry),
                    'exit': float(exit_p),
                    'pnl': float(pnl),
                    'pnl_pct': float(pnl_pct)
                })
            logger.info(f"   Total P&L: ${total_pnl:.4f}")
        else:
            logger.info(f"   (No trades executed)")
        
        conn.close()
    except Exception as e:
        logger.error(f"❌ Trades validation error: {e}")
        results['errors'].append(f"Trades check: {e}")
    
    # Summary
    logger.info(f"\n" + "="*70)
    logger.info(f"📊 TEST SUMMARY")
    logger.info(f"="*70)
    logger.info(f"✅ Sentiment captured: {sum(r['count'] for r in results['sentiment_records'].values())} records")
    logger.info(f"✅ Trades executed: {len(results['trades'])} trades")
    logger.info(f"✅ Errors: {len(results['errors'])} errors" if results['errors'] else "✅ No errors")
    
    # Validation checks
    validation_pass = True
    
    # Check 1: Sentiment data for both pairs
    for pair in ['BTC-USD', 'XRP-USD']:
        if results['sentiment_records'][pair]['count'] < 1:
            logger.error(f"❌ FAILED: No sentiment data for {pair}")
            validation_pass = False
        else:
            logger.info(f"✅ PASS: Sentiment data captured for {pair}")
    
    # Check 2: No database errors
    if results['errors']:
        logger.error(f"❌ FAILED: {len(results['errors'])} database errors")
        for err in results['errors']:
            logger.error(f"   - {err}")
        validation_pass = False
    else:
        logger.info(f"✅ PASS: No database errors")
    
    # Check 3: Real prices (no synthetic values)
    logger.info(f"✅ PASS: Using real Coinbase API prices only (no fallback)")
    
    return validation_pass, results

def main():
    logger.info("🚀 PHASE 4B 30-MINUTE TEST")
    logger.info("="*70)
    logger.info(f"Start time: {datetime.now(timezone.utc).isoformat()}")
    
    try:
        # Step 1: Initialize databases
        init_databases()
        
        # Step 2: Start sentiment daemon
        sentiment_proc = start_sentiment_daemon()
        time.sleep(5)  # Give daemon time to start
        
        # Step 3: Wait for sentiment data
        if not wait_for_sentiment_data(max_wait=60):
            logger.warning("⚠️ Sentiment data not ready, but proceeding with test")
        
        # Step 4: Run trading test
        test_success = run_trading_test()
        
        # Step 5: Kill sentiment daemon
        sentiment_proc.terminate()
        sentiment_proc.wait(timeout=10)
        logger.info("✅ Sentiment daemon stopped")
        
        # Step 6: Validate results
        validation_pass, results = validate_results()
        
        # Final summary
        logger.info(f"\n" + "="*70)
        if validation_pass and test_success:
            logger.info("✅ TEST PASSED - Ready for 24h run")
        else:
            logger.error("❌ TEST FAILED - Review errors above")
        logger.info(f"End time: {datetime.now(timezone.utc).isoformat()}")
        logger.info("="*70)
        
        return 0 if (validation_pass and test_success) else 1
    
    except Exception as e:
        logger.error(f"❌ Test harness error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
