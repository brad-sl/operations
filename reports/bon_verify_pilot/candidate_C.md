## Candidate C · angle=evidence_clock

### Primary (exactly one task id)
`P6-SCALE-GAP-06-PERF-API-SOAK-20260816`

### Optional secondary (0–1)
`P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816` (watch-not-build; clock not mature — 0 recent staged decisions)

### Why now (≤5 bullets)
- GAP-06 Flag=NEEDS_VALIDATE post 2026-08-16 perf cache fix + 60s cache ship; frozen ISO bar on MASTER for cold+warm+concurrent soak exactly matches evidence_clock angle (finish/unblock ≤7d with existing harness).
- Can close this week: extend `test_isolation_kpi_truth.py` + concurrent curls against live /api/performance; assert non-null when history, explicit timeout status, SLA (warm p95<1s, cold<8s); decide/ship via isolation gate.
- GAP-04 blocked on collection quality; hard_exit_decisions.jsonl has only July cleanups (6 lines), current regime_hard_exit_shadow has n=0 proposals; no ≥7d / ≥5 staged decisions accruing yet — cannot mature clock in 7d.
- L4 KPI soak protects operator trust at N accounts before scaling other lanes; recent honesty anchors show perf N/A was the class bug now fixed in code, needs soak validation only.
- No live changes, no TP/mid-cycle/capital; OPT_EX SYNTH idle-with-reason; focus frozen bars + NEEDS_VALIDATE items that actually have harness ready today.

### Kill / pass criteria
- Pass staff week: soak report with concurrent N runs green; no silent N/A; SLA documented in L4 map; decide packet + ship (extend isolation test); zero config writes.
- Kill/reprioritize if: concurrent test fails to run without new infra; persistent N/A under load (gap_in_code); any creep into live_apply, hard-exit auto, or data collection for GAP-04.

### Must not touch
Live TP, hard-exit auto-apply, mid-cycle allocator, USDC park, capital rewrite, sleeve trims, live_partial liq hop, dropped Fib/SR/stoch mashups.

### Effort class: S
