# Handoff — PLATFORM COMPLETENESS epic — 2026-09-11

**Task ID (MASTER):** `PLATFORM-COMPLETENESS-20260911`  
**Parent:** — (epic hub)  
**Assigned To:** crypto-orchestrator (hub tracking); children per lane  
**Date Assigned:** 2026-09-11  
**Board:** `crypto-bot-project`

### Objective

Turn the 2026-09-11 core-platform gap review into a durable MASTER epic, task breakdown, and Kanban pack so agents staff **leak-free lot-true money path** work — not new research sprawl.

### Context & Background

Subsystems exist (basket, circulation, qualifier, manager, monitor, dashboard, OPT). Biggest recent losses were **bugs**. Missing pieces are episode identity, exit proof, sleeve→fill realism, L2 deployability, attribution N, and process-book proof — **not** another named box. Mission: trust → edge → scale.

### Scope & Boundaries

**Must Do:**
- Keep MASTER epic + children current as work lands
- Staff only STAGED cards with written handoffs
- Verify readiness before claiming a lane “ready”
- Leave live book unless child has Brad GO

**Must Not Do / Touch:**
- Auto-promote shadow arms / live_membership_swaps
- Multi-book / SCALING-1000 runtime as part of this epic
- STAMPEDE / on-chain / tier-C flood / fee-tier volume grind
- Force-rebalance or knobs “to generate green days”

**Files / Directories to Work In:**
- `docs/MASTER_TASK_TRACKING.md`
- `docs/plans/2026-09-11-platform-completeness.md`
- `handoffs/platform/Handoff_PC-*.md`
- `data/state/platform_functional_gaps.json`
- `data/state/kanban_master_sync_latest.json` (sync append)

**Files / Directories to Leave Untouched:**
- Live trading knobs unless explicit GO on a child
- Unrelated SCALING-1000 / marketing boards

### Expected Deliverables

- MASTER epic + child rows
- Plan + per-lane handoffs
- Kanban hub + tagged children (scheduled park, no thrash)
- Readiness report: `reports/PLATFORM_COMPLETENESS_READINESS_20260911.md`

### Success Criteria

- `hermes kanban list | rg COMPLETENESS|PC-0` shows hub + 01..09 + REV
- Idempotent keys `master:PLATFORM-COMPLETENESS-*` / `master:PC-0*`
- No unassigned **ready** cards from this pack
- Readiness verdict honest (what can staff now vs gated)

### Validation Method

```bash
cd /home/brad/projects/crypto-trading-bot
hermes kanban --board crypto-bot-project list | rg 'COMPLETENESS|PC-0'
test -f docs/plans/2026-09-11-platform-completeness.md
test -f reports/PLATFORM_COMPLETENESS_READINESS_20260911.md
bash scripts/hermes/pre_ship_quality.sh   # baseline health
```

### Notes & Warnings

- PC-01 continues A2 from `PLATFORM-MISSION-P0-CLOSEOUT-20260910` (A1/A3/A4 done).
- Paper-primary is already `rel_btc_stable` (2026-09-11); live swaps OFF.
- AVAX force_eligible is live tryout policy — still eng-sent blocked; do not confuse free tee with gates.
