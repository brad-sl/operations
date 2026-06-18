"""
Backtest Engine – Phase 6 Volatile Pair Expansion Comparison

Real data version for ROI comparison between default basket and expansion.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import date
import logging

from phase6.backtest.pair_selector import PairCandidate, select_new_pairs

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    start_date: date
    end_date: date
    initial_capital: float = 1000.0
    enable_pair_expansion: bool = False
    candidate_universe: List[str] = field(default_factory=list)
    rebalance_frequency_days: int = 7
    rebalance_cap_usd: float = 200.0


@dataclass
class Position:
    pair: str
    amount: float
    entry_price: float
    entry_date: date


@dataclass
class BacktestResult:
    config: BacktestConfig
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    avg_pairs_held: float
    rebalance_count: int
    equity_curve: List[float] = field(default_factory=list)
    trades: List[dict] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.positions: Dict[str, Position] = {}
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.rebalance_count = 0

    def run(self) -> BacktestResult:
        """Run daily simulation with real prices."""
        logger.info(f"Starting backtest | Expansion={self.config.enable_pair_expansion}")

        from phase6.backtest.data_loader import DailyDataLoader
        loader = DailyDataLoader()
        price_data = loader.load_universe(
            list(set((self.config.candidate_universe or []) +
                     ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]))
        )

        current_date = self.config.start_date
        equity = self.config.initial_capital
        self.equity_curve = [equity]
        cash = self.config.initial_capital

        # Seed initial basket
        default_pairs = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
        alloc_each = self.config.initial_capital * 0.18
        day_key = current_date
        for pair in default_pairs:
            df = price_data.get(pair)
            if df is not None and day_key in df.index:
                close = float(df.loc[day_key, "close"])
                if close > 0:
                    amount = alloc_each / close
                    self.positions[pair] = Position(pair, amount, close, current_date)
                    cash -= alloc_each

        while current_date <= self.config.end_date:
            day_key = current_date

            # Mark portfolio to market
            portfolio_value = cash
            for pos in list(self.positions.values()):
                df = price_data.get(pos.pair)
                if df is not None and day_key in df.index:
                    close = float(df.loc[day_key, "close"])
                    portfolio_value += pos.amount * close
                else:
                    portfolio_value += pos.amount * pos.entry_price
            equity = portfolio_value
            self.equity_curve.append(equity)

            # Rebalance / expansion
            if (current_date - self.config.start_date).days % self.config.rebalance_frequency_days == 0:
                self.rebalance_count += 1

                if self.config.enable_pair_expansion and self.config.candidate_universe:
                    candidates = [
                        PairCandidate(p, volatility_score=0.78, sentiment=0.28, rsi=47,
                                      correlation_with_holdings=0.35, segment="Layer1")
                        for p in self.config.candidate_universe
                    ]
                    new_pairs = select_new_pairs(
                        candidates, list(self.positions.keys()), [], max_new=1
                    )
                    if new_pairs:
                        pair = new_pairs[0]
                        df = price_data.get(pair)
                        if df is not None and day_key in df.index:
                            close = float(df.loc[day_key, "close"])
                            alloc = min(self.config.rebalance_cap_usd, cash * 0.35)
                            if alloc > 20 and close > 0:
                                amount = alloc / close
                                self.positions[pair] = Position(pair, amount, close, current_date)
                                cash -= alloc
                                self.trades.append({"date": current_date, "action": "ADD", "pair": pair, "usd": alloc})

            current_date = current_date.fromordinal(current_date.toordinal() + 1)

        final_equity = self.equity_curve[-1]
        total_return = (final_equity / self.config.initial_capital - 1) * 100

        result = BacktestResult(
            config=self.config,
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_return, 2),
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            total_trades=len(self.trades),
            avg_pairs_held=len(self.positions),
            rebalance_count=self.rebalance_count,
            equity_curve=self.equity_curve,
            trades=self.trades
        )
        logger.info(f"Backtest complete | Final Equity=${final_equity:.2f} | Return={total_return:.1f}%")
        return result
