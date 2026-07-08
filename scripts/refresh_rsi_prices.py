#!/usr/bin/env python3
"""
RSI Price Refresher (15m decoupled) - REAL FULL BASKET IMPLEMENTATION

Replaces the previous mock (which only covered 6 pairs with fake data).

- Loads the authoritative full trading basket from config/trading_config_phase6.json
  (global_settings.pairs preferred; falls back to phase_6_specific.opportunity_pool for completeness).
- Uses the live price history maintained by the runner (data/state/price_history.json via PriceHistoryManager).
- Computes real Wilder's RSI (exact 14-period logic matching phase6/core/phase6_runner.py).
- Writes complete rsi_cache.json (format consumed by coverage tests, scorer fallbacks, reports).
- Persists fresh values to phase6.db rsi_values table (queried by load_latest_sentiment_for_basket and scorer).
- Logs per-pair details + full count ("synced for N pairs").

This ensures downstream (runner rebalance, rebalancer, SignalGenerator, twice-daily intelligence,
dashboards, opportunity scanner, etc.) have real RSI for the *entire* basket.

Upstream dependency: Runner populates price_history.json during live cycles.
Downstream consumers: sentiment_scorer.py (DB + cache), reports, signals.

Real data only. No mocks or placeholders. See docs/RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md for full graph.

Run manually or via hermes rsi-15min-refresher cron.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# P2-01 fix: no hardcoded absolute paths; use canonical paths + load_trading_basket
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # root/scripts location
from phase6.core.paths import PROJECT_ROOT, RSI_CACHE as _RSI_CACHE, PHASE6_DB, load_trading_basket

CONFIG_PATH = PROJECT_ROOT / "config" / "trading_config_phase6.json"
PRICE_HISTORY_PATH = PROJECT_ROOT / "data" / "state" / "price_history.json"
RSI_CACHE_PATH = _RSI_CACHE
DB_PATH = PHASE6_DB

# --- Real RSI calculation (Wilder's, 14-period) ---
# Exact match to the implementation in phase6/core/phase6_runner.py
def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """Wilder's RSI - pure Python, no external deps."""
    if len(prices) < period + 1:
        return []
    deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(round(rsi, 2))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return rsi_values


def calculate_stochastic_rsi(
    prices: List[float], rsi_period: int = 14, k_period: int = 14, d_period: int = 3
) -> tuple[list[float], list[float]]:
    """Pure-Python StochRSI (no numpy). Returns (k_values, d_values)."""
    rsi_values = calculate_rsi(prices, rsi_period)
    if len(rsi_values) < k_period:
        return [], []

    k_values: list[float] = []
    for i in range(k_period - 1, len(rsi_values)):
        window = rsi_values[i - k_period + 1 : i + 1]
        min_r = min(window)
        max_r = max(window)
        if max_r == min_r:
            k = 50.0
        else:
            k = 100.0 * (rsi_values[i] - min_r) / (max_r - min_r)
        k_values.append(round(k, 2))

    d_values: list[float] = []
    for i in range(d_period - 1, len(k_values)):
        d = sum(k_values[i - d_period + 1 : i + 1]) / d_period
        d_values.append(round(d, 2))

    return k_values, d_values


# --- Basket loading (config-driven, full coverage) ---
# P2-01: delegate to central load_trading_basket for single source (avoids dupe fallback logic)
def load_full_basket() -> List[str]:
    try:
        pairs = load_trading_basket()
        if pairs:
            return pairs
    except Exception as e:
        print(f"[WARN] central load_trading_basket failed, falling back: {e}")
    # last resort fallback (should not hit)
    return ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
            "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD"]


# --- PriceHistoryManager (lightweight inline for standalone; mirrors core) ---
class _PriceHistoryManager:
    def __init__(self, persist_path: str):
        self.persist_path = Path(persist_path)
        self.history: Dict[str, List[float]] = {}
        if self.persist_path.exists():
            try:
                data = json.loads(self.persist_path.read_text())
                self.history = data.get("history", {})
            except Exception as e:
                print(f"[WARN] Failed to load price_history: {e}")

    def get_prices(self, pair: str, n: int = None) -> List[float]:
        prices = self.history.get(pair, [])
        if n is None:
            return prices[:]
        return prices[-n:] if n > 0 else []

    def has_enough_data(self, pair: str, min_points: int = 15) -> bool:
        return len(self.history.get(pair, [])) >= min_points


def main():
    print(f"=== RSI Price Refresher (15m decoupled) @ {datetime.utcnow().isoformat()} ===")

    basket = load_full_basket()
    print(f"Full basket loaded from config: {len(basket)} pairs -> {basket}")

    mgr = _PriceHistoryManager(str(PRICE_HISTORY_PATH))

    rsi_entries: Dict[str, Any] = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    db_rows = []

    for pair in basket:
        if not mgr.has_enough_data(pair, 30):  # raised for StochRSI(14,14) safety
            print(f"  {pair}: insufficient history (skipped for RSI/StochRSI)")
            continue

        prices = mgr.get_prices(pair, n=100)  # Longer-term: use up to 100 points (full available history)
        rsi_list = calculate_rsi(prices, period=14)
        if not rsi_list:
            print(f"  {pair}: not enough deltas for RSI (skipped)")
            continue

        rsi_val = rsi_list[-1]
        k_list, d_list = calculate_stochastic_rsi(prices, rsi_period=14, k_period=14, d_period=3)
        stoch_k = k_list[-1] if k_list else None
        stoch_d = d_list[-1] if d_list else None

        candle_count = len(prices)

        rsi_entries[pair] = {
            "rsi": rsi_val,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "timestamp": now_iso,
            "source": "15m_candles_from_history_longer_term",
            "candle_count": candle_count,
            "age_minutes": 0,
            "fresh": True,
        }

        db_rows.append((now_iso, pair, rsi_val, "refresh_15m_long"))

        print(f"  {pair}: fetched {candle_count} candles from price_history, {candle_count} valid closes")
        print(f"    -> RSI={rsi_val} (from {candle_count} closes, Wilder)")
        if stoch_k is not None:
            print(f"    -> StochRSI %K={stoch_k} %D={stoch_d}")

    # Write rsi_cache.json (full basket)
    cache_payload = {
        "timestamp": now_iso,
        "rsi": rsi_entries
    }
    try:
        RSI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RSI_CACHE_PATH, "w") as f:
            json.dump(cache_payload, f, indent=2)
        print(f"Canonical RSI cache written to {RSI_CACHE_PATH}")
    except Exception as e:
        print(f"[ERROR] Failed to write rsi_cache: {e}")

    # Persist to DB (for scorer queries)
    if db_rows:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.executemany(
                "INSERT OR REPLACE INTO rsi_values (ts, pair, value, source) VALUES (?, ?, ?, ?)",
                db_rows
            )
            conn.commit()
            conn.close()
            print(f"DB rsi_values updated for {len(db_rows)} pairs")
        except Exception as e:
            print(f"[ERROR] DB persist failed: {e}")

    synced_count = len(rsi_entries)
    print(f"Live state RSI synced for {synced_count} pairs")
    print(f"Refresher complete. Calls: {synced_count}. Pairs updated: {synced_count}. Errors/skipped: {len(basket) - synced_count}")

    if synced_count == len(basket):
        print("SUCCESS: Full basket RSI coverage achieved (real data from runner price history).")
    else:
        print("WARNING: Partial coverage - some pairs lacked sufficient price history in runner's price_history.json.")


if __name__ == "__main__":
    main()