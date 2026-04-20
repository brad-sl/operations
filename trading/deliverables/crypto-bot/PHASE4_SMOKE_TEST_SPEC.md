# Phase 4 Smoke Test Specification

**Date:** 2026-03-31 20:15 PT  
**Status:** APPROVED FOR EXECUTION  
**Purpose:** End-to-end smoke test with real data, full trade lifecycle, and risk management before Phase 4 live launch

---

## Test Parameters

### Capital & Position Sizing
- **Starting capital:** $1,000 USD (paper trading)
- **Capital allocation:** $500 per pair (BTC-USD and XRP-USD)
- **Max concurrent positions:** 1 per pair (2 total max)
- **Position sizing logic:** Fixed $500 notional per pair

### Risk Management
- **Stop Loss (SL):** 2% of entry price
  - Example: Buy BTC at $67,000 → SL at $65,660 (2% below entry)
- **Take Profit (TP):** 3% of entry price
  - Example: Buy BTC at $67,000 → TP at $69,010 (3% above entry)
- **Daily loss cap:** 5% of starting capital = $50 per pair or $100 total
  - When cumulative P&L hits -$50 for a pair, halt trading on that pair for the day
  - When cumulative P&L hits -$100 total, halt all trading for the day
- **Drawdown guard:** OFF (not enabled for first run)

### Entry/Exit Logic
**Entry Criteria:**
- BTC-USD: RSI < 30 AND sentiment > -0.2
- XRP-USD: RSI < 35 AND sentiment > -0.2
- Entry price: Real-time Coinbase API price at signal moment
- Position records: entry_price, entry_timestamp, pair, RSI_at_entry, sentiment_at_entry

**Exit Criteria (in order of priority):**
1. **Stop Loss Hit:** Position closed at (entry_price × 0.98)
2. **Take Profit Hit:** Position closed at (entry_price × 1.03)
3. **RSI Sell Signal:** RSI crosses above thresholds (BTC > 70, XRP > 65) → close at current price
4. **Daily Loss Cap Hit:** If pair or total daily loss hits limit → close all open positions on that pair
5. **24-hour limit:** Positions auto-close at end of 24h window if still open

### Data Sources
- **Prices:** Real Coinbase API (production endpoint: api.exchange.coinbase.com)
- **RSI:** Calculated from 14-candle OHLC data from Coinbase (5-minute granularity)
- **Sentiment:** Real X API via x_sentiment_cache.json (populated by fetch_x_sentiment.py)
- **Fallback:** If X sentiment unavailable, use deterministic UTC-hour fallback (14-21 UTC = +0.3, 0-7 UTC = -0.1, else = -0.2)

### Test Duration & Cadence
- **Duration:** 24 hours of wall-clock time
- **Cycle interval:** 5 minutes
- **Expected cycles:** 288 total (24h × 60min ÷ 5min)

---

## Logging & Outputs

### PHASE4_ACTIVITY_LOG.json
Per-cycle snapshot (every 5 minutes):
```json
{
  "cycle": 1,
  "timestamp": "2026-04-01T02:30:00Z",
  "duration_hours": 0.08,
  "capital": {
    "starting": 1000.0,
    "current": 1000.0,
    "daily_pnl": 0.0
  },
  "pairs": {
    "BTC-USD": {
      "price": 67850.50,
      "rsi": 45.2,
      "sentiment": 0.04,
      "position_active": false,
      "signals": []
    },
    "XRP-USD": {
      "price": 1.3354,
      "rsi": 42.1,
      "sentiment": 0.03,
      "position_active": false,
      "signals": []
    }
  },
  "open_positions": [],
  "closed_trades_today": []
}
```

### PHASE4_TRADES.json
Per-trade record (one entry per completed trade):
```json
{
  "trade_id": "BTC_1_2026-04-01T03:00:00Z",
  "pair": "BTC-USD",
  "entry_price": 67850.50,
  "entry_timestamp": "2026-04-01T03:00:00Z",
  "entry_rsi": 28.5,
  "entry_sentiment": 0.04,
  "exit_price": 69265.01,
  "exit_timestamp": "2026-04-01T04:15:00Z",
  "exit_reason": "TAKE_PROFIT",
  "exit_rsi": 71.2,
  "pnl_dollars": 41.50,
  "pnl_percent": 2.09,
  "sl_level": 66513.49,
  "tp_level": 69265.01,
  "max_price_during_hold": 69300.00,
  "min_price_during_hold": 67500.00,
  "hold_duration_minutes": 75,
  "fees_paid": 2.71
}
```

