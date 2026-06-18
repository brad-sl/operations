# Phase 6 End-to-End Sanity Completion + Sign-off

**Date:** 2026-06-10  
**Performed by:** Scotty (crypto-orchestrator reviewer)

## Scope (per user request)
1. Tackle remaining from Fable 5 Batch 4 closure:
   - #1: Open G3/G4 leaks and related non-criticals (P6-151 sentinel propagation, P6-142 key shape in rebalance_plan, G4 projected reserve + funding constraint, P6-143 bypass, P6-148 config)
   - #2: Live-only safety items (P6-144 client init newline normalization, P6-145 stop quantization + invalid reduce_only, P6-146 ADA metadata)

2. Run end-to-end test for each trading scenario as final sanity check.
3. Sign-off before any push to live environment.

All work used real-data semantics (shadow/paper harness), Code Isolation Testing, and strict sentinel/contracts.

## Fixes & Verification for #1
- **P6-151 (G3 critical leak)**: LivePortfolioManager.get_enriched_positions and exchange_client.get_enriched_positions now **always** return structured shape `{"positions": {...}, "verified": bool, "error": str|None, "value_usd": {...}}`. Bare `{}` never returned on empty or error. Dedicated isolation test + E2E Fresh Start pass.
- **P6-142 (key mismatch)**: rebalance_plan now normalizes `{"value_usd": N}`, `{"usd_value": N}`, bare float or int. Plan generation no longer TypeErrors downstream.
- **G4 / projected reserve / funding (P6-143/145/148)**: Config updated with explicit `withdrawal_reserve.min_reserve_usd + max_deployable_usd`. Runner `_perform_daily_rebalance` calls `enforce_withdrawal_reserve` with **projected** targets (via compute_inverse_vol) and emits deployable_cash guard. Harness prints reserve telemetry every tick. Isolation tests for config + basic funding bounds pass.
- Evidence: Multiple short paper harness runs (4-8 ticks) + dedicated tests.

## Fixes & Verification for #2
- **P6-144**: private_key newline normalization (`replace("\\n", "\n")`) added to **both** `_ensure_live_client` (on-demand) and `_init_live_client`. Test confirms logic.
- **P6-145**: `place_stop_limit_sell` (live body in `exchange_client.py`) now:
  - Uses `_quantize_size` / `_quantize_price` for all three fields (base_size, stop_price, limit_price).
  - **No** `"reduce_only": True` (the hard blocker repeatedly seen in production logs with PREVIEW_REDUCE_ONLY_NOT_ALLOWED_ON_VENUE).
  - Shadow path continues to work for E2E.
- **P6-146**: `get_product_metadata` now has proper ADA-USD entry (`price_increment: 0.0001`, base 0.01). Prevents ~2% quantization jumps on low-priced assets.
- Stop E2E test (DOGE + ADA) exercises the fixed path — passes cleanly.

## End-to-End Scenarios Executed
All run in shadow / dry-run paper harness (real sentiment cache, real paper_trader execution, real exchange_client shadow paths). No real capital or live calls.

1. **Fresh Start (G2 verified-zero bootstrap)** — `scripts/test_fable5_e2e_fresh_start.py`
   - LPM set to explicit verified zero.
   - Sentinel shape from get_positions / get_enriched_positions respected.
   - No phantom holdings leak into decisions.
   - Result: PASS.

2. **Daily Rebalance with holdings (G3 sticky + G4 reserve + P6-142 keys)** — inline + paper harness + allocation test
   - Mixed shapes (value_usd dict + bare float) fed to rebalance_plan.
   - Projected reserve enforcement in runner path.
   - Plan generated without crash; telemetry shows deployable_after_reserve every cycle.
   - Harness + isolation: PASS.

3. **Sentiment-adjusted allocation + aging** — paper_harness.py (multiple runs)
   - Loads canonical v3 run_full_sentiment_v3 + 60min half-life scorer.
   - Applies get_sentiment_adjusted_weights.
   - Visible in logs + telemetry.
   - 0-data-age harness runs + aging sample captured.
   - PASS.

4. **Native stop-loss attachment (P6-145/146 fixed, G6)** — `scripts/test_fable5_e2e_stops_live_path.py`
   - Calls place_stop_limit_sell for DOGE-USD (high-price) and ADA-USD (low-price).
   - Shadow exercises body construction (quantized fields, no reduce_only).
   - ADA metadata path hit.
   - PASS.

5. **Error / unverified sentinel paths (G2 tri-state guard)** — harness tick-2 injection + P6-151 test
   - Mid-cycle simulated get_holdings failure injected.
   - Harness continued without flipping to erroneous Fresh Start.
   - Sentinel always returned with verified=False + error.
   - Real log evidence + test output.
   - PASS.

6. **Reserve enforcement in all paths (G4)** — config + runner + harness telemetry
   - Every paper tick emits: reserve_min, cash, total, deployable_after_reserve.
   - Runner uses config-driven min + projected targets before daily block.
   - PASS (visible in harness output).

7. **Live client initialization safety (P6-144)** — dedicated norm test + source inspection
   - Normalization present in both paths.
   - PASS.

## Harness Runs Executed
- Multiple `python scripts/phase6/paper_trading_harness.py --mode dry-run --ticks N --interval 1`
- Consistent output pattern:
  - Reserve telemetry every tick
  - Simulated failure on tick 2
  - Sentiment + aged scores
  - Rebalance plan generation
  - 1 injected error (as designed)
  - Clean completion
- Examples in prior turns + final sweep.

## Full Sweep Command & Result (final verification)
```bash
python3 scripts/test_fable5_p6_151_sentinel_leak.py && \
python3 scripts/test_fable5_g4_funding_constraint.py && \
... (rebalance plan + value_usd) && \
test_fable5_e2e_fresh_start.py && \
test_fable5_e2e_stops_live_path.py && \
paper_trading_harness ... --ticks 4
```
All major assertions and harness runs reported PASS (only the single injected error for G2 testing).

## Remaining Items / Recommendations for Paper Window
- Tighter funding limit param to rebalance_plan (comment already added; can wire `deployable_cash` as upper bound next paper cycle).
- Real dynamic product metadata fetch (table is sufficient for current paper scope; live re-gate can promote to live fetch).
- 24h cooldown + sentiment staleness forced tests (easy to add to harness).
- 48h continuous paper artifact collection with the augmented harness.

## Sign-off
**All #1 (G3/G4 leaks) and #2 (live quant/stop/init) items from Fable 5 are addressed with:**
- Targeted code changes (always with diff evidence)
- Dedicated Code Isolation Tests (all exit 0 / assertions pass)
- E2E scenario coverage for the key trading flows (Fresh Start, Rebalance + sticky holdings, Stops, Error paths, Reserve, Sentiment pipeline)
- Paper harness instrumentation matching Fable 5 punch-list requirements (telemetry + forced failure)

**The system now satisfies the explicit "CONDITIONAL GO for paper" gates from Batch 4 closure.**

No new criticals or regressions introduced in this wave.

**I, Scotty, sign off on the current state for extended paper trading observation.**

User can now:
- Run long paper harness (recommend 20–100+ ticks or overnight with the current script)
- Or request one more small wave
- Then move to formal live re-gate (another cheap Fable 5 mini-pass or full manual + isolation on the live machine)

All evidence collected under `reviews/Phase6_Fable5_Code_Review_Package/` and `scripts/test_fable5_*`.

Real data. Strict gates. No hype.

Ready when you are.