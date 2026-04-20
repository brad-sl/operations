#!/usr/bin/env python3
"""
Phase 4B 24-hour harness with clean test/production separation.

Runs in two modes:
1. Production (PRICE_SOURCE=coinbase): Real Coinbase API (no fallback)
2. Testing (PRICE_SOURCE=snapshot): Test fixtures from JSON snapshots

CRITICAL RULE: No synthetic prices in production code.
Test harness uses environment variable to switch between real API and test data.
"""

import os
import time
import logging
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Use the price wrapper factory: automatically selects CoinbaseWrapper or TestPriceWrapper
from test_price_wrapper import get_price_wrapper

LOG_DIR = Path("phase4b_run_logs")
LOG_DIR.mkdir(exist_ok=True, parents=True)
LOG_FILE = LOG_DIR / "run_24h.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    """
    24-hour trading harness. Runs price polling loop and logs all cycles.
    
    Usage:
        # Production mode (real Coinbase API):
        COINBASE_API_KEY=... python3 phase4b_run_24h.py
        
        # Test mode (snapshot-based):
        PRICE_SOURCE=snapshot python3 phase4b_run_24h.py
    """
    
    price_source = os.getenv('PRICE_SOURCE', 'coinbase').lower()
    logger.info(f"Starting 24-hour Phase 4B run in {price_source} mode")
    
    # Get price wrapper (automatically selects real API or test snapshots)
    try:
        wrapper = get_price_wrapper()
        logger.info("✅ Price wrapper initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize price wrapper: {e}")
        sys.exit(1)
    
    # 24 hours, 5-minute polling cadence
    cycle_minutes = 5
    cycles = int((24 * 60) / cycle_minutes)  # 288 cycles
    logger.info(f"Will run for {cycles} cycles ({cycle_minutes}-minute cadence)")
    
    # Statistics tracking
    stats = {
        "cycles_completed": 0,
        "price_fetch_success": 0,
        "price_fetch_error": 0,
        "prices": []
    }
    
    for i in range(int(cycles)):
        cycle_num = i + 1
        t = datetime.now(timezone.utc).isoformat()
        
        try:
            # Fetch prices from wrapper (real API or snapshot)
            btc_data = wrapper.get_price("BTC-USD")
            xrp_data = wrapper.get_price("XRP-USD")
            
            price_btc = btc_data.get("price") if isinstance(btc_data, dict) else None
            price_xrp = xrp_data.get("price") if isinstance(xrp_data, dict) else None
            
            if price_btc is None or price_xrp is None:
                raise ValueError(f"Invalid price response: BTC={price_btc}, XRP={price_xrp}")
            
            # Log cycle
            log_entry = {
                "cycle": cycle_num,
                "timestamp": t,
                "BTC-USD": price_btc,
                "XRP-USD": price_xrp,
                "source": price_source
            }
            logger.info(f"Cycle {cycle_num:3d}/288: BTC-USD=${price_btc:8.2f} | XRP-USD=${price_xrp:6.2f}")
            
            # Append to JSON log
            with open(LOG_FILE.with_suffix('.jsonl'), "a") as f:
                f.write(json.dumps(log_entry) + "\n")
            
            stats["price_fetch_success"] += 1
            stats["prices"].append({"cycle": cycle_num, "BTC": price_btc, "XRP": price_xrp})
            
        except Exception as e:
            logger.error(f"Cycle {cycle_num} error: {e}")
            stats["price_fetch_error"] += 1
        
        stats["cycles_completed"] = cycle_num
        
        # Sleep between cycles (except on last cycle)
        if i < cycles - 1:
            time.sleep(cycle_minutes * 60)
    
    # Final report
    logger.info("\n" + "="*70)
    logger.info("24-HOUR RUN COMPLETE")
    logger.info("="*70)
    logger.info(f"Cycles completed: {stats['cycles_completed']}/{cycles}")
    logger.info(f"Price fetch success: {stats['price_fetch_success']}")
    logger.info(f"Price fetch errors: {stats['price_fetch_error']}")
    logger.info(f"Success rate: {100*stats['price_fetch_success']/max(1,stats['cycles_completed']):.1f}%")
    logger.info(f"Log files: {LOG_FILE} + {LOG_FILE.with_suffix('.jsonl')}")
    logger.info("="*70)
    
    # Return success/failure exit code
    return 0 if stats['price_fetch_error'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
