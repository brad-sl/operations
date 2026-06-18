# IDEALOOP Live Trading Enablement Roadmap (DOGE/SOL Proposals + General)

**Date:** 2026-06-13  
**Context:** Lackluster market (~$614 USD, 4 pairs active, low execution, RSI oversold signals e.g. BTC 42.48 / DOGE 36.27).  
**Current State:** 
- Scanner proposals live in data/state/opportunity_proposals.jsonl (DOGE add $36.8 test, SOL tilt $49.1) — explicitly gated "#5 shadow only".
- #5 Shadow A/B isolation test PASSED (real data).
- #2 scanner + isolation PASSED.
- Runner has shadow_mode (default) + recent self.shadow_params patch.
- Previous Phase 6 live approval (2026-06-10) via paper harness + sign-off (reviews/Phase6_Pre_Live_Paper_Signoff_2026-06-10.md). FABLE5 review CONDITIONAL GO (no new P0s).
- Dashboard live (port 8502), crons active, dual-writes, quality gates (sentiment, stop-loss, reserves) present.

**Goal:** Safely promote scanner-proposed opportunities (new pairs / tilts) to live trading using the IDEALOOP framework (#5 guardrail first, then #1 monitoring, #2 scanner). Follow all prior disciplines: real data, isolation tests, paper/shadow before live, quality gates, MASTER tracking, handoffs, sign-off.

## Phased Roadmap

### Phase 0: Foundation (Current — Mostly Complete)
- Designs + handoffs for #5/#1/#2.
- Isolation tests for #5 and #2 (PASSED, real data).
- Scanner producing proposals on real data.
- Runner shadow support + shadow_params.
- MASTER + Kanban docs updated.
- Artifacts: logs/shadow_ab_isolation_test_report.md, logs/opportunity_scanner/*, data/state/opportunity_proposals.jsonl.

### Phase 1: #5 Shadow A/B Guardrail Integration (Immediate Priority)
- Wire opportunity_scanner proposals into Phase6Runner (use self.shadow_params to drive test_alloc_pair / tilt, run parallel shadow decision path).
- Implement / extend comparator: on each cycle or periodic, run scanner in shadow context, compare shadow decisions vs baseline (deploy delta, pair count, P&L attribution, risk metrics).
- Log shadow results durably (extend rebalance_history or new shadow_ab_results.jsonl; dual-write).
- Add CLI / config support: --shadow-config or --shadow-params for specific tests (e.g. DOGE expansion).
- Isolation test for the integration (update or new test_isolation_shadow_ab_integration.py).
- Run on real cycles (shadow mode) for 50-100 ticks or 1-2 days. Collect metrics.
- Update handoff, MASTER, Kanban card.
- Success: Shadow decisions on real data produce comparable logs + positive deltas without side effects. Report shows opportunity (e.g. DOGE add improves deploy in low-RSI regime).

**Owner:** crypto-engineer (or delegate).  
**Artifacts:** Updated runner.py, new comparator, integration isolation test, shadow run logs/reports.  
**Gates:** All existing (sentiment threshold, 24h cooldown, reserves, no-fab).

### Phase 2: #1 Performance Feedback + #2 Refinement (Parallel)
- Use perf calculator / analyzer to baseline current vs proposed (win rate by signal, per-pair edge on DOGE/SOL, realized vs backtest).
- Refine scanner scoring if needed (from #1 metrics).
- Propose specific param variants or basket changes for A/B.
- Isolation tests + reports.
- Feed proposals back into #5 shadow.

**Owner:** Delegation / crypto-engineer.  
**Artifacts:** Perf reports, updated proposals, MASTER appends.

### Phase 3: Paper Validation Harness for Proposals (Pre-Live Gate)
- Use existing PaperTrader / pre-live harness patterns (from 2026-06-10 sign-off).
- Simulate the exact proposals: add DOGE-USD with ~$37 test alloc (or small %), tilt SOL.
- Run 100+ ticks with real data replay (price_history, rsi, sentiment).
- Exercise quality gates, stop-loss, recovery, rebalance on new pair.
- Measure: execution rate, P&L attribution, max DD, turnover, sentiment compliance.
- Isolation test + full report (like Phase6_Pre_Live_Paper_Signoff).
- Must pass all prior FABLE5 conditions + new lackluster-market specifics.

**Owner:** crypto-engineer + ops.  
**Artifacts:** Paper harness run logs, validation report, sign-off doc (e.g. reviews/IDEALOOP_Paper_Validation_DOGE_SOL_2026-06-XX.md).  
**Success:** Clean paper execution, positive or neutral risk-adjusted metrics, all gates pass.

### Phase 4: Controlled Live Promotion + Monitoring
- Update MASTER with paper sign-off (Scotty / human).
- Small live enable: Use canonical runner `--mode live --confirm-live` with tiny test (e.g. the $36.8 DOGE alloc or scaled down).
- Monitor first 1-2 cycles closely (dashboard, ops-engineer cron, Telegram).
- Enable dual-write / dashboard updates for new pair.
- Post-deploy: Activate #1 monitoring loop (weekly perf feedback).
- Rollback plan: Revert basket via config, shadow mode if issues.
- Ops handoff (update scripts/ops/ops_engineer.py if needed).

**Command pattern** (from prior live deploy): See docs/LIVE_DEPLOY_COMMAND_2026-06-10.txt + `--mode live --confirm-live`.
**Gates:** All quality + new pair liquidity/sentiment checks.

### Phase 5: Continuous Improvement (Post-Live)
- #1 loop active for ongoing param optimization.
- #2 scanner continues to propose (now with live data).
- #5 A/B for future changes.
- Regular MASTER / Kanban updates.
- Ops monitoring + escalation.

## Cross-Cutting Requirements (Non-Negotiable)
- **Real data only** at every step (no mocks).
- **Isolation tests** before integration or promotion.
- **Shadow / paper before live** (per #5 guardrail and prior FABLE5 process).
- **Quality gates** always (sentiment threshold, 24h post-SL cooldown even in recovery, reserves, one-sided SELLs, etc.).
- **Tracking**: Update MASTER_TASK_TRACKING.md, handoffs/ideas/, Kanban (via docs + reminder cron), todo.
- **Sign-off**: Explicit "PAPER GO" + "LIVE APPROVAL" (like 2026-06-10). Reference FABLE5 review.
- **Monitoring**: Dashboard (port 8502), crons, ops-engineer.
- **Rollback**: Always possible via config + shadow mode.

## Immediate Next Actions (as of 2026-06-13)
1. Integrate scanner into runner shadow mode + basic comparator (Phase 1).
2. Run shadow A/B simulation on DOGE/SOL proposals (collect real deltas).
3. Create / execute paper validation harness for the proposals.
4. Append this roadmap + progress to MASTER.
5. Create tight handoff for Phase 1 integration.
6. Update Kanban cards (MASTER) and run reminder cron manually if needed.
7. Delegate #1 audit refinement + Phase 3 paper harness prep if bandwidth.

**Success for Live Enablement**: DOGE or SOL (or both) added to active basket with measurable improvement in deployment/opportunity capture, all gates passed, full audit trail, no regressions to existing safety or capital.

This roadmap ensures safe, disciplined progress from current shadow-gated proposals to live trading while adding opportunities in the lackluster market.

*Single source of truth: This doc + MASTER_TASK_TRACKING.md. Reference IDEALOOP designs/handoffs and prior pre-live sign-off.*