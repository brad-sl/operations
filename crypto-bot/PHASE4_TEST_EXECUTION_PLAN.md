# Phase 4 Trade Throttle Test — Execution Plan & Knowledge Transfer

**Start Time:** 2026-03-29 14:15 PT (21:15 UTC)  
**Duration:** 48 hours (until 2026-03-31 14:15 PT)  
**Test Name:** phase4_v5_simple.py  
**Database:** phase4_trades.db (SQLite)  
**Output Log:** phase4_48h_run.log  

---

## Purpose

Determine the optimal exit threshold strategy that **minimizes trading fees while maintaining profitability**:

1. **FIXED (1.0%)** — Conservative baseline: exit only when profit ≥ 1.0%
2. **FEE_AWARE (0.75%)** — Calculated from Coinbase fees: (0.25% entry + 0.25% exit) × 1.5 safety margin = 0.75%
3. **PAIR_SPECIFIC (0.5/1.5%)** — Tuned per pair: BTC-USD 0.5%, XRP-USD 1.5%

All three strategies run **in parallel on identical entry signals**, differing only in exit thresholds.

---

## Why This Test Matters

### Context: Fee Minimization Problem

**Problem:** Too many trades → High fee drag  
**Problem:** Too few trades → Miss profitable exits  
**Solution:** Find the "sweet spot" threshold that maximizes net P&L after fees

### Actual Coinbase Fees (Documented)
Reference: `COINBASE_FEE_RESEARCH.md`
- **Maker fee (Advanced 1+ tier):** 0.25% per side
- **Round-trip cost:** 0.25% entry + 0.25% exit = 0.5%
- **FEE_AWARE threshold:** (0.5% × 1.5 safety margin) = 0.75% min profit to break even + margin

---

## Test Configuration

### Strategies Seeded in DB (trader_configs table)

```
trader_id | pair      | strategy        | min_profit_pct | entry_fee | exit_fee | override
----------|-----------|-----------------|----------------|-----------|----------|----------
brad      | BTC-USD   | fixed           | 1.0            | 0.25      | 0.25     | NULL
brad      | BTC-USD   | fee_aware       | 0.75           | 0.25      | 0.25     | NULL
brad      | BTC-USD   | pair_specific   | 1.0            | 0.25      | 0.25     | 0.5
brad      | XRP-USD   | fixed           | 1.0            | 0.25      | 0.25     | NULL
brad      | XRP-USD   | fee_aware       | 0.75           | 0.25      | 0.25     | NULL
brad      | XRP-USD   | pair_specific   | 1.0            | 0.25      | 0.25     | 1.5
```

### Polling Parameters
- **Cycle interval:** 5 minutes (spec-compliant with RSI polling)
- **Pairs:** BTC-USD, XRP-USD (dual-pair testing)
- **Cycle limit:** 288 cycles (48 hours)
- **Price source:** Coinbase API (`https://api.exchange.coinbase.com/products/{pair}/ticker`)

### Database Tables

**trades table:**
- Records each simulated trade execution
- Fields: pair, signal, entry_price, exit_price, pnl, pnl_pct, result (WIN/LOSS), timestamps, regime
- Used for detailed post-analysis

**strategy_backtest table:**
- Aggregated results per strategy (trades, wins, losses, win_rate, total_pnl, avg_pnl_per_trade, sharpe_ratio)
- Summary metrics for final comparison

---

## Test Execution (phase4_v5_simple.py)

### Key Features

1. **Robust DB Handling**
   - Fresh SQLite connection per cycle (avoids long-held locks)
   - 10-second timeout on DB operations (prevents deadlocks)
   - Each trade write is atomic (commit immediately after insert)

2. **Strategy Logic**
   - Load config from trader_configs per strategy/pair
   - Calculate min_profit_pct dynamically (handles overrides)
   - Evaluate exit condition: `pnl_pct >= min_profit_pct`
   - Log execution to trades table

3. **Real-Time Monitoring**
   - Print cycle summary every 5 minutes
   - Per-strategy metrics: trade count, W/L, total P&L, average P&L per trade
   - Timestamp elapsed hours for progress tracking

4. **Error Resilience**
   - Catch & report DB errors without crashing
   - Catch & report price fetch errors without crashing
   - Continue cycling despite individual failures

### Source Code Documentation

Every function is commented with:
- Purpose and context
- Parameters and return types
- Error handling strategy
- References to data source or calculation method

### Running the Test

```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot
python3 phase4_v5_simple.py > phase4_48h_run.log 2>&1 &

# Monitor progress
tail -f phase4_48h_run.log

# Check status (DB should show trades accumulating)
sqlite3 phase4_trades.db "SELECT strategy, COUNT(*), SUM(pnl) FROM trades GROUP BY strategy;"
```

**Status check command (run anytime):**
```bash
python3 - << 'PY'
import sqlite3
conn = sqlite3.connect('/home/brad/.openclaw/workspace/operations/crypto-bot/phase4_trades.db')
cur = conn.cursor()
cur.execute("""
  SELECT strategy, COUNT(*) as trades, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
         SUM(pnl) as total_pnl, AVG(pnl) as avg_pnl
  FROM trades
  GROUP BY strategy
  ORDER BY strategy
""")
print("Strategy Results:")
for row in cur.fetchall():
    strat, trades, wins, total, avg = row
    wr = (wins / trades * 100) if trades > 0 else 0
    print(f"  {strat:15} | Trades: {trades:3} | Wins: {wins:3} ({wr:5.1f}%) | Total P&L: ${total:+10.2f} | Avg: ${avg:+8.2f}")
conn.close()
PY
```

