# Phase 6 Task Breakdown (Updated)

**Owner:** Brad + Coding Agent  
**Status:** Planning  
**Updated:** 2026-04-21 (Added Task 0: Rebalancing)

---

## Task 0: Implement Weekly Rebalancing (NEW)

**Description:** Code correlation-aware rebalancing into phase5_multi_pair.py

**Background:** 1-year backtest shows weekly rebalancing beats monthly (+3.3% gain) and daily (fee drag). See PHASE_6_REBALANCING.md for full analysis.

**Checklist:**
- [ ] Read PHASE_6_REBALANCING.md (algorithm + results)
- [ ] Create correlation matrix calculator (30-cycle window)
- [ ] Implement rebalancing trigger (every 7 cycles = ~7 min)
- [ ] Code allocation shift logic:
  - [ ] Calculate correlation across 30-cycle price history
  - [ ] Detect high-correlation pairs (>0.7 threshold)
  - [ ] Move 50% of over-correlated allocation to reserve
  - [ ] Re-deploy from reserve based on sentiment weighting
- [ ] Add logging metrics:
  - [ ] Average correlation each cycle
  - [ ] High-correlation pair detection
  - [ ] Allocations before/after
  - [ ] Reserve level tracking
- [ ] Test with mock correlation data
- [ ] Integrate with sentiment aggregator

**Code Template:**
```python
if self.cycle_number % 7 == 0:  # Every 7 cycles
    corr_matrix = np.corrcoef(self.price_history[-30:].T)
    if np.mean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)]) > 0.7:
        high_corr_pairs = identify_correlated_clusters(corr_matrix)
        for pair in high_corr_pairs:
            shift = self.allocations[pair] * 0.5
            self.allocations[pair] -= shift
            self.reserve += shift
```

**Expected Outcome:**
- 21.5% annual return (vs 18.2% without rebalancing)
- ~52 rebalances/year (~1 per week)
- Sharpe ratio 1.58 (best risk-adjusted returns)
- 0.4% fee drag (vs 2% with daily rebalancing)

**Estimated Effort:** 3-4 hours  
**Owner:** Coding Agent  
**Priority:** HIGH (must complete before Task 3)

---

## Task 1: Validate order_executor.py

**Description:** Inspect order_executor.py to confirm production readiness

**Checklist:**
- [ ] Read full order_executor.py (17KB)
- [ ] Review API surface:
  - [ ] `execute_buy(pair, price)` signature
  - [ ] `execute_sell(pair, price)` signature
  - [ ] `get_position(pair)` signature
  - [ ] Error handling classes
- [ ] Check Coinbase integration:
  - [ ] Uses coinbase_wrapper.py
  - [ ] ES256 JWT auth (proven working)
  - [ ] Order placement API version
- [ ] Validate spend tracking:
  - [ ] Daily budget limits
  - [ ] Transaction fee accounting (0.4%)
  - [ ] Position size constraints
- [ ] Confirm checkpointing:
  - [ ] STATE.json format
  - [ ] MANIFEST.json format
  - [ ] Atomic writes
  - [ ] Backup creation
- [ ] Test with mock data:
  - [ ] Create sandbox test
  - [ ] Verify order construction
  - [ ] Check error handling
- [ ] Document integration API in comments

**Estimated Effort:** 2-3 hours  
**Owner:** Coding Agent (inspection) + Brad (approval)

---

## Task 2: Inspect portfolio_tracker.py

**Description:** Verify portfolio_tracker.py exists and is complete

**Checklist:**
- [ ] Confirm file exists: `/home/brad/.openclaw/workspace/operations/crypto-bot/portfolio_tracker.py`
- [ ] If exists:
  - [ ] Read full file
  - [ ] Map expected handoff protocol from order_executor
  - [ ] Check portfolio state schema
  - [ ] Validate P&L calculation logic
  - [ ] Test with mock portfolio data
- [ ] If missing:
  - [ ] Search for portfolio management code elsewhere
  - [ ] Decide: build new or skip for Phase 6.1
- [ ] Document findings in decision log

**Estimated Effort:** 1-2 hours  
**Owner:** Coding Agent

---

