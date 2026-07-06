## Task Handoff Document

Task ID: P4-02
Parent Task: P4 (Architecture completion)
Assigned To: code-reviewer
Date Assigned: 2026-07-05

### Objective
Unify per-cycle evaluation and enable **shadow-only** mid-cycle allocator (`mid_cycle_allocator_enabled`) so signals can drive plans between rebalance windows without live trades.

### Context & Background
`_run_cycle` still logs decorative `SignalGenerator` output; trades remain rebalance-gated. ARCHITECTURE_ISOLATED_COMPONENTS.md: evaluation should feed action. P4-02 is medium risk — new timing.

### Scope & Boundaries

Must Do:
- Replace parallel signal-only logging with one `evaluate_universe` snapshot per cycle (reuse for hybrid trigger + optional mid-cycle allocator).
- Add config flag `mid_cycle_allocator_enabled` (default false for live; shadow/PAPER can enable).
- When flag on in shadow: run allocator on strong proposals outside rebalance window; **no live execution** until shadow evidence reviewed.
- Isolation wrapper: real caches → proposals → plan (empty or non-empty) without fabricating data.
- Log proposal acceptance / utilization metrics; MASTER before/after note.

Must Not Do / Touch:
- Enable mid-cycle **live** execution in this card (orchestrator sign-off required later).
- Break existing 09:05 / 21:05 rebalance cron behavior.

Files / Directories to Work In:
- `phase6/core/phase6_runner.py`
- `phase6/core/evaluation.py`
- config templates / prod config (flag only, default off live)

### Expected Deliverables
- Flag + unified evaluation path + isolation test/script output.
- Shadow run notes (optional 1–2 cycles in PAPER).

### Success Criteria
- Single evaluation snapshot per cycle; shadow mid-cycle produces sane plans in isolation + optional paper log.

### Validation Method
- Isolation test first; then shadow cycle with flag true in PAPER/shadow mode only.

### Notes & Warnings for Sub-Agent
- **Depends on P4-01 + P4-03** complete (single path + no hybrid stub plans). Do not start until parents done.