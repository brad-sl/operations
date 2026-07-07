# Long-Term Strategy Evaluation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Simulate 6-12 months of trading data to evaluate the P&L impact of three scoring modes ("oversold", "bullish", "hybrid").

**Architecture:**
- Create a backtest runner that iterates over historical price data.
- Maintain a virtual ledger for each mode to track cumulative P&L.
- Log trades and performance metrics for comparison.

**Tech Stack:** Python 3.11, pandas (if installed), matplotlib (optional)

---

### Task 1: Setup Backtest Simulation Harness
**Objective:** Create a script to simulate trades over longer datasets (e.g., 6 months).

**Files:**
- Create: `projects/crypto-trading-bot/backtests/simulate_long_term.py`

**Step 1: Implement Ledger Simulation Logic**
```python
# pseudo-structure
def run_simulation(mode):
    portfolio = {"balance": 10000, "positions": {}}
    for timestamp, price_data in historical_data:
        score = score_opportunity(..., mode=mode)
        # Apply trading logic: Buy if score > threshold, sell/TP/SL logic
    return portfolio
```

### Task 2: Data Preparation
**Objective:** Ensure enough historical price data for the simulation.

**Files:**
- Check: `projects/crypto-trading-bot/projects/crypto-trading-bot/data/` (or similar)

**Step 1: Data Gathering**
Ensure we have at least 180 days of candle data for the pairs in `FIXED_UNIVERSE`.

### Task 3: Execution and Comparison
**Objective:** Run the simulation for all modes and report results.

**Files:**
- Modify: `projects/crypto-trading-bot/backtests/simulate_long_term.py`

**Step 1: Execute**
Run: `python3 projects/crypto-trading-bot/backtests/simulate_long_term.py --run-all-modes`

**Step 2: Analysis**
Compare final portfolio balances, total trades, win rate, and drawdown.

---

Plan complete. Ready to execute using `subagent-driven-development` — I'll dispatch a fresh subagent per task with two-stage review. Shall I proceed?
