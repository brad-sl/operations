# Phase 5 Specification
**Version:** 5.1 (Live)  
**Status:** Production (Phase 4d Algorithm)  
**Last Updated:** 2026-04-21

---

## Overview

Phase 5 implements multi-pair cryptocurrency trading on Coinbase using RSI-based signal generation and real sentiment weighting.

**Active Configuration:**
- Algorithm: Phase 4d (RSI<30 entry, RSI>70 exit, 2% SL)
- Pairs: BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD, ADA-USD
- Capital: $1,000 ($166.67 per pair)
- Data: Real-time via Coinbase API (no synthetic data)
- Sentiment: Real X API + Reddit fallback (30-min aggregation)

---

## Entry Signal

**RSI < 30** (oversold threshold)

```python
rsi = calculate_rsi(prices[-14:], period=14)
if rsi < 30:
    ENTRY = True
```

**Exit Signals:**
1. **Profit-Taking:** RSI > 70 (overbought)
2. **Stop-Loss:** Price drops 2% from entry

---

## Components

### 1. Main Runtime
**File:** `phase5_multi_pair.py`  
**Purpose:** Multi-pair signal generation + position tracking  
**Cycle Time:** 5 minutes  
**State:** JSON (position_state.json)

### 2. Price Data
**File:** `price_wrapper.py`  
**Purpose:** Fetch OHLCV from Coinbase  
**API:** Public (no auth required for prices)

### 3. Sentiment Aggregation
**File:** `sentiment_aggregator_v2.py`  
**Cadence:** Every 30 minutes  
**Sources:** 
- Primary: X API (real trader sentiment)
- Fallback: Reddit (r/cryptocurrency, r/Bitcoin)
- Cache: sentiment_cache.json

### 4. Coinbase Integration
**File:** `coinbase_wrapper.py`  
**Auth:** ES256 JWT (ECDSA P-256)
**Credentials:** .env (COINBASE_API_KEY, COINBASE_API_SECRET)

### 5. State Persistence
**File:** `checkpoint_manager.py`  
**Format:** JSON (atomic writes + backup)
**Data:** Active positions, entry prices, timestamps

---

## Real Data Backtest Results

**Period:** 2025-04-20 to 2026-04-20 (1 year, bearish market)

| Metric | Result |
|--------|--------|
| Total Trades | 78 |
| Win Rate | 33.3% |
| Total P&L | +$192.84 |
| Avg Win | $18.79 |
| Avg Loss | -$5.69 |
| ROI | +19.3% |

**Note:** Tested on actual market data. Phase 5 Full Spec (with StochRSI + 2×ATR) returned $64.18 on same period. Phase 4d algorithm proved superior on real data.

---

## Deployment

```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot
./venv/bin/python3 phase5_multi_pair.py --cycles 999999
```

**Status:** RUNNING (PID tracked by HEARTBEAT monitor)

---

## No Synthetic Data

**Policy:** NO_FAKE_DATA_POLICY_2026_03_31.md applies.
- All backtesting uses real OHLCV data
- All sentiment uses real X API + Reddit
- No generated price data
- Fail loudly if data source missing

---

## Next: Phase 6

Phase 6 will integrate `order_executor.py` for full BUY/SELL execution (currently signals-only).
