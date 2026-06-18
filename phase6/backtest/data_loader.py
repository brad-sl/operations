"""
Daily Historical Data Loader for Backtesting

Supports real project JSON files (backtests/data/backtest_historical_ohlcv_*.json)
and falls back to CSV.
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
from pathlib import Path
import json

@dataclass
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

class DailyDataLoader:
    """
    Loads daily OHLCV data for backtesting from real historical files.
    """

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path
        self._cache: Dict[str, pd.DataFrame] = {}

    def load_pair(self, pair: str) -> pd.DataFrame:
        """Load daily data for a single pair. Supports project JSON files + CSV."""
        if pair in self._cache:
            return self._cache[pair]

        # Try project historical JSON first
        symbol = pair.split("-")[0].lower()
        json_path = Path("backtests/data") / f"backtest_historical_ohlcv_{symbol}_2025-04-20_to_2026-04-20.json"
        if json_path.exists():
            with open(json_path) as f:
                raw = json.load(f)
            df = pd.DataFrame(raw)
            df["date"] = pd.to_datetime(df["timestamp"]).dt.date
            df = df.set_index("date")
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            self._cache[pair] = df
            return df

        # Fallback to CSV in data_path
        if self.data_path and (self.data_path / f"{pair}.csv").exists():
            df = pd.read_csv(self.data_path / f"{pair}.csv", parse_dates=["date"])
            df = df.set_index("date")
            self._cache[pair] = df
            return df

        return pd.DataFrame()

    def load_universe(self, pairs: List[str]) -> Dict[str, pd.DataFrame]:
        """Load data for multiple pairs."""
        return {pair: self.load_pair(pair) for pair in pairs}

if __name__ == "__main__":
    loader = DailyDataLoader()
    print("DailyDataLoader initialized with real data support")
