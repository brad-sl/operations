"""
Phase 6 State Persistence Manager - v6.01

Manages durable state persistence for Phase 6 trading bot.
- Survives OpenClaw/process restarts
- Atomic writes prevent corruption on crash
- JSON schema validation
- Thread-safe for concurrent access
"""

import json
import logging
import os
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field


__version__ = "6.01"


# JSON Schema for state validation
PHASE6_STATE_SCHEMA = {
    "version": str,
    "created_at": str,
    "last_updated": str,
    "liquidation_history": list,
    "last_pain_score_calc": dict,
    "positions_monitored": list,
    "trading_cycles": int,
    "total_liquidations": int,
    "session_start": str,
    "config_hash": (str, type(None)),
}


@dataclass
class LiquidationEvent:
    """Represents a liquidation event."""
    timestamp: str
    pair: str
    reason: str
    price: float
    quantity: float
    pnl: Optional[float] = None
    order_id: Optional[str] = None


@dataclass
class PainScoreRecord:
    """Represents a PAIN_SCORE calculation record."""
    timestamp: str
    score: float
    pairs: List[str] = field(default_factory=list)
    correlation_matrix: Optional[Dict[str, float]] = None
    rsi_values: Optional[Dict[str, float]] = None


class StateManager:
    """
    Manages Phase 6 persistent state with atomic writes and validation.
    
    Features:
    - Atomic writes (temp file + rename) prevent corruption
    - JSON schema validation on read/write
    - Thread-safe state access
    - Automatic state migration on version change
    """
    
    def __init__(self, state_dir: str = None, version: str = __version__):
        """
        Initialize StateManager.
        
        Args:
            state_dir: Directory for state files (default: ./state)
            version: Version string for state (default: current module version)
        """
        if state_dir is None:
            state_dir = os.path.join(
                os.path.dirname(__file__), 
                'state'
            )
        
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.state_dir / "phase6_state.json"
        self.version = version
        self.lock = threading.RLock()
        
        self.logger = logging.getLogger(__name__)
        
        # Load or initialize state
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from disk with validation."""
        with self.lock:
            if not self.state_file.exists():
                return self._create_empty_state()
            
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                # Validate schema
                self._validate_schema(state)
                
                # Check version mismatch
                if state.get('version') != self.version:
                    self.logger.warning(
                        f"State version mismatch: {state.get('version')} vs {self.version}. "
                        f"Migrating state."
                    )
                    state = self._migrate_state(state)
                
                self.logger.debug(f"✅ State loaded from {self.state_file}")
                return state
                
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load state: {e}. Creating new state.")
                return self._create_empty_state()
    
    def _create_empty_state(self) -> Dict[str, Any]:
        """Create a fresh empty state."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        return {
            "version": self.version,
            "created_at": now,
            "last_updated": now,
            "liquidation_history": [],
            "last_pain_score_calc": {
                "timestamp": None,
                "value": None,
                "pairs_monitored": []
            },
            "positions_monitored": [],
            "trading_cycles": 0,
            "total_liquidations": 0,
            "session_start": now,
            "config_hash": None,
        }
    
    def _validate_schema(self, state: Dict[str, Any]) -> bool:
        """Validate state against schema."""
        for key, expected_type in PHASE6_STATE_SCHEMA.items():
            if key not in state:
                raise ValueError(f"Missing required state key: {key}")
            
            value = state[key]
            if isinstance(expected_type, tuple):
                # Allow multiple types (e.g., str or None)
                if not any(isinstance(value, t) for t in expected_type):
                    raise TypeError(
                        f"State[{key}] type mismatch: got {type(value)}, "
                        f"expected {expected_type}"
                    )
            else:
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"State[{key}] type mismatch: got {type(value)}, "
                        f"expected {expected_type}"
                    )
        
        return True
    
    def _migrate_state(self, old_state: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate state from older version to current version."""
        # For v6.01, no migration needed yet; just ensure all fields exist
        new_state = self._create_empty_state()
        
        # Preserve liquidation history and cycles
        new_state['liquidation_history'] = old_state.get('liquidation_history', [])
        new_state['trading_cycles'] = old_state.get('trading_cycles', 0)
        new_state['total_liquidations'] = old_state.get('total_liquidations', 0)
        
        if old_state.get('created_at'):
            new_state['created_at'] = old_state['created_at']
        
        self.logger.info(f"State migrated to v{self.version}")
        return new_state
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state (thread-safe copy)."""
        with self.lock:
            return dict(self.state)
    
    def update_state(self, updates: Dict[str, Any], atomic: bool = True) -> bool:
        """
        Update state with atomic writes to prevent corruption.
        
        Args:
            updates: Dict of fields to update
            atomic: Use temp file + rename for safety (default True)
        
        Returns:
            True if successful, False if validation failed
        """
        with self.lock:
            try:
                # Merge updates into state
                self.state.update(updates)
                self.state['last_updated'] = (
                    datetime.now(timezone.utc).isoformat() + "Z"
                )
                
                # Validate before writing
                self._validate_schema(self.state)
                
                # Write atomically
                if atomic:
                    self._write_atomic(self.state)
                else:
                    self._write_direct(self.state)
                
                self.logger.debug(f"State updated: {list(updates.keys())}")
                return True
                
            except (TypeError, ValueError) as e:
                self.logger.error(f"State validation failed: {e}")
                return False
            except IOError as e:
                self.logger.error(f"Failed to write state: {e}")
                return False
    
    def _write_atomic(self, state: Dict[str, Any]) -> None:
        """Write state atomically using temp file + rename."""
        temp_file = self.state_file.with_suffix('.json.tmp')
        
        try:
            # Write to temp file
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            # Atomic rename (overwrites on most filesystems)
            temp_file.replace(self.state_file)
            
        finally:
            # Clean up temp file if still exists
            if temp_file.exists():
                temp_file.unlink()
    
    def _write_direct(self, state: Dict[str, Any]) -> None:
        """Write state directly (less safe but faster)."""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def add_liquidation_event(
        self,
        pair: str,
        reason: str,
        price: float,
        quantity: float,
        pnl: Optional[float] = None,
        order_id: Optional[str] = None
    ) -> bool:
        """
        Record a liquidation event.
        
        Args:
            pair: Trading pair
            reason: Why liquidation happened
            price: Execution price
            quantity: Amount liquidated
            pnl: Profit/loss if known
            order_id: Associated order ID
        
        Returns:
            True if successful
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "pair": pair,
            "reason": reason,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "order_id": order_id,
        }
        
        history = self.state.get('liquidation_history', [])
        history.append(event)
        
        total = self.state.get('total_liquidations', 0)
        
        return self.update_state({
            'liquidation_history': history,
            'total_liquidations': total + 1,
        })
    
    def update_pain_score(
        self,
        score: float,
        pairs: List[str],
        correlation_matrix: Optional[Dict[str, float]] = None,
        rsi_values: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Record PAIN_SCORE calculation.
        
        Args:
            score: Calculated PAIN_SCORE
            pairs: Pairs included in calculation
            correlation_matrix: Correlation data
            rsi_values: RSI values by pair
        
        Returns:
            True if successful
        """
        return self.update_state({
            'last_pain_score_calc': {
                'timestamp': datetime.now(timezone.utc).isoformat() + "Z",
                'value': score,
                'pairs_monitored': pairs,
                'correlation_matrix': correlation_matrix,
                'rsi_values': rsi_values,
            }
        })
    
    def update_positions(self, positions: List[Dict[str, Any]]) -> bool:
        """Update monitored positions list."""
        return self.update_state({
            'positions_monitored': positions
        })
    
    def increment_cycle_count(self) -> bool:
        """Increment trading cycle counter."""
        count = self.state.get('trading_cycles', 0)
        return self.update_state({'trading_cycles': count + 1})
    
    def set_config_hash(self, config_dict: Dict[str, Any]) -> bool:
        """
        Set config hash for change detection.
        
        Args:
            config_dict: Configuration to hash
        
        Returns:
            True if successful
        """
        config_str = json.dumps(config_dict, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()
        return self.update_state({'config_hash': config_hash})
    
    def get_config_hash(self) -> Optional[str]:
        """Get current config hash."""
        return self.state.get('config_hash')
    
    def get_liquidation_history(self) -> List[Dict[str, Any]]:
        """Get all liquidation events."""
        return self.state.get('liquidation_history', [])
    
    def get_pain_score_record(self) -> Optional[Dict[str, Any]]:
        """Get last PAIN_SCORE calculation."""
        record = self.state.get('last_pain_score_calc', {})
        if record.get('timestamp'):
            return record
        return None
    
    def clear_session(self) -> bool:
        """Clear session data (for new trading day)."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        return self.update_state({
            'trading_cycles': 0,
            'positions_monitored': [],
            'session_start': now,
        })
    
    def export_snapshot(self) -> str:
        """Export current state as JSON string."""
        with self.lock:
            return json.dumps(self.state, indent=2)
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"StateManager(v{self.version}, "
            f"cycles={self.state.get('trading_cycles', 0)}, "
            f"liquidations={self.state.get('total_liquidations', 0)})"
        )


if __name__ == '__main__':
    # Simple test
    logging.basicConfig(level=logging.DEBUG)
    
    sm = StateManager()
    print(f"✅ StateManager initialized: {sm}")
    
    # Test liquidation event
    sm.add_liquidation_event(
        pair="BTC-USD",
        reason="PAIN_SCORE > 25",
        price=45000.0,
        quantity=0.1,
        pnl=150.0
    )
    
    # Test PAIN_SCORE
    sm.update_pain_score(
        score=28.5,
        pairs=["BTC-USD", "ETH-USD"],
        rsi_values={"BTC-USD": 65.2, "ETH-USD": 72.1}
    )
    
    # Increment cycle
    sm.increment_cycle_count()
    
    print(f"\n✅ State after operations:\n{sm.export_snapshot()}")
