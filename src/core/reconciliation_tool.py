#!/usr/bin/env python3
"""
Reconciliation Tool for Phase 5.1 Transactions
Matches untracked orders from Coinbase with ledger entries
Allows manual backfilling of order IDs
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from transaction_ledger import TransactionLedger
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransactionReconciler:
    def __init__(self):
        self.ledger = TransactionLedger()
    
    def find_untracked_trades(self) -> List[Dict]:
        """Find all trades in ledger without order IDs"""
        trades = self.ledger.get_all_trades()
        untracked = [t for t in trades if not t.get('order_id')]
        
        if untracked:
            logger.info(f"\n📋 Found {len(untracked)} trades without order IDs:")
            for t in untracked:
                logger.info(f"  - {t['timestamp']} | {t['pair']} {t['side']} {t['quantity']} @ ${t['price']:.2f}")
        else:
            logger.info("✅ All trades have order IDs!")
        
        return untracked
    
    def find_by_timestamp_and_pair(self, timestamp: str, pair: str, side: str) -> Optional[Dict]:
        """Find trade by approximate timestamp, pair, and side"""
        trades = self.ledger.get_all_trades()
        
        for trade in trades:
            if trade['pair'] == pair and trade['side'] == side:
                # Check if timestamps are close (within 60 seconds)
                try:
                    trade_time = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                    query_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    diff = abs((trade_time - query_time).total_seconds())
                    if diff < 60:
                        return trade
                except:
                    pass
        
        return None
    
    def add_order_id_to_trade(self, trade_id: str, order_id: str, notes: str = "") -> bool:
        """Update a trade with its order ID"""
        success = self.ledger.update_trade_status(
            trade_id,
            status='EXECUTED',
            order_id=order_id,
            notes=notes or 'Manually backfilled order ID'
        )
        
        if success:
            logger.info(f"✅ Updated {trade_id}: Added order_id={order_id}")
        else:
            logger.warning(f"❌ Failed to update {trade_id}")
        
        return success
    
    def backfill_missing_trades(self, trades_to_add: List[Dict]) -> int:
        """
        Backfill trades from Coinbase that weren't logged
        Each trade must have: timestamp, pair, side, quantity, price, usd_amount, order_id
        
        Args:
            trades_to_add: List of trade dicts from Coinbase API
        
        Returns:
            Number of trades added
        """
        count = 0
        for trade in trades_to_add:
            try:
                self.ledger.log_trade(
                    timestamp=trade['timestamp'],
                    pair=trade['pair'],
                    side=trade['side'],
                    quantity=trade['quantity'],
                    price=trade['price'],
                    usd_amount=trade['usd_amount'],
                    order_id=trade.get('order_id'),
                    sl_order_id=trade.get('sl_order_id'),
                    status='EXECUTED',
                    notes=trade.get('notes', 'Backfilled from Coinbase')
                )
                count += 1
                logger.info(f"✅ Backfilled: {trade['pair']} {trade['side']} {trade['quantity']}")
            except Exception as e:
                logger.error(f"Failed to backfill trade: {e}")
        
        return count
    
    def generate_reconciliation_report(self) -> str:
        """Generate HTML reconciliation report"""
        trades = self.ledger.get_all_trades()
        summary = self.ledger.get_summary()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Phase 5.1 Reconciliation Report</title>
    <style>
        body {{ font-family: Arial; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .missing-order {{ background-color: #ffcccc; }}
        .summary {{ background-color: #e7f3fe; padding: 20px; margin: 20px 0; }}
        .stat {{ display: inline-block; margin-right: 30px; }}
    </style>
</head>
<body>
    <h1>Phase 5.1 Transaction Reconciliation Report</h1>
    <p>Generated: {datetime.utcnow().isoformat()}Z</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="stat"><strong>Total Trades:</strong> {summary.get('total_trades', 0)}</div>
        <div class="stat"><strong>✅ Successful:</strong> {summary.get('successful', 0)}</div>
        <div class="stat"><strong>❌ Failed:</strong> {summary.get('failed', 0)}</div>
        <div class="stat"><strong>⏳ Pending:</strong> {summary.get('pending', 0)}</div>
        <div class="stat"><strong>💰 Total USD:</strong> ${summary.get('total_usd_traded', 0):.2f}</div>
    </div>
    
    <h2>Detailed Trades</h2>
    <table>
        <tr>
            <th>Timestamp</th>
            <th>Pair</th>
            <th>Side</th>
            <th>Quantity</th>
            <th>Price</th>
            <th>USD Amount</th>
            <th>Order ID</th>
            <th>Status</th>
            <th>Notes</th>
        </tr>
"""
        
        for trade in trades:
            order_id = trade.get('order_id', '')
            row_class = 'missing-order' if not order_id else ''
            
            html += f"""
        <tr class="{row_class}">
            <td>{trade.get('timestamp', '')}</td>
            <td>{trade.get('pair', '')}</td>
            <td>{trade.get('side', '')}</td>
            <td>{trade.get('quantity', 0):.6f}</td>
            <td>${trade.get('price', 0):.2f}</td>
            <td>${trade.get('usd_amount', 0):.2f}</td>
            <td>{order_id or '<em>MISSING</em>'}</td>
            <td>{trade.get('status', '')}</td>
            <td>{trade.get('notes', '')}</td>
        </tr>
"""
        
        html += """
    </table>
</body>
</html>
"""
        return html
    
    def save_reconciliation_report(self, output_path: str = None):
        """Save reconciliation report as HTML"""
        if output_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_path = os.path.join(script_dir, 'state', 'reconciliation_report.html')
        
        report = self.generate_reconciliation_report()
        
        try:
            with open(output_path, 'w') as f:
                f.write(report)
            logger.info(f"📄 Reconciliation report saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


def interactive_reconciliation():
    """Interactive reconciliation wizard"""
    reconciler = TransactionReconciler()
    
    print("\n" + "="*60)
    print("PHASE 5.1 TRANSACTION RECONCILIATION WIZARD")
    print("="*60)
    
    while True:
        print("\n\nOptions:")
        print("1. View untracked trades")
        print("2. Add order ID to a trade")
        print("3. Backfill missing trades")
        print("4. Generate reconciliation report")
        print("5. View all trades")
        print("6. Exit")
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == '1':
            untracked = reconciler.find_untracked_trades()
            if untracked:
                print(f"\n{len(untracked)} untracked trades found")
        
        elif choice == '2':
            trade_id = input("Enter trade ID: ").strip()
            order_id = input("Enter order ID from Coinbase: ").strip()
            notes = input("Optional notes: ").strip()
            reconciler.add_order_id_to_trade(trade_id, order_id, notes)
        
        elif choice == '3':
            print("\nEnter trades to backfill (JSON array format)")
            print("Example: [{\"timestamp\": \"...\", \"pair\": \"ETH-USD\", ...}]")
            try:
                json_str = input("Paste JSON: ").strip()
                trades = json.loads(json_str)
                count = reconciler.backfill_missing_trades(trades)
                print(f"✅ Backfilled {count} trades")
            except json.JSONDecodeError:
                print("❌ Invalid JSON")
        
        elif choice == '4':
            reconciler.save_reconciliation_report()
            print("✅ Report saved")
        
        elif choice == '5':
            trades = reconciler.ledger.get_all_trades()
            print(f"\nAll {len(trades)} trades:")
            for t in trades:
                print(f"  {t['timestamp']} | {t['pair']} {t['side']} | ${t['usd_amount']:.2f} | ID: {t.get('order_id', 'MISSING')}")
        
        elif choice == '6':
            print("\nGoodbye!")
            break
        
        else:
            print("Invalid choice")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'batch':
        # Batch mode: read trades from file
        if len(sys.argv) > 2:
            with open(sys.argv[2], 'r') as f:
                trades = json.load(f)
            reconciler = TransactionReconciler()
            count = reconciler.backfill_missing_trades(trades)
            print(f"✅ Backfilled {count} trades")
    else:
        # Interactive mode
        interactive_reconciliation()