---

## Knowledge Transfer & State Preservation

### Key Files & Their Purpose

| File | Purpose | Reference |
|------|---------|-----------|
| `phase4_v5_simple.py` | Main test harness (fully commented) | This plan |
| `phase4_trades.db` | SQLite DB with all results | Trades table, strategy_backtest table |
| `phase4_48h_run.log` | Real-time cycle output & cycle summaries | Monitor progress via `tail -f` |
| `COINBASE_FEE_RESEARCH.md` | Fee documentation (0.25% maker) | Justification for FEE_AWARE threshold |
| `TRADE_THROTTLE_TEST_SUMMARY.md` | Original planning doc | Hypothesis & expected outcomes |
| `THROTTLE_TEST_FINDINGS.md` | Previous 2-hour run analysis | Baseline data (2 trades, $79.13 P&L) |
| `PHASE4_TEST_EXECUTION_PLAN.md` | This document | Complete context for any session restart |

### How to Resume if Session Interrupts

1. **Check current status:**
   ```bash
   # Are processes running?
   ps aux | grep phase4_v5_simple.py | grep -v grep
   
   # How many trades so far?
   sqlite3 phase4_trades.db "SELECT COUNT(*) FROM trades;"
   
   # What's the latest cycle?
   tail -20 phase4_48h_run.log
   ```

2. **If process died:**
   ```bash
   cd /home/brad/.openclaw/workspace/operations/crypto-bot
   python3 phase4_v5_simple.py >> phase4_48h_run.log 2>&1 &
   # Appends to existing log; DB continues accumulating from where it left off
   ```

3. **If database got corrupted:**
   ```bash
   # Backup old DB
   cp phase4_trades.db phase4_trades.db.backup
   
   # Recreate schema & re-seed (script at bottom of this file)
   # Then restart test
   ```

### Data Persistence

- **Each trade is written atomically** to the trades table immediately after execution
- **No in-memory state required** — all strategy state lives in DB
- **Test is restartable** — can resume from any cycle without data loss
- **Logs are appended** — can re-run test, logs grow continuously

---

## Expected Outcomes (Hypothesis)

### Trade Frequency Expectations

| Strategy | Min Profit | Expected Trades (48h) | Win Rate | Expected P&L |
|----------|------------|----------------------|----------|--------------|
| FIXED | 1.0% | 50-60 | ~60% | $400-500 |
| FEE_AWARE | 0.75% | 60-70 | ~59% | $500-700 |
| PAIR_SPECIFIC | 0.5/1.5% | 45-55 | ~63% | $400-600 |

### Interpretation Guide

1. **Higher trade count doesn't always mean higher P&L** (due to fee drag)
2. **FEE_AWARE should have best risk/reward** (threshold bakes in fee cost)
3. **PAIR_SPECIFIC should balance frequency & quality** (BTC more frequent, XRP more selective)
4. **Win rate may converge** (RSI signals consistent across thresholds)

---

## Final Report (After 48 Hours)

### Analysis Metrics

1. **Primary:** Net P&L per strategy (winner = highest net profit after fees)
2. **Secondary:** Win rate, average P&L per trade
3. **Tertiary:** Trade frequency, fee efficiency ratio

### Report Structure (to be delivered)

```
PHASE 4 THROTTLE TEST — FINAL RESULTS
=====================================

📊 Strategy Comparison (48-hour run):

FIXED (1.0% threshold)
  Trades: XX | Wins: XX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

FEE_AWARE (0.75% threshold)
  Trades: XX | Wins: XX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

PAIR_SPECIFIC (0.5/1.5% threshold)
  Trades: XX | Wins: XX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

🏆 WINNER: [Strategy Name] with $+XXX.XX net P&L

💡 RECOMMENDATION FOR PHASE 4:
[Use this strategy for live $1K trading]
```

---

## Troubleshooting

### Issue: DB locked error
- **Cause:** Multiple processes writing simultaneously
- **Fix:** Kill all phase4_v5_simple.py processes, wait 5s, restart single instance

### Issue: Coinbase API timeouts
- **Cause:** Network latency or API rate limiting
- **Fix:** Code catches & logs, test continues; non-blocking per cycle

### Issue: Test stops unexpectedly
- **Cause:** Process killed, timeout, or unhandled exception
- **Fix:** Check `ps aux` and `tail -50 phase4_48h_run.log`; restart via append

### Issue: Log file is huge
- **Cause:** Every cycle prints detailed output
- **Fix:** `tail -100 phase4_48h_run.log` gets latest; full log saved for audit

---

## References

- **Coinbase Fee Model:** `/operations/crypto-bot/COINBASE_FEE_RESEARCH.md`
- **Original Test Plan:** `/operations/crypto-bot/TRADE_THROTTLE_TEST_SUMMARY.md`
- **Previous Results:** `/operations/crypto-bot/THROTTLE_TEST_FINDINGS.md`
- **Code Source:** `/operations/crypto-bot/phase4_v5_simple.py`

---

## Next Steps (After 48 Hours)

1. **Collect final stats** from phase4_trades.db strategy_backtest table
2. **Analyze P&L per strategy** to identify winner
3. **Document recommendation** for Phase 4 live trading
4. **Commit all results** to git with results snapshot
5. **Decide:** Deploy winning strategy to Phase 4 with $1K allocation

---

**Test Status:** 🟢 READY TO RUN  
**Start Command:** `python3 phase4_v5_simple.py > phase4_48h_run.log 2>&1 &`  
**Monitor Command:** `tail -f phase4_48h_run.log`  
**Completion:** 2026-03-31 14:15 PT (Sunday afternoon)
