# 🚀 PHASE 3: PAPER TRADING TRIAL — EXECUTION PLAN

**Status:** ✅ **APPROVED** (2026-03-23 13:46 PT)  
**Duration:** 24-48 hours  
**Objective:** Validate signal generation + order execution + P&L tracking in sandbox

---

## Pre-Flight Checklist (Today)

### 1. Environment Validation (5 min)
- [ ] Verify .env sandbox configuration
  ```bash
  grep "SANDBOX_MODE" .env  # Should be: true
  grep "ORDER_SIZE_USD" .env  # Should be: 50.0
  grep "COINBASE" .env  # Should be sandbox API keys
  ```

### 2. Checkpoint Validation (10 min)
- [ ] Run checkpoint test with 5 mock signals
  ```bash
  cd /home/brad/.openclaw/workspace/operations/crypto-bot
  python -c "
  from checkpoint_manager import CheckpointManager
  cm = CheckpointManager('test-session', 'order_executor', '/tmp/test_checkpoint', 5)
  for i in range(5):
    cm.mark_complete(i, {'result': f'Signal {i} executed'})
  final = cm.finalize()
  print('✅ Checkpoint validation passed')
  "
  ```
  - Verify: STATE.json, MANIFEST.json, RECOVERY.md created
  - Verify: No API keys in files

### 3. Sandbox Mode Enforcement (5 min)
- [ ] Test live trading block
  ```python
  from coinbase_wrapper import CoinbaseWrapper
  try:
    wrapper = CoinbaseWrapper("key", "secret", "pass", sandbox=False)
    wrapper.create_order("BTC-USD", "buy", "market", 50000.0, 0.001)
  except SystemExit as e:
    print(f"✅ Live trading blocked: {e}")
  ```

### 4. Mock Execution Test (10 min)
- [ ] Run Order Executor with 10 mock signals
  ```bash
  cd /home/brad/.openclaw/workspace/operations/crypto-bot
  python order_executor.py  # Uses mock signals, sandbox=True
  ```
  - Verify: 10 signals processed
  - Verify: No errors in execution
  - Verify: Handoff to Module 7 printed

---

## Phase 3 Execution (24-48 Hours)

### Day 1: Setup + Initial Execution (4 hours)

**13:30 PT - Spawn Order Executor with $1K Portfolio**

1. Create sandbox trading environment
   ```python
   from order_executor import OrderExecutor
   from coinbase_wrapper import CoinbaseWrapper
   from signal_generator import SignalGenerator
   
   # Initialize components
   wrapper = CoinbaseWrapper(
       api_key=os.getenv("COINBASE_SANDBOX_KEY"),
       private_key=os.getenv("COINBASE_SANDBOX_SECRET"),
       passphrase=os.getenv("COINBASE_PASSPHRASE"),
       sandbox=True
   )
   
   signal_gen = SignalGenerator(
       rsi_period=14,
       stochastic_period=3,
       x_sentiment_weight=0.3,
       rsi_weight=0.7
   )
   
   executor = OrderExecutor(
       signals=signal_gen.generate_signals(50),
       coinbase_wrapper=wrapper,
       product_id="BTC-USD",
       order_size_usd=50.0,
       sandbox_mode=True
   )
   
   results = executor.execute_all_signals()
   ```

2. Monitor execution
   - Print execution summary
   - Verify: Orders created in Coinbase sandbox
   - Verify: Checkpoint files written
   - Verify: Handoff to Module 7 sent

**Metrics to track:**
- Total signals processed
- BUY/SELL/HOLD distribution
- Success rate (failed_orders / total)
- Total USD executed
- Transaction costs

### Day 2: Monitoring + Recovery Test (4 hours)

**Morning (10:00 AM PT):**

1. **Portfolio Status Check**
   - Read current portfolio balance
   - Calculate P&L (buys vs sells)
   - Verify FIFO position accounting
   - Inspect checkpoint state

2. **Signal Accuracy Analysis**
   - Review generated signals (RSI values, sentiment scores)
   - Compare against real BTC price movements
   - Document confidence scores
   - Note any anomalies

3. **Checkpoint Recovery Test (Optional)**
   - Intentionally stop execution mid-run
   - Inspect STATE.json / MANIFEST.json
   - Resume from checkpoint
   - Verify: No duplicate orders, no data loss

**Afternoon (14:00 PT):**

1. **Generate Phase 3 Report**
   - Final portfolio value
   - P&L summary (realized + unrealized)
   - Signal quality analysis
   - Error handling review
   - Checkpoint reliability confirmation

