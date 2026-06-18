# Handoff: FABLE5-P6-101 (P0-Critical)

**Title**: API failures in `get_holdings()`/`get_account_balance()` return empty/zero — indistinguishable from verified zero holdings (Fresh Start trigger hazard)

**From**: Fable 5 Batch 1 review (2026-06-10)

**Objective**: Make holdings and balance reads distinguish "verified empty" from "fetch failed / unknown". Never silently turn errors into `{}` or `0.0`.

**Must Do**:
- In `phase6/core/exchange_client.py`: `get_holdings()` and `get_account_balance()` must raise a typed exception (e.g. `ExchangeDataUnavailable`) or return `None` / `(data, verified=False)` sentinel on any exception path or missing live client.
- Add `get_holdings_verified()` (returns tuple or wrapper with `positions`, `verified: bool`, `error: Optional[str]`).
- Audit and update all callers: `phase6/core/phase6_runner.py` (Fresh Start gate, `_run_cycle`), `live_portfolio_manager.py`, `stop_loss_coordinator.verify_reconciliation`, any rebalancer path.
- Ensure Fresh Start only triggers on `has_positions is False` (verified empty), never on `None` or exception rate-limited case.
- Add Code Isolation Test that calls the method while forcing API exception; confirms no Fresh Start is triggered and `verified=False` is surfaced.
- Add real-data verification (shadow + one live mock) before any promotion.

**Must Not Do**:
- Do not swallow exceptions into `{}` / `0.0` in the data layer.
- Do not treat "API call raised or returned empty on error" as evidence of zero holdings.
- Do not change Fresh Start trigger logic without the verified flag (P6-001 lesson).

**Files in scope**:
- phase6/core/exchange_client.py (get_holdings, get_account_balance, _ensure_live_client)
- phase6/core/phase6_runner.py (Fresh Start detection + _handle_fresh_start guard)
- phase6/core/live_portfolio_manager.py
- phase6/core/stop_loss_coordinator.py (verify_reconciliation)
- Any new handoff docs that follow

**Deliverables**:
1. Patched exchange_client with typed failure paths + verified wrapper.
2. Updated runner + coordinator callers to respect the verified sentinel.
3. Standalone Code Isolation Test script: `scripts/test_fable5_p6_101_holdings_verified.py` that proves error vs genuine zero.
4. Updated MASTER_TASK_TRACKING.md entry.
5. New Kanban card on crypto-bot-project (reference this handoff).
6. Scotty shadow verification comment on the card before close.

**Success Criteria**:
- Fresh Start only fires on explicitly verified zero holdings.
- A simulated Coinbase outage (mock) causes verified=False / skip + error log, never Fresh Start.
- verify_reconciliation reports correctly when holdings fetch fails vs real zero balance.
- Isolation test passes with real client in shadow; evidence attached to Kanban.

**Standing Constraints** (from Fable 5 rubric + user):
- Real data only. Fresh Start = bootstrap-only on *verified* zero.
- Code Isolation Testing required before patch promotion.
- No live changes until shadow + real-data verification complete.
- Scotty (crypto-orchestrator) as integration reviewer must sign off on evidence before card complete.

**References**:
- Fable 5 Batch 1 response: reviews/Phase6_Fable5_Code_Review_Package/fable5_batch1_response.md (P6-101)
- Batch 0 P6-001 (related unit/zero state lessons)
- handoffs/phase6/Handoff_FABLE5_P6-004_FreshStart_Guards.md (prior work on this area)

**Priority**: P0-Critical (immediate blocker for any production use involving Fresh Start or orphan detection)