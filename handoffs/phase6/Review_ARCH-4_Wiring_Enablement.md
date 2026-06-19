# Review Handoff: ARCH-4 Wiring & Enablement (Thin Orchestrator)

**Date**: 2026-06-19 (Reviewer: code-reviewer profile)
**Role**: Pure review — audit, gap identification, evidence collection. Do not implement changes.
**Goal**: Validate that the new Evaluation + Allocator stack is wired into a thin orchestrator/runner with safe rollout. Confirm flag behavior, proposal flow, metrics, and path to production enablement.

## Context & Success Criteria (from MASTER)
- Runner (or new orchestrator) reduced to cycle coordination: refresh data → evaluate() → allocate() → if plan: execute(wrapped).
- use_new_allocator flag loaded (default False for safety).
- When enabled: proposals from ARCH-1 feed Allocator (ARCH-2).
- Added observability: per-cycle metrics (proposals, plans non-empty, capital deployed, utilization, active pairs).
- Isolation + paper E2E exercised.
- Old paths preserved temporarily for compatibility.

## Current Evidence (Live Verification 2026-06-19)
### Live Evaluation (ARCH-1)
```
SOL-USD: ROTATE_IN score=0.90 src=opportunity_scanner sent=0.604
BTC-USD: HOLD score=0.50 src=signal_generator sent=0.032
ETH-USD: HOLD score=0.50 src=signal_generator sent=0.013
XRP-USD: HOLD score=0.50 src=signal_generator sent=-0.022
DOGE-USD: HOLD score=0.50 src=signal_generator sent=0.008
```

### Allocator Output (ARCH-2, current conditions)
- Strategy: rebalance_tilt (fallback due to low sentiment)
- Actions: [{'pair': 'SOL-USD', 'action': 'BUY', 'usd': 35.44, 'reason': 'deploy_capital_fallback'}]
- Exposure: 1.0
- Rotations/Stops: 0/0

### Flag Status
- use_new_allocator (global_settings): False
- phase_6_specific: None
- In runner: self.use_new_allocator = bool(...) default False
- NEW_ALLOCATOR_AVAILABLE = True in code
- In _run_cycle: conditional call to evaluate_universe + logging of non-HOLD when flag on. Legacy path still executes rebalance.

### Tests
- test_isolation_evaluation.py, test_isolation_allocator.py, test_isolation_integrated... , test_isolation_runner_wiring_arch4.py: 3/4 relevant passed (warnings on pytest return-value hygiene).

### Code Audit Points (phase6/core/phase6_runner.py)
- Lines ~754-774: ARCH-4 branch for proposals.
- Rebalance still unconditional on `_should_rebalance` or hybrid.
- No metrics logging for new stack.
- Runner remains monolithic (~1500+ lines).
- Skeleton `_execute_trade_plan` exists but not primary.

## Gaps / Edge Cases / Maintainability Issues (Reviewer Findings)
1. **Flag not enabled anywhere** — new architecture is "shadow" only. No production or sustained paper evidence of Allocator driving trades.
2. **No per-cycle metrics** — missing: proposals generated, plan acceptance rate, utilization %, active basket size in new path.
3. **Dual paths smell** — legacy rebalance + new evaluation side-by-side. Hard to maintain long-term.
4. **Runner not thin** — still handles data refresh, SL, dashboard, state, execution.
5. **Edge cases untested in wired path**:
   - Low basket (<4 active) triggering aggressive rotation (see ARCH-2 logic but not exercised in runner).
   - High sentiment regime.
   - Empty cash / full positions.
   - Flag toggle mid-run.
6. **Execution mapping** — TradePlan.actions not yet driving real execution when flag on.
7. **No paper/shadow harness evidence** with flag=True for >1 cycle showing TradePlan → execution.

## Review Recommendations (Actionable for Engineer)
- Enable flag in paper/trading_config_phase6.json or via runtime for isolated testing.
- Add metrics logging in the ARCH-4 branch.
- Wire allocator.allocate() result into execution (map to executor + SL wrapper).
- Thin runner progressively (move heavy logic to components).
- Run 24-48h paper run with flag on; capture utilization and plan data.
- Add isolation test variant simulating low-basket + flag on.

## Verification Steps (Must Run & Paste Output)
1. `hermes kanban show <this-task-id>` (or equivalent)
2. Enable flag temporarily and run `python phase6/core/phase6_runner.py` or cycle simulation.
3. `python -m pytest phase6/tests/test_isolation_runner_wiring_arch4.py -q --tb=short`
4. Check logs for "[ARCH-4 PROPOSAL]" and Allocator plan when flag on.
5. Update MASTER with evidence (utilization %, plans produced).

## References
- phase6/core/phase6_runner.py (use_new_allocator sections)
- phase6/core/evaluation.py, allocator.py
- phase6/tests/test_isolation_runner_wiring_arch4.py
- docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md
- Previous handoff: handoffs/phase6/ARCH-Integration-Audit.md

**Handoff ready for review after engineer implements wiring + metrics.**
**Do not assign implementation to code-reviewer profile.**
