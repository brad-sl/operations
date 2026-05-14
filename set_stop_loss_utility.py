#!/usr/bin/env python3
"""
Stop-Loss Utility Script
Set or update stop-loss orders for active trading positions
Can be used manually to adjust SL margins at any time

Usage:
    python3 set_stop_loss_utility.py --pair BTC-USD --entry-price 62500 --qty 0.00257 --sl-pct 0.02
    python3 set_stop_loss_utility.py --batch-update  # Read from position_state.json
    python3 set_stop_loss_utility.py --list-positions  # Show all active positions
"""

import os
import sys
import json
import logging
import argparse
from dotenv import load_dotenv
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

from position_state_manager import PositionStateManager
from sl_placement_module import SLPlacement

try:
    from coinbase_advanced_client import CoinbaseAdvancedClient
    ADVANCED_TRADE_AVAILABLE = True
except ImportError:
    print("ERROR: Coinbase Advanced Trade SDK not installed")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description="Set or update stop-loss orders for trading positions"
    )
    parser.add_argument('--pair', type=str, help='Trading pair (e.g., BTC-USD)')
    parser.add_argument('--entry-price', type=float, help='Entry price of position')
    parser.add_argument('--qty', type=float, help='Position quantity (in base asset)')
    parser.add_argument('--sl-pct', type=float, default=0.02, help='Stop-loss percentage (default: 0.02 = 2%)')
    parser.add_argument('--sl-price', type=float, help='Explicit stop-loss price (overrides --sl-pct calculation)')
    parser.add_argument('--batch-update', action='store_true', help='Update SL for all positions in position_state.json')
    parser.add_argument('--list-positions', action='store_true', help='List all active positions from state')
    parser.add_argument('--sandbox', action='store_true', default=True, help='Use sandbox (default: True)')
    
    args = parser.parse_args()
    
    # Initialize clients
    try:
        cb_client = CoinbaseAdvancedClient(test_mode=args.sandbox)
        sl_placer = SLPlacement(cb_client)
        pos_manager = PositionStateManager()
        logger.info(f"✅ Clients initialized (sandbox={args.sandbox})")
    except Exception as e:
        logger.error(f"❌ Client initialization failed: {e}")
        sys.exit(1)
    
    # List positions
    if args.list_positions:
        logger.info("\n=== ACTIVE POSITIONS ===")
        all_pos = pos_manager.get_all_positions()
        if not all_pos:
            logger.info("No active positions")
        else:
            for pair, pos in all_pos.items():
                logger.info(f"\n{pair}:")
                logger.info(f"  Entry: ${pos.get('entry_price', 0):.2f}")
                logger.info(f"  Qty: {pos.get('entry_qty', 0):.8f}")
                logger.info(f"  SL Price: ${pos.get('sl_price', 0):.2f}")
                logger.info(f"  SL Order ID: {pos.get('sl_order_id', 'NOT SET')}")
                logger.info(f"  Entry Time: {pos.get('entry_time', 'N/A')}")
        return
    
    # Batch update SL for all positions
    if args.batch_update:
        logger.info("\n=== BATCH SL UPDATE ===")
        all_pos = pos_manager.get_all_positions()
        if not all_pos:
            logger.info("No positions to update")
            return
        
        results = {'success': 0, 'failed': 0, 'skipped': 0}
        
        for pair, pos in all_pos.items():
            entry_price = pos.get('entry_price', 0)
            entry_qty = pos.get('entry_qty', 0)
            existing_sl_id = pos.get('sl_order_id')
            
            if not entry_price or not entry_qty:
                logger.warning(f"⏭️  Skipping {pair}: incomplete position data")
                results['skipped'] += 1
                continue
            
            # Calculate SL (use stored SL price or recalculate from default 2%)
            sl_price = pos.get('sl_price') or sl_placer.get_sl_price(entry_price, 0.02)
            
            logger.info(f"\n📍 {pair}:")
            logger.info(f"   Entry: ${entry_price:.2f} | Qty: {entry_qty:.8f}")
            logger.info(f"   SL Price: ${sl_price:.2f}")
            
            if existing_sl_id:
                logger.info(f"   ⚠️  Existing SL ID: {existing_sl_id} (keeping)")
                results['skipped'] += 1
            else:
                success, order_id, error = sl_placer.place_stop_limit_sell(
                    pair, entry_qty, sl_price
                )
                if success:
                    pos_manager.update_position(
                        pair=pair,
                        entry_price=entry_price,
                        entry_qty=entry_qty,
                        sl_order_id=order_id,
                        sl_price=sl_price,
                        timestamp=datetime.utcnow().isoformat() + 'Z'
                    )
                    logger.info(f"   ✅ SL placed: {order_id}")
                    results['success'] += 1
                else:
                    logger.error(f"   ❌ Failed: {error}")
                    results['failed'] += 1
        
        logger.info(f"\n=== BATCH SUMMARY ===")
        logger.info(f"Success: {results['success']} | Failed: {results['failed']} | Skipped: {results['skipped']}")
        return
    
    # Single pair SL placement
    if args.pair and args.entry_price and args.qty:
        logger.info(f"\n=== SINGLE SL PLACEMENT ===")
        logger.info(f"Pair: {args.pair}")
        logger.info(f"Entry Price: ${args.entry_price:.2f}")
        logger.info(f"Quantity: {args.qty:.8f}")
        
        # Calculate SL price
        if args.sl_price:
            sl_price = args.sl_price
            logger.info(f"SL Price (explicit): ${sl_price:.2f}")
        else:
            sl_price = sl_placer.get_sl_price(args.entry_price, args.sl_pct)
            logger.info(f"SL Price ({args.sl_pct*100}% margin): ${sl_price:.2f}")
        
        # Place SL order
        success, order_id, error = sl_placer.place_stop_limit_sell(
            args.pair, args.qty, sl_price
        )
        
        if success:
            logger.info(f"✅ SL order placed: {order_id}")
            
            # Save to position state
            pos_manager.update_position(
                pair=args.pair,
                entry_price=args.entry_price,
                entry_qty=args.qty,
                sl_order_id=order_id,
                sl_price=sl_price,
                timestamp=datetime.utcnow().isoformat() + 'Z'
            )
            logger.info(f"✅ Position state updated")
        else:
            logger.error(f"❌ Failed: {error}")
            sys.exit(1)
        
        return
    
    # No action specified
    parser.print_help()

if __name__ == '__main__':
    main()
