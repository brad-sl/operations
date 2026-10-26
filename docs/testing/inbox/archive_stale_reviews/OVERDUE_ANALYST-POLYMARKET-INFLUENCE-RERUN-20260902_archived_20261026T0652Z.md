# Closeout overdue — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

**Status:** `RUNNING`

**Reason:** `past_final_still_open`

**final_at:** `2026-09-16T22:00:00+00:00`

**Final report:** `—`

**Proposed recommendation:** `—`

**Completeness issues:** ['success_criteria.min_n_trades', 'final_report path missing on disk', 'final_recommendation enum', 'outcome{} block']

**Family:** `polymarket_influence` · **MASTER:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902`

## Why this ping exists

Trials must not end quietly. Past `final_at` without finalize → review → `decide` is a process bug. This packet is the forced decision ask.

## Operator path

```bash
cd /home/brad/projects/crypto-trading-bot
# 1) If report missing, run the family final/report runner, then:
.venv/bin/python3 phase6/research/trial_cycle.py finalize-report ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902 \
  --report reports/<STEM>.md --json reports/<STEM>.json \
  --enum drop|continue_observe_only|… --outcome-class <class> \
  --primary-pass false --plain-english '…'
.venv/bin/python3 phase6/research/trial_cycle.py review-request ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902
# 2) Brad decide (closes trial + MASTER):
.venv/bin/python3 phase6/research/trial_cycle.py decide ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902 <enum> \
  --note '…' --follow-on none|extend|scoped_shadow|promotion_queue
```

Enums: `continue_observe_only` | `extend_trial` | `propose_scoped_experiment` | `drop` | `promote_blend` | `promote_primary` | `abort`
