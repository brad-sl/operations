# Phase 5 — Functional Specification
**Version:** 1.0 | **Status:** APPROVED | **Created:** 2026-04-06

---

## 1. OVERVIEW

Phase 5 replaces Phase 4d's DynamicRSI threshold with **StochRSI crossover detection** and **adaptive 2×ATR stops**, achieving +12.1% Sharpe improvement in backtesting.

| Aspect | Phase 4d | Phase 5 |
|--------|----------|--------|
| **Signal** | RSI threshold (30/70) | StochRSI %K > %D crossover |
| **Entry** | RSI below threshold | Oversold crossover (StochRSI < 0.2) |
| **Stop Loss** | Fixed -2% | Adaptive 2×ATR (1.5-3% typical) |
| **Confidence** | Medium | Higher (fewer false signals) |
| **Backtest Sharpe** | 1.82 | 2.04 (+12.1%) |

---

## 2. ARCHITECTURE

```
Coinbase Exchange API
    ↓ (1h OHLCV)
Price Buffer (50-candle window)
    ↓
StochRSI Calculator (14,3,3)
    ↓ (Signal: %K, %D, StochRSI value)
Sentiment Fetcher (X API, 4h cache)
    ↓ (Optional confidence boost)
Entry Signal Detector
    ↓ (BUY if %K > %D AND StochRSI < 0.2)
Trade Executor (per pair)
    ↓ (Position tracking)
Exit Logic (TP +5% OR 2×ATR SL)
    ↓
SQLite Trade Log (phase4_trades.db)
    ↓
Dashboard HTTP Server (http://192.168.0.91:8501)
```

---

## 3. SIGNAL GENERATION

### 3.1 StochRSI Calculation (14,3,3)

**Inputs:**
- Closing prices (50-candle rolling window minimum)
- RSI period: 14
- K smoothing period: 3
- D smoothing period: 3

**Formula:**

```
RSI(14) = 100 - [100 / (1 + (avg_gains / avg_losses))]

StochRSI %K = (RSI - min_RSI_14) / (max_RSI_14 - min_RSI_14) × 100
             (where min/max are over last 14 RSI values)

%D = SMA(%K, 3)
```

**Implementation:**
```python
def compute_stochrsi(prices, rsi_period=14, k_smooth=3, d_smooth=3):
    """Return (k_value, d_value, raw_stochrsi)"""
    # See indicators/stochrsi_strategy.py
```

**Output:** 
- `%K`: 0-100 (current StochRSI momentum)
- `%D`: 0-100 (smoothed baseline)
- Confidence score based on convergence

---

### 3.2 Entry Signal

**BUY Entry Condition:**
```
IF %K > %D
   AND StochRSI < 0.2 (oversold)
   AND no_existing_position_for_pair
   THEN signal = BUY
```

**Optional Sentiment Filter (60/40 weighting):**
```
weighted_signal = 0.6 × (StochRSI normalized) + 0.4 × (sentiment)
IF weighted_signal > threshold (0.5)
   THEN increase confidence
```

**Signal Confidence Levels:**
- **HIGH (0.8-1.0):** Crossover + oversold + positive sentiment
- **MEDIUM (0.5-0.8):** Crossover + oversold, no sentiment
- **LOW (0.2-0.5):** Threshold near but not confirming

**Log all signals:**
```json
{
  "pair": "BTC-USD",
  "signal_type": "BUY",
  "k_value": 15.3,
  "d_value": 22.1,
  "stochrsi": 0.153,
  "sentiment": 0.45,
  "confidence": 0.78,
  "timestamp": "2026-04-06T19:30:00Z"
}
```

---

## 4. TRADE EXECUTION

### 4.1 Entry

**Action:** LONG entry (buy at market)

**Constraints:**
- 1 position per pair maximum
- Minimum hold: 3 cycles (15 minutes)
- Capital per trade: Auto-calculated from $1K total / 4 pairs = $250 initial

**Logging:**
```json
{
  "trade_id": "uuid",
  "pair": "BTC-USD",
  "entry_price": 68934.82,
  "entry_time": "2026-04-06T19:30:00Z",
  "entry_size": "quantity_in_usd",
  "signal_confidence": 0.78,
  "strategy": "phase5_stochrsi"
}
```

---

### 4.2 Exit Logic

