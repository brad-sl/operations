# Handoff Document: RSI-SENT-007 — Fix syntax from appends + P6-140 re-verify

**Task ID**: t_93815799 (RSI-SENT-007)
**Kanban Board**: crypto-bot-project
**Assigned To**: crypto-engineer
**Date Assigned**: 2026-06-12
**Parent / Related**: RSI_SENTIMENT_RELIABILITY_PLAN.md (Phase 1/2 items), FABLE5-P6-140 blocked card, prior RSI-SENT-002/003

## Objective
Fix Python syntax corruptions introduced by prior "appends"/edits (mangled docstrings and similar) across the codebase (starting with identified legacy files), and re-verify + remediate the FABLE5-P6-140 (P0-Critical one-sided rebalance execution hazard for SELL legs) per its handoff and the detailed prior orchestrator review. Ensure the RSI sentiment reliability workstream remains unblocked by these issues. Deliver clean, verifiable code with isolation tests.

## Context & Background
- This card was created (2026-06-11) as follow-on to RSI-SENT audit/implementation wave and syntax cleanup note in master tracking.
- Recent autonomous progress (per master): RSI refresher producing fresh data, runner wired to canonical rsi_cache, crons attempted, but syntax issues from append operations surfaced (e.g. phase5_1_multi_pair.py and dynamic_backtest.py start with literal \"\"\" docstrings causing "unexpected character after line continuation").
- P6-140 remains blocked (t_4e4193a9, assignee crypto-engineer): prior crypto-engineer summary claimed atomic logic in executor, but orchestrator review (2026-06-11) found:
  - Runner (phase6/core/phase6_runner.py) uses its own inline loop over rebalance_plan moves, not the atomic execute_rebalance_plan.
  - No success check/abort on SELL in live path (unconditionally continues to buys).
  - exchange_client.py missing place_market_sell (only buy/stop paths).
  - Isolation test broken (import/path, ctor signature drift requiring stop_loss_manager, shadow client fakes success).
  - Rebalance_plan emits SELLs for negative deltas.
- "P6-140 re-verify" explicitly in this card's title; syntax fixes are prerequisite for clean re-verification and any related appends during RSI work.
- Broader: Part of RSI_SENTIMENT_RELIABILITY_PLAN.md Phase 1 (canonicalize, stabilize) + Phase 5 (integration, testing). Permanent artifacts required in reports/ and committed to phase-6.1 branch.
- User prefs: Code Isolation Testing mandatory (standalone test wrappers first to verify "as designed"), real data only, master list as source of truth, tight handoffs, no permission prompts for obvious next steps.

## Scope & Boundaries

**Must Do**:
- Fix all syntax errors from appends/edits (at minimum: repair docstrings in phase5_1_multi_pair.py and dynamic_backtest.py; scan and fix any similar corruption in phase6/, scripts/, src/, exchange_client, runner, order_executor, sentiment files).
- Re-verify P6-140:
  - Confirm or implement full live market sell path (place_market_sell in exchange_client.py mirroring buy, using verified qty from live_portfolio_manager/holdings, proper quantization).
  - Wire coinbase_wrapper_FIXED.py if needed.
  - Update order_executor.py execute_rebalance_plan / execute_sell to use real calls or explicit failure.
  - Update phase6/core/phase6_runner.py _perform_daily_rebalance (and any rebalance loop) to either:
    - Call the atomic execute_rebalance_plan with proper success/abort for SELLs (prefer this), or
    - Add explicit one-sided prevention (sort sells first, break/raise on live SELL failure before any buys).
  - Fix the isolation test scripts/test_fable5_p6_140_live_sell_one_sided.py (or equivalent) to:
    - Match current OrderExecutor ctor (include stop_loss_manager arg).
    - Properly test the hazard (or the refusal/impl) with realistic shadow/live parity.
    - Exercise the actual runner path where possible.
  - Ensure sell sizing from verified holdings (post P6-001 etc.).
  - Add/update any missing methods; no stubs or "success=True" fabrication in live.
- Tie any fixes back to RSI pipeline if syntax or appends affected signal/rebalance code.
- Run Code Isolation Tests for the fixes (create/update standalone wrappers if missing; run them to produce raw output showing correct behavior before claiming done).
- Update docs/MASTER_TASK_TRACKING.md with evidence, commands, results.
- Produce artifacts in /home/brad/projects/crypto-trading-bot/reports/ (e.g. syntax_fix_report_YYYY-MM-DD.md, p6_140_reverify_YYYY-MM-DD.md, test outputs).
- Commit changes to phase-6.1 branch.
- After fixes, leave card in state for orchestrator (Scotty) sign-off if review-required pattern applies (per fable5-blocked-card-orchestrator-signoff.md checklist).

**Must Not Do / Touch**:
- Do not fabricate success/fills for sells or positions.
- Do not allow one-sided rebalance execution in live.
- Do not touch unrelated marketing boards/profiles or non-crypto-bot code.
- Do not use placeholder data in trading paths.
- Avoid in-place patches without tests; follow isolation test discipline.
- Do not close P6-140 blocked card yourself — that requires separate orchestrator sign-off after this work.

**Files / Directories to Work In**:
- phase5_1_multi_pair.py, dynamic_backtest.py (syntax repair)
- phase6/core/phase6_runner.py (rebalance loop, integration)
- phase6/core/order_executor.py, exchange_client.py (SELL impl)
- phase6/core/live_portfolio_manager.py (holdings verification)
- coinbase_wrapper_FIXED.py (if SELL logic there)
- scripts/test_fable5_p6_140_live_sell_one_sided.py (or new equivalent under scripts/)
- Any RSI/sentiment files with syntax issues (run_full_sentiment*.py, run_sentiment_system.py, sentiment_*.py, price_history_manager.py, etc.)
- handoffs/phase6/ (update if needed), docs/ (master + reports)
- Use git for changes; workspace under ~/.hermes/kanban/... is scratch only — final changes to main repo.

**Files / Directories to Leave Untouched**:
- Production .env with real keys (load only, never commit)
- Live trading without sign-off
- Other boards (marketing-consultancy)
- Non-phase6 legacy unless directly required for syntax scan

## Expected Deliverables
- All identified syntax errors fixed and py_compile clean across scanned .py files.
- P6-140 remediation complete: either real place_market_sell + atomic execution, or hard atomic refusal for SELL-containing plans in live.
- Updated isolation test that demonstrates the hazard is closed (raw output captured).
- Runner and executor paths traced and verified (no more inline no-abort SELLs).
- Updated master tracking entry + any RSI-SENT-007 progress notes.
- Reports/ artifacts with evidence (test runs, git diff summary, before/after).
- Kanban card updated with summary + links; ready for sign-off or completion.
- If new crons/scripts from RSI plan touched, ensure they remain functional.

## Success Criteria
- `python3 -m py_compile` passes for all .py in project (or at least the touched + core phase6/ ones).
- Isolation test for P6-140 (re-run by orchestrator later) shows: in live-mode simulation, SELL failure aborts before any BUYs execute; no one-sided; real holdings used for sizing.
- Prior orchestrator review gaps addressed point-by-point (runner uses atomic or has abort; exchange_client has place_market_sell; test exercises real path; no fabrication).
- Fresh RSI/sentiment data still flows (re-run refresher if touched).
- All changes committed; no regressions in existing RSI pipeline (re-run relevant isolation tests from RSI-SENT-002/003).
- Master list and card comments reference this handoff + evidence.
- Orchestrator can follow fable5 sign-off checklist (re-run test, trace runner path, map to must-dos) and either sign-off or leave blocked with clear next.

## Constraints & Requirements
- Real data / verified holdings only for any sizing or tests involving positions.
- Follow Code Isolation Testing: create/run standalone test script first to verify "as designed" output before integrating to deployed runner/exchange_client.
- Permanent output to reports/ dir; no scratch-only artifacts for final deliverables.
- Respect rate limits, no-fab rules from sentiment plan.
- Use hermes kanban comment for progress if needed; keep bodies short/clean (point to master list).
- Branch: work on phase-6.1 or feature; commit with clear messages.
- If P6-140 requires new code in exchange_client, mirror existing buy patterns exactly.
- Update any callers (allocation, hybrid rebalancer) if signatures change.

## Validation Method
- Orchestrator (Scotty) will:
  1. Re-run the named isolation test(s) in current env (e.g. PYTHONPATH=. python3 scripts/test_fable5_p6_140_....py).
  2. Trace actual execution path in phase6/core/phase6_runner.py vs order_executor.
  3. Verify py_compile + git diff for syntax fixes.
  4. Check master tracking append for evidence.
  5. Run relevant RSI refresher + confirm cache freshness.
  6. Add SCOTTY SIGN-OFF or detailed STILL BLOCKED comment + update master.
- Sub-agent must provide raw test output, command logs, and file paths in card summary.
- Board verification: hermes kanban --board crypto-bot-project show t_93815799 post-work.

## Notes & Warnings for Sub-Agent
- This is high-agency execution: own the full remediation + verification without mid-stream asks.
- Syntax "from appends" is likely from prior string-escaping or cat/echo >> style edits — fix by restoring proper """ docstrings and scanning for similar (use grep for \"\"\" or lone \ at line ends in .py).
- P6-140 is P0-Critical: live rebalance with any SELL (e.g. from sentiment shift or pair removal) will currently execute buys while skipping sells → portfolio drift. Must close the hazard.
- Do not trust prior "tests pass" claims — re-execute isolation tests yourself and compare to deployed caller (runner).
- See full fable5-blocked-card-orchestrator-signoff.md for the 7-step checklist the orchestrator will apply.
- Cross-reference: RSI_SENTIMENT_RELIABILITY_PLAN.md, Handoff_FABLE5_P6-140_Live_SELL_Not_Implemented.md, prior master entries for RSI-SENT-002/003 and 2026-06-11 syntax cleanup.
- After this, expect separate orchestrator sign-off card or direct on the P6-140 card.
- Use Code Isolation Testing discipline as standard (see memory: create standalone test wrappers like coinbase_wrapper_FIXED).
- If more syntax files found during scan, fix them as part of scope.
- Log everything to master list.

**References**:
- docs/RSI_SENTIMENT_RELIABILITY_PLAN.md
- docs/MASTER_TASK_TRACKING.md (append your progress here)
- handoffs/phase6/Handoff_FABLE5_P6-140_Live_SELL_Not_Implemented.md
- references/fable5-blocked-card-orchestrator-signoff.md (in .hermes/skills)
- kanban-orchestrator skill for patterns
- Reports dir for artifacts: /home/brad/projects/crypto-trading-bot/reports/

This handoff + the Kanban card body/comment + master entry = the full contract. Execute to completion, then hand back for sign-off.