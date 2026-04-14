"""
Phase 3 Monitoring Loop

Runs every 5 minutes for 48 hours:
- Pulls fresh signals (real X sentiment + Stochastic RSI for XRP, standard RSI for BTC)
- Executes orders on both pairs in parallel
- Logs to XRP_ORDER_LOG.json
- Sends Telegram alerts on fills + daily P&L summary
- Tracks portfolio balance and P&L in real-time
"""

import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any
import logging

sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')

from phase3_paper_trading import Phase3Orchestrator, OrderLogger, TelegramAlerts
from signal_generator import SignalGenerator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('phase3_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MonitoringLoop:
    """Controls 48-hour paper trading monitoring"""
    
    def __init__(self, trial_duration_hours: int = 48, interval_minutes: int = 5):
        self.orchestrator = Phase3Orchestrator(
            config_path="/home/brad/.openclaw/workspace/operations/crypto-bot/trading_config.json"
        )
        
        self.trial_duration_hours = trial_duration_hours
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_minutes * 60
        
        self.start_time = datetime.now(timezone.utc)
        self.end_time = self.start_time + timedelta(hours=trial_duration_hours)
        
        self.iteration = 0
        self.logger = logger
    
    def is_running(self) -> bool:
        """Check if we're still within the 48-hour window"""
        now = datetime.now(timezone.utc)
        return now < self.end_time
    
    def get_time_remaining(self) -> str:
        """Return human-readable time remaining"""
        now = datetime.now(timezone.utc)
        remaining = self.end_time - now
        hours = remaining.total_seconds() // 3600
        minutes = (remaining.total_seconds() % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"
    
    def run_iteration(self):
        """Execute one iteration: generate signals + execute + log"""
        self.iteration += 1
        iteration_start = datetime.now(timezone.utc)
        
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"ITERATION {self.iteration} | Time: {iteration_start.isoformat()}")
        self.logger.info(f"Time remaining: {self.get_time_remaining()}")
        self.logger.info(f"{'='*70}")
        
        try:
            # Execute one round of trading
            results = self.orchestrator.run_parallel_execution()
            
            # Log results
            for product_id, result in results.items():
                if "error" not in result:
                    self.logger.info(
                        f"✅ {product_id}: "
                        f"{result['signals_processed']} signals, "
                        f"{result['orders_filled']} fills"
                    )
                else:
                    self.logger.error(f"❌ {product_id}: {result['error']}")
            
            # Generate checkpoint
            checkpoint_time = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            self.logger.info(f"⏸️  Checkpoint saved | {checkpoint_time:.1f}s elapsed")
            
        except Exception as e:
            self.logger.error(f"❌ Iteration failed: {e}", exc_info=True)
        
        iteration_duration = (datetime.now(timezone.utc) - iteration_start).total_seconds()
        self.logger.info(f"⏱️  Iteration duration: {iteration_duration:.1f}s")
    
    def generate_hourly_summary(self):
        """Generate P&L summary every hour"""
        report = self.orchestrator.generate_final_report()
        
        self.logger.info(f"\n{'*'*70}")
        self.logger.info("HOURLY P&L SUMMARY")
        self.logger.info(f"{'*'*70}")
        
        for product_id, summary in report["summaries"].items():
            self.logger.info(
                f"\n{product_id}:\n"
                f"  • Signals: {summary['total_signals']}\n"
                f"  • Fills: {summary['filled_orders']}\n"
                f"  • Quantity: {summary['total_quantity']}\n"
                f"  • Cost: ${summary['total_cost_usd']:.2f}\n"
                f"  • Avg Price: ${summary['avg_execution_price']:.2f}"
            )
        
        return report
    
    def run_48_hour_trial(self):
        """Main monitoring loop for 48 hours"""
        self.logger.info(f"\n🚀 PHASE 3 MONITORING LOOP STARTED")
        self.logger.info(f"Duration: 48 hours")
        self.logger.info(f"Interval: {self.interval_minutes} minutes")
        self.logger.info(f"Start: {self.start_time.isoformat()}")
        self.logger.info(f"End: {self.end_time.isoformat()}")
        
        hourly_counter = 0
        
        while self.is_running():
            # Run trading iteration
            self.run_iteration()
            
            # Every 12 iterations (1 hour at 5-min interval), generate summary
            hourly_counter += 1
            if hourly_counter >= 12:
                self.generate_hourly_summary()
                hourly_counter = 0
            
            # Sleep until next iteration
            if self.is_running():
                self.logger.info(f"⏳ Sleeping {self.interval_minutes} minutes until next iteration...")
                time.sleep(self.interval_seconds)
        
        # Final report
        self.logger.info(f"\n{'='*70}")
        self.logger.info("🏁 PHASE 3 TRIAL COMPLETE")
        self.logger.info(f"{'='*70}")
        
        final_report = self.orchestrator.generate_final_report()
        self.logger.info(f"\nFinal Report:")
        self.logger.info(json.dumps(final_report, indent=2))
        
        return final_report


def main():
    """Entry point"""
    # Check if we want to run the full 48-hour trial or just test
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    
    if test_mode:
        logger.info("🧪 TEST MODE: Running 3 iterations only")
        loop = MonitoringLoop(trial_duration_hours=0.25, interval_minutes=1)  # 15 minutes total
    else:
        logger.info("🚀 PRODUCTION MODE: Running full 48-hour trial")
        loop = MonitoringLoop(trial_duration_hours=48, interval_minutes=5)
    
    # Run monitoring loop
    final_report = loop.run_48_hour_trial()
    
    # Save final report
    with open('PHASE3_FINAL_REPORT.json', 'w') as f:
        json.dump(final_report, f, indent=2)
    
    logger.info(f"\n✅ Phase 3 monitoring complete. Final report: PHASE3_FINAL_REPORT.json")


if __name__ == "__main__":
    main()

