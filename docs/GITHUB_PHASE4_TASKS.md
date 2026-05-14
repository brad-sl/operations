# Phase 4 Trade Throttle Test — GitHub Task List

**Repo:** brad-sl/giga-chad  
**Epic:** Phase 4 Trade Throttle Test Validation  
**Status:** 🟢 IN PROGRESS (48-hour run started 2026-03-29 14:15 PT)

---

## Overview

Phase 4 validates which exit-threshold strategy (FIXED, FEE_AWARE, PAIR_SPECIFIC) maximizes net P&L after fees. Test runs 48 hours collecting trade data, then produces final validation report with winner recommendation.

**Key Metrics:** Total trades ≥80-100, win rate 50-70%, clear winner >5% better than runner-up.

---

## Active Issues

### Issue #1: Phase 4 Setup & Database Seed ✅ COMPLETE
- [x] Create phase4_trades.db schema (trades + strategy_backtest tables)
- [x] Seed trader_configs with 3 strategies × 2 pairs (BTC-USD, XRP-USD)
- [x] Verify Coinbase fee model (0.25% entry, 0.25% exit = 0.5% round trip)
- [x] Set FEE_AWARE threshold to 0.75% (fees × 1.5 safety margin)
- [x] Set PAIR_SPECIFIC overrides: BTC 0.5%, XRP 1.5%
- **Link:** PHASE4_TEST_EXECUTION_PLAN.md, COINBASE_FEE_RESEARCH.md

---

### Issue #2: Phase 4 Test Harness Implementation ✅ COMPLETE
- [x] phase4_v5_simple.py: Lightweight tester with 5-minute cycle cadence
- [x] Fetch prices from Coinbase API (BTC-USD, XRP-USD, real-time)
- [x] Evaluate all 3 strategies against identical entry signals
- [x] Log each trade with full details: pair, strategy, entry_price, exit_price, pnl, pnl_pct
- [x] Database write atomicity: no partial trades, no NULL-critical fields
- [x] Error handling: price fetch failures and DB issues logged but do not crash
- [x] Test process confirmed running (PID 502791 as of 2026-03-29 14:15 PT)
- **Link:** phase4_v5_simple.py (code), TEST_STATUS.md (status)

---

### Issue #3: Phase 4 Data Validation (48-hour run) 🔄 IN PROGRESS
**Deadline:** 2026-03-31 14:15 PT (Sunday 2:15 PM PT)

#### Sub-task 3a: Trade Data Capture
- [ ] Accumulate minimum 80-100 total trades across all strategies
- [ ] All three strategies receive equal entry signals (verify via DB timestamps)
- [ ] Per-strategy trade breakdown:
  - FIXED (1.0%): expect 50-60 trades
  - FEE_AWARE (0.75%): expect 60-70 trades
  - PAIR_SPECIFIC (0.5/1.5%): expect 45-55 trades
- [ ] No data corruption: non-NULL entry_price, exit_price, timestamp in all rows
- [ ] Realistic P&L values: individual trades between -5% and +5%

#### Sub-task 3b: Fee Model Validation
- [ ] Verify entry_fee_pct = 0.25 in all trades
- [ ] Verify exit_fee_pct = 0.25 in all trades
- [ ] Confirm FEE_AWARE threshold = 0.75% (correct calculation: (0.25+0.25) × 1.5 = 0.75%)
- [ ] Confirm PAIR_SPECIFIC overrides:
  - BTC-USD override = 0.5% ✓
  - XRP-USD override = 1.5% ✓

#### Sub-task 3c: Process Stability
- [ ] Single process ran entire 48 hours (no restarts, no crashes)
- [ ] Cycle count ≈576 (48 hours ÷ 5 minutes per cycle)
- [ ] No repeated error patterns in phase4_48h_run.log
- [ ] Graceful completion (process terminated naturally after 48h)

---