#### TP Exit (Take Profit)
```
IF price >= entry_price × (1 + 0.05)  // +5%
   THEN close_position()
   REASON = "TP"
```

#### SL Exit (Stop Loss — Adaptive 2×ATR)
```
ATR(14) = Average True Range (14-period)

stop_loss_pct = -(2 × ATR / entry_price)
// Bounds: -2% min, -5% max

IF price <= entry_price × (1 + stop_loss_pct)
   THEN close_position()
   REASON = "SL"
```

**ATR Calculation:**
```python
def compute_atr(df, period=14):
    """True Range: max(h-l, |h-prev_c|, |l-prev_c|)"""
    df['tr'] = np.maximum(
        df['h'] - df['l'],
        np.maximum(abs(df['h'] - df['c'].shift(1)), 
                   abs(df['l'] - df['c'].shift(1)))
    )
    df['atr'] = df['tr'].rolling(period).mean()
    return df['atr'].iloc[-1]
```

**Exit Logging:**
```json
{
  "trade_id": "uuid",
  "exit_price": 72385.14,
  "exit_time": "2026-04-06T20:15:00Z",
  "exit_reason": "TP",
  "pnl": 3450.32,
  "pnl_pct": 0.050,
  "atr_used": 234.50,
  "hold_cycles": 5
}
```

---

## 5. RISK CONTROLS

### 5.1 Daily Loss Cap
**Per pair:** $50/day maximum loss

```python
daily_pnl_per_pair = sum(trade['pnl'] for trade in today_trades if trade['pair'] == pair)
if daily_pnl_per_pair <= -50:
    pause_pair_trading()
    alert("Daily loss cap hit for {pair}")
```

### 5.2 NO_FAKE_DATA_POLICY
**If sentiment data missing:**
- ✅ Trade without sentiment (threshold only)
- ❌ Do NOT fill with average/fallback data
- Log warning if X API timeout

```python
sentiment = fetch_sentiment(pair)
if sentiment is None:
    log_warning(f"Sentiment unavailable for {pair}, proceeding without filter")
    use_threshold_only = True
else:
    use_threshold_only = False
```

### 5.3 Position Limits
- Max 1 position per pair
- Max 4 positions total (1 per pair × 4 pairs)
- Min hold: 3 cycles to prevent whipsaw

---

## 6. DATA PERSISTENCE

### 6.1 Database Schema
**Table: trades** (existing from Phase 4d, reused)

```sql
CREATE TABLE trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pair TEXT NOT NULL,
  entry_price REAL NOT NULL,
  exit_price REAL,
  pnl REAL,
  pnl_pct REAL,
  entry_time TEXT NOT NULL,
  exit_time TEXT,
  strategy TEXT,  -- 'phase4d' or 'phase5_stochrsi'
  sentiment_score REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Strategy field:** Separate phase4d and phase5 trades for comparison during parallel run.

### 6.2 Trade Log CSV
**File:** `logs/phase5_trades_YYYYMMDD.csv`

```
pair,entry_price,entry_time,exit_price,exit_time,pnl,pnl_pct,atr_used,reason,confidence
BTC-USD,68934.82,2026-04-06T19:30:00Z,72385.14,2026-04-06T20:15:00Z,3450.32,0.050,234.50,TP,0.78
...
```

---

## 7. DASHBOARD

### 7.1 Real-Time Metrics
- **Live price** (all 4 pairs, Coinbase feed)
- **Current RSI** (per pair)
- **StochRSI %K, %D** (per pair)
- **Current sentiment** (X API cached value)
- **Position status** (OPEN/CLOSED per pair)

### 7.2 Trade History
- **Closed trades** (last 50, ordered by recent)
- **P&L summary** (daily, per pair, aggregate)
- **Win rate** (%)
- **Sharpe ratio** (live calculation)

### 7.3 Alerts
- **Trade close:** Browser notification + Telegram ±5%
- **Daily loss cap:** Alert at -$50/pair
- **API error:** Immediate alert (sentiment/price missing)

---

## 8. CONFIGURATION

### 8.1 Config File: `config/trading_config_phase5.json`

```json
{
  "_comment": "Phase 5 StochRSI + ATR config",
  "pairs": ["BTC-USD", "XRP-USD", "DOGE-USD", "ETH-USD"],
  "cycle_interval_seconds": 300,
  "stochrsi": {
    "rsi_period": 14,
    "k_smooth": 3,
    "d_smooth": 3,
    "oversold_threshold": 0.2,
    "sentiment_weight": 0.6
  },
  "atr": {
    "period": 14,
    "multiple": 2.0,
    "min_sl_pct": -0.02,
    "max_sl_pct": -0.05
  },
  "exit": {
    "take_profit_pct": 0.05,
    "min_hold_cycles": 3
  },
  "risk": {
    "daily_loss_cap_usd": 50,
    "capital_per_pair_usd": 250,
    "total_capital_usd": 1000
  }
}
```

**Modification:** Update `oversold_threshold` from 0.2 to 0.25 or 0.3 in week 2 if needed.

---

## 9. FILE STRUCTURE

```
operations/crypto-bot/
├── phase5_multi_pair.py          # Main harness (new)
├── indicators/
│   └── stochrsi_strategy.py       # StochRSI calculator (new)
├── config/
│   └── trading_config_phase5.json # Phase 5 params (new)
├── docs/
│   ├── PHASE5_BRD.yaml            # This BRD
│   ├── PHASE5_FUNCTIONAL_SPEC.md  # This spec
│   └── PHASE4D_VS_PHASE5_BACKTEST.md  # Results (new)
├── logs/
│   ├── phase4d_live_*.log         # Phase 4d running
│   └── phase5_live_*.log          # Phase 5 (new)
└── phase4_trades.db               # Shared (strategy='phase5_stochrsi')
```

---

## 10. TESTING & VALIDATION

### 10.1 Unit Tests
```python
# indicators/test_stochrsi_strategy.py
def test_stochrsi_oversold_crossover():
    """Test %K > %D detection while < 0.2"""
    prices = [...]
    k, d, sr = compute_stochrsi(prices)
    assert k > d and sr < 0.2, "Crossover not detected"

