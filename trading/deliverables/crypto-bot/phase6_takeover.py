#!/usr/bin/env python3
'''Phase 6 Takeover: Manage existing positions + reserve cash.'''
import os
import sys
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Import from Phase 5 to inherit base logic
from phase5_multi_pair import Phase5Harness
from dotenv import load_dotenv

class TakeoverHarness(Phase5Harness):
    def __init__(self, takeover_state_path=None):
        """
        Initialize Phase 6 Takeover Harness
        Extends Phase 5 Harness with advanced position management
        """
        # Initialize base Phase 5 harness first
        super().__init__()
        
        # Takeover-specific initialization
        self.cash_reserve = self.total_capital * 0.2  # 20% reserve
        self.max_pairs = 12  # Maximum number of pairs
        
        # State management
        self.state_path = takeover_state_path or os.path.join(
            os.path.dirname(__file__), 
            'takeover_account.json'
        )
        
        # Additional universe for expansion
        self._universe = self._get_universe()
        
        # Logging
        self.logger.info("Phase 6 Takeover Harness Initialized")
    
    def _get_universe(self) -> List[str]:
        """
        Define expanded trading universe
        Low correlation pairs with good market characteristics
        """
        return [
            'SOL-USD', 'ADA-USD', 'LINK-USD', 'AVAX-USD', 
            'DOT-USD', 'NEAR-USD', 'ATOM-USD', 'UNI-USD'
        ]
    
    def _load_state(self):
        """
        Load existing trading state
        Creates new state if no previous state exists
        """
        try:
            with open(self.state_path, 'r') as f:
                state = json.load(f)
                self.cash_reserve = state.get('cash_reserve', self.total_capital * 0.2)
                self.positions = state.get('positions', {})
        except FileNotFoundError:
            # Initialize default state
            self.positions = {}
        
        self.logger.info(f"Loaded state: Cash ${self.cash_reserve:.2f}, Positions: {len(self.positions)}")
    
    def _save_state(self):
        """Save current trading state"""
        state = {
            'timestamp': datetime.now().isoformat(),
            'cash_reserve': self.cash_reserve,
            'positions': self.positions
        }
        
        with open(self.state_path, 'w') as f:
            json.dump(state, f, indent=2)
        
        self.logger.info("Trading state saved")
    
    def _score_candidate(self, candidate: str) -> float:
        """
        Advanced candidate scoring for pair expansion
        Considers multiple factors for pair selection
        """
        # Mock implementation with multiple scoring factors
        try:
            price = self.price_wrapper.get_price(candidate)
            sentiment = self._get_sentiment(candidate)
            
            # Scoring components
            price_factor = min(max(1 - (price / 10000), 0.1), 1.0)
            sentiment_factor = (sentiment + 1) / 2  # Normalize to 0-1
            volume_mock = np.random.uniform(0.5, 1.0)  # Mock volume indicator
            correlation_mock = np.random.uniform(0.1, 0.5)  # Mock low correlation
            
            # Weighted scoring
            score = (
                0.3 * price_factor + 
                0.2 * sentiment_factor + 
                0.2 * volume_mock + 
                0.3 * (1 - correlation_mock)
            )
            
            return score
        except Exception as e:
            self.logger.warning(f"Scoring error for {candidate}: {e}")
            return 0.0
    
    def run_cycle(self):
        """
        Execute a single trading cycle with advanced logic
        Manages existing positions and potential expansions
        """
        self._load_state()
        
        # Rebalance existing positions
        self._rebalance_positions()
        
        # Expand if needed and capital allows
        self._expand_portfolio()
        
        # Save state after cycle
        self._save_state()
    
    def _rebalance_positions(self):
        """
        Advanced position rebalancing
        Adjusts existing positions based on performance
        """
        for pair, position in list(self.positions.items()):
            current_price = self.price_wrapper.get_price(pair)
            pnl_pct = (current_price - position['entry_price']) / position['entry_price']
            
            # Dynamic position management
            if abs(pnl_pct) > 0.05:  # 5% threshold
                if pnl_pct > 0:
                    # Take partial profits
                    profit = position['size'] * 0.2
                    self.cash_reserve += profit
                    position['size'] -= profit
                    self.logger.info(f"Partial profit taken on {pair}: ${profit:.2f}")
                else:
                    # Cut losses
                    if pnl_pct < -0.02:  # 2% stop loss
                        self.cash_reserve += position['size']
                        del self.positions[pair]
                        self.logger.warning(f"Position closed due to loss on {pair}")
    
    def _expand_portfolio(self):
        """
        Intelligent portfolio expansion strategy
        """
        if len(self.positions) < 6 and self.cash_reserve > self.total_capital * 0.2:
            # Score potential candidates
            candidates = [
                (pair, self._score_candidate(pair)) 
                for pair in self._universe 
                if pair not in self.positions
            ]
            
            # Sort and select top candidates
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            for pair, score in candidates[:2]:  # Limit to 2 new pairs per cycle
                if score > 0.6 and len(self.positions) < 6:
                    self._add_position(pair)
    
    def _add_position(self, pair):
        """
        Add a new trading position
        """
        # Allocate capital
        position_size = min(
            self.cash_reserve * 0.3,  # 30% of remaining cash
            self.total_capital * 0.2  # Max 20% of total capital
        )
        
        current_price = self.price_wrapper.get_price(pair)
        
        self.positions[pair] = {
            'entry_price': current_price,
            'size': position_size,
            'entry_timestamp': datetime.now().isoformat()
        }
        
        self.cash_reserve -= position_size
        
        self.logger.info(f"Added new position: {pair} @ ${current_price:.4f}, Size: ${position_size:.2f}")

def main():
    """Entry point for Phase 6 Takeover"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 6 Trading Bot Takeover")
    parser.add_argument("--paper", action="store_true", help="Run in paper trading mode")
    parser.add_argument("--hours", type=int, default=24, help="Trading duration in hours")
    args = parser.parse_args()
    
    harness = TakeoverHarness()
    cycles = args.hours * 2  # 30-minute cycles
    
    for _ in range(cycles):
        harness.run_cycle()

if __name__ == '__main__':
    main()