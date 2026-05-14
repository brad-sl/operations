#!/usr/bin/env python3
"""
Transaction Ledger Manager for Phase 5.1
Persistent JSON-based audit trail for all trades
Survives restarts and provides order ID tracking
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import logging

class TransactionLedger:
    """
    Persistent ledger for tracking all trades with full order details
    """
    
    def __init__(self, ledger_path: str = None):
        if ledger_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            ledger_path = os.path.join(script_dir, 'state', 'phase5_trades.json')
        
        self.ledger_path = ledger_path
        self.logger = logging.getLogger(__name__)
        
        # Ensure state directory exists
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        
        # Load or initialize
        self._ensure_ledger_exists()
    
    def _ensure_ledger_exists(self):
        """Create ledger if it doesn't exist"""
        if not os.path.exists(self.ledger_path):
            self._write_ledger({
                "trades": [],
                "summary": {
                    "total_trades": 0,
                    "successful": 0,
                    "failed": 0,
                    "pending": 0,
                    "last_trade": None,
                    "total_usd_traded": 0.0,
                    "version": "1.0"
                }
            })
    
    def _read_ledger(self) -> Dict:
        """Read ledger from disk"""
        try:
            with open(self.ledger_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to read ledger: {e}")
            return {"trades": [], "summary": {"total_trades": 0, "successful": 0, "failed": 0, "pending": 0}}
    
    def _write_ledger(self, data: Dict):
        """Write ledger to disk (atomic)"""
        try:
            # Write to temp file first, then rename (atomic on Unix)
            temp_path = self.ledger_path + '.tmp'
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.ledger_path)
        except Exception as e:
            self.logger.error(f"Failed to write ledger: {e}")
    
    def log_trade(self, 
                  timestamp: str,
                  pair: str,
                  side: str,
                  quantity: float,
                  price: float,
                  usd_amount: float,
                  order_id: Optional[str] = None,
                  sl_order_id: Optional[str] = None,
                  status: str = "PENDING",
                  coinbase_response: Optional[Dict] = None,
                  notes: str = "") -> str:
        """
        Log a new trade to the ledger
        
        Args:
            timestamp: ISO format timestamp
            pair: Trading pair (e.g., 'ETH-USD')
            side: 'BUY' or 'SELL'
            quantity: Amount of base asset
            price: Price per unit
            usd_amount: Total USD spent/received
            order_id: Coinbase order ID
            sl_order_id: Stop-loss order ID
            status: PENDING, EXECUTED, FAILED, PARTIALLY_FILLED
            coinbase_response: Full API response object
            notes: Optional notes
        
        Returns:
            Trade ID (for later reference)
        """
        ledger = self._read_ledger()
        
        trade_id = f"{pair}_{side}_{timestamp}_{int(time.time()*1000)}"
        
        trade_entry = {
            "trade_id": trade_id,
            "timestamp": timestamp,
            "pair": pair,
            "side": side,
            "quantity": quantity,
            "price": price,
            "usd_amount": usd_amount,
            "order_id": order_id,
            "sl_order_id": sl_order_id,
            "status": status,
            "coinbase_response": coinbase_response or {},
            "notes": notes,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        ledger["trades"].append(trade_entry)
        
        # Update summary
        ledger["summary"]["total_trades"] = len(ledger["trades"])
        ledger["summary"]["last_trade"] = timestamp
        
        # Count by status
        statuses = {}
        total_usd = 0.0
        for trade in ledger["trades"]:
            st = trade.get("status", "UNKNOWN")
            statuses[st] = statuses.get(st, 0) + 1
            if st in ["EXECUTED", "PARTIALLY_FILLED"]:
                total_usd += trade.get("usd_amount", 0)
        
        ledger["summary"]["successful"] = statuses.get("EXECUTED", 0) + statuses.get("PARTIALLY_FILLED", 0)
        ledger["summary"]["failed"] = statuses.get("FAILED", 0)
        ledger["summary"]["pending"] = statuses.get("PENDING", 0)
        ledger["summary"]["total_usd_traded"] = round(total_usd, 2)
        
        self._write_ledger(ledger)
        self.logger.info(f"📝 Logged trade: {trade_id} ({pair} {side} {quantity})")
        
        return trade_id
    
    def update_trade_status(self, trade_id: str, status: str, order_id: Optional[str] = None, 
                           notes: str = ""):
        """Update status of an existing trade"""
        ledger = self._read_ledger()
        
        for trade in ledger["trades"]:
            if trade["trade_id"] == trade_id:
                trade["status"] = status
                if order_id:
                    trade["order_id"] = order_id
                if notes:
                    trade["notes"] = notes
                trade["updated_at"] = datetime.utcnow().isoformat() + "Z"
                
                # Recalc summary
                statuses = {}
                total_usd = 0.0
                for t in ledger["trades"]:
                    st = t.get("status", "UNKNOWN")
                    statuses[st] = statuses.get(st, 0) + 1
                    if st in ["EXECUTED", "PARTIALLY_FILLED"]:
                        total_usd += t.get("usd_amount", 0)
                
                ledger["summary"]["successful"] = statuses.get("EXECUTED", 0) + statuses.get("PARTIALLY_FILLED", 0)
                ledger["summary"]["failed"] = statuses.get("FAILED", 0)
                ledger["summary"]["pending"] = statuses.get("PENDING", 0)
                ledger["summary"]["total_usd_traded"] = round(total_usd, 2)
                
                self._write_ledger(ledger)
                self.logger.info(f"✅ Updated {trade_id}: {status}")
                return True
        
        self.logger.warning(f"Trade ID not found: {trade_id}")
        return False
    
    def get_trade_by_id(self, trade_id: str) -> Optional[Dict]:
        """Retrieve a trade by ID"""
        ledger = self._read_ledger()
        for trade in ledger["trades"]:
            if trade["trade_id"] == trade_id:
                return trade
        return None
    
    def get_trades_by_pair(self, pair: str) -> List[Dict]:
        """Get all trades for a specific pair"""
        ledger = self._read_ledger()
        return [t for t in ledger["trades"] if t["pair"] == pair]
    
    def get_trades_by_status(self, status: str) -> List[Dict]:
        """Get all trades with a specific status"""
        ledger = self._read_ledger()
        return [t for t in ledger["trades"] if t["status"] == status]
    
    def get_summary(self) -> Dict:
        """Get trading summary"""
        ledger = self._read_ledger()
        return ledger.get("summary", {})
    
    def get_all_trades(self) -> List[Dict]:
        """Get all trades"""
        ledger = self._read_ledger()
        return ledger.get("trades", [])
    
    def export_to_csv(self, output_path: str = None, include_response: bool = False):
        """
        Export ledger to CSV format
        
        Args:
            output_path: Where to save CSV (defaults to state/trades_live.csv)
            include_response: Include full Coinbase response in export
        """
        import csv
        
        if output_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_path = os.path.join(script_dir, 'state', 'trades_live.csv')
        
        ledger = self._read_ledger()
        trades = ledger.get("trades", [])
        
        if not trades:
            self.logger.info("No trades to export")
            return
        
        try:
            with open(output_path, 'w', newline='') as csvfile:
                fieldnames = [
                    'timestamp', 'pair', 'side', 'quantity', 'price', 'usd_amount',
                    'order_id', 'sl_order_id', 'status', 'trade_id', 'notes'
                ]
                
                if include_response:
                    fieldnames.append('coinbase_response')
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for trade in trades:
                    row = {
                        'timestamp': trade.get('timestamp', ''),
                        'pair': trade.get('pair', ''),
                        'side': trade.get('side', ''),
                        'quantity': trade.get('quantity', ''),
                        'price': trade.get('price', ''),
                        'usd_amount': trade.get('usd_amount', ''),
                        'order_id': trade.get('order_id', ''),
                        'sl_order_id': trade.get('sl_order_id', ''),
                        'status': trade.get('status', ''),
                        'trade_id': trade.get('trade_id', ''),
                        'notes': trade.get('notes', '')
                    }
                    
                    if include_response:
                        row['coinbase_response'] = json.dumps(trade.get('coinbase_response', {}))
                    
                    writer.writerow(row)
            
            self.logger.info(f"📊 Exported {len(trades)} trades to {output_path}")
        except Exception as e:
            self.logger.error(f"CSV export failed: {e}")
    
    def print_summary(self):
        """Pretty-print summary stats"""
        summary = self.get_summary()
        print("\n=== TRANSACTION LEDGER SUMMARY ===")
        print(f"Total Trades: {summary.get('total_trades', 0)}")
        print(f"✅ Successful: {summary.get('successful', 0)}")
        print(f"❌ Failed: {summary.get('failed', 0)}")
        print(f"⏳ Pending: {summary.get('pending', 0)}")
        print(f"💰 Total USD Traded: ${summary.get('total_usd_traded', 0):.2f}")
        print(f"Last Trade: {summary.get('last_trade', 'N/A')}")
        print("=" * 35)


if __name__ == "__main__":
    # Test
    ledger = TransactionLedger()
    ledger.print_summary()