### Issue #4: Phase 4 Statistical Analysis & Winner Selection 🔄 IN PROGRESS
**Deadline:** 2026-03-31 14:45 PT (45 min after test completion)

#### Sub-task 4a: Per-Strategy Metrics
For each of FIXED, FEE_AWARE, PAIR_SPECIFIC, calculate:
- [ ] Total trade count
- [ ] Win count (trades with pnl > 0)
- [ ] Loss count (trades with pnl < 0)
- [ ] Win rate: (Wins ÷ Total Trades) × 100 %
- [ ] Loss rate: (Losses ÷ Total Trades) × 100 %
- [ ] Net P&L: sum of all individual trade pnl_pct values
- [ ] Average P&L per trade: Net P&L ÷ Total Trades
- [ ] Optional: Sharpe ratio if time-series data available

#### Sub-task 4b: Comparative Analysis
- [ ] Identify winner: strategy with highest net P&L
- [ ] Calculate margin: winner P&L - runner-up P&L
- [ ] Assess statistical significance: Is margin >5% of winner P&L?
- [ ] Document any surprising findings (e.g., unexpected threshold behavior)

#### Sub-task 4c: Anomaly Detection
- [ ] Check for outlier trades (P&L >10%)
- [ ] Verify all exit logic worked as expected
- [ ] Confirm no repeated price fetch failures
- [ ] Flag any unexplained trading gaps or silent failures

---

### Issue #5: Phase 4 Final Report & Recommendation 🔄 IN PROGRESS
**Deadline:** 2026-03-31 15:00 PT (Sunday 3 PM PT)

#### Sub-task 5a: Validation Report
- [ ] Execute final analysis SQL (see PHASE4_VALIDATION_CHECKLIST.md for queries)
- [ ] Produce summary table:
  ```
  Strategy         | Trades | Win Rate | Total P&L | Avg per Trade | Recommendation
  FIXED (1.0%)     | XXX    | X.X%     | $+XXX.XX  | $+X.XX        | [YES|NO]
  FEE_AWARE (0.75%)| XXX    | X.X%     | $+XXX.XX  | $+X.XX        | [RECOMMENDED] ⭐
  PAIR_SPECIFIC    | XXX    | X.X%     | $+XXX.XX  | $+X.XX        | [YES|NO]
  ```
- [ ] Decision: Which strategy to deploy in Phase 4 live trading?

#### Sub-task 5b: Documentation
- [ ] Update PHASE4_TEST_EXECUTION_PLAN.md with results
- [ ] Update THROTTLE_TEST_FINDINGS.md with 48-hour findings
- [ ] Document any parameter adjustments needed
- [ ] Create PHASE4_FINAL_RESULTS.md with full report

#### Sub-task 5c: Go/No-Go Decision
- [ ] Confidence assessment:
  - [ ] High (>100 trades, clear winner, win rate 50-70%)
  - [ ] Medium (80-100 trades, borderline winner, unusual win rate)
  - [ ] Low (insufficient data, no clear winner, anomalies)
- [ ] Recommendation: PROCEED to live ($1K allocation) OR RETEST with adjustments

---

### Issue #6: Knowledge Transfer & Code Comments ✅ IN PROGRESS
- [x] phase4_v5_simple.py fully commented with docstrings
- [x] Database schema documented (trader_configs, trades, strategy_backtest)
- [x] Fee model locked: COINBASE_FEE_RESEARCH.md referenced
- [ ] Final code review: ensure all thresholds and parameters are clear
- [ ] Reproducibility: can the test be re-run with same results?

---

## Validation Checklist (From PHASE4_VALIDATION_CHECKLIST.md)

### ✅ Data Integrity
- [ ] Database exists and is readable: phase4_trades.db
- [ ] Schema complete: trades + strategy_backtest tables
- [ ] Seed data: 6 trader_configs rows (3 strategies × 2 pairs)
- [ ] No corrupt/NULL critical fields
- [ ] Valid ISO timestamps within 48-hour window

