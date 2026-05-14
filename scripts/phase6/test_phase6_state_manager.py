"""
Unit tests for Phase 6 StateManager

Tests:
- Schema validation
- Atomic writes
- State persistence
- Thread safety (basic)
- Liquidation event tracking
- PAIN_SCORE updates
"""

import unittest
import tempfile
import json
import os
import time
import threading
from pathlib import Path

from phase6_state_manager import StateManager, PHASE6_STATE_SCHEMA


class TestStateManager(unittest.TestCase):
    """Test Phase 6 StateManager functionality."""
    
    def setUp(self):
        """Create temporary state directory for tests."""
        self.test_dir = tempfile.mkdtemp()
        self.state_manager = StateManager(state_dir=self.test_dir)
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_initialization(self):
        """Test StateManager initializes with empty state."""
        state = self.state_manager.get_state()
        self.assertEqual(state['version'], "6.01")
        self.assertEqual(state['trading_cycles'], 0)
        self.assertEqual(state['total_liquidations'], 0)
        self.assertEqual(state['liquidation_history'], [])
    
    def test_state_file_created(self):
        """Test state file is created on disk."""
        state_file = Path(self.test_dir) / "phase6_state.json"
        self.assertTrue(state_file.exists())
    
    def test_schema_validation(self):
        """Test state schema validation."""
        state = self.state_manager.get_state()
        # Validate all required keys exist
        for key in PHASE6_STATE_SCHEMA.keys():
            self.assertIn(key, state)
    
    def test_add_liquidation_event(self):
        """Test adding liquidation event."""
        result = self.state_manager.add_liquidation_event(
            pair="BTC-USD",
            reason="PAIN_SCORE > 25",
            price=45000.0,
            quantity=0.1,
            pnl=150.0,
            order_id="order123"
        )
        
        self.assertTrue(result)
        state = self.state_manager.get_state()
        self.assertEqual(len(state['liquidation_history']), 1)
        self.assertEqual(state['total_liquidations'], 1)
        
        event = state['liquidation_history'][0]
        self.assertEqual(event['pair'], "BTC-USD")
        self.assertEqual(event['reason'], "PAIN_SCORE > 25")
        self.assertEqual(event['price'], 45000.0)
        self.assertEqual(event['pnl'], 150.0)
    
    def test_update_pain_score(self):
        """Test updating PAIN_SCORE record."""
        result = self.state_manager.update_pain_score(
            score=28.5,
            pairs=["BTC-USD", "ETH-USD"],
            rsi_values={"BTC-USD": 65.2, "ETH-USD": 72.1}
        )
        
        self.assertTrue(result)
        state = self.state_manager.get_state()
        pain_record = state['last_pain_score_calc']
        
        self.assertEqual(pain_record['value'], 28.5)
        self.assertEqual(len(pain_record['pairs_monitored']), 2)
        self.assertIsNotNone(pain_record['timestamp'])
        self.assertEqual(pain_record['rsi_values']['BTC-USD'], 65.2)
    
    def test_increment_cycle_count(self):
        """Test cycle counter increment."""
        for i in range(5):
            self.state_manager.increment_cycle_count()
        
        state = self.state_manager.get_state()
        self.assertEqual(state['trading_cycles'], 5)
    
    def test_persistence_reload(self):
        """Test state persists after creating new manager."""
        # Add events with first manager
        self.state_manager.add_liquidation_event(
            pair="BTC-USD",
            reason="Test",
            price=40000.0,
            quantity=0.1
        )
        self.state_manager.increment_cycle_count()
        
        # Create new manager pointing to same directory
        state_manager2 = StateManager(state_dir=self.test_dir)
        state = state_manager2.get_state()
        
        # Verify persistence
        self.assertEqual(state['total_liquidations'], 1)
        self.assertEqual(state['trading_cycles'], 1)
        self.assertEqual(len(state['liquidation_history']), 1)
    
    def test_atomic_write_safety(self):
        """Test atomic writes don't corrupt state."""
        # Add multiple events rapidly
        for i in range(10):
            self.state_manager.add_liquidation_event(
                pair=f"PAIR-{i}",
                reason="Test",
                price=float(i * 1000),
                quantity=0.1
            )
        
        # Verify all events persisted correctly
        state = self.state_manager.get_state()
        self.assertEqual(len(state['liquidation_history']), 10)
        self.assertEqual(state['total_liquidations'], 10)
        
        # Verify file is valid JSON
        state_file = Path(self.test_dir) / "phase6_state.json"
        with open(state_file, 'r') as f:
            loaded = json.load(f)
        self.assertEqual(len(loaded['liquidation_history']), 10)
    
    def test_config_hash(self):
        """Test config hash tracking."""
        config = {'deploy_pct': 0.80, 'reserve_pct': 0.20}
        self.state_manager.set_config_hash(config)
        
        state = self.state_manager.get_state()
        self.assertIsNotNone(state['config_hash'])
        
        # Verify same config produces same hash
        hash1 = state['config_hash']
        hash2 = self.state_manager.state.get('config_hash')
        self.assertEqual(hash1, hash2)
    
    def test_update_positions(self):
        """Test updating positions list."""
        positions = [
            {'pair': 'BTC-USD', 'qty': 0.5, 'entry': 40000},
            {'pair': 'ETH-USD', 'qty': 2.0, 'entry': 2500}
        ]
        
        result = self.state_manager.update_positions(positions)
        self.assertTrue(result)
        
        state = self.state_manager.get_state()
        self.assertEqual(len(state['positions_monitored']), 2)
    
    def test_invalid_state_update_rejected(self):
        """Test that invalid state updates are rejected."""
        # Try to update with wrong type
        result = self.state_manager.update_state({
            'total_liquidations': "not_an_int"  # Should be int
        })
        
        # Should fail validation
        self.assertFalse(result)
        
        # Original state should be unchanged
        state = self.state_manager.get_state()
        self.assertIsInstance(state['total_liquidations'], int)
    
    def test_thread_safety_basic(self):
        """Test basic thread safety of concurrent updates."""
        def add_events(n):
            for i in range(n):
                self.state_manager.add_liquidation_event(
                    pair=f"PAIR-{i}",
                    reason="Thread test",
                    price=1000.0,
                    quantity=0.1
                )
        
        # Spawn threads
        threads = [
            threading.Thread(target=add_events, args=(5,)),
            threading.Thread(target=add_events, args=(5,)),
            threading.Thread(target=add_events, args=(5,))
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify all events recorded (15 total)
        state = self.state_manager.get_state()
        self.assertEqual(state['total_liquidations'], 15)
        self.assertEqual(len(state['liquidation_history']), 15)
    
    def test_clear_session(self):
        """Test session clearing."""
        # Add some data
        self.state_manager.increment_cycle_count()
        self.state_manager.add_liquidation_event(
            pair="BTC-USD",
            reason="Test",
            price=40000.0,
            quantity=0.1
        )
        
        # Clear session
        result = self.state_manager.clear_session()
        self.assertTrue(result)
        
        state = self.state_manager.get_state()
        self.assertEqual(state['trading_cycles'], 0)
        self.assertEqual(len(state['positions_monitored']), 0)
        # Note: liquidation_history NOT cleared, only session data
        self.assertEqual(state['total_liquidations'], 1)  # Still tracked
    
    def test_export_snapshot(self):
        """Test exporting state as JSON string."""
        self.state_manager.add_liquidation_event(
            pair="BTC-USD",
            reason="Test",
            price=40000.0,
            quantity=0.1
        )
        
        snapshot = self.state_manager.export_snapshot()
        
        # Should be valid JSON
        parsed = json.loads(snapshot)
        self.assertEqual(len(parsed['liquidation_history']), 1)
        self.assertIn('version', parsed)
    
    def test_get_liquidation_history(self):
        """Test retrieving liquidation history."""
        # Add multiple events
        for i in range(3):
            self.state_manager.add_liquidation_event(
                pair=f"PAIR-{i}",
                reason="Test",
                price=float(i * 1000),
                quantity=0.1
            )
        
        history = self.state_manager.get_liquidation_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['pair'], "PAIR-0")
        self.assertEqual(history[2]['pair'], "PAIR-2")
    
    def test_get_pain_score_record(self):
        """Test retrieving PAIN_SCORE record."""
        # Initially None
        record = self.state_manager.get_pain_score_record()
        self.assertIsNone(record)
        
        # After update
        self.state_manager.update_pain_score(score=25.0, pairs=['BTC-USD'])
        record = self.state_manager.get_pain_score_record()
        
        self.assertIsNotNone(record)
        self.assertEqual(record['value'], 25.0)
        self.assertIn('timestamp', record)