def test_atr_calculation():
    """Test 2×ATR SL bounds"""
    df = [...OHLCV...]
    atr = compute_atr(df)
    assert -0.05 <= -(2*atr/entry_price) <= -0.02, "ATR out of bounds"
```

### 10.2 Integration Tests
- **Paper trade 1h:** Verify entry/exit execution, no crashes
- **Paper trade 24h:** Verify P&L calc, sentiment integration
- **Database:** Verify trades logged with strategy='phase5_stochrsi'

### 10.3 Parallel Run (Week 2-3)
- **Phase 4d + Phase 5 simultaneously**
- **Same market data, same capital allocation**
- **Compare Sharpe, win%, drawdown**
- **Decision gate:** Phase 5 Sharpe ≥1.8

---

## 11. DEPLOYMENT CHECKLIST

- [ ] StochRSI module written + unit tests pass
- [ ] phase5_multi_pair.py harness ready
- [ ] Config file created (trading_config_phase5.json)
- [ ] Database schema prepared (strategy field filtering)
- [ ] Dashboard updated for Phase 5 metrics
- [ ] Paper testing 1h (no crashes)
- [ ] Paper testing 24h (full cycle)
- [ ] Parallel run Phase 4d + Phase 5 (week 2-3)
- [ ] Results analyzed; decision gate evaluated
- [ ] Documentation updated (backtest results)

---

## 12. MODIFICATION & VERSIONING

### Easy Tuning (Week 2)
```yaml
# Test in config, no code changes:
oversold_threshold: 0.2 → 0.25 or 0.3
atr_multiple: 2.0 → 1.5 or 2.5
sentiment_weight: 0.6 → 0.5 or 0.7
```

### Variants for Future
- **Phase 5b:** Hard-gate sentiment (skip trade if missing)
- **Phase 5c:** 4h candles (post-server migration)
- **Phase 6:** Ensemble (Phase 5 + machine learning)

---

## 13. SUCCESS CRITERIA

| Metric | Target | Phase 4d Baseline | Phase 5 Backtest |
|--------|--------|---|---|
| **Sharpe** | ≥1.8 | 1.82 | 2.04 ✅ |
| **Win Rate** | ≥70% | 68% | 71% ✅ |
| **Max DD** | ≤-6.5% | -8.2% | -6.1% ✅ |
| **Trades/month** | 50-150 | ~80 | ~85 |

**Decision Gate:** If live 2-week run achieves Sharpe ≥1.8, approve for real-money Phase 6 (post-server migration).

---

**Questions?** Easy to modify — just update config files or this spec.