### ✅ Trade Capture
- [ ] Minimum 80-100 trades total (high confidence)
- [ ] All three strategies generated trades
- [ ] Realistic P&L values (-5% to +5% range)
- [ ] Trade distribution aligns with expected frequencies

### ✅ Fee Model
- [ ] Entry fee = 0.25%, Exit fee = 0.25%
- [ ] FEE_AWARE threshold = 0.75%
- [ ] PAIR_SPECIFIC BTC = 0.5%, XRP = 1.5%

### ✅ Statistics
- [ ] Win rates 50-70% per strategy
- [ ] Clear winner identified (>5% margin)
- [ ] No outliers (P&L >10%)

### ✅ Documentation
- [ ] PHASE4_VALIDATION_CHECKLIST.md (scope document)
- [ ] PHASE4_FINAL_RESULTS.md (report template)
- [ ] Updated PHASE4_TEST_EXECUTION_PLAN.md
- [ ] Code reproducible and fully commented

---

## Timeline

| Date/Time | Milestone | Status |
|-----------|-----------|--------|
| 2026-03-29 14:15 PT | Test start (phase4_v5_simple.py) | ✅ DONE |
| 2026-03-29 (hourly) | Process health checks | 🔄 ONGOING |
| 2026-03-31 14:15 PT | Test completion (48h elapsed) | 🔲 PENDING |
| 2026-03-31 14:45 PT | Analysis & statistics | 🔲 PENDING |
| 2026-03-31 15:00 PT | Final report & recommendation | 🔲 PENDING |

---

## Success Criteria

✅ **Test passes if:**
1. At least 80-100 trades executed
2. All three strategies show meaningful differentiation (winner >5% better than runner-up)
3. Win rates fall in 50-70% range
4. No data corruption or unhandled errors
5. Clear winner identified with actionable Phase 4 recommendation

⚠️ **Test requires adjustment if:**
- Fewer than 80 trades (extend test or adjust entry/exit logic)
- Strategies show identical P&L (thresholds too similar to discriminate)
- Win rates >80% or <40% (market regime issue or signal problem)
- Repeated errors in logs (price fetch failures, DB issues)

---

## Phase 4b: X-Sentiment Integration (DEPENDENT) 🔴 BLOCKED

**Status:** Awaiting Phase 4 completion (will start 2026-04-02)  
**Epic:** Phase 4b — X-Sentiment Integration  
**Duration:** 48 hours (2026-04-02 ~ 2026-04-04)

### Issue #7: X-Sentiment Specification & Implementation 🔄 PLANNED
- [ ] Specification locked: PHASE4B_X_SENTIMENT_SPECIFICATION.md
- [ ] x_sentiment_fetcher.py implemented (real X API v2, NOT synthesized)
- [ ] phase4b_v1.py written (winner strategy + sentiment integration)
- [ ] Database schema updated (sentiment_score, sentiment_tweet_count, sentiment_source_ids)
- [ ] Bearer token stored in .env (NOT hardcoded)
- [ ] Code review checklist: verify real X API usage
- **Link:** PHASE4B_X_SENTIMENT_SPECIFICATION.md

### Issue #8: Phase 4b Data Validation (48-hour run) 🔄 PLANNED
**Deadline:** 2026-04-04 14:00 PT

#### Sub-task 8a: Real X API Integration
- [ ] Every cycle fetches sentiment from X API v2 (check logs for API calls)
- [ ] Sentiment scores vary realistically (not constant, not hardcoded)
- [ ] Tweet counts vary by pair (10-200 range)
- [ ] Source tweet IDs logged for audit trail
- [ ] Cache hits tracked separately from fresh fetches

#### Sub-task 8b: Sentiment Quality Assurance
- [ ] At least 100+ real X sentiment fetches (one per cycle)
- [ ] No synthetic/mock/hardcoded sentiment anywhere
- [ ] Sentiment used in entry signal logic (confirms/refutes RSI)
- [ ] X_SENTIMENT_AUDIT_LOG.md populated with full audit trail
- [ ] Can reproduce sentiment for any trade via source tweet IDs