## Task 3: Wire order_executor into phase5_multi_pair.py

**Description:** Integrate order execution into signal-to-trade pipeline

**Prerequisite:** Task 0 (rebalancing), Task 1 (order_executor validation)

**Changes to phase5_multi_pair.py:**

```python
# NEW: Import order_executor
from order_executor import OrderExecutor

# NEW: Initialize executor in __init__
self.executor = OrderExecutor(
    self.cb_client,
    capital_per_pair=self.capital_per_pair,
    daily_budget=self.total_capital / 30  # Monthly/30
)

# MODIFY: _check_exit() - add SELL execution
def _check_exit(self, pair, rsi, price):
    if rsi > 70:  # TP signal
        result = self.executor.execute_sell(pair, price)
        if result.success:
            self.logger.info(f"SELL executed: {pair} @ ${price:.2f}")
        return True
    return False

# MODIFY: _execute_buy() - use executor instead of simulating
def _execute_buy(self, pair, price):
    result = self.executor.execute_buy(pair, price)
    if result.success:
        self.POSITION_MANAGER.update_position(
            pair=pair,
            entry_price=price,
            entry_qty=result.quantity,
            timestamp=datetime.utcnow().isoformat() + 'Z'
        )
        self.logger.info(f"BUY executed: {pair} qty={result.quantity:.6f}")
        return True
    else:
        self.logger.error(f"BUY failed: {pair} - {result.error}")
        return False
```

**Checklist:**
- [ ] Import OrderExecutor
- [ ] Initialize executor with proper config
- [ ] Replace mock buy execution with real
- [ ] Replace exit signals with real sell execution
- [ ] Add error handling for execution failures
- [ ] Update logging to show real vs. simulated
- [ ] Add spend tracking to state
- [ ] Test with sandbox account
- [ ] Verify position state sync after fills

**Estimated Effort:** 3-4 hours  
**Owner:** Coding Agent (implementation) + Brad (review)

---

## Task 4: Integrate portfolio_tracker.py

**Description:** Add portfolio-level tracking after order execution

**Prerequisite:** Task 2 (portfolio_tracker inspection)

**If portfolio_tracker.py exists:**

```python
# NEW: Import portfolio tracker
from portfolio_tracker import PortfolioTracker

# NEW: Initialize in __init__
self.portfolio = PortfolioTracker(initial_capital=self.total_capital)

# NEW: Update after buy execution
def _execute_buy(self, pair, price):
    result = self.executor.execute_buy(pair, price)
    if result.success:
        self.portfolio.add_position(pair, result.quantity, price)

# NEW: Update after sell execution
def _check_exit(self, pair, rsi, price):
    if should_exit:
        result = self.executor.execute_sell(pair, price)
        if result.success:
            pnl = self.portfolio.close_position(pair, result.quantity, price)
            self.logger.info(f"Position closed: P&L=${pnl:.2f}")

# NEW: Periodic portfolio snapshot (every 10 cycles)
if cycle % 10 == 0:
    snapshot = self.portfolio.get_summary()
    self.logger.info(f"Portfolio: ${snapshot['total_value']:.2f} | P&L: ${snapshot['total_pnl']:.2f}")
```

**Checklist:**
- [ ] Determine portfolio_tracker.py status (Task 2)
- [ ] If complete:
  - [ ] Import PortfolioTracker
  - [ ] Initialize with starting capital
  - [ ] Update on position opens
  - [ ] Update on position closes
  - [ ] Log portfolio snapshots
- [ ] If incomplete:
  - [ ] Document in decision log
  - [ ] Decide: build now or defer to Phase 6.2
- [ ] Test with mock data
- [ ] Verify P&L calculations

**Estimated Effort:** 2-3 hours (if complete) or 4-6 hours (if building new)  
**Owner:** Coding Agent (implementation) + Brad (scope decision)

---

## Task 5: Sandbox Testing (48-72 hours)

**Description:** Run integrated system with $100 sandbox capital

**Prerequisite:** Tasks 0-4 complete

**Setup:**
- [ ] Enable Coinbase sandbox API
- [ ] Fund sandbox account with $100 virtual capital
- [ ] Switch phase5_multi_pair.py to sandbox mode
- [ ] Log all orders to detailed CSV

