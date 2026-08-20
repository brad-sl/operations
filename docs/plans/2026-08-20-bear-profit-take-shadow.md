# Bear profit-take shadow — Implementation Plan

> **For Hermes:** Implement task-by-task; shadow only.

**Goal:** Ship Phase 1 bear ladder profit-take shadow per FEAT-BEAR-PROFIT-TAKE-2026-08.

**Architecture:** Config-driven ladder evaluator; same holdings path as regime_exit_shadow; no orders; script messages.

**Tech:** Python 3, existing Phase 6 state paths, isolation tests.

---

### Task 1: Config
Create `config/bear_profit_take.json` with mode=shadow, ladder tranches, auto_promote false.

### Task 2: Engine + tests
`bear_profit_take_shadow.py` + isolation (bear fires, non-bear idle, live forced off).

### Task 3: Compose + CLI + runner hook
Messages, `run_bear_profit_take_shadow.py`, phase6_runner try/except hook.

### Task 4: Docs/skill/MASTER note + commit
