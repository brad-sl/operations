#!/usr/bin/env python3
"""
Order Tracking & Confirmation Logger
=====================================

Capture full order details: ID, status, confirmation code, timestamps, raw responses.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OrderTracker:
    """Track and log all orders with full details."""
    
    def __init__(self, log_dir: str = '/home/brad/.openclaw/workspace/operations/crypto-bot'):
        self.log_dir = Path(log_dir)
        self.orders_log = self.log_dir / 'phase5_1_orders_detailed.jsonl'
        self.orders_csv = self.log_dir / 'phase5_1_orders_summary.csv'
        
        self.orders_log.touch(exist_ok=True)
        
        # Initialize CSV header if new file
        if self.orders_csv.stat().st_size == 0:
            with open(self.orders_csv, 'w') as f:
                f.write('timestamp,pair,side,amount_usd,qty,price,order_id,confirmation_code,status,raw_response\n')
        
        logger.info(f"OrderTracker initialized")
        logger.info(f"  Detailed log: {self.orders_log}")
        logger.info(f"  Summary CSV: {self.orders_csv}")
    
    def log_order(
        self,
        pair: str,
        side: str,
        amount_usd: float,
        qty: float,
        price: float,
        raw_response: Dict[str, Any],
        success: bool = True
    ) -> str:
        """
        Log order with full details.
        
        Args:
            pair: Trading pair (e.g., 'BTC-USD')
            side: BUY or SELL
            amount_usd: USD amount
            qty: Quantity
            price: Price
            raw_response: Full API response
            success: Whether order succeeded
        
        Returns:
            Order tracking ID
        """
        timestamp = datetime.utcnow().isoformat()
        tracking_id = f"ord-{int(datetime.utcnow().timestamp() * 1000)}"
        
        # Extract order ID and status from response
        order_id = ""
        confirmation_code = ""
        status = "UNKNOWN"
        
        if raw_response:
            # Try multiple field names for order ID
            order_id = (
                raw_response.get('order_id') or
                raw_response.get('id') or
                raw_response.get('success_response', {}).get('order_id') or
                raw_response.get('success_response', {}).get('id') or
                ""
            )
            
            # Confirmation code (same as order ID for Coinbase)
            confirmation_code = order_id
            
            # Status
            status = (
                raw_response.get('status') or
                raw_response.get('order_status') or
                raw_response.get('success_response', {}).get('status') or
                ("FAILED" if not success else "PENDING")
            )
        
        # Detailed log entry (JSONL)
        log_entry = {
            'tracking_id': tracking_id,
            'timestamp': timestamp,
            'pair': pair,
            'side': side,
            'amount_usd': amount_usd,
            'qty': qty,
            'price': price,
            'order_id': order_id,
            'confirmation_code': confirmation_code,
            'status': status,
            'success': success,
            'raw_response': raw_response
        }
        
        # Write to JSONL
        with open(self.orders_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        # Write to CSV
        csv_row = f'{timestamp},{pair},{side},{amount_usd:.2f},{qty:.6f},{price:.2f},"{order_id}","{confirmation_code}",{status},"{json.dumps(raw_response).replace(",", ";")}"'
        with open(self.orders_csv, 'a') as f:
            f.write(csv_row + '\n')
        
        logger.info(f"Order logged:")
        logger.info(f"  Tracking ID: {tracking_id}")
        logger.info(f"  Order ID: {order_id}")
        logger.info(f"  Confirmation: {confirmation_code}")
        logger.info(f"  Status: {status}")
        
        return tracking_id
    
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Look up order by ID."""
        if not self.orders_log.exists():
            return None
        
        with open(self.orders_log, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry['order_id'] == order_id:
                        return entry
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def get_orders_by_pair(self, pair: str) -> list:
        """Get all orders for a pair."""
        orders = []
        
        if not self.orders_log.exists():
            return []
        
        with open(self.orders_log, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry['pair'] == pair:
                        orders.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return orders
    
    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        if not self.orders_log.exists():
            return {}
        
        total = 0
        successful = 0
        failed = 0
        total_deployed = 0.0
        
        with open(self.orders_log, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    total += 1
                    if entry['success']:
                        successful += 1
                        total_deployed += entry['amount_usd']
                    else:
                        failed += 1
                except json.JSONDecodeError:
                    continue
        
        return {
            'total_orders': total,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total * 100) if total > 0 else 0,
            'total_deployed_usd': total_deployed
        }


# Singleton
_tracker = None

def get_tracker() -> OrderTracker:
    """Get or create singleton tracker."""
    global _tracker
    if _tracker is None:
        _tracker = OrderTracker()
    return _tracker


if __name__ == '__main__':
    # Test
    tracker = get_tracker()
    
    # Simulate order logging
    response = {
        'order_id': 'ORDER-123456',
        'status': 'FILLED',
        'filled_size': '0.002572',
        'executed_value': '160.61'
    }
    
    tracking_id = tracker.log_order(
        pair='BTC-USD',
        side='BUY',
        amount_usd=160.61,
        qty=0.002572,
        price=62450.00,
        raw_response=response,
        success=True
    )
    
    print(f"\nOrder tracked: {tracking_id}")
    print(f"\nSummary: {tracker.get_summary()}")