**Test Protocol:**
- [ ] Run 24-hour continuous cycle
- [ ] Verify all signals generate orders
- [ ] Check order fills on Coinbase
- [ ] Validate position state persistence
- [ ] Confirm P&L calculations
- [ ] Verify rebalancing executes correctly (every 7 cycles)
- [ ] Monitor for errors/edge cases
- [ ] Run 48h more if all healthy

**Acceptance Criteria:**
- ✅ All orders execute successfully
- ✅ No position state desync
- ✅ Correct P&L calculations
- ✅ Rebalancing triggers every 7 cycles
- ✅ Correlation metrics logged correctly
- ✅ No crashes > 1 minute
- ✅ Spend tracking accurate

**Estimated Effort:** 6-12 hours (mostly monitoring)  
**Owner:** Brad (oversight) + Automation (continuous)

---

## Task 6: Live Deployment (Approval Required)

**Description:** Deploy to production with real $750 capital

**Prerequisite:** Task 5 sandbox tests passed

**Pre-Deployment Checklist:**
- [ ] All Tasks 0-5 complete and approved
- [ ] Sandbox tests passed (48h+)
- [ ] All error handling verified
- [ ] Logging at INFO level
- [ ] Daily budget enforcement working
- [ ] Rebalancing logic verified
- [ ] Brad's explicit approval on record

**Deployment Steps:**
- [ ] Switch to production Coinbase API
- [ ] Reduce capital to $250 initial allocation
- [ ] Deploy phase5_multi_pair.py (production branch)
- [ ] Monitor for 72 hours
- [ ] Check first 10-20 orders execute correctly
- [ ] Verify fills match expectations
- [ ] Scale to $750 when confident

**Monitoring (72h):**
- [ ] Check logs every 30 minutes first 24h
- [ ] Review P&L every 4 hours
- [ ] Monitor rebalancing events (should see ~7 per week)
- [ ] Verify position state stays in sync
- [ ] Alert on any execution failures

**Estimated Effort:** Ongoing (1-2h/day monitoring)  
**Owner:** Brad (deployment decision) + Automation (monitoring)

---

## Dependencies & Ordering

```
Task 0 (Rebalancing) ──────────┐
                                ├──> Task 3 (Wire into phase5)
Task 1 (Validate order_executor) ──┤
                                ├──> Task 3
Task 2 (Inspect portfolio_tracker) ┤
                                ├──> Task 4

Task 3 (Wire execution) ────────┐
                                ├──> Task 5 (Sandbox test)
Task 4 (Integrate portfolio) ───┘

Task 5 (Sandbox test) ──────────> Task 6 (Live deployment - optional)
```

**Critical Path:** Task 0 → Tasks 1,2 → Task 3 → Task 4 → Task 5 → Task 6

**Parallel Work:** Tasks 0, 1, 2 can run in parallel

---

## Decision Points

| Point | Decision | Owner | Impact |
|-------|----------|-------|--------|
| Rebalancing implemented (Task 0) | Proceed or defer? | Brad | Must complete for optimal returns |
| Portfolio tracker completeness (Task 2) | Build new or defer? | Brad | 4-6h or 2-3h |
| Sandbox duration (Task 5) | 24h, 48h, or 72h? | Brad | Thoroughness vs. speed |
| Live deployment (Task 6) | Proceed or hold? | Brad | Real capital usage |
| Capital allocation | $250 initial or $750 direct? | Brad | Risk tolerance |

---

## Success Metrics

**Phase 6 Complete When:**
- ✅ All 6 tasks finished (Task 6 optional)
- ✅ Sandbox tests passed
- ✅ Integration documentation complete
- ✅ Decision log recorded
- ✅ Git commit for final state

**Live Trading Success When:**
- ✅ 100+ live orders executed
- ✅ Zero execution failures
- ✅ Rebalancing events logged correctly (~1 per week)
- ✅ P&L tracking accurate (verified against Coinbase)
- ✅ 72h+ uptime without crashes
- ✅ Position state always in sync
- ✅ 21.1% annual return (net of fees) achieved on 90-day rolling basis
