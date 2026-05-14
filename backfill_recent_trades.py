#!/usr/bin/env python3
"""
Backfill Recent Live Trades (XRP, SOL, ETH)
Script to add the 3 real trades executed on Apr 30, 2026 ~21:11
These trades executed but weren't tracked in the ledger
"""

import json
from transaction_ledger import TransactionLedger
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_april_30_trades():
    """
    Backfill the 3 real trades from April 30, 2026
    From task description: "Phase 5.1 made 3 real trades (XRP, SOL, ETH)"
    """
    ledger = TransactionLedger()
    
    # These are the 3 trades mentioned that executed but weren't logged
    # Timestamps approximate from "21:11" on 2026-04-30
    recent_trades = [
        {
            "timestamp": "2026-04-30T21:11:15.000Z",
            "pair": "ETH-USD",
            "side": "BUY",
            "quantity": 0.03651111,
            "price": 2283.23,
            "usd_amount": 83.33,
            "order_id": None,  # Will be filled manually from Coinbase
            "sl_order_id": None,
            "notes": "Real trade executed on Apr 30. Order ID needs to be recovered from Coinbase"
        },
        {
            "timestamp": "2026-04-30T21:11:20.000Z",
            "pair": "SOL-USD",
            "side": "BUY",
            "quantity": 0.95694,
            "price": 87.04,
            "usd_amount": 83.33,
            "order_id": None,  # Will be filled manually from Coinbase
            "sl_order_id": None,
            "notes": "Real trade executed on Apr 30. Order ID needs to be recovered from Coinbase"
        },
        {
            "timestamp": "2026-04-30T21:11:22.452Z",
            "pair": "XRP-USD",
            "side": "BUY",
            "quantity": 58.24,
            "price": 1.4307,
            "usd_amount": 83.33,
            "order_id": None,  # Will be filled manually from Coinbase
            "sl_order_id": None,
            "notes": "Real trade executed on Apr 30. Order ID needs to be recovered from Coinbase"
        }
    ]
    
    print("\n" + "="*70)
    print("BACKFILLING APRIL 30 TRADES")
    print("="*70)
    print("\nThese 3 trades executed in Phase 5.1 but weren't tracked:")
    print()
    
    count = 0
    for i, trade in enumerate(recent_trades, 1):
        print(f"\n{i}. {trade['pair']} {trade['side']}")
        print(f"   Time: {trade['timestamp']}")
        print(f"   Qty: {trade['quantity']:.6f} @ ${trade['price']:.2f}")
        print(f"   USD: ${trade['usd_amount']:.2f}")
        
        # Log to ledger
        trade_id = ledger.log_trade(
            timestamp=trade['timestamp'],
            pair=trade['pair'],
            side=trade['side'],
            quantity=trade['quantity'],
            price=trade['price'],
            usd_amount=trade['usd_amount'],
            order_id=trade.get('order_id'),
            sl_order_id=trade.get('sl_order_id'),
            status='EXECUTED',  # Mark as executed since they DID trade
            notes=trade['notes']
        )
        
        print(f"   ✅ Logged as: {trade_id}")
        count += 1
    
    print("\n" + "="*70)
    print(f"\n✅ Backfilled {count} trades\n")
    
    # Print updated summary
    print("Updated Ledger Summary:")
    print("-" * 70)
    ledger.print_summary()
    
    print("\n" + "="*70)
    print("NEXT STEPS: RECOVERY ORDER IDs FROM COINBASE")
    print("="*70)
    print("""
To complete the reconciliation, you need to get the order IDs from Coinbase:

1. Go to https://www.coinbase.com/dashboard/activity or Coinbase Pro
2. Find these 3 BUY orders:
   - ETH-USD: ~83.33 USD on 2026-04-30 ~21:11
   - SOL-USD: ~83.33 USD on 2026-04-30 ~21:11
   - XRP-USD: ~83.33 USD on 2026-04-30 ~21:11
3. Copy the Order ID for each (UUID format)
4. Run: python3 reconciliation_tool.py
5. Select option "2" and enter each Order ID

Or use the interactive reconciliation tool:
   python3 reconciliation_tool.py

For batch updates, create a JSON file:
[
  {
    "timestamp": "2026-04-30T21:11:15.000Z",
    "pair": "ETH-USD",
    "side": "BUY",
    "quantity": 0.03651111,
    "price": 2283.23,
    "usd_amount": 83.33,
    "order_id": "<ACTUAL_COINBASE_ORDER_ID>",
    "sl_order_id": null,
    "notes": "Recovered from Coinbase"
  },
  ...
]

Then run: python3 reconciliation_tool.py batch <file.json>
""")


def show_untracked():
    """Show all trades without order IDs"""
    from reconciliation_tool import TransactionReconciler
    
    reconciler = TransactionReconciler()
    untracked = reconciler.find_untracked_trades()
    
    if untracked:
        print("\nTo add Order IDs, run: python3 reconciliation_tool.py")


if __name__ == "__main__":
    backfill_april_30_trades()
    show_untracked()