2. **Issues Log**
   - Document any problems encountered
   - Categorize by severity (Critical / High / Medium / Low)
   - Propose fixes or workarounds

---

## Success Criteria

### Critical (Blocking)
- ✅ No crashes during execution
- ✅ Orders execute without errors
- ✅ Checkpoint files created + valid
- ✅ P&L calculations accurate
- ✅ No fund-at-risk issues detected

### High (Important)
- ✅ Signal generation reasonable (RSI 0-100, sentiment -1 to +1)
- ✅ Order execution completes within 30 seconds per signal
- ✅ Portfolio balance tracked correctly
- ✅ Checkpoint recovery works if tested

### Medium (Nice-to-Have)
- ✅ Performance: <500ms per signal execution
- ✅ Cost tracking: Order fees calculated correctly
- ✅ Documentation: All outputs human-readable

---

## Monitoring Dashboard (Real-Time)

**Watch these files during execution:**

1. **STATE.json** (update every checkpoint)
   ```json
   {
     "progress": { "completed": 10, "failed": 0, "pending": 40 },
     "costs": { "totalCost": 500.50 },
     "recovery": { "resumePoint": "Task 10 of 50" }
   }
   ```

2. **MANIFEST.json** (final outputs)
   ```json
   {
     "outputs": {
       "completed": [
         { "taskIndex": 0, "output": { "order_id": "...", "status": "FILLED" } },
         ...
       ]
     }
   }
   ```

3. **RECOVERY.md** (human-readable status)
   ```markdown
   - Progress: 10/50 tasks (20%)
   - Status: in_progress
   - Estimated Time Remaining: 12m 30s
   ```

---

## Rollback Plan (If Issues Found)

### Scenario 1: Order Execution Failure
- **Detected:** >50% failed orders or repeated error pattern
- **Action:** Pause execution, inspect error logs
- **Recovery:** Fix Coinbase wrapper issue, restart from checkpoint
- **Escalation:** Escalate to Brad if can't resolve

### Scenario 2: Checkpoint Corruption
- **Detected:** STATE.json invalid JSON or missing fields
- **Action:** Inspect RECOVERY.md + MANIFEST.json for consistency
- **Recovery:** Roll back to last valid checkpoint (30 sec prior)
- **Escalation:** If multiple failures, disable checkpointing + restart

### Scenario 3: P&L Calculation Error
- **Detected:** Realized PnL doesn't match manual calculation
- **Action:** Inspect portfolio_tracker.py FIFO logic
- **Recovery:** Manual audit of all trades + recalculate
- **Escalation:** Hold trading until root cause fixed

### Scenario 4: Sandbox Mode Bypass
- **Detected:** Live orders appear in Coinbase account
- **Action:** IMMEDIATE STOP — Contact Brad
- **Recovery:** Manual reversal of live orders (if any)
- **Escalation:** CRITICAL — Security review required

---

## Phase 3 → Phase 4 Transition Criteria

**Must be true before proceeding to live trading:**

1. ✅ Paper trading trial completed successfully (24-48 hours)
2. ✅ No crashes, data loss, or fund-at-risk issues
3. ✅ P&L calculations verified accurate
4. ✅ Checkpoint recovery tested + working
5. ✅ Signal quality meets expectations (80%+ accuracy)
6. ✅ All issues documented + resolved
7. ⏳ Ed25519 signing implemented (not HMAC)
8. ⏳ Approval gating Stage 1-4 implemented
9. ⏳ Live trading security audit passed
10. ✅ Brad sign-off received

---

## Key Contacts / Escalation

- **Issues/Bugs:** Check Phase 3 Report
- **Critical Problems:** Notify Brad immediately
- **Questions:** Reference PHASE_2_COMPLETION_REPORT.md + test coverage

---

## Timeline Summary

| Phase | Start | Duration | Status |
|-------|-------|----------|--------|
| Pre-Flight | Today 13:47 PT | 30 min | ✅ Ready |
| Paper Trading Day 1 | Today 14:00 PT | 4 hours | ⏳ Pending |
| Monitoring Day 2 | Tomorrow 10:00 PT | 4 hours | ⏳ Pending |
| Analysis + Report | Tomorrow 18:00 PT | 1 hour | ⏳ Pending |
| Sign-Off + Transition | Tomorrow 19:00 PT | TBD | ⏳ Pending |

**Expected Completion:** 2026-03-24 ~19:00 PT

**Next Phase (Phase 4):** Security audit + live trading approval (pending Phase 3 success)

---

**Ready to proceed? ✅**
