# Inter-Session Messaging for Modules 6-8

**Goal:** Enable real-time collaboration between Order Executor, Portfolio Tracker, and Unit Tests

---

## Architecture

```
Module 6 (Order Executor)
  ↓ sessions_send("module-7-portfolio")
  └→ "Executed 70 orders. Portfolio state: ..."

Module 7 (Portfolio Tracker)  
  ↓ receives live order data
  ├→ calculates P&L immediately
  └→ sessions_send("module-8-tests")
     └→ "Portfolio complete. Ready for validation."

Module 8 (Unit Tests)
  ↓ receives readiness signal
  ├→ runs pytest suite
  └→ validates Modules 5-7 outputs via sessions_history
```

---

## Pattern 1: Output Handoff (Module 6 → Module 7)

**Module 6 (Order Executor) — End of execution:**

```python
import json
from sessions_send import sessions_send  # OpenClaw tool

# After execute_all_signals() completes:
results = executor.execute_all_signals()
execution_summary = {
    "total_signals": len(signals),
    "buy_orders": sum(1 for r in results if r.signal_type == "BUY" and r.status != "FAILED"),
    "sell_orders": sum(1 for r in results if r.signal_type == "SELL" and r.status != "FAILED"),
    "failed_orders": sum(1 for r in results if r.status == "FAILED"),
    "total_usd_executed": sum(r.quantity * r.price_executed for r in results if r.price_executed),
    "order_ids": [r.order_id for r in results if r.order_id],
    "timestamp": datetime.utcnow().isoformat() + "Z"
}

# Send to Module 7 (Portfolio Tracker)
sessions_send(
    label="module-7-portfolio-tracker",
    message=f"Order execution complete. Summary: {json.dumps(execution_summary, indent=2)}"
)

print("✅ Handoff to Module 7 sent. Awaiting portfolio calculation...")
```

**Module 7 (Portfolio Tracker) — Startup:**

```python
# Module 7 receives message automatically (OpenClaw routes it)
# Process it like normal input

def track_portfolio(order_execution_message):
    """
    Receives message from Module 6:
    "Order execution complete. Summary: {...}"
    """
    # Parse the order summary
    import json
    summary_text = order_execution_message.split("Summary: ")[1]
    order_summary = json.loads(summary_text)
    
    # Calculate portfolio state
    portfolio = {
        "btc_holdings": order_summary["buy_orders"] * (50 / get_price("BTC-USD")),
        "cash_remaining": 10000 - order_summary["total_usd_executed"],
        "order_count": order_summary["total_signals"],
        "execution_rate": (order_summary["buy_orders"] + order_summary["sell_orders"]) / order_summary["total_signals"],
        "failed_rate": order_summary["failed_orders"] / order_summary["total_signals"]
    }
    
    return portfolio
```

---

## Pattern 2: Readiness Signal (Module 7 → Module 8)

**Module 7 (Portfolio Tracker) — End of execution:**

```python
# After portfolio tracking complete:
portfolio_state = track_portfolio_complete()

# Signal Module 8 that we're ready
sessions_send(
    label="module-8-unit-tests",
    message=f"Portfolio tracking complete. {len(portfolio_state['orders'])} orders tracked, P&L calculated. Ready for unit tests."
)

print("✅ Module 8 notified. Tests can now begin...")
```

**Module 8 (Unit Tests) — Startup:**

```python
# Module 8 receives readiness signal
# Knows it can safely run because Modules 5-7 are complete

def run_full_test_suite():
    """
    Triggered by message from Module 7:
    "Portfolio tracking complete. X orders tracked, P&L calculated. Ready for unit tests."
    """
    
    # All prior modules are complete
    pytest.main([
        "tests/test_signal_generator.py",
        "tests/test_order_executor.py",
        "tests/test_portfolio_tracker.py",
        "-v", "--tb=short"
    ])
```

---

## Implementation Checklist

### Module 6 (Order Executor)

- [ ] Add `import json` and datetime
- [ ] At end of `execute_all_signals()`, build `execution_summary` dict
- [ ] Call `sessions_send(label="module-7-portfolio-tracker", message=...)`
- [ ] Log successful handoff
- [ ] Commit to git

### Module 7 (Portfolio Tracker)

- [ ] Add startup logic to receive message from Module 6
- [ ] Parse order execution summary from message
- [ ] Use summary data to initialize portfolio state
- [ ] Calculate P&L based on order data
- [ ] At end, call `sessions_send(label="module-8-unit-tests", message=...)`
- [ ] Commit to git

### Module 8 (Unit Tests)

- [ ] Add startup logic to receive readiness signal from Module 7
- [ ] Wait for message before running tests (or run immediately if message received)
- [ ] Run full pytest suite
- [ ] Report results
- [ ] Commit to git

---

## Execution Flow (with messaging)

1. **Module 6 spawns** (order executor)
   - Executes 70 orders
   - Sends: "Order execution complete. BUY: 40, SELL: 30, FAILED: 0"
   
2. **Module 7 spawns in parallel** (portfolio tracker)
   - Waits for Module 6's message
   - Receives: "Order execution complete..."
   - Calculates P&L: +$500, portfolio value: $10,500
   - Sends: "Portfolio complete. P&L: +$500, ready for tests"
   
3. **Module 8 spawns in parallel** (unit tests)
   - Waits for Module 7's message
   - Receives: "Portfolio complete..."
   - Runs pytest (all 3 modules' tests)
   - Reports: "All 66 tests passing"

**Time saved:**
- Sequential (old): 6 + 7 + 8 = 15 min total
- Parallel (new): 6 (then 7 & 8 together) = ~9 min total
- **Savings: ~6 minutes** (40% faster)

---

## Error Handling

**If Module 6 fails:**
- Message: "Order execution FAILED. Error: rate limit exceeded. 0 orders executed."
- Module 7 receives failure signal, aborts gracefully
- Module 8 notified to skip portfolio tests

**If Module 7 receives partial data:**
- Works with what it has
- Logs warning: "Received 40 orders instead of expected 70"
- Continues (robustness)

---

## Security Notes

- **No credentials exposed** — Messages contain only data summaries, no API keys
- **Audit trail** — Full conversation logged by OpenClaw
- **Resumability** — Module 7 can query `sessions_history(module-6)` to get full order data if needed

---

## Benefits Summary

| Feature | Without Messaging | With Messaging |
|---------|-------------------|-----------------|
| Parallelization | Sequential (slow) | True parallel (fast) |
| Error handling | Files only (brittle) | Live signals (robust) |
| Audit trail | File timestamps | Full conversation |
| Debuggability | Read files manually | Query any session |
| Resilience | Restart from 0 | Resume from checkpoint + message |
| Time (6+7+8) | ~15 min | ~9 min |

