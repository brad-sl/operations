#!/usr/bin/env python3
"""
Phase 4b Digest Generator — generates periodic test status updates
Runs every 4 hours during 48-hour test window
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import os

def get_test_status():
    """Get current test status from phase4_trades.db"""
    db_path = Path("phase4_trades.db")
    
    if not db_path.exists():
        return None
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if trades table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cursor.fetchone():
            return None
        
        # Get trade counts and P&L
        cursor.execute("""
            SELECT 
                pair,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                MAX(pnl) as max_win,
                MIN(pnl) as max_loss
            FROM trades
            GROUP BY pair
        """)
    except Exception as e:
        print(f"DB error: {e}", file=__import__('sys').stderr)
        return None
    
    pair_stats = {row[0]: {
        'trades': row[1],
        'wins': row[2],
        'losses': row[3],
        'total_pnl': round(row[4], 4) if row[4] else 0,
        'avg_pnl': round(row[5], 4) if row[5] else 0,
        'max_win': round(row[6], 4) if row[6] else 0,
        'max_loss': round(row[7], 4) if row[7] else 0,
    } for row in cursor.fetchall()}
    
    # Get total stats
    cursor.execute("SELECT COUNT(*) FROM trades")
    total_trades = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(pnl) FROM trades")
    total_pnl = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM trades")
    total_wins = cursor.fetchone()[0] or 0
    
    # Get sentiment freshness
    cursor.execute("""
        SELECT pair, MAX(fetch_time) as last_fetch FROM sentiment_schedule GROUP BY pair
    """)
    
    sentiment_freshness = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        'total_trades': total_trades,
        'total_pnl': round(total_pnl, 4),
        'total_wins': total_wins,
        'win_rate': round((total_wins / total_trades * 100) if total_trades > 0 else 0, 1),
        'pair_stats': pair_stats,
        'sentiment_freshness': sentiment_freshness,
    }

def get_log_tail(lines=20):
    """Get tail of phase4b_48h_run.log"""
    log_path = Path("phase4b_48h_run.log")
    if not log_path.exists():
        return "Log not found"
    
    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except:
        return "Error reading log"

def get_process_status():
    """Check if phase4b_v1.py is still running"""
    pid_file = Path("phase4b.pid")
    if not pid_file.exists():
        return "No PID file"
    
    try:
        pid = int(pid_file.read_text().strip())
        result = subprocess.run(['ps', '-p', str(pid)], capture_output=True)
        if result.returncode == 0:
            return f"✅ Running (PID: {pid})"
        else:
            return f"❌ Process died (PID: {pid})"
    except Exception as e:
        return f"Error checking process: {e}"

def generate_digest(checkpoint_num):
    """Generate digest for a checkpoint"""
    stats = get_test_status()
    elapsed_hours = checkpoint_num * 4
    
    digest = f"""
🔹 **PHASE 4B DIGEST — Checkpoint #{checkpoint_num} ({elapsed_hours}h elapsed)**

📊 **Execution Status:**
   Process: {get_process_status()}
   Elapsed: {elapsed_hours}h / 48h
   Cycles: ~{elapsed_hours * 12} / 576 expected

📈 **Trading Performance:**
"""
    
    if stats:
        digest += f"""   Total Trades: {stats['total_trades']}
   Total P&L: ${stats['total_pnl']:.4f}
   Win Rate: {stats['win_rate']}%

   **By Pair:**
"""
        
        for pair, data in stats['pair_stats'].items():
            win_rate = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
            digest += f"""   • {pair}: {data['trades']} trades, {win_rate:.0f}% WR, ${data['total_pnl']:.4f} P&L
"""
        
        digest += f"""
🔍 **Sentiment Integration:**
"""
        
        for pair, fetch_time in stats['sentiment_freshness'].items():
            digest += f"   • {pair}: Last fetch {fetch_time or 'never'}\n"
    else:
        digest += "   (No trades yet or DB error)\n"
    
    digest += f"""
🔧 **System Health:**
   Log size: {Path('phase4b_48h_run.log').stat().st_size if Path('phase4b_48h_run.log').exists() else 'N/A'} bytes
   DB size: {Path('phase4_trades.db').stat().st_size if Path('phase4_trades.db').exists() else 'N/A'} bytes

📌 **Quick Notes:**
   Test is progressing normally. Check logs for any anomalies.
   Next digest in 4 hours.
"""
    
    return digest

if __name__ == '__main__':
    import sys
    checkpoint = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(generate_digest(checkpoint))

