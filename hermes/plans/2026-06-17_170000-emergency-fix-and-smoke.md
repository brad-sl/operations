# Emergency Risk/Liquidation Fix Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fix critical Stop-Loss and Liquidation issues, and implement a robust E2E smoke test that captures diagnostics.

**Architecture:**
- Fix `StopLossManager` precision formatting (price formatting issue).
- Patch `ExchangeWrapper` to support valid `get_order`/`cancel_order` requests.
- Create a `RobustSmokeTest.py` that executes a mock cycle and logs full diagnostic traces.

---

### Task 1: Fix SL Precision & API wrapper
**Objective:** Correct price formatting in `StopLossManager` and ensure correct endpoint communication.

**Files:**
- Modify: `projects/crypto-trading-bot/phase6/core/stop_loss_manager.py` (ensure correct decimal handling)
- Modify: `projects/crypto-trading-bot/projects/crypto-trading-bot/coinbase_advanced_client.py` (ensure order reconciliation methods are functional)

### Task 2: Implement Robust Smoke Test
**Objective:** Build a test harness that logs every error to a diagnostic file.

**Files:**
- Create: `projects/crypto-trading-bot/projects/crypto-trading-bot/tests/RobustSmokeTest.py`

```python
import logging
logging.basicConfig(filename='smoke_test.log', level=logging.ERROR)

def run_diagnostic_cycle():
    try:
        # Run liquidation and SL attachment flow
        # Log any exceptions to smoke_test.log
    except Exception as e:
        logging.error(f"Smoke Test Failed: {e}", exc_info=True)
```

### Task 3: Execution & Verification
**Objective:** Run diagnostic smoke test and verify position audit capabilities.

**Files:**
- Run: `python3 projects/crypto-trading-bot/projects/crypto-trading-bot/tests/RobustSmokeTest.py`

---

Plan complete. Ready to execute using `subagent-driven-development` — I'll dispatch a fresh subagent per task with two-stage review. Shall I proceed?
