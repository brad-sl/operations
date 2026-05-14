#!/usr/bin/env python3
"""
Test suite for Transaction Ledger System
Verifies:
1. Ledger creation and persistence
2. Trade logging
3. Status updates
4. CSV export
5. Reconciliation functions
"""

import os
import json
import tempfile
from datetime import datetime
from transaction_ledger import TransactionLedger
from reconciliation_tool import TransactionReconciler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_ledger_creation():
    """Test that ledger file is created properly"""
    print("\n" + "="*60)
    print("TEST 1: Ledger Creation and Initialization")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        ledger = TransactionLedger(ledger_path)
        
        # Check file exists
        assert os.path.exists(ledger_path), "❌ Ledger file not created"
        print("✅ Ledger file created")
        
        # Check schema
        with open(ledger_path, 'r') as f:
            data = json.load(f)
        
        assert 'trades' in data, "❌ Missing 'trades' key"
        assert 'summary' in data, "❌ Missing 'summary' key"
        assert isinstance(data['trades'], list), "❌ Trades not a list"
        
        print("✅ Ledger schema valid")
        print(f"   Summary keys: {list(data['summary'].keys())}")


def test_trade_logging():
    """Test logging trades"""
    print("\n" + "="*60)
    print("TEST 2: Trade Logging")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        ledger = TransactionLedger(ledger_path)
        
        # Log a test trade
        trade_id = ledger.log_trade(
            timestamp="2026-04-30T21:11:15.000Z",
            pair="ETH-USD",
            side="BUY",
            quantity=0.03651111,
            price=2283.23,
            usd_amount=83.33,
            order_id="abc-123-def",
            status="EXECUTED",
            notes="Test trade"
        )
        
        assert trade_id, "❌ No trade ID returned"
        print(f"✅ Trade logged: {trade_id}")
        
        # Check ledger updated
        summary = ledger.get_summary()
        assert summary['total_trades'] == 1, "❌ Total trades not incremented"
        assert summary['successful'] == 1, "❌ Successful count not incremented"
        assert summary['total_usd_traded'] == 83.33, "❌ USD amount not tracked"
        
        print(f"✅ Summary updated: {summary['total_trades']} trades, ${summary['total_usd_traded']:.2f}")
        
        # Retrieve trade
        trade = ledger.get_trade_by_id(trade_id)
        assert trade is not None, "❌ Trade not retrievable"
        assert trade['pair'] == 'ETH-USD', "❌ Pair mismatch"
        assert trade['order_id'] == 'abc-123-def', "❌ Order ID mismatch"
        print(f"✅ Trade retrieved and verified")


def test_status_updates():
    """Test updating trade status"""
    print("\n" + "="*60)
    print("TEST 3: Trade Status Updates")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        ledger = TransactionLedger(ledger_path)
        
        # Log a pending trade
        trade_id = ledger.log_trade(
            timestamp="2026-04-30T21:11:15.000Z",
            pair="BTC-USD",
            side="BUY",
            quantity=0.01,
            price=78000.00,
            usd_amount=780.00,
            status="PENDING"
        )
        print(f"✅ Logged pending trade: {trade_id}")
        
        # Update to executed with order ID
        success = ledger.update_trade_status(
            trade_id,
            status='EXECUTED',
            order_id='xyz-456-ghi',
            notes='Order confirmed'
        )
        
        assert success, "❌ Status update failed"
        print("✅ Status updated to EXECUTED")
        
        # Verify update
        trade = ledger.get_trade_by_id(trade_id)
        assert trade['status'] == 'EXECUTED', "❌ Status not updated"
        assert trade['order_id'] == 'xyz-456-ghi', "❌ Order ID not set"
        
        summary = ledger.get_summary()
        assert summary['successful'] == 1, "❌ Successful count not updated"
        assert summary['pending'] == 0, "❌ Pending count not updated"
        
        print("✅ Trade state verified")


def test_batch_logging():
    """Test logging multiple trades"""
    print("\n" + "="*60)
    print("TEST 4: Batch Trade Logging")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        ledger = TransactionLedger(ledger_path)
        
        trades_to_log = [
            ("ETH-USD", "BUY", 0.036, 2283.23, 83.33),
            ("SOL-USD", "BUY", 0.957, 87.04, 83.33),
            ("XRP-USD", "BUY", 58.24, 1.4307, 83.33),
        ]
        
        count = 0
        for pair, side, qty, price, usd in trades_to_log:
            ledger.log_trade(
                timestamp=f"2026-04-30T21:11:{20+count}Z",
                pair=pair,
                side=side,
                quantity=qty,
                price=price,
                usd_amount=usd,
                status="EXECUTED"
            )
            count += 1
        
        summary = ledger.get_summary()
        assert summary['total_trades'] == 3, "❌ Expected 3 trades"
        assert summary['successful'] == 3, "❌ Expected 3 successful"
        assert abs(summary['total_usd_traded'] - 249.99) < 0.1, "❌ Total USD mismatch"
        
        print(f"✅ Logged {count} trades")
        print(f"✅ Summary: {summary['total_trades']} total, ${summary['total_usd_traded']:.2f} USD")


def test_csv_export():
    """Test CSV export"""
    print("\n" + "="*60)
    print("TEST 5: CSV Export")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        csv_path = os.path.join(tmpdir, 'test_export.csv')
        
        ledger = TransactionLedger(ledger_path)
        
        # Log some trades
        for i in range(3):
            ledger.log_trade(
                timestamp=f"2026-04-30T21:11:{10+i}Z",
                pair="ETH-USD",
                side="BUY",
                quantity=0.03,
                price=2283.23,
                usd_amount=68.50,
                order_id=f"order-{i}",
                status="EXECUTED"
            )
        
        # Export to CSV
        ledger.export_to_csv(csv_path)
        
        assert os.path.exists(csv_path), "❌ CSV file not created"
        print(f"✅ CSV exported to {csv_path}")
        
        # Verify CSV content
        with open(csv_path, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 4, f"❌ Expected 4 lines (header + 3 trades), got {len(lines)}"
        assert 'timestamp' in lines[0], "❌ Header missing timestamp"
        assert 'order_id' in lines[0], "❌ Header missing order_id"
        
        print(f"✅ CSV has {len(lines)-1} trades (+ header)")


def test_reconciliation():
    """Test reconciliation functions"""
    print("\n" + "="*60)
    print("TEST 6: Reconciliation Functions")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        
        # Create and populate ledger
        ledger = TransactionLedger(ledger_path)
        
        # Log trades - some with, some without order IDs
        ledger.log_trade(
            timestamp="2026-04-30T21:11:00Z",
            pair="ETH-USD",
            side="BUY",
            quantity=0.03,
            price=2283.23,
            usd_amount=68.50,
            order_id="order-1",
            status="EXECUTED"
        )
        
        ledger.log_trade(
            timestamp="2026-04-30T21:11:01Z",
            pair="SOL-USD",
            side="BUY",
            quantity=0.95,
            price=87.04,
            usd_amount=82.69,
            status="PENDING"  # No order ID
        )
        
        # Test reconciliation
        reconciler = TransactionReconciler()
        
        # Find untracked
        untracked = reconciler.find_untracked_trades()
        assert len(untracked) == 1, "❌ Expected 1 untracked trade"
        print(f"✅ Found {len(untracked)} untracked trades")
        
        # Add order ID
        trade_id = untracked[0]['trade_id']
        success = reconciler.add_order_id_to_trade(
            trade_id,
            'recovered-order-id',
            'Recovered from Coinbase'
        )
        
        assert success, "❌ Failed to add order ID"
        print("✅ Added order ID via reconciliation")
        
        # Verify
        untracked_after = reconciler.find_untracked_trades()
        assert len(untracked_after) == 0, "❌ Untracked still exists after update"
        print("✅ All trades now have order IDs")


def test_persistence():
    """Test that ledger persists across instances"""
    print("\n" + "="*60)
    print("TEST 7: Persistence Across Instances")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, 'test_ledger.json')
        
        # Create first instance and log trade
        ledger1 = TransactionLedger(ledger_path)
        ledger1.log_trade(
            timestamp="2026-04-30T21:11:00Z",
            pair="BTC-USD",
            side="BUY",
            quantity=0.01,
            price=78000.00,
            usd_amount=780.00,
            order_id="persist-test",
            status="EXECUTED"
        )
        print("✅ Logged trade with first instance")
        
        # Create second instance and read
        ledger2 = TransactionLedger(ledger_path)
        trades = ledger2.get_all_trades()
        
        assert len(trades) == 1, "❌ Trade not persisted"
        assert trades[0]['pair'] == 'BTC-USD', "❌ Data corrupted"
        
        print("✅ Trade persisted and readable by second instance")
        
        summary = ledger2.get_summary()
        assert summary['total_trades'] == 1, "❌ Summary not persisted"
        print(f"✅ Summary persisted: {summary}")


def run_all_tests():
    """Run complete test suite"""
    print("\n\n")
    print("╔" + "="*58 + "╗")
    print("║" + " TRANSACTION LEDGER SYSTEM - FULL TEST SUITE ".center(58) + "║")
    print("╚" + "="*58 + "╝")
    
    tests = [
        ("Ledger Creation", test_ledger_creation),
        ("Trade Logging", test_trade_logging),
        ("Status Updates", test_status_updates),
        ("Batch Logging", test_batch_logging),
        ("CSV Export", test_csv_export),
        ("Reconciliation", test_reconciliation),
        ("Persistence", test_persistence),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ TEST ERROR: {e}")
            failed += 1
    
    print("\n\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total:  {passed + failed}")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
