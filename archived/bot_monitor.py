#!/usr/bin/env python3
"""
Comprehensive Trading Bot Monitoring System
Tracks Phase 6 Takeover Bot Performance and Health
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timedelta
import psutil
import sqlite3
import requests
from dotenv import load_dotenv

class TradingBotMonitor:
    def __init__(self, 
                 bot_process_name='phase6_takeover.py', 
                 log_file='/home/brad/.openclaw/workspace/operations/crypto-bot/bot_monitor.log'):
        """
        Initialize Trading Bot Monitor
        
        :param bot_process_name: Name of the trading bot process to monitor
        :param log_file: Path to log monitoring activities
        """
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load environment variables
        load_dotenv()
        
        # Monitor configuration
        self.bot_process_name = bot_process_name
        self.database_path = '/home/brad/.openclaw/workspace/operations/crypto-bot/phase6_monitor.db'
        
        # Monitoring thresholds
        self.memory_threshold_mb = 500  # 500 MB
        self.cpu_threshold_pct = 80     # 80% CPU
        self.restart_cooldown = timedelta(minutes=15)
        
        # Metrics tracking
        self.last_restart_time = None
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Create SQLite database for monitoring metrics"""
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_metrics (
                    timestamp DATETIME PRIMARY KEY,
                    cpu_usage REAL,
                    memory_usage REAL,
                    num_trades INTEGER,
                    current_capital REAL,
                    sentiment_score REAL,
                    status TEXT
                )
            ''')
            conn.commit()
    
    def _log_bot_metrics(self, metrics):
        """Log bot metrics to SQLite database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bot_metrics 
                    (timestamp, cpu_usage, memory_usage, num_trades, 
                     current_capital, sentiment_score, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    metrics['cpu_usage'],
                    metrics['memory_usage'],
                    metrics['num_trades'],
                    metrics['current_capital'],
                    metrics['sentiment_score'],
                    metrics['status']
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to log metrics: {e}")
    
    def _find_bot_process(self):
        """Find the trading bot process"""
        for proc in psutil.process_iter(['name']):
            if self.bot_process_name in proc.info['name']:
                return proc
        return None
    
    def _check_bot_health(self):
        """
        Comprehensive bot health check
        
        :return: Dictionary of bot health metrics
        """
        bot_process = self._find_bot_process()
        if not bot_process:
            self.logger.warning("Trading bot process not found!")
            return {
                'cpu_usage': 0,
                'memory_usage': 0,
                'num_trades': 0,
                'current_capital': 0,
                'sentiment_score': 0,
                'status': 'PROCESS_MISSING'
            }
        
        try:
            # Resource utilization
            cpu_usage = bot_process.cpu_percent()
            memory_usage = bot_process.memory_info().rss / 1024 / 1024  # MB
            
            # Read trading state
            state_file = '/home/brad/.openclaw/workspace/operations/crypto-bot/takeover_account.json'
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    current_capital = state.get('cash_reserve', 0)
                    num_trades = len(state.get('positions', {}))
            except Exception:
                current_capital = 0
                num_trades = 0
            
            # Sentiment score from last sentiment fetch
            try:
                with open('/home/brad/.openclaw/workspace/operations/crypto-bot/sentiment_cache/x_sentiment_cache.json', 'r') as f:
                    sentiment_data = json.load(f)
                    sentiment_score = sentiment_data.get('BTC-USD', {}).get('sentiment', 0)
            except Exception:
                sentiment_score = 0
            
            # Check for critical conditions
            status = 'RUNNING'
            if cpu_usage > self.cpu_threshold_pct:
                status = 'HIGH_CPU'
            if memory_usage > self.memory_threshold_mb:
                status = 'HIGH_MEMORY'
            
            metrics = {
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'num_trades': num_trades,
                'current_capital': current_capital,
                'sentiment_score': sentiment_score,
                'status': status
            }
            
            self._log_bot_metrics(metrics)
            
            # Alert mechanism for critical conditions
            if status != 'RUNNING':
                self._send_alert(metrics)
            
            return metrics
        
        except Exception as e:
            self.logger.error(f"Bot health check failed: {e}")
            return {
                'cpu_usage': 0,
                'memory_usage': 0,
                'num_trades': 0,
                'current_capital': 0,
                'sentiment_score': 0,
                'status': 'ERROR'
            }
    
    def _send_alert(self, metrics):
        """
        Send alerts via multiple channels
        
        :param metrics: Bot health metrics
        """
        # Telegram alert
        try:
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            if telegram_token and chat_id:
                message = f"""🚨 Trading Bot Alert 🚨
Status: {metrics['status']}
CPU Usage: {metrics['cpu_usage']}%
Memory: {metrics['memory_usage']:.2f} MB
Trades: {metrics['num_trades']}
Capital: ${metrics['current_capital']:.2f}
Sentiment: {metrics['sentiment_score']:.2f}"""
                
                requests.get(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                              params={"chat_id": chat_id, "text": message})
        except Exception as e:
            self.logger.error(f"Telegram alert failed: {e}")
    
    def restart_bot_if_needed(self):
        """
        Restart bot if health metrics exceed thresholds
        Prevent rapid restart attempts
        """
        # Cooldown check
        if (self.last_restart_time and 
            datetime.now() - self.last_restart_time < self.restart_cooldown):
            return
        
        metrics = self._check_bot_health()
        
        if (metrics['status'] != 'RUNNING' or 
            metrics['cpu_usage'] > self.cpu_threshold_pct or 
            metrics['memory_usage'] > self.memory_threshold_mb):
            
            self.logger.warning("Restarting trading bot due to health issues")
            
            # Kill existing process
            for proc in psutil.process_iter(['name']):
                if self.bot_process_name in proc.info['name']:
                    proc.terminate()
                    time.sleep(5)
                    proc.kill()
            
            # Restart bot
            restart_cmd = (
                "cd /home/brad/.openclaw/workspace/operations/crypto-bot && "
                "source venv/bin/activate && "
                "nohup python3 phase6_takeover.py --paper > phase6_paper.log 2>&1 & "
                "echo $! > phase6_paper.pid"
            )
            os.system(restart_cmd)
            
            self.last_restart_time = datetime.now()
    
    def continuous_monitoring(self, interval=300):
        """
        Continuously monitor bot health
        
        :param interval: Monitoring interval in seconds
        """
        while True:
            try:
                self.restart_bot_if_needed()
                time.sleep(interval)
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(interval)
    
    def start_monitoring(self):
        """Start monitoring in a separate thread"""
        monitor_thread = threading.Thread(target=self.continuous_monitoring)
        monitor_thread.daemon = True
        monitor_thread.start()
        self.logger.info("Trading Bot Monitor started")

def main():
    """Entry point for bot monitoring"""
    monitor = TradingBotMonitor()
    monitor.start_monitoring()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Bot Monitor shutting down")

if __name__ == '__main__':
    main()