# Handoff: P6-PROTECTED-EXIT-CALLERS-20260826

## Objective
Migrate remaining live sell paths onto `phase6/core/protected_market_exit.py` so Coinbase stop-hold unlock is never re-implemented ad hoc.

## Parent
- SSOT already shipped: `P6-PROTECTED-MARKET-EXIT-SSOT-20260826` / Kanban `t_bcbca9c2`
- MASTER: `docs/MASTER_TASK_TRACKING.md` § P6-PROTECTED-EXIT-CALLERS-20260826

## Children (independent)

### 1) P6-PE-CALLER-OPTRIM-20260826
- Files: `scripts/phase6/operator_trim_*.py`
- Replace cancel + `place_market_sell` with `protected_market_exit`
- Keep one-pair-at-a-time operator rule
- Isolation: mock cancel-before-sell + reattach

### 2) P6-PE-CALLER-DUST-20260826
- File: `phase6/core/sl_dust_sweep.py`
- Residual after SL may still need cancel if hold lingers
- Use protected exit; respect preserve/excluded pairs
- Isolation: dust path calls SSOT

### 3) P6-PE-CALLER-OE-SELL-20260826
- File: `phase6/core/order_executor.py` `execute_sell`
- Rebalance legs that sell base under a stop must unlock first
- Preserve P0-02.6 USD→quantize size behavior / ledger shape
- Isolation: execute_sell under mocked stop lock

## Must not
- Change entry/buy attach path
- Live book changes without Brad go
- Fake fills/prices

## Done when
- Grep shows no raw `place_market_sell` in the three targets without SSOT
- Tests PASS; MASTER children + parent DONE; Kanban complete
