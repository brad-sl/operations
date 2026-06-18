# Handoff: FABLE5-P6-102 (P0-Critical)

**Title**: `execute_sell()` stub returns `success: True` — fabricated fills propagate into rebalance results

**From**: Fable 5 Batch 1 review (2026-06-10)

**Objective**: Ensure every SELL leg in rebalance plans either succeeds against real exchange or fails loudly with no fabricated success. Hard-block any plan that would use sells until real implementation is present.

**Must Do**:
- In `phase6/core/order_executor.py`: Make `execute_sell` return `{"success": False, "error": "not_implemented", ...}` in live mode (or raise). Never fabricate "success": True outside an explicitly labeled isolation test.
- Fix units: `usd_amount` or `size` must be converted to correct base quantity using real current holdings / fill price (do not pass quote USD as "size").
- Update `execute_rebalance_plan` to treat any SELL leg as blocking unless `success=True` from real execution (log the failure and abort remainder).
- Add Code Isolation Test: `scripts/test_fable5_p6_102_execute_sell_real_data.py` (shadow + forced live path) proving no fabricated success and that plans with sells are correctly rejected or halted.
- Ensure withdrawal reserve (P6-107) and real holdings (P6-101) are consulted before sizing sells.
- Update any call sites in runner or hybrid rebalancer.

**Must Not Do**:
- Do not return success=True for unimplemented live sells.
- Do not allow rebalance plans to proceed when SELL legs would be fabricated.
- No synthetic order_ids outside test fixtures.

**Files in scope**:
- phase6/core/order_executor.py
- phase6/core/phase6_runner.py (daily rebalance paths)
- phase6/core/rebalancing/hybrid_rebalancer.py (if it calls execution)
- phase6/core/exchange_client.py (place_market_sell or equivalent)

**Deliverables**:
1. Patched order_executor with fail-loud execute_sell + unit fix.
2. Updated execute_rebalance_plan to hard-fail on SELL legs.
3. Isolation test proving behavior.
4. MASTER update + handoff reference.
5. Kanban card.
6. Scotty shadow verification (real-data shadow cycle showing sell paths are blocked until fixed).

**Success Criteria**:
- Any plan with a net SELL leg fails immediately with clear error (no phantom USD credit).
- Isolation test demonstrates fabricated paths are impossible in the reviewed code.
- No downstream accounting/ledger corruption from stub success.

**Standing Constraints**: Real data only. No fabricated fills/success outside labeled tests. Code Isolation Testing + Scotty sign-off.

**References**:
- Fable 5 Batch 1: P6-102, P6-101 (holdings for sizing), P6-107 (reserve).

**Priority**: P0-Critical (blocks any SELL-involved rebalance)