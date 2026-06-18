#!/usr/bin/env python3
"""
Phase 5.1 Execute LIVE Orders
==============================

Use current prices from allocation report (calculated at 13:08 UTC).
Place 5 market buy orders directly with Coinbase API.
"""

import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from coinbase_wrapper import CoinbaseWrapper

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_live_orders.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def execute_live_orders():
    """Execute 5 market buy orders using init report prices."""
    
    logger.info("=" * 80)
    logger.info("PHASE 5.1 EXECUTE LIVE ORDERS")
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
    
    # Initialize Coinbase
    try:
        wrapper = CoinbaseWrapper(api_key, private_key, sandbox=False)
        logger.info("✅ Connected to Coinbase LIVE API")
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        return False
    
    # Execute 5 market buy orders
    executed_orders = []
    
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
                logger.error(f"  ❌ Order failed: {result.get('error', 'unknown error')}")
        
        except Exception as e:
            logger.error(f"  ❌ Exception: {e}")
        
        logger.info("")
    
    # Summary
    logger.info("-" * 80)
    logger.info(f"EXECUTION SUMMARY:")
    logger.info(f"  Orders executed: {len(executed_orders)}/5")
    logger.info(f"  Total deployed: ${sum(o['usd_amount'] for o in executed_orders):.2f}")
    logger.info(f"  Reserve: $250.00")
    logger.info("")
    
    if len(executed_orders) > 0:
        logger.info("✅ LIVE TRADING INITIATED")
    else:
        logger.error("❌ No orders executed")
    
    # Save report
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'ORDERS_EXECUTED' if len(executed_orders) > 0 else 'EXECUTION_FAILED',
        'orders_executed': len(executed_orders),
        'orders': executed_orders,
        'total_deployed': sum(o['usd_amount'] for o in executed_orders),
        'reserve': 250.00,
        'total_capital': 1000.00
    }
    
    with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_live_orders.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report: phase5_1_live_orders.json")
    logger.info("=" * 80)
    
    return len(executed_orders) > 0

if __name__ == '__main__':
    success = execute_live_orders()
    exit(0 if success else 1)
