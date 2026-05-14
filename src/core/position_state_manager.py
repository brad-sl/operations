#!/usr/bin/env python3
"""Position State Manager: Persistent tracking + Coinbase balance sync"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

STATE_DIR = '/home/brad/.openclaw/workspace/operations/crypto-bot/state'
STATE_FILE = os.path.join(STATE_DIR, 'position_state.json')

class PositionStateManager:
    def __init__(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.state: Dict[str, Dict[str, Any]] = self._load_state()
        self.sl_pct = 0.02  # Default 2%, overridden by config

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        """Load state from JSON, create if missing."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f'State load failed: {e}')
            return {}

    def _save_state(self):
        """Atomically save state with backup."""
        try:
            backup = STATE_FILE + '.backup'
            with open(backup, 'w') as f:
                json.dump(self.state, f, indent=2)
            os.replace(backup, STATE_FILE)  # Atomic
            os.chmod(STATE_FILE, 0o600)
            logger.debug('State saved')
        except Exception as e:
            logger.error(f'State save failed: {e}')

    def get_position(self, pair: str) -> Optional[Dict[str, Any]]:
        """Get position for pair."""
        return self.state.get(pair)

    def update_position(self, pair: str, entry_price: float, entry_qty: float, sl_order_id: str, sl_price: float, timestamp: str):
        """Record new position post-BUY fill."""
        self.state[pair] = {
            "entry_price": entry_price,
            "entry_qty": entry_qty,
            "sl_order_id": sl_order_id,
            "sl_price": sl_price,
            "entry_time": timestamp
        }
        self._save_state()
        logger.info(f'Position updated: {pair} @ {entry_price}, SL={sl_price}, SL_ID={sl_order_id}')

    def clear_position(self, pair: str):
        """Remove closed position."""
        if pair in self.state:
            del self.state[pair]
            self._save_state()
            logger.info(f'Position cleared: {pair}')

    def validate_all(self, cb_client) -> Dict[str, Any]:
        """Validate all positions against Coinbase balances."""
        report = {"pairs": {}, "mismatches": [], "cleared": []}
        
        for pair in list(self.state.keys()):
            base_asset = pair.split("-")[0]
            pos = self.state[pair]
            
            try:
                # Get actual balance
                balance_info = cb_client.get_account_balance(base_asset)
                actual_qty = float(balance_info.get("available", 0))
                expected_qty = pos.get("entry_qty", 0)
                
                report["pairs"][pair] = {
                    "expected": expected_qty,
                    "actual": actual_qty,
                    "sl_order_id": pos.get("sl_order_id")
                }
                
                # Mismatch detection
                if expected_qty > 0 and actual_qty < 0.0001:
                    logger.warning(f'Ghost position detected: {pair} (expected {expected_qty}, got 0)')
                    report["cleared"].append(pair)
                    self.clear_position(pair)
                elif abs(actual_qty - expected_qty) / expected_qty > 0.01 if expected_qty > 0 else False:
                    logger.warning(f'Position mismatch: {pair} (expected {expected_qty}, got {actual_qty})')
                    report["mismatches"].append({
                        "pair": pair,
                        "expected": expected_qty,
                        "actual": actual_qty
                    })
                    # Auto-correct state
                    pos["entry_qty"] = actual_qty
                    self._save_state()
                    
            except Exception as e:
                logger.error(f'Validation failed for {pair}: {e}')
        
        return report

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active positions."""
        return self.state.copy()
