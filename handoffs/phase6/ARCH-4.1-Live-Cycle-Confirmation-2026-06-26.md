# ARCH-4.1: Full cycle confirmation in live (proc_629acdae1493)

**Date**: 2026-06-26  
**Kanban**: t_c6047a29 (CLOSED)  
**Related**: live_cutover proc_629acdae1493, PID ~3956186, MASTER section appended same date.

## Summary
Monitored live runner (phase6.core.phase6_runner --mode live --confirm-live) through multiple cycles post cutover. Confirmed:

- Full ARCH-4 stack active in production: new Allocator + RotationStrategy path.
- Expected 0 actions from reserve guard (min $200, current cash near 0).
- Per-cycle dashboard cache + metrics DB emission.
- State persistence with arch4 metadata, proposals.
- CR-03 re-attach context exercised.
- Stable operation (takeover with 4 positions ~$717 total).

## Evidence
- **Log excerpts** (from logs/phase6_runner_error.log and live_cutover_1782511285.log):
  - CYCLE 1-5 (e.g. 15:06, 15:07:43, 15:09:16, 15:10:49, 15:12:23):
    `[CYCLE N] ... rebalance_needed=True`
    `[ARCH-4] Using new Allocator + RotationStrategy path (replacing direct deploy_capital)`
    `[ARCH-4] No actions in TradePlan`
    `[ARCH-4] Rebalance complete via new stack. Strategy=rotation_catch_wave, actions=0, exposure=100.0%`
  - Reserve: `Reserve guard active: only $0.00 deployable after $200.0 reserve`
  - Dashboard: `[DASHBOARD] Cache written (using price snapshot): 4 positions, holdings=$716.72, total=$716.72`
  - Metrics: `[METRICS DB] Persisted recovery=0/0, sl_rate=0.00, replay=0.0, brief=False`
- **State** (`data/state/phase6_live_state.json` last ~15:11):
  - 4 positions (UNI/LINK/OP/ADA)
  - `arch4.use_new_allocator: true`
  - proposals_summary, last_strategy=rotation_catch_wave, rotations=0
  - total ~$716.72, cash ~$0.005
- **Process**: Still running, healthy, cycles ~1.5-2min interval.
- **Code confirmation**: phase6/core/phase6_runner.py:718 (allocator log), rebalance paths, _write_dashboard_cache, persist_facts/metrics (WAL hardened).
- Full details + more excerpts in MASTER_TASK_TRACKING.md (2026-06-26 ARCH-4.1 section).

## Observations / Open Items
- 0 actions correct per current reserves + holdings (conservative good).
- SL attachments failing on INSUFFICIENT_FUND (expected; reduce_only fix in place but cash constraint).
- 401 Unauthorized still on get_open_orders/historical (API key scope for brokerage/orders).
- DB persist occasional locks (non-fatal).
- Brief flag in metrics persisting as False (set in code at rebalance; timing/DB query?).
- Dashboard serve should reflect live data (cache + DB).

## Next / Recommendations
- Continue monitoring for cycles where reserve allows non-zero actions (or simulate with lower min_reserve for test).
- Address open auth/SL/reserve-calc items in separate tasks (see prior LIVE-MONITOR t_13c78ac4 notes).
- When capital allows, validate actual trades + SL attach in live.
- Consider periodic heartbeat or cron for live health + daily triage.
- Preserve logs/state for audit.

**Closed**: After verification of next monitored run (CYCLE 5+). ARCH-4.1 complete.

**Handoff to**: Ongoing live ops, future ARCH-5 or allocator tuning tasks, dashboard verification.
