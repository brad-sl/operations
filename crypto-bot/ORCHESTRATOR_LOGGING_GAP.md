# Orchestrator Logging Gap Analysis

**Status:** Current Phase 3 execution is logging **EVERY SIGNAL**, not **actual trades**

---

## Current Logging (What we're doing now)

```json
{
  "cycle": 1,
  "timestamp": "2026-03-25T02:59:36.611133",
  "product_id": "BTC-USD",
  "signal": "HOLD",              // ← Every cycle generates a signal
  "rsi": 43.39,
  "sentiment": -0.31,
  "order_id": "PAPER_BTC-USD_000001",
  "price": 67500,
  "quantity": 0,                 // ← HOLD = no order
  "status": "FILLED",
  "sentiment_fresh": true
}
```

**Problem:** We're logging 288 cycles = 288 "orders" even though most are HOLD (quantity=0)

---

## What We SHOULD Log (Production Schema)

```json
{
  "event_type": "ENTRY",
  "event_id": "BTC_20260325_001",
  "timestamp": "2026-03-25T08:23:45.123Z",
  "product_id": "BTC-USD",
  "side": "LONG",
  "entry_price": 67523.50,
  "entry_quantity": 0.01,
  "signal_details": {
    "rsi": 28.5,
    "sentiment": -0.65,
    "confidence": 0.85
  },
  "risk_parameters": {
    "stop_loss_price": 66750,
    "stop_loss_amount_usd": 50
  }
}
```

**Then when trade closes:**

```json
{
  "event_type": "OUTCOME",
  "entry_event_id": "BTC_20260325_001",
  "exit_price": 67650.00,
  "pnl_usd": 1.27,
  "net_pnl_pct": 0.1872,
  "trade_result": "WIN"
}
```

---

## The Gap

| Aspect | Current | Should Be | Impact |
|--------|---------|-----------|--------|
| **Events logged per cycle** | 1 (every signal) | 0 or 1 (only actual trades) | 288 fake "orders" for 3-6 real trades |
| **Quantity field** | Shows 0 for HOLD | Only populated for BUY/SELL | Can't tell trades from noise |
| **Exit tracking** | Not tracked | OUTCOME event with exit details | No way to calculate P&L |
| **P&L calculation** | Not calculated | Automatic on OUTCOME | Can't measure strategy quality |
| **Analysis capability** | "Did we generate 288 signals?" | "Did we win 45% of trades?" | Everything changes |

---

## Decision Point

**For current Phase 3 execution (already running):**

### Option A: Continue As-Is
- ✅ Execution runs to completion (48h countdown active)
- ❌ Output shows 576 "orders" but only ~9-12 actual trades
- ❌ Can't properly analyze strategy effectiveness
- ⏳ Need to manually parse logs post-completion to extract real trades

### Option B: Kill & Restart with Correct Logging
- ✅ Get clean data from the start
- ✅ Can properly calculate P&L for all trades
- ✅ Analysis is straightforward (no manual parsing)
- ❌ Restart timer (another 48 hours to wait)
- ❌ Lose the work already done

### Option C: Continue + Implement Post-Processing
- ✅ Execution completes on schedule (Wed 20:03 PDT)
- ⏳ After completion, extract real trades from logs
- ⏳ Manually calculate P&L, win rate, etc.
- ✅ Still get valid analysis, just not automated
- ✅ Phase 4 decision still possible

---

## Recommendation

**Since we're already running (20:28 Tuesday):** 

Go with **Option C: Continue + Post-Process**

**Why:**
1. We already have 4+ hours of clean execution data
2. 44 hours remain (nearly full 48h)
3. Post-processing trades from logs is feasible (write a parser)
4. We'll get valid analysis by Wed 20:03 anyway
5. No time lost

**What to do when Phase 3 completes:**
1. Extract ENTRY/EXIT/OUTCOME events from logs
2. Map to real trades (where quantity > 0)
3. Calculate P&L, win rate, metrics
4. Answer: "Ready for Phase 4?"

---

## For Phase 4 (Live Trading)

**MUST implement:**
1. Only log BUY/SELL signals (not HOLD)
2. Track entry price + quantity
3. Track exit price + exit reason
4. Calculate P&L automatically
5. Aggregate metrics by pair

This is already defined in `TRADING_EVENT_SCHEMA.md` — just needs to be coded.

---

## Action Items

- ✅ TRADING_EVENT_SCHEMA.md — Finalized
- ⏳ Current execution — Continue (post-process on completion)
- 📋 Post-completion analysis — Extract real trades + calculate metrics
- 🔧 Phase 4 orchestrator update — Implement proper event logging

---

**Bottom line:** We're getting insight on the strategy even if the current logging is noisy. Wednesday's analysis will be solid.
