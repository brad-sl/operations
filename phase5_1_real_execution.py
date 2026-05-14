#!/usr/bin/env python3
"""
Phase 5.1 Real Execution
========================

EXECUTE: Real $1K funding orders via Coinbase Advanced Trade API.
Authentication: 2 credentials only (api_key + private_key).
NO passphrase required (that's legacy Pro API).

See: COINBASE_API_SPEC.md for full spec.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

# Load .env
from dotenv import load_dotenv

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_real_execution.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def execute_real_orders():
    """Execute 5 market buy orders with real Coinbase Advanced Trade API."""
    
    logger.info("=" * 80)
    logger.info("PHASE 5.1 REAL EXECUTION — LIVE TRADING WITH $1K CAPITAL")
    logger.info("=" * 80)
    
    # Verify credentials (2 only: api_key + private_key)
    api_key = os.getenv('COINBASE_API_KEY')
    private_key = os.getenv('COINBASE_API_SECRET')
    
    if not api_key or not private_key:
        logger.error("❌ Coinbase credentials NOT found in .env")
        logger.error("   Required: COINBASE_API_KEY + COINBASE_API_SECRET")
        logger.error("   See: COINBASE_API_SPEC.md")
        return False
    
    logger.info(f"✅ Credentials loaded from .env")
    logger.info(f"   API Key: {api_key[:20]}...")
    logger.info(f"   Private Key: {private_key[:30]}...")
    logger.info("")
    
    # Load allocation
    try:
        with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_init_report.json', 'r') as f:
            init_report = json.load(f)
    except FileNotFoundError:
        logger.error("Init report not found")
        return False
    
    allocations = init_report['allocations']
    logger.info(f"Total capital to deploy: ${sum(allocations.values()):.2f}")
    logger.info("")
    
    # Import Coinbase wrapper
    try:
        from coinbase_wrapper import CoinbaseWrapper
        logger.info("✅ CoinbaseWrapper imported")
    except ImportError as e:
        logger.error(f"❌ Cannot import CoinbaseWrapper: {e}")
        return False
    
    # Initialize Coinbase connection (2 credentials only!)
    try:
        wrapper = CoinbaseWrapper(
            api_key=api_key,
            private_key=private_key,
            sandbox=False  # REAL TRADING
        )
        logger.info("✅ Coinbase Advanced Trade API connection established (LIVE MODE)")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Coinbase: {e}")
        return False
    
    # Execute 5 market buy orders
    executed_orders = []
    
    for pair, usd_amount in allocations.items():
        logger.info(f"EXECUTING REAL ORDER: {pair}")
        logger.info(f"  USD Amount: ${usd_amount:.2f}")
        
        try:
            # Get current price from Coinbase
            price_data = wrapper.get_price(pair)
            current_price = float(price_data.get('price', 0))
            
            if current_price == 0:
                logger.error(f"  ❌ Could not get price for {pair}")
                continue
            
            qty = usd_amount / current_price
            logger.info(f"  Current Price: ${current_price:.2f}")
            logger.info(f"  Quantity: {qty:.6f}")
            
            # Place REAL market buy order
            order = wrapper.place_market_buy(pair, qty)
            
            logger.info(f"  ✅ Order placed: {order.get('id', 'PENDING')}")
            logger.info(f"  Status: {order.get('status', 'SUBMITTED')}")
            logger.info("")
            
            executed_orders.append({
                'timestamp': datetime.utcnow().isoformat(),
                'pair': pair,
                'side': 'BUY',
                'qty': qty,
                'price': current_price,
                'usd_amount': usd_amount,
                'order_id': order.get('id'),
                'status': order.get('status'),
                'response': order
            })
            
        except Exception as e:
            logger.error(f"  ❌ Error executing {pair}: {e}")
            continue
    
    # Summary
    logger.info("-" * 80)
    logger.info(f"REAL EXECUTION SUMMARY:")
    logger.info(f"  Orders executed: {len(executed_orders)}/5")
    logger.info(f"  Total deployed: ${sum(o['usd_amount'] for o in executed_orders):.2f}")
    logger.info(f"  Reserve: $250.00")
    logger.info(f"  Total capital: $1,000.00")
    logger.info("")
    
    if len(executed_orders) > 0:
        logger.info("✅ LIVE TRADING INITIATED")
    else:
        logger.error("❌ No orders executed")
    
    # Save execution log
    execution_report = {
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'LIVE_TRADING_ACTIVE' if len(executed_orders) > 0 else 'EXECUTION_FAILED',
        'orders': executed_orders,
        'total_deployed': sum(o['usd_amount'] for o in executed_orders),
        'reserve': 250.00,
        'total_capital': 1000.00
    }
    
    with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_live_execution_report.json', 'w') as f:
        json.dump(execution_report, f, indent=2)
    
    logger.info(f"Report saved: phase5_1_live_execution_report.json")
    logger.info("=" * 80)
    
    return len(executed_orders) > 0

if __name__ == '__main__':
    success = execute_real_orders()
    if success:
        print("\n✅✅✅ PHASE 5.1 LIVE TRADING ACTIVE WITH REAL CAPITAL ✅✅✅")
    else:
        print("\n⚠️ Execution failed - check logs")
