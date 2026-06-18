# Task Handoff Document

**Task ID:** IDEALOOP-005-PHASE1-INTEGRATION  
**Parent Task:** IDEALOOP-005 Shadow A/B (guardrail)  
**Assigned To:** crypto-engineer (Scotty orchestration + sub-delegation)  
**Date Assigned:** 2026-06-13  

## Objective
Wire the IDEALOOP-002 opportunity_scanner into Phase6Runner's shadow path using the new self.shadow_params. Implement basic A/B comparator that runs proposals in parallel shadow decision, logs deltas (deploy, pairs, risk) vs baseline without any live impact. Enable first real-cycle shadow runs for DOGE/SOL proposals.

## Context
- Current lackluster market: ~$614 USD, 4 pairs, low execution (executed=0 in recent rebalances), BTC RSI 42.48, DOGE RSI 36.27 (strong oversold proposal).
- Scanner already produces real proposals gated to "#5 shadow only".
- Runner has shadow_mode (default), self.shadow_params (recent patch for A/B), _perform_daily_rebalance, fresh_start, order_executor with shadow skips.
- Isolation tests for #5 and #2 already PASSED with real data.
- Dupe persist_facts_to_db exists (P6-160) — avoid touching unrelated code.
- All work must be real-data-only, isolation-tested, shadow-gated.

## Scope
**Must Do:**
- Import opportunity_scanner (or its scan_opportunities) in phase6_runner.py.
- In shadow_mode paths (daily rebalance, fresh_start if relevant), check shadow_params for 'test_alloc_pair' or 'enable_scanner'. If present, call scanner, adjust weights or force small test allocation for the proposal pair (e.g. DOGE-USD $36-40).
- Add _run_shadow_ab_comparator() or inline logic: capture baseline decision, shadow decision, compute deltas (capital_deployed, executed count, pairs_after, risk metrics), log to new or extended shadow_ab_results.jsonl + rebalance_event with "shadow_ab" tag.
- Support CLI/config for shadow_params (e.g. --shadow-test DOGE or via config).
- Create/update standalone Code Isolation Test: phase6/core/test_isolation_shadow_ab_integration.py (loads real state/rsi/proposals, exercises runner in shadow with params, asserts no side effects, deltas computed, real data used).
- Run the isolation test successfully.
- Execute at least one full shadow simulation run (or 20-50 cycles via harness) using real data, produce report with opportunity deltas.
- Update docs/MASTER_TASK_TRACKING.md with Phase 1 status, links to reports, artifacts.
- Create this handoff (done).

**Must Not Do:**
- Any changes to live order paths or non-shadow code.
- Touch unrelated dupe code (persist_facts).
- Deploy or mutate state outside shadow logging.
- Skip isolation test before runner changes.

## Deliverables
1. Patched phase6/core/phase6_runner.py (minimal, targeted integration).
2. phase6/core/test_isolation_shadow_ab_integration.py (PASSED).
3. Shadow run report (e.g. logs/shadow_ab_phase1_report.md or from comparator).
4. Updated MASTER section for Phase 1 complete.
5. Any new shadow logs (shadow_ab_results.jsonl).
6. This handoff document.

## Success Criteria
- Isolation test passes with real data (asserts: scanner called in shadow, proposal (DOGE or SOL) appears in shadow decision, deltas logged (e.g. +$36 deploy), no writes to live_state/positions, no real orders).
- Shadow simulation shows opportunity (e.g. higher deploy or new pair in shadow vs baseline).
- All outputs explicitly note "SHADOW A/B — #5 guardrail — no live impact".
- MASTER and handoff updated.
- Ready for Phase 2/3 handoff.

## Constraints & Quality Gates
- Real data exclusively (use phase6_live_state.json, rsi_cache, opportunity_proposals, price_history).
- Follow existing patterns (log_rebalance_event, shadow logging).
- Quality gates from runner (sentiment, reserves, min $20, etc.) must apply to shadow decisions too.
- No fabrication. Use calculate_rsi etc. from existing.
- If scanner proposes DOGE, shadow should surface +test alloc without breaking existing basket logic.
- Track in MASTER as primary.

## Validation Method
- Run: python phase6/core/test_isolation_shadow_ab_integration.py (must PASS + print real deltas).
- Manual: python -m phase6.core.phase6_runner --mode shadow --config ... (or test wrapper) with shadow_params set.
- Review logs for "SHADOW A/B", proposal application, deltas.
- Cross-check against opportunity_scanner proposals.

## Notes / Warnings
- Runner has duplication in persist code — only edit rebalance/decision sections.
- Previous FABLE5 sign-off and Phase 6 live is already active; this is additive improvement only.
- After this, immediately move to paper harness (Phase 3) using src/sim/paper_trader.py.
- Use delegation for parallel Phase 2 (#1 metrics) and Phase 3 prep if needed.

Proceed immediately per user "proceed through all 5 phases". Update MASTER on completion of each major sub-step. Real data. Isolation first. Shadow only until Phase 4 sign-off.