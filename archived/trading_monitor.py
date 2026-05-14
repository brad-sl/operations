#!/usr/bin/env python3
import os
import re
import subprocess
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger('TradingMonitor')

def check_active_trades():
    """Scan for active trading processes and log files"""
    try:
        # Find phase* log files modified in last 24h
        find_cmd = "find /home/brad/.openclaw/workspace/operations/crypto-bot/ -name 'phase*_live.log' -mtime -1"
        recent_logs = subprocess.check_output(find_cmd, shell=True).decode().strip().split('\n')
        
        # Check running processes
        ps_cmd = "ps aux | grep -E 'phase[3-6]_multi_pair|trading_bot'"
        processes = subprocess.check_output(ps_cmd, shell=True).decode().strip()
        
        logger.info(f"Active Trading Logs: {recent_logs}")
        logger.info(f"Active Trading Processes:\n{processes}")
        
        # Analyze last log entries
        for log in recent_logs:
            with open(log, 'r') as f:
                tail = f.readlines()[-10:]  # Last 10 lines
                logger.info(f"Log Tail for {log}:\n{''.join(tail)}")
        
    except Exception as e:
        logger.error(f"Monitoring error: {e}")

def main():
    check_active_trades()

if __name__ == '__main__':
    main()