# Handoff: RSI Pipeline Restoration (Phase 6)

**Task ID**: RSI-001  
**Priority**: High (Core signal engine regression)  
**Created**: 2026-06-04  
**Owner**: TBD (orchestrator or crypto-engineer)  
**Status**: Ready for implementation

---

## Goal

Restore the **RSI-driven signal generation** as the primary driver of trading decisions in Phase 6, with sentiment as a supplementary conviction layer. This reverses the current regression where only the sentiment pipeline is active.

The system must align with the documented architecture in `docs/TRADING_BOT_DOCS.md` (Phase 6.01 section):

> "Uses RSI-based signals (< 30 BUY, > 70 SELL)"  
> Flow: Fetch prices → Update price history → Calculate RSI → Generate signals → Load sentiment (supplement)

---

## Background & References

**Source Documents:**
- `docs/TRADING_BOT_DOCS.md` — Phase 6.01 architecture and 10-step cycle (lines 122–139)
- `phase5_multi_pair.py` — Original `_calculate_rsi()`, `_get_sentiment()`, and `_determine_trade_signal()` (lines 193–282)
- `src/indicators/rsi.py` — Cleaner numpy implementation with proper Wilder smoothing + Stochastic RSI support
- `indicators/dynamic_rsi_strategy.py` — Weighted signal approach (60% sentiment + 40% RSI)

**Current State:**
- Sentiment cron + `run_sentiment_system.py` is working.
- No price history buffer exists in `phase6/core/phase6_runner.py`.
- No RSI calculation step exists.
- Trading Intelligence Report falls back to stale "last known" RSI values.

---

## Must Do

1. Create a clean `PriceHistoryManager` (or integrate into runner) that:
   - Maintains last 50–100 prices per pair in memory.
   - Persists to `data/state/price_history.json` on shutdown / periodic flush.
   - Provides `add_price(pair, price)` and `get_prices(pair, n=50)` methods.

2. Integrate RSI calculation using `src/indicators/rsi.py:calculate_rsi()` (preferred over the basic version in Phase 5.1).

3. Implement signal generation where **RSI is primary**:
   - Oversold (`RSI < 30`) → bullish bias
   - Overbought (`RSI > 70`) → bearish bias
   - Use Stochastic RSI (`calculate_stochastic_rsi()`) optionally for entry timing.

4. Use sentiment as a **conviction multiplier** (recommended improvement):
   - Example: `final_score = rsi_signal * (1.0 + sentiment * 0.4)`
   - Or adjust buy/sell thresholds based on sentiment strength.
   - Avoid the strict Phase 5.1 "AND gate" unless backtesting proves it superior.

5. Expose current RSI values (and optionally Stochastic %K/%D) to:
   - `data/state/phase6_live_state.json` (for dashboard)
   - Trading Intelligence Report
   - `/api/rsi` or similar endpoint if needed.

6. Update `run_sentiment_system.py` cron or create a combined `run_technical_intelligence.py` that runs every 30 minutes alongside sentiment.

7. Add logging of RSI values and final signal per cycle.

---

## Must Not Do

- Do **not** use mock or random price data in live mode.
- Do **not** keep price history only in-memory without persistence (risk of losing history on restart).
- Do **not** re-implement the overly strict Phase 5.1 AND-gate logic without explicit approval.
- Do **not** bypass the existing `sentiment_cache.json` — sentiment should still be read from there.

---

## Suggested Improvements (Open for Discussion)

- Use **Stochastic RSI** for better-timed entries (already implemented in `src/indicators/rsi.py`).
- Maintain a rolling 100-price buffer per pair (instead of 15–20).
- Add ATR or volatility context later (future enhancement).
- Make signal thresholds configurable via `config.yaml` or environment variables.
- Store RSI history alongside price history for dashboard charting.

---

## Success Criteria

- After implementation, a full cycle produces non-neutral RSI values for the 6 pairs.
- Trading Intelligence Report shows fresh RSI numbers instead of "No fresh RSI in cache".
- `phase6_live_state.json` contains `rsi` and optionally `stoch_rsi_k` / `stoch_rsi_d` fields.
- Signals are generated primarily from RSI, with sentiment visibly influencing conviction.
- No regression in existing sentiment or dashboard functionality.

---

## Files to Touch / Create

**New:**
- `phase6/core/price_history_manager.py` (recommended)
- `phase6/core/rsi_calculator.py` (thin wrapper around `src/indicators/rsi.py`)

**Modify:**
- `phase6/core/phase6_runner.py` — integrate price history + RSI calculation into `_run_cycle()`
- `run_sentiment_system.py` or new `run_technical_intelligence.py` — scheduling
- `serve_dashboard.py` — optional new `/api/rsi` endpoint
- `docs/MASTER_TASK_TRACKING.md` — add RSI-001 task

**Reference (read-only):**
- `src/indicators/rsi.py`
- `phase5_multi_pair.py` (for original logic)

---

## Validation Steps

1. Run a manual cycle and verify RSI values appear in logs and cache.
2. Confirm Trading Intelligence Report shows fresh RSI.
3. Restart runner — price history should survive via the JSON snapshot.
4. Dashboard reflects RSI-influenced state (future visual).

---

## Notes for Implementer

The user is open to improvements over the Phase 5.1 version. The conservative AND-gate approach was likely too restrictive. A weighted or multiplier approach is preferred unless backtesting shows otherwise.

This task restores the **core identity** of the bot (RSI primary) while modernizing the implementation.