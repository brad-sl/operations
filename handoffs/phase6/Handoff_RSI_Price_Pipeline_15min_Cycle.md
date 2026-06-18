# Handoff Document: RSI / Price Signal Pipeline (Decoupled + 15min Cycle Optimization)

**Task ID**: RSI-SENT-002 (from RSI_SENTIMENT_RELIABILITY_PLAN.md)  
**Priority**: P0-Critical  
**Created**: 2026-06-11  
**Owner**: Autonomous execution (Scotty)  
**Status**: Ready for implementation (Phase 2 of plan)  
**Related**: User question on 15min candles vs 60s cycle; overall RSI freshness in plan.

## Objective
Create a **decoupled, reliable, rate-efficient** price history + RSI computation pipeline that is independent of the main trading runner loop. 

Directly address: 
- "If we are using 15 min. candles, would a 15 min. cycle be adequate?" → **Yes**. Design the pipeline around 15m granularity for RSI(14).
- Reduce API calls significantly while maintaining signal quality for rebalancing, signals, and allocation.
- Establish canonical PriceHistoryManager + RSI cache as single source of truth.

## Background / Root Causes (from Audit + Plan)
- Current: RSI updates tied to runner's 60s cycle (`_update_price_history_and_calculate_rsi` in phase6/core/phase6_runner.py). Mixes frequent spot `get_price()` + conditional 15m candle fetches only when history short. Falls back to accumulated spots.
- Specs (PHASE_5_1_REBALANCE + REBALANCING): Fresh prices + RSI every cycle for signals; prefer 15m candles.
- But 15m candles only meaningfully update RSI on bar close. 60s polling with same bar = wasted calls + no new RSI info.
- Exchange client `get_recent_prices(granularity=900)` already supports 15m and has in-mem caching + rate-limit note.
- PriceHistoryManager exists (`phase6/core/price_history_manager.py`) with persist to `data/state/price_history.json` (currently populated, 8kB as of 2026-06-11).
- Runner often fails (exchange errors), leaving stale RSI in live_state.
- No dedicated script or Hermes cron for prices/RSI.
- Rebalancer (HybridRebalancer) is a consumer (via evaluate() which pulls sentiment; RSI via runner state/signals).

**Answer to user question (to be implemented here)**: 
A dedicated 15-minute cycle for 15m-candle-based RSI is **adequate and strongly recommended**. 
- New RSI value is only produced when a new 15m bar arrives.
- Reduces calls from ~60/hour (current) to 4/hour per pair (or batched).
- Runner can still fetch lightweight spot prices more frequently (for "current_price" in positions/rebalance) without full RSI recompute.
- Hybrid: Dedicated pipeline owns canonical RSI + history for signals/rebalance; runner consumes read-only.

## Must Do
1. Create dedicated refresh script: `scripts/refresh_rsi_prices.py` (or `phase6/scripts/refresh_price_history.py`).
   - Uses `PriceHistoryManager` (canonical).
   - Batch or efficient fetch across FIXED_UNIVERSE using exchange client's public 15m candle path (`get_recent_prices(..., granularity=900, limit=30+)`).
   - Compute RSI(14) on the candle closes when new bar available.
   - Update canonical `data/state/price_history.json` + write `data/state/rsi_cache.json` (with pair, rsi, timestamp, age_minutes, source="15m_candles", candle_count).
   - Support incremental: only fetch since last known bar if possible.
   - Rate-limit safe: respect any existing caches in exchange_client; add sleeps/backoff if needed; log #calls.
2. Schedule via Hermes cron: 15-minute or "every 15min" job calling the script (no_agent=True, script-based for reliability).
3. Update `phase6/core/price_history_manager.py` if needed for better 15m bar awareness or multi-gran support.
4. Modify runner to **consume** the new canonical RSI cache (read-only) instead of (or in addition to) computing inline. Remove or deprecate heavy candle logic from main loop. Keep lightweight spot price for live prices.
5. Update HybridRebalancer / signal paths to read fresh RSI from canonical (confirm it already pulls via runner state).
6. Add strong staleness: If last RSI update >30min, log warning + fall back to conservative (e.g., RSI=50).
7. **Code Isolation Test**: `phase6/core/test_isolation.py` or new `tests/test_rsi_pipeline_isolation.py`.
   - Mock exchange to return controlled 15m candles.
   - Verify: RSI computed correctly on new bars; no unnecessary calls; persist works; stale handling.
