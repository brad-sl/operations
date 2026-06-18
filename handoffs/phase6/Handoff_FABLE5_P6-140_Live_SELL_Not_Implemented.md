# Handoff: FABLE5-P6-140 (P0-Critical)

**Title**: Live execute_sell always returns success=False + not_implemented — one-sided rebalance execution (all BUYs, no SELLs) in live mode

**From**: Fable 5 Batch 3 review (2026-06-10, #2 new CRITICAL)

**Objective**: Either implement real live market sell using verified holdings + proper quantization, or make rebalance plan execution refuse atomically when it contains SELL legs in live mode (all-or-nothing). Ensure no partial execution that leaves portfolio unbalanced long.

**Files in scope**:
- phase6/core/order_executor.py (execute_sell, execute_rebalance_plan)
- phase6/core/exchange_client.py (add/implement live sell path if needed)
- coinbase_wrapper_FIXED.py (actual sell order logic)
- phase6/core/phase6_runner.py (_perform_daily_rebalance)
- phase6/core/allocation_engine.py or hybrid_rebalancer (plan generation)
- Config for any thresholds

**Standing constraints**:
- Real data only (verified post-fill sizes, prices, no faked success or fills from spot ticker).
- Sticky holdings respected.
- Reserve respected.
- Code Isolation Testing (realistic fixtures for shadow; live parity where possible) + Scotty sign-off before done.

**Must Do**:
1. In order_executor.execute_sell: Make it actually call a real sell in live (via exchange_client.place_market_sell or equivalent) or raise/explicitly return failure with clear reason.
2. In execute_rebalance_plan / _perform_daily_rebalance: Before executing any plan with SELL legs in live mode, either (a) fail the entire plan or (b) execute atomically (sells first, then buys, with rollback on partial failure). Log and block.
3. Ensure sell sizing uses verified holdings from get_holdings_verified (post any P6-001 normalization to -USD + value_usd).
4. Return real fill data on success (size, avg_price, order_id) — not estimates from get_price().
5. Update any callers (runner, hybrid, deploy) to respect the new failure or refusal.
6. Write Code Isolation Test `scripts/test_fable5_p6_140_live_sell_one_sided.py` that:
   - In shadow: plan with SELL succeeds or logic is exercised.
   - Shows that live would fail the plan if SELL present (or that implemented sell works).
   - Demonstrates no one-sided execution possible.
7. Scotty executes the test, adds sign-off comment.

**Must Not Do**:
- Do not fabricate success for sells in live.
- Do not allow partial plan execution (buy legs succeed while sells are skipped).
- Do not size sells from estimated positions.
- No live trading until isolation test + Scotty sign-off.

**Deliverables**:
- Updated order_executor.py and/or exchange_client with honest live sell or hard atomic refuse.
- Test script that passes with evidence (shadow realistic).
- Scotty sign-off on Kanban.
- Reference in any related CR-03 / reconciliation work.

**Success criteria**:
- Isolation test shows the one-sided hazard is closed (either by implementation or explicit block).
- Scotty detailed sign-off.
- Fable 5 (if closure review) sees the refusal or real impl + no partial plans.

**References**:
- Fable 5 Batch 3: P6-140 section, G5 gate fail.
- P6-102 handoff (related stub resolution).
- P6-101/P6-132 sentinel work for verified positions.

**Created**: 2026-06-10 by Scotty (crypto-orchestrator) — small batch ingest #1 (with P6-132/133).