class TestStateManagerVersioning(unittest.TestCase):
    """Test state versioning and migration."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_version_mismatch_migration(self):
        """Test state migrates when version mismatches."""
        # Create state with old version
        state_file = Path(self.test_dir) / "phase6_state.json"
        old_state = {
            'version': '6.0',
            'created_at': '2026-04-29T00:00:00Z',
            'last_updated': '2026-04-29T00:00:00Z',
            'liquidation_history': [{'pair': 'BTC-USD', 'reason': 'Old'}],
            'last_pain_score_calc': {'timestamp': None, 'value': None, 'pairs_monitored': []},
            'positions_monitored': [],
            'trading_cycles': 5,
            'total_liquidations': 1,
            'session_start': '2026-04-29T00:00:00Z',
            'config_hash': None,
        }
        
        with open(state_file, 'w') as f:
            json.dump(old_state, f)
        
        # Load with new manager (version 6.01)
        sm = StateManager(state_dir=self.test_dir, version='6.01')
        state = sm.get_state()
        
        # Should migrate
        self.assertEqual(state['version'], '6.01')
        self.assertEqual(state['total_liquidations'], 1)  # Preserved
        self.assertEqual(state['trading_cycles'], 5)  # Preserved
        self.assertEqual(len(state['liquidation_history']), 1)  # Preserved


if __name__ == '__main__':
    unittest.main()