8. Update relevant specs/docs if cycle changes (note 15m for RSI is intentional optimization).
9. Ensure real data only; update live_state.json with fresh RSI values (runner or dedicated writer).
10. Log metrics: calls made, bars processed, RSI values, freshness.

## Must Not Do
- Do not keep heavy 15m candle fetching inside the 60s runner loop for RSI computation.
- Do not fabricate RSI values (use prior or neutral on failure).
- Do not break existing PriceHistoryManager persist or runner spot price usage without migration.
- Avoid new external deps.

## Files in Scope
- New: `scripts/refresh_rsi_prices.py` (or phase6/scripts/)
- Modify: `phase6/core/phase6_runner.py` (consume only, reduce _update_... logic)
- Modify: `phase6/core/price_history_manager.py` (enhance if needed for 15m)
- Modify: `phase6/core/exchange_client.py` (ensure batch-friendly 15m path, improve logging)
- Modify: `phase6/core/rebalancing/hybrid_rebalancer.py` (if direct RSI access needed)
- Test: `phase6/core/test_isolation.py` or dedicated isolation test
- Config/Cron: Hermes jobs via cronjob tool or jobs.json
- Docs: Update plan + MASTER_TASK_TRACKING.md

## Integration Points (Shared Consumers)
- **Runner**: Primary consumer for signals (SignalGenerator already takes RSI).
- **HybridRebalancer**: Yes — confirmed consumer (evaluates rebalance using state that includes RSI-derived signals + sentiment). Must get fresh RSI.
- Reports, dashboards, allocation_engine, backtests/paper harness.
- Future Signal Provider.

## Success Criteria
- Dedicated script runs cleanly, produces correct RSI(14) from 15m candles (verified by isolation test + manual run).
- Hermes cron job active at ~15min interval; cache updated with fresh timestamps.
- Runner consumes canonical RSI (logs show "loaded from cache" or similar); no more inline 15m fetches every 60s for RSI.
- API calls for 15m data reduced ≥10x in normal operation.
- live_state.json and reports show fresh RSI values (age <20min).
- Rebalancer receives updated RSI context (via state or direct).
- Isolation test passes (realistic candle data → correct RSI, persist roundtrip, stale fallback).
- No breakage to existing spot price or position tracking.

## Standing Constraints
- Real data only (Coinbase public candles or live).
- Rate-limit safe (document calls per run).
- Align with SENTIMENT_SYSTEM_SPEC style (standalone, cache + staleness first-class).
- Update Master Task Tracking List upon completion.

## References
- RSI_SENTIMENT_RELIABILITY_PLAN.md (Phases 1-3, 15min cycle question, shared consumers section)
- phase6/specs/PHASE_5_1_REBALANCE_FEATURE_SPEC.md (per-cycle prices/RSI, 15m preference)
- phase6/core/phase6_runner.py (_update... and _run_cycle)
- phase6/core/price_history_manager.py + current data/state/price_history.json
- phase6/core/exchange_client.py (get_recent_prices with granularity)
- phase6/core/rebalancing/hybrid_rebalancer.py
- Prior handoffs: GAP-002 (SignalGenerator)

## Deliverables
1. Working `refresh_rsi_prices.py` + 15min Hermes cron.
2. Updated runner consumption path.
3. Passing Code Isolation Test + manual verification run output.
4. Updated live data in caches/state.
5. Master list entry + plan doc update.
6. Brief handoff completion note.

**Next after this handoff**: Proceed to Sentiment handoff (RSI-SENT-003) or full Phase 0 audit completion.

**Verification Command Example**:
```bash
python scripts/refresh_rsi_prices.py --dry-run
# Then check data/state/rsi_cache.json and price_history.json freshness
```

Ready for sub-agent or direct implementation. Provide context from this handoff + plan.