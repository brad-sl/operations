# Handoff: FABLE5-P6-145 (P0-Critical)

**Title**: Reserve enforcement reactive only (checked pre-trade, never post-trade projected) + completely bypassed in deploy_capital (no reserve subtraction, renormalizes)

**From**: Fable 5 Batch 3 (rank #3 new CRITICAL)

**Objective**: Enforce withdrawal reserve on *projected* post-trade capital in every path (runner rebalance, deploy_capital, hybrid). Make deploy_capital respect the reserve and never drop or resize existing heavy holdings.

**Files**:
- src/capital_allocation/withdrawal_reserve.py (enforce projected)
- phase6/scripts/deploy_capital.py (call reserve, pass current holdings unchanged, filter cooldown/sentiment)
- phase6/core/phase6_runner.py (_perform_daily_rebalance reserve blocks)
- phase6/core/rebalancing/hybrid_rebalancer.py (plan builder)
- config (unify reserve value)
- phase6/core/allocation_engine.py (if used for plans)

**Must Do**:
- Modify enforce to accept target allocations and compute if the *resulting* cash after moves breaches reserve.
- In deploy_capital: treat new_capital as additional only; never renormalize existing; subtract min_reserve from deployable before weighting; respect 24h cooldown unconditionally.
- Unify reserve number to one source (prefer capital_allocation_config or trading_config_phase6).
- Add isolation test proving reserve is respected in deployment and rebalance plans.
- Scotty shadow verification with realistic numbers.

**Must Not Do**:
- Do not check reserve only on current state.
- Do not drop existing pairs or resize them to fit new capital.
- Do not bypass in emergency/recovery paths.

**Success**: Isolation test + Scotty sign-off; no plan can allocate below reserve.

**Created**: 2026-06-10 small-batch ingest.