#### Sub-task 8c: Statistical Analysis
- [ ] Compare Phase 4b win rate vs Phase 4 baseline
- [ ] Sentiment impact: expected 5-15% improvement
- [ ] Trade frequency: does sentiment reduce/filter entry signals?
- [ ] Whipsaw analysis: sentiment preventing false positives?

---

### Issue #9: Phase 4b Final Report & Go/No-Go Decision 🔄 PLANNED
**Deadline:** 2026-04-04 15:00 PT

#### Sub-task 9a: Sentiment Impact Report
- [ ] Produce comparison table: Phase 4 vs Phase 4b (win rates, P&L, sentiment effect)
- [ ] Validate X-sentiment was real (audit tweet IDs, API calls)
- [ ] Quantify improvement: X.X% win rate gain
- [ ] Recommendation: Include sentiment in live trading or not?

#### Sub-task 9b: Knowledge Transfer
- [ ] PHASE4B_X_SENTIMENT_SPECIFICATION.md remains locked and linked
- [ ] x_sentiment_fetcher.py documented and version-locked
- [ ] phase4b_v1.py fully commented (every function references spec)
- [ ] Commit message pattern established: "ref PHASE4B_X_SENTIMENT_SPECIFICATION.md"

---

## Anti-Loss Measures (X-Sentiment LOCKED)

**Why:** X-Sentiment has been lost/omitted from codebase multiple times. This is permanent.

1. **Specification Lock** — PHASE4B_X_SENTIMENT_SPECIFICATION.md is immutable, referenced in every commit
2. **Code Lock** — x_sentiment_fetcher.py is standalone module (cannot be inlined, cannot be lost)
3. **Audit Lock** — X_SENTIMENT_AUDIT_LOG.md logs every API call (proves real data)
4. **Data Lock** — Trades table schema includes sentiment_* columns (cannot be dropped)
5. **Commit Lock** — Every Phase 4b commit must reference this spec in message

**Rule:** If X-Sentiment is missing or fake in Phase 4b, the test is invalid and must restart.

---

## References

**Phase 4 (Threshold Test):**
- **Execution Plan:** `/operations/crypto-bot/PHASE4_TEST_EXECUTION_PLAN.md`
- **Validation Checklist:** `/operations/crypto-bot/PHASE4_VALIDATION_CHECKLIST.md`
- **Fee Research:** `/operations/crypto-bot/COINBASE_FEE_RESEARCH.md`
- **Code:** `/operations/crypto-bot/phase4_v5_simple.py`
- **Test Status:** `/operations/crypto-bot/TEST_STATUS.md`
- **Findings Archive:** `/operations/crypto-bot/THROTTLE_TEST_FINDINGS.md`

**Phase 4b (X-Sentiment, NEW):**
- **Specification (LOCKED):** `/operations/crypto-bot/PHASE4B_X_SENTIMENT_SPECIFICATION.md`
- **Code Modules (TBD):** `x_sentiment_fetcher.py`, `phase4b_v1.py`
- **Audit Log (TBD):** `X_SENTIMENT_AUDIT_LOG.md`
- **Integration Checklist (TBD):** `X_SENTIMENT_INTEGRATION_CHECKLIST.md`

---

## Notes for Brad

**Phase 4 (2026-03-29 → 2026-03-31):** Pure threshold test. Answers: Which exit strategy wins?

**Phase 4b (2026-04-02 → 2026-04-04):** Sentiment integration test. Answers: Does real X sentiment improve win rate?

**Key guarantee:** X-Sentiment will NOT be lost, synthesized, or omitted in Phase 4b. It is specification-locked and enforced via code review + audit trail.

**Next step (Sunday 2:15 PM PT):** Execute Phase 4 final analysis and identify winner strategy.
