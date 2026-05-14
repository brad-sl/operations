#!/usr/bin/env python3
"""
Phase 5.1 FINAL LIVE EXECUTION
===============================

Complete order execution with:
- Error logging (INSUFFICIENT_FUND, API errors)
- Order tracking (ID, confirmation code, status)
- Full response capture for troubleshooting
"""

import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from coinbase_wrapper import CoinbaseWrapper
from error_notifier import get_notifier, log_insufficient_fund, log_api_error
from order_tracker import get_tracker

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_final.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def execute_phase5_1_final():
    """Execute Phase 5.1 with full logging and tracking."""
    
    logger.info("=" * 80)
    logger.info("PHASE 5.1 FINAL EXECUTION")
    logger.info("=" * 80)
    
    # Load credentials
    api_key = os.getenv('COINBASE_API_KEY')
    private_key = os.getenv('COINBASE_API_SECRET')
    
    # Load allocation
    try:
        with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_init_report.json', 'r') as f:
            init_report = json.load(f)
    except FileNotFoundError:
        logger.error("Init report not found!")
        return False
    
    allocations = init_report['allocations']
    logger.info(f"Capital: ${sum(allocations.values()):.2f} deploy + $250 reserve")
    logger.info("")
    
    # Get systems
    notifier = get_notifier()
    tracker = get_tracker()
    
    # Connect
    try:
        wrapper = CoinbaseWrapper(api_key, private_key, sandbox=False)
        logger.info("✅ Connected to Coinbase LIVE")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        log_api_error('/api/v3/brokerage', 500, str(e))
        return False
    
    logger.info("")
    
    # Execute orders
    executed = []
    failed = []
    
    for i, (pair, usd) in enumerate(allocations.items(), 1):
        price = init_report['trades'][i-1]['price']
        qty = usd / price
        
        logger.info(f"[{i}/5] {pair}: ${usd:.2f}")
        
        try:
            result = wrapper.place_market_buy(pair, qty)
            
            if result.get('success', False):
                order_id = result.get('id', '')
                status = result.get('status', 'UNKNOWN')
                
                # Log to tracker
                tid = tracker.log_order(pair, 'BUY', usd, qty, price, result, True)
                
                logger.info(f"  ✅ Order ID: {order_id}")
                logger.info(f"  Status: {status}")
                logger.info(f"  Tracking: {tid}")
                
                executed.append({
                    'pair': pair,
                    'order_id': order_id,
                    'confirmation_code': order_id,
                    'status': status,
                    'tracking_id': tid
                })
            else:
                error = result.get('error', 'unknown')
                
                # Log to tracker
                tid = tracker.log_order(pair, 'BUY', usd, qty, price, result, False)
                
                logger.error(f"  ❌ Failed: {error}")
                logger.error(f"  Tracking: {tid}")
                
                # Notify
                if 'INSUFFICIENT_FUND' in error or 'insufficient' in error.lower():
                    notif, eid = log_insufficient_fund(pair, usd, 0, result.get('id', ''))
                else:
                    notif, eid = notifier.notify_critical('ORDER_FAILED', f"Failed: {pair}", 
                        {'pair': pair, 'error': error})
                
                failed.append({
                    'pair': pair,
                    'error': error,
                    'tracking_id': tid,
                    'event_id': eid
                })
        
        except Exception as e:
            tid = tracker.log_order(pair, 'BUY', usd, qty, price, {'exception': str(e)}, False)
            logger.error(f"  ❌ Exception: {e}")
            logger.error(f"  Tracking: {tid}")
            
            notif, eid = log_api_error(f'/orders ({pair})', 500, str(e))
            
            failed.append({
                'pair': pair,
                'exception': str(e),
                'tracking_id': tid,
                'event_id': eid
            })
        
        logger.info("")
    
    # Summary
    logger.info("-" * 80)
    logger.info(f"EXECUTION COMPLETE:")
    logger.info(f"  Executed: {len(executed)}/5")
    logger.info(f"  Failed: {len(failed)}/5")
    logger.info(f"  Deployed: ${sum(a['usd'] for _, a in allocations.items() if len(executed) > _ - 1):.2f}")
    logger.info("")
    
    if executed:
        logger.info("EXECUTED ORDERS:")
        for o in executed:
            logger.info(f"  {o['pair']}: {o['order_id']} ({o['status']})")
    
    if failed:
        logger.warning("\nFAILED ORDERS:")
        for f in failed:
            logger.warning(f"  {f['pair']}: {f.get('error', f.get('exception'))}")
    
    # Tracker summary
    summary = tracker.get_summary()
    logger.info(f"\nTracker Summary:")
    logger.info(f"  Total: {summary['total_orders']}")
    logger.info(f"  Success rate: {summary['success_rate']:.1f}%")
    logger.info(f"  Deployed: ${summary['total_deployed_usd']:.2f}")
    
    logger.info("=" * 80)
    
    return len(executed) > 0

if __name__ == '__main__':
    success = execute_phase5_1_final()
    exit(0 if success else 1)
