# Handoff: FABLE5-P6-143 + G4 (P1 — constraint-level, paper priority)

**Title**: Withdrawal reserve not enforced on *projected* post-allocation state; rebalance plans emit unfunded buys; active config lacks min_reserve key

**From**: Fable 5 Batch 4 (hard FAIL on G4, top risk #1, explicit "Scotty sign-off required on the constraint fix").

**Objective**: Every allocation path (daily rebalance, Fresh Start guard already mostly good, deploy) must respect the configured withdrawal reserve **after** the proposed moves. Rebalance plans must only emit buys that are funded by net sells/cash · after reserve. The active config must declare the reserve explicitly.

**Files**:
- phase6/core/phase6_runner.py (_perform_daily_rebalance — build real target_allocations_usd from the plan's BUY legs and pass to enforce).
- phase6/core/rebalancing/allocation_engine.py (rebalance_plan — add funding constraint so usd_needed ≤ available after sells + deployable_cash - reserve).
- src/capital_allocation/withdrawal_reserve.py (ensure it accepts projected post-move allocations).
- config/trading_config_phase6.json (add "min_reserve_usd": 200 (or 250), adjust max_deployable_usd accordingly).
- phase6/core/live_portfolio_manager / exchange_client (ensure enriched has value_usd so math is correct).
- phase6/scripts/deploy_capital.py (if still relevant).

**Must Do**:
- In runner: build a dict of planned target USD by pair from the BUY moves (or the full allocation plan) and pass it.
- In rebalance_plan: net buys against sells_proceeds + (cash - reserve).
- Add or confirm reserve key in config; make runner load it from one source.
- Write isolation test (realistic current positions + planned redeploy) proving a plan that would breach reserve is rejected/trimmed.
- Scotty shadow run with realistic fixtures + forced low-cash case; sign-off comment (constraint-level gate).
- Log explicitly per cycle: cash, projected after plan, reserve floor.

**Must Not Do**:
- Continue calling enforce with empty target_allocations_usd (no-op).
- Emit buy moves without a funding check.
- Leave reserve out of the active config (or have runner default to 0/None).

**Success criteria**:
- Isolation test + shadow verification shows reserve breach is blocked at planning time.
- Scotty "SCOTTY SIGN-OFF — G4 constraint now satisfied".
- Paper logs for first 48h demonstrate the three numbers every cycle.
- Fable 5 re-gate on G4 would pass (or accept the evidence).

**References**:
- Fable 5 Batch 4 §3 (G4 FAIL + P6-143), top risks table #1, punch-list Day 1 item #2, "Scotty sign-off on G4" requirement.
- Prior P6-145 handoff + Fable 5 Batch 3 (bypass in deploy).

**Created**: 2026-06-10 (Batch 4 closure + G4 as highest-leverage structural follow-on).