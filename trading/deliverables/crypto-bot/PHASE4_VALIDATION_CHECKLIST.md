# Phase 4 Trade Throttle Test — Validation Checklist

**Test Duration:** 48 hours (2026-03-29 14:15 PT → 2026-03-31 14:15 PT)  
**Test Harness:** phase4_v5_simple.py  
**Database:** phase4_trades.db  
**Log:** phase4_48h_run.log

---

## Scope: What We're Validating

The test compares **three exit threshold strategies** running in parallel on identical entry signals to answer:
> **Which strategy maximizes net P&L after fees?**

### The Three Strategies

| Strategy | Threshold | Rationale | Expected Frequency |
|----------|-----------|-----------|-------------------|
| **FIXED** | 1.0% | Conservative baseline; exit when profit ≥ 1.0% | 50-60 trades (48h) |
| **FEE_AWARE** | 0.75% | Dynamic threshold based on fees: (0.25% entry + 0.25% exit) × 1.5 = 0.75% | 60-70 trades (48h) |
| **PAIR_SPECIFIC** | 0.5% (BTC), 1.5% (XRP) | Per-pair tuning: BTC more sensitive, XRP more selective | 45-55 trades (48h) |

**Key constraint:** All three strategies receive the **same entry signals** and price data. The ONLY difference is the exit threshold.

---

## Validation Checklist (Final Report, 2026-03-31 14:15 PT)

### ✅ Data Integrity Checks

- [ ] **Database connectivity:** phase4_trades.db exists and is readable
- [ ] **Schema present:** Both `trades` and `strategy_backtest` tables exist with expected columns
- [ ] **trader_configs seeded:** All 6 rows present (3 strategies × 2 pairs)
  - BTC-USD: fixed, fee_aware, pair_specific
  - XRP-USD: fixed, fee_aware, pair_specific
- [ ] **No corrupt rows:** No NULL entry_price or exit_price values (would indicate failed inserts)
- [ ] **Timestamps valid:** All trades have realistic entry_time and exit_time (within 48-hour window)
- [ ] **Log file complete:** phase4_48h_run.log exists and contains full 48 hours of cycle output

### ✅ Process & Execution Checks

- [ ] **Single process active:** Exactly one phase4_v5_simple.py process ran (no restarts or crashes mid-run)
- [ ] **Cycle cadence:** ~576 cycles completed (48 hours ÷ 5 minutes per cycle)
- [ ] **No errors in logs:** Check for repeated error patterns (fetch failures, DB timeouts, exceptions)
- [ ] **Graceful completion:** Process ran to natural completion (did not crash or hang)

### ✅ Data Quality Checks

- [ ] **Minimum trade count:** At least 80-100 total trades across all three strategies (sufficient for statistical confidence)
- [ ] **Trade distribution:** All three strategies generated trades (not just one strategy dominating)
  - FIXED: ≥ 40 trades expected
  - FEE_AWARE: ≥ 50 trades expected
  - PAIR_SPECIFIC: ≥ 35 trades expected
- [ ] **Realistic P&L:** Individual trades show P&L values between -5% and +5% (plausible market movement)
- [ ] **Win rate sanity:** Each strategy shows 50-70% win rate (consistent with 60% hypothesis)
- [ ] **No outliers:** No single trade with P&L > 10% (would suggest data anomaly)

### ✅ Fee Model Validation

- [ ] **Coinbase fee rates correct:** Verify entry_fee_pct = 0.25 and exit_fee_pct = 0.25 for all strategies (documented in COINBASE_FEE_RESEARCH.md)
- [ ] **FEE_AWARE threshold correct:** min_profit_pct = 0.75% for FEE_AWARE strategy (calculated as (0.25 + 0.25) × 1.5)
- [ ] **PAIR_SPECIFIC overrides correct:**
  - BTC-USD: min_profit_pct_override = 0.5%
  - XRP-USD: min_profit_pct_override = 1.5%

### ✅ Statistical Analysis Checks

For each strategy, calculate and verify:

- [ ] **Trade count:** Total number of executed trades
- [ ] **Win rate:** (Wins ÷ Total Trades) × 100 %
- [ ] **Loss rate:** (Losses ÷ Total Trades) × 100 %
- [ ] **Net P&L:** Sum of all individual trade P&L
- [ ] **Average P&L per trade:** Net P&L ÷ Total Trades
- [ ] **Sharpe ratio (optional):** If time-series data available, calculate Sharpe ratio for each strategy
- [ ] **Comparison:** Identify which strategy has highest net P&L (winner)

### ✅ Behavior Validation

- [ ] **Entry signals consistent:** All three strategies received identical entry prices/times (verify by checking trades table for same pair/time)
- [ ] **Exit logic working:** Trades exit when expected (verify by checking pnl_pct ≥ threshold per strategy)
- [ ] **Price fetch reliability:** No repeated Coinbase API timeouts or failures
- [ ] **Database writes atomic:** No partial/corrupted trades (all required fields populated)

### ✅ Knowledge Transfer Documentation

- [ ] **PHASE4_TEST_EXECUTION_PLAN.md updated:** Document final results and decision
- [ ] **Code comments present:** All functions in phase4_v5_simple.py have docstrings and reference data sources
- [ ] **Database schema documented:** trader_configs and trades table structure captured in a reference doc
- [ ] **Fee model locked down:** COINBASE_FEE_RESEARCH.md referenced and versioned
- [ ] **Results reproducible:** All parameters and thresholds documented so test can be repeated

---

## Final Report Deliverables (2026-03-31 14:15 PT)

### Core Results

```
PHASE 4 TRADE THROTTLE TEST — FINAL RESULTS
=============================================

📊 STRATEGY COMPARISON (48-hour run):

FIXED (1.0% threshold)
  Trades: XXX | Wins: XXX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

FEE_AWARE (0.75% threshold) ⭐ [WINNER if highest P&L]
  Trades: XXX | Wins: XXX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

PAIR_SPECIFIC (0.5/1.5% threshold)
  Trades: XXX | Wins: XXX | Win Rate: X.X% | Total P&L: $+XXX.XX | Avg per trade: $+X.XX

🏆 WINNER: [Strategy Name] with $+XXX.XX net P&L
   Recommendation: Use this strategy for Phase 4 live trading ($1K allocation)
```

### Detailed Analysis

- Win rate comparison (which strategy had best signal quality?)
- Trade frequency comparison (did thresholds align with expectations?)
- Fee efficiency (net P&L as % of gross moves)
- Anomalies or surprises (any unexpected behavior?)

### Phase 4 Recommendation

Based on winner selection:
- **Strategy to deploy:** [FIXED | FEE_AWARE | PAIR_SPECIFIC]
- **Confidence level:** High/Medium (based on trade count and statistical significance)
- **Live trading parameters:** Daily budget, position size, stop loss, take profit per Phase 4 decision doc
- **Go/No-Go:** PROCEED to Phase 4 with $1K allocation OR RETEST with parameter adjustments

---

## Commands to Run Final Analysis

After 2026-03-31 14:15 PT, execute:

```bash
# Check process status
ps aux | grep phase4_v5_simple.py | grep -v grep

# Extract final statistics from DB
python3 - << 'PY'
import sqlite3
conn = sqlite3.connect('/home/brad/.openclaw/workspace/operations/crypto-bot/phase4_trades.db')
cur = conn.cursor()

# Per-strategy summary
cur.execute("""
  SELECT strategy, COUNT(*) as trades, 
         SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
         SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
         SUM(pnl) as total_pnl,
         AVG(pnl) as avg_pnl,
         ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
  FROM trades
  GROUP BY strategy
  ORDER BY total_pnl DESC
""")

print("\n" + "="*80)
print("PHASE 4 FINAL RESULTS")
print("="*80)
for row in cur.fetchall():
    strat, trades, wins, losses, total_pnl, avg_pnl, wr = row
    print(f"\n{strat.upper():15} | Trades: {trades:3} | Wins: {wins:3} | Win%: {wr:5.1f}% | "
          f"Total P&L: ${total_pnl:+10.2f} | Avg: ${avg_pnl:+7.2f}")

conn.close()
PY
```

```bash
# Extract tail of log to confirm completion
tail -100 /home/brad/.openclaw/workspace/operations/crypto-bot/phase4_48h_run.log
```

---

## Success Criteria

✅ **Test passes validation if:**
1. At least 80-100 trades executed across all strategies
2. All three strategies show meaningful differentiation (highest winner >5% better than lowest)
3. Win rates fall in expected range (50-70%)
4. No data corruption or unhandled errors in logs
5. Clear winner emerges with actionable recommendation for Phase 4

⚠️ **Test requires adjustment if:**
- Fewer than 80 trades total (market movement too low; consider extending or adjusting thresholds)
- All strategies show identical or near-identical P&L (exit thresholds too similar to detect difference)
- Win rates exceed 80% or fall below 40% (suggests market regime change or signal problem)
- Repeated errors in logs (price fetch failures, DB issues)

---

## Timeline

- **Start:** 2026-03-29 14:15 PT
- **Checkpoint (4h):** 2026-03-29 18:15 PT (skipped per Option B)
- **Completion:** 2026-03-31 14:15 PT
- **Final Report:** 2026-03-31 14:15 PT + 30 minutes (time to analyze and document)

---

## References

- **Fee Documentation:** `/operations/crypto-bot/COINBASE_FEE_RESEARCH.md`
- **Execution Plan:** `/operations/crypto-bot/PHASE4_TEST_EXECUTION_PLAN.md`
- **Code Source:** `/operations/crypto-bot/phase4_v5_simple.py`
- **Test Status:** `/operations/crypto-bot/TEST_STATUS.md`
- **Findings Archive:** `/operations/crypto-bot/THROTTLE_TEST_FINDINGS.md`