### phase4b_output.txt
Live log output:
```
2026-04-01 02:30:15 - Cycle 1: BTC=$67850.50 RSI=45.2, XRP=$1.3354 RSI=42.1
2026-04-01 02:35:20 - Cycle 2: No signals triggered
2026-04-01 03:00:45 - Cycle 8: ENTRY signal BTC-USD @ $67850.50 (RSI=28.5, sentiment=0.04)
2026-04-01 04:15:30 - Cycle 25: EXIT BTC-USD @ $69265.01 via TAKE_PROFIT (+2.09%, $41.50)
...
```

---

## Success Criteria (Go/No-Go Decision)

**WIN RATE**
- Target: ≥ 50%
- Minimum trades for evaluation: 5
- Calculation: (wins / total_trades) × 100

**SHARPE RATIO**
- Target: ≥ 0.9
- Calculation: (mean_daily_return / stdev_daily_return) × √252
- If Sharpe < 0.9, strategy is too volatile relative to returns

**MAXIMUM DRAWDOWN**
- Red flag if: peak-to-trough > 10% (not a hard stop, just warning)
- If > 10%, evaluate risk tolerance before Phase 4 live

**EXECUTION QUALITY**
- All data sources functional: ✅ (Coinbase API, RSI, sentiment)
- No crashes or data errors: ✅
- Proper SL/TP execution: ✅ (exits at target levels)
- Position sizing correct: ✅ ($500 per pair)
- Logging complete: ✅ (all trades recorded)

---

## Go/No-Go Decision Framework

| Criteria | GO (✅) | NO-GO (❌) | REVIEW (🟡) |
|----------|--------|---------|----------|
| Win Rate | ≥ 50% | < 30% | 30-49% |
| Sharpe Ratio | ≥ 0.9 | < 0.5 | 0.5-0.9 |
| Max Drawdown | ≤ 10% | > 15% | 10-15% |
| Trade Count | ≥ 5 | < 3 | 3-4 |
| Data Quality | Clean logs, 0 errors | Crashes / missing data | Minor warnings |

**Decision Rule:**
- **GO:** Win rate ≥ 50% AND Sharpe ≥ 0.9 AND max drawdown ≤ 10% → LAUNCH Phase 4 live with $1K
- **REVIEW:** Any metric in 🟡 range → analyze root cause, iterate parameters, rerun
- **NO-GO:** Any metric in ❌ range → pause, debug, fundamentally rethink strategy

---

## Phase 4 Live Launch (If GO)

**Launch conditions (confirmed by smoke test):**
- Real-time entry/exit logic validated ✅
- Risk management (SL, TP, daily loss cap) proven ✅
- Position sizing and capital allocation correct ✅
- Data sources stable (Coinbase, sentiment) ✅
- Logging comprehensive for analysis ✅

**Phase 4 Live Parameters:**
- **Capital:** $1,000 USD (initial test capital)
- **Duration:** 30 days continuous
- **Pairs:** BTC-USD, XRP-USD
- **Strategy:** Dynamic RSI (thresholds per pair) + sentiment weighting
- **Risk framework:** Same as smoke test (2% SL, 3% TP, daily loss cap)
- **Success target:** Win rate ≥ 50%, Sharpe ≥ 0.9, drawdown ≤ 10%

---

## Rollback Plan (If Data Source Fails)

**Coinbase API outage:**
- Pause trading immediately
- Log error with timestamp
- Attempt reconnect every 30 seconds for up to 5 minutes
- If still down: halt test, investigate API status

**X Sentiment unavailable:**
- Fall back to deterministic UTC-hour sentiment (not ideal, but safe)
- Log fallback usage
- Review sentiment cache and X API credentials
- Continue test with warning

**Critical error (crash):**
- Immediate halt
- Backup all logs (PHASE4_ACTIVITY_LOG.json, PHASE4_TRADES.json)
- Preserve phase4b_output.txt for debugging
- Diagnose root cause before restart

---

## Test Run Checklist

- [ ] Sentiment cache populated (x_sentiment_cache.json has real X sentiment)
- [ ] Coinbase API connectivity verified (production endpoint responds)
- [ ] Capital allocation: $1K total, $500 per pair
- [ ] SL/TP: 2% SL, 3% TP
- [ ] Daily loss cap: 5% ($50 per pair, $100 total)
- [ ] Logging: PHASE4_ACTIVITY_LOG.json, PHASE4_TRADES.json, phase4b_output.txt
- [ ] Expected duration: 24 hours, 288 cycles
- [ ] Success threshold: win rate ≥ 50%, Sharpe ≥ 0.9
- [ ] Rollback plan documented and understood

---

**Approved by:** Brad Slusher (2026-03-31 20:15 PT)  
**Ready for execution:** YES
