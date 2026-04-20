#!/usr/bin/env python3
'''Phase 6 Takeover: Manage existing positions + reserve cash.'''
import json, numpy as np, pandas as pd
from phase5_multi_pair import Phase5Harness, load_dotenv  # Base logic
import logging, time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TakeoverHarness(Phase5Harness):
    def __init__(self, takeover_state_path: str):
        super().__init__()
        self.state_path = Path(takeover_state_path)
        self.cash_reserve = 0.0
        self._load_state()
        self.max_pairs = 12
        self.reserve_min_pct = 0.2
        self._universe = self._get_universe()

    def _load_state(self):
        with open(self.state_path) as f:
            state = json.load(f)
        self.cash_reserve = state['cash_reserve']
        self.positions = {p['pair']: p for p in state['positions']}
        self.price_history = state['price_history']
        logger.info(f"Takeover: Cash ${self.cash_reserve} | Positions {len(self.positions)}")

    def _get_universe(self) -> List[str]:
        return ['SOL-USD', 'ADA-USD', 'LINK-USD', 'AVAX-USD']  # Top low-corr

    def _score_candidate(self, cand: str) -> float:
        # Simplified scoring
        sent = self.sentiment_fetcher.get_sentiment(cand)[0]
        corr = 0.4  # Mock low corr
        return 0.4*1.2 + 0.2*sent + 0.2*(1-corr) + 0.1*1.0 + 0.1*1.0  # 1.0 mock liq

    def run_cycle(self):
        super().run_cycle()
        self._rebalance()
        self._expand_if_needed()

    def _rebalance(self):
        var = 0.01  # Mock <0.02 OK
        for pair, pos in list(self.positions.items()):
            pnl_pct = (self.price_wrapper.get_price(pair) - pos['entry_price']) / pos['entry_price']
            hold = 5  # Mock
            signal = 'HOLD'  # Mock Phase 5
            sentiment = 0.1
            if pnl_pct > 0.015 and hold < 20:
                self._pyramid(pair, 0.5)
            elif pnl_pct < -0.01 and hold > 3:
                self._exit(pair)
        if var > 0.02:
            self._reduce(0.2)

    def _pyramid(self, pair, size_mult):
        size = self.cash_reserve * 0.8 * size_mult
        if size > 0:
            self.cash_reserve -= size
            logger.info(f"Pyramid {pair}: +${size}")

    def _exit(self, pair):
        price = self.price_wrapper.get_price(pair)
        pnl_pct = (price - self.positions[pair]['entry_price']) / self.positions[pair]['entry_price']
        self.cash_reserve += self.positions[pair]['size_value'] * (1 + pnl_pct)
        del self.positions[pair]
        logger.info(f"Exit {pair} PnL {pnl_pct:.2%}")

    def _expand_if_needed(self):
        if len(self.positions) < 4 and self.cash_reserve > self.total_capital * 0.2:
            candidates = sorted([(c, self._score_candidate(c)) for c in self._universe], reverse=True)
            if candidates[0][1] > 0.65:
                new_pair = candidates[0][0]
                self._add_pair(new_pair, self.cash_reserve * 0.3)
        
    def _add_pair(self, pair, seed):
        self.positions[pair] = {'entry_price': self.price_wrapper.get_price(pair), 'unreal_pnl_pct': 0.0, 'size_value': seed}
        self.cash_reserve -= seed
        self.price_history[pair] = []  # Init
        logger.info(f"Added {pair} seed ${seed}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--paper', action='store_true')
    parser.add_argument('--hours', type=int, default=24)
    args = parser.parse_args()
    harness = TakeoverHarness('takeover_account.json')
    cycles = args.hours * 2  # 30min cycles
    for c in range(cycles):
        harness.run_cycle()
        if args.paper:
            time.sleep(0.1)  # Fast paper
        else:
            time.sleep(1800)