# Handoff Document: Paper Trading Test Harness (t_c2d9c000)

**Task:** t_c2d9c000 — Build end-to-end paper trading test harness for Phase 6  
**Assignee:** crypto-engineer  
**Priority:** 9

## Objective
Create a runnable, configurable paper trading harness that validates the full Phase 6 pipeline in a safe environment before live deployment. The harness should exercise sentiment (with TextBlob + staleness), allocation, rebalancing, Fresh Start, error handling, and monitoring.

## Scope

### In Scope
- Main harness script (`scripts/phase6/paper_trading_harness.py`)
- Support for `dry-run`, `paper`, and `shadow` modes
- Integration with:
  - `sentiment_scorer.py` (TextBlob + staleness)
  - `allocation_engine.py`
  - `phase6_runner.py` (rebalance loop)
  - State persistence (`phase6_state.json`)
- Configurable tick interval and duration (for 48h simulations)
- Logging + summary report at the end
- Basic error injection / resilience testing

### Out of Scope
- Live trading execution
- Real exchange API calls (use shadow/paper simulation)
- Advanced monitoring dashboard (separate task)
- Full backtesting engine

## Success Criteria
- Harness can run for N ticks without crashing
- Correctly applies sentiment-adjusted weights
- Properly handles Fresh Start when no positions exist
- Logs all important events (rebalances, sentiment scores, errors)
- Produces a clean end-of-run summary
- Easy to configure via CLI args or config file

## Key Components to Implement

1. **Harness Orchestrator**
   - Main loop with configurable interval
   - Mode switching (dry-run / paper / shadow)

2. **Sentiment Integration**
   - Call `load_sentiment_scores()` with staleness
   - Apply `get_sentiment_adjusted_weights()`

3. **Rebalance Simulation**
   - Trigger `_perform_daily_rebalance()` style logic
   - Track virtual positions and P&L

4. **State Management**
   - Load/save `phase6_state.json`
   - Handle restarts gracefully

5. **Reporting**
   - End-of-run summary (positions, trades, errors, sentiment impact)
   - Optional CSV/JSON export

## Files to Create / Modify

- **New:**
  - `scripts/phase6/paper_trading_harness.py`
  - `scripts/phase6/harness_config.yaml` (example config)

- **Reference / Modify if needed:**
  - `phase6/core/phase6_runner.py`
  - `phase6/core/allocation_engine.py`
  - `phase6/core/sentiment/sentiment_scorer.py`

## Verification Steps

1. Run harness in `dry-run` mode for 20 ticks
2. Verify sentiment scores are being applied
3. Confirm Fresh Start logic triggers correctly
4. Check that state is persisted between runs
5. Review end-of-run report for accuracy

## Notes
- Keep the harness lightweight and easy to run locally
- Use existing Phase 6 modules rather than duplicating logic
- Make configuration explicit (CLI + YAML)

---
**Owner:** crypto-engineer  
**Status:** Ready for implementation