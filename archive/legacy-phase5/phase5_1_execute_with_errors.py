#!/usr/bin/env python3
"""
Phase 5.1 Execute LIVE Orders WITH ERROR LOGGING
==================================================

Place orders and log/notify on failures (INSUFFICIENT_FUND, API errors, etc.).
"""

import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from coinbase_wrapper import CoinbaseWrapper
from error_notifier import get_notifier, log_insufficient_fund, log_api_error

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_with_errors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def execute_live_orders_with_error_handling():
    """Execute 5 market buy orders with comprehensive error logging."""
    
    logger.info("=" * 80)
    logger.info("PHASE 5.1 EXECUTE LIVE ORDERS (WITH ERROR HANDLING)")
    logger.info("=" * 80)
    
    # Load credentials
    api_key = os.getenv('COINBASE_API_KEY')
    private_key = os.getenv('COINBASE_API_SECRET')
    
    # Load allocation from init report
    try:
        with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_init_report.json', 'r') as f:
            init_report = json.load(f)
    except FileNotFoundError:
        logger.error("Init report not found!")
        return False
    
    allocations = init_report['allocations']
    logger.info(f"Total capital: ${sum(allocations.values()):.2f}")
    logger.info("")
    
    # Get error notifier
    notifier = get_notifier()
    
    # Initialize Coinbase
    try:
        wrapper = CoinbaseWrapper(api_key, private_key, sandbox=False)
        logger.info("✅ Connected to Coinbase LIVE API")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        log_api_error('/api/v3/brokerage', 500, str(e))
        return False
    
    # Execute 5 market buy orders
    executed_orders = []
    failed_orders = []
    
    for i, (pair, usd_amount) in enumerate(allocations.items()):
        price = init_report['trades'][i]['price']
        qty = usd_amount / price
        
        logger.info(f"PLACING ORDER {i+1}/5: {pair}")
        logger.info(f"  Amount: ${usd_amount:.2f}")
        logger.info(f"  Price: ${price:.2f}")
        logger.info(f"  Qty: {qty:.6f}")
        
        try:
            # Place market buy order
            result = wrapper.place_market_buy(pair, qty)
            
            if result.get('success', False):
                logger.info(f"  ✅ Order placed: {result['id']}")
                executed_orders.append({
                    'pair': pair,
                    'qty': qty,
                    'price': price,
                    'usd_amount': usd_amount,
                    'order_id': result['id'],
                    'status': result['status'],
                    'timestamp': datetime.utcnow().isoformat()
                })
            else:
                # Order failed — log error
                error_msg = result.get('error', 'unknown error')
                logger.error(f"  ❌ Order failed: {error_msg}")
                
                # Check error type and log appropriately
                if 'INSUFFICIENT_FUND' in error_msg or 'insufficient' in error_msg.lower():
                    notification, event_id = log_insufficient_fund(
                        pair=pair,
                        required=usd_amount,
                        available=0,  # Would need to fetch from account
                        order_id=result.get('id', '')
                    )
                    logger.error(f"  NOTIFICATION TRIGGERED:\n{notification}")
                else:
                    notification, event_id = notifier.notify_critical(
                        'ORDER_FAILED',
                        f"Failed to place order for {pair}",
                        {'pair': pair, 'amount': usd_amount, 'error': error_msg}
                    )
                    logger.error(f"  NOTIFICATION TRIGGERED:\n{notification}")
                
                failed_orders.append({
                    'pair': pair,
                    'amount': usd_amount,
                    'error': error_msg,
                    'event_id': event_id,
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        except Exception as e:
            logger.error(f"  ❌ Exception: {e}")
            notification, event_id = log_api_error(
                f'/api/v3/brokerage/orders (for {pair})',
                500,
                str(e)
            )
            logger.error(f"  NOTIFICATION TRIGGERED:\n{notification}")
            failed_orders.append({
                'pair': pair,
                'exception': str(e),
                'event_id': event_id,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        logger.info("")
    
    # Summary
    logger.info("-" * 80)
    logger.info(f"EXECUTION SUMMARY:")
    logger.info(f"  Orders executed: {len(executed_orders)}/5")
    logger.info(f"  Orders failed: {len(failed_orders)}/5")
    logger.info(f"  Total deployed: ${sum(o['usd_amount'] for o in executed_orders):.2f}")
    logger.info(f"  Reserve: $250.00")
    logger.info("")
    
    if len(failed_orders) > 0:
        logger.warning(f"FAILED ORDERS:")
        for order in failed_orders:
            logger.warning(f"  {order['pair']}: {order.get('error', order.get('exception'))}")
    
    if len(executed_orders) > 0:
        logger.info("✅ LIVE TRADING INITIATED")
    else:
        logger.error("❌ No orders executed")
    
    # Save report
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'PARTIAL_SUCCESS' if (len(executed_orders) > 0 and len(failed_orders) > 0) else ('SUCCESS' if len(executed_orders) == 5 else 'FAILED'),
        'executed': len(executed_orders),
        'failed': len(failed_orders),
        'orders': executed_orders,
        'failed_orders': failed_orders,
        'total_deployed': sum(o['usd_amount'] for o in executed_orders),
        'reserve': 250.00,
        'total_capital': 1000.00
    }
    
    with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_execution_with_errors.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report: phase5_1_execution_with_errors.json")
    logger.info("=" * 80)
    
    return len(executed_orders) > 0

if __name__ == '__main__':
    success = execute_live_orders_with_error_handling()
    exit(0 if success else 1)
