# Regimen queue audit — 2026-08-17

**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Question:** Did we close placeholders that should have been real tests?

## Short answer

**No.** Nothing that was a *placeholder for a future real test* was closed as a market reject.

| Item | What happened | Placeholder? |
|------|----------------|--------------|
| FIB entry shadow | Real multipair OHLCV dig; long-tape no_go; **CR REJECT drop** | **No** — evidence reject |
| SR structure shadow | Real dig; less-loss ≠ edge; **CR REJECT drop** | **No** — evidence reject |
| BULL-KNOBS-001 | **abort** zombie (`reports=[]`); successor **PLAN-BULL-KNOBS-002** stays planned | Abort was process; **002 is the real test** |
| BEAR-PARK / METHOD / BULL-002 | Stay **planned** with full design + success_criteria + protocols | **Real future tests** — not closed |
| Scale GAP-03…06, 08…10 | Stay **QUEUED** with frozen success criteria | **Real** — not closed |
| GAP-07 unstick | **DONE** hygiene (capacity unstuck) | Hygiene task, not expectancy test |

## Closed trials — regimen retrofit (decisions unchanged)

All CLOSED trials now have: `success_criteria`, `outcome`, `follow_on`, `decision_packet`.

| Trial | Enum | CR | Follow-on |
|-------|------|-----|-----------|
| Kelly | drop | REJECT | none |
| Bull knobs 001 | abort | REJECT (process) | **extend → PLAN-BULL-KNOBS-002** |
| Flat knobs | propose_scoped_experiment | ACCEPT scoped | scoped_shadow |
| Transition | drop | REJECT | none |
| Stoch SL predictor | drop | REJECT | none |
| Stoch parallel | continue_observe_only | NO_CR | extend (~2026-09-03 reeval) |
| Combined ablation | drop | REJECT | none |
| Fib | drop | REJECT | none |
| SR | drop | REJECT | none |

Packets: `docs/testing/decisions/DEC_*_20260817.md`

## Planned strategy queue (regimen-ready, still planned)

| Plan | Prio | Gate | Protocol |
|------|------|------|----------|
| PLAN-BULL-KNOBS-002 | 28 | `emit_only_when_regime=bull` | `docs/testing/trials/PLAN-BULL-KNOBS-002_PROTOCOL.md` |
| PLAN-BEAR-PARK-001 | 40 | — | `docs/testing/trials/PLAN-BEAR-PARK-001_PROTOCOL.md` |
| PLAN-METHOD-ROTATION-001 | 50 | — | `docs/testing/trials/PLAN-METHOD-ROTATION-001_PROTOCOL.md` |

Each has frozen `design` + `success_criteria` on `TEST_STRATEGY.json`.

## Emit enforcement

`analyst_test_strategy.emit` now **skips** plans missing `success_criteria.primary_window` (and hypothesis/design).  
Handoff + MASTER emit templates include regimen + frozen criteria JSON.

## Capacity

`review_pending=0` · `offline_running=0` · `instru_running=0`

## Policy going forward

1. Never `decide drop` a planned real test without outcome evidence.  
2. `abort` only for process zombies; always name successor if the science remains.  
3. Sparse N / bags-only → reject promote, not soft yes.  
4. Placeholders that are *future work* stay `planned`/`QUEUED` with frozen bars — they are not closable stubs.

## Scripts

- `phase6/research/_audit_regimen_queue.py` — debt scan  
- `phase6/research/_apply_regimen_queue.py` — one-shot retrofit (already applied)
