# Crypto Bot Architecture — Canonical Reference

**READ THIS BEFORE TOUCHING ANY CODE.**
This document is the source of truth. Any new script or modification must be consistent with what's documented here.
Last verified: 2026-04-02

---

## 1. Module Map

| File | Purpose | Status | Touch? |
|------|---------|--------|--------|
| `indicators/dynamic_rsi_strategy.py` | Signal engine: regime detection + RSI + sentiment → BUY/SELL/HOLD | ✅ Working | NO — read only |
| `x_sentiment_fetcher.py` | X API sentiment, 4h cache, LunarCrush/CryptoPanic failover scaffold | ✅ Working | NO — read only |
| `config/sentiment_config.json` | Externalized sentiment config (cache hours, providers, calibration) | ✅ Working | Edit only to tune config |
| `coinbase_wrapper.py` | Real Coinbase price + order API | ✅ Working | NO |
| `test_price_wrapper.py` | Snapshot-based prices for testing (PRICE_SOURCE=snapshot) | ✅ Working | NO |
| `test_fixtures/` | Snapshot JSON for deterministic testing | ✅ Present | Add new snapshots only |
| `phase4_trades.db` | SQLite trade log (entry, exit, P&L, strategy) | ✅ Schema OK | Never manually edit |
| `phase4b_run_24h.py` | Phase 4b price logger (NOT a trading engine) | ⚠️ Historical | DO NOT use as template |
| `phase4b_v1.py` | Phase 4b with static RSI, no DynamicRSI import | ⚠️ Broken | DO NOT use |
| `phase4b_smoke_test.py` | Sentiment-only smoke test (overwritten 2026-04-02) | ⚠️ Degraded | Do not rely on |
| `phase4c_multi_pair.py` | **THE NEW HARNESS** — to be written | 🔲 Not yet | Write fresh |

---

## 2. DynamicRSISignalCalculator — Exact API

**Import:**
```python
from indicators.dynamic_rsi_strategy import DynamicRSISignalCalculator, SignalContext
```

**Instantiate once per run (maintains per-pair regime state):**
```python
calc = DynamicRSISignalCalculator()
```

**Call signature (verified 2026-04-02):**
```python
ctx: SignalContext = calc.calculate_signal(
    pair="BTC-USD",
    current_price=67800.0,         # float — live price this cycle
    rsi=32.5,                       # float 0–100 — computed from price history
    sentiment_score=0.3,            # float -1.0 to +1.0 — from XSentimentFetcher
    price_history=[(px, ts), ...],  # List[Tuple[float, datetime]] — rolling window
    candles=[{"close": ...}, ...],  # List[Dict] — OHLCV (may be empty list)
)
```

**SignalContext fields:**
```python
ctx.signal          # "BUY" | "SELL" | "HOLD"
ctx.regime          # Regime("UPTREND"|"DOWNTREND"|"SIDEWAYS")
ctx.thresholds      # RSIThresholds(buy=int, sell=int)
ctx.confidence      # float 0.0–1.0
ctx.weighted_signal # float — the combined RSI+sentiment value
ctx.position_size_multiplier  # 1.2 (uptrend) | 1.0 (sideways) | 0.7 (downtrend)
ctx.price           # float
ctx.rsi             # float
ctx.sentiment_score # float
```

**Regime thresholds (from the module):**
```
UPTREND:   buy < 20, sell > 80   (size mult 1.2x)
DOWNTREND: buy < 40, sell > 60   (size mult 0.7x)
SIDEWAYS:  buy < 30, sell > 70   (size mult 1.0x)
```

**Signal weighting:**
```
weighted = (sentiment_normalized_0_100 * 0.6) + (rsi * 0.4)
```

---

## 3. XSentimentFetcher — Exact API

**Import:**
```python
from x_sentiment_fetcher import XSentimentFetcher
```

**Instantiate (reads cache_hours from config/sentiment_config.json, default 4h):**
```python
fetcher = XSentimentFetcher(cache_dir=str(LOG_DIR))
```

**Call:**
```python
sentiment_score, metadata = fetcher.get_sentiment("BTC-USD")
# sentiment_score: float -1.0 to +1.0
# metadata: dict with source, fetch_time, total_tweets, etc.
```

**Config-driven pair queries (in sentiment_config.json):**
```json
"pair_queries": {
    "BTC-USD":  "(Bitcoin OR BTC) lang:en -is:retweet",
    "XRP-USD":  "(XRP OR Ripple) lang:en -is:retweet",
    "ETH-USD":  "(Ethereum OR ETH) lang:en -is:retweet",
    "DOGE-USD": "(Dogecoin OR DOGE) lang:en -is:retweet",
    "_default": "({symbol}) lang:en -is:retweet"
}
```

---

## 4. Price Wrapper — Exact API

**Production (real Coinbase prices):**
```python
from coinbase_wrapper import CoinbaseWrapper
cb = CoinbaseWrapper(api_key, private_key, passphrase, sandbox=True)
result = cb.get_price("BTC-USD")
price = result["price"]  # float
```

**Test (snapshot prices, deterministic):**
```python
import os; os.environ["PRICE_SOURCE"] = "snapshot"
from test_price_wrapper import get_price_wrapper
wrapper = get_price_wrapper()
result = wrapper.get_price("BTC-USD")
price = result["price"]  # float
```

---

## 5. RSI Calculation — Must Compute from Price History

**Phase 4b bug: RSI was hardcoded at 35.0 for BTC and 65.0 for XRP every cycle.**
**Phase 4c requirement: RSI must be computed from rolling price history.**

Standard 14-period RSI:
```python
def compute_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0  # neutral if not enough data
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)
```

**price_history list for DynamicRSI:** `List[Tuple[float, datetime]]` — newest appended each cycle, keep last 50.

---

## 6. Trade Logging — DB Schema

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    pnl REAL,
    pnl_pct REAL,
    entry_time TEXT,
    exit_time TEXT,
    strategy TEXT,
    sentiment_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Log a closed trade:**
```python
conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
cursor = conn.cursor()
cursor.execute(
    "INSERT INTO trades (pair, entry_price, exit_price, pnl, pnl_pct, "
    "entry_time, exit_time, strategy, sentiment_score) VALUES (?,?,?,?,?,?,?,?,?)",
    (pair, entry_px, exit_px, pnl, pnl_pct, entry_time, exit_time, strategy, sentiment)
)
conn.commit(); conn.close()
```

---

## 7. Phase 4c Config

All runtime parameters live in `config/trading_config.json` (to be created alongside phase4c).
Never hardcode pairs, thresholds, or intervals in the script itself.

```json
{
  "pairs": ["BTC-USD", "XRP-USD", "DOGE-USD", "ETH-USD"],
  "cycle_interval_seconds": 300,
  "rsi_period": 14,
  "price_history_window": 50,
  "min_hold_cycles": 3,
  "stop_loss_pct": -0.02,
  "take_profit_pct": 0.015,
  "daily_loss_cap_usd": 50,
  "paper_capital_usd": 1000
}
```

---

## 8. Rules — What Must Be True Before Any Live Run

- [ ] `python3 -m py_compile phase4c_multi_pair.py` exits 0
- [ ] Snapshot smoke test: `PRICE_SOURCE=snapshot python3 phase4c_multi_pair.py --cycles 20` produces ≥1 closed trade per pair
- [ ] RSI varies per cycle (not static)
- [ ] Regime changes at least once across test run
- [ ] Trade logged correctly to SQLite (check with `sqlite3 phase4_trades.db "SELECT * FROM trades LIMIT 5"`)
- [ ] 30-min live paper run: at least 1 BUY fires, at least 1 exit triggers
- [ ] All above pass → full 24h multi-pair paper run → Go/No-Go decision

---

## 9. Files to Never Modify

- `indicators/dynamic_rsi_strategy.py`
- `coinbase_wrapper.py`
- `test_price_wrapper.py`
- `phase4b_run_24h.py` (historical record)
- `phase4_trades.db` (production data)
