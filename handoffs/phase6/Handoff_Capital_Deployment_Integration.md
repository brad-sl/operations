# Handoff: Capital Deployment Integration

**Task ID**: CD-001  
**Priority**: High  
**Owner**: Sub-agent  
**Created**: 2026-06-03  
**Status**: Ready for execution

---

## Goal

Integrate the standalone `deploy_capital()` module into the Phase 6 runner and rebalancing logic so that freed or new capital is automatically and intelligently redeployed according to the rules defined in `CAPITAL_DEPLOYMENT.md`.

---

## Current State

- `deploy_capital()` exists and is functional (`phase6/scripts/deploy_capital.py`)
- Documentation exists (`phase6/docs/CAPITAL_DEPLOYMENT.md`)
- Not yet wired into `phase6_runner.py` or rebalancing paths
- No automatic redeployment is currently happening

---

## Key Requirements

1. **Respect existing holdings** — Never renormalize allocations to sum to 1.0
2. **Quality threshold for new pairs** — Stronger sentiment required (≥ +0.20)
3. **Reserve discipline** — When `source="reserve"`, only deploy to pairs with non-negative sentiment
4. **Trigger points**:
   - After liquidation / stop-loss exit
   - During reserve redeployment in rebalancing
   - On detected deposits (future)

---

## Integration Points

| Location                        | Action                                      | Source Value     |
|--------------------------------|---------------------------------------------|------------------|
| `_rebalance_if_needed()`       | Call after freeing capital from sells       | `"reserve"`      |
| Liquidation / Stop-Loss handler| Call after position closed                  | `"liquidation"`  |
| Deposit monitor (future)       | Call on new deposit detection               | `"deposit"`      |

---

## Must Do

- Wire `deploy_capital()` into the runner
- Preserve all existing capital deployment rules
- Add logging for every deployment decision
- Write unit tests for edge cases (empty basket, weak sentiment, reserve source)
- Update `MASTER_TASK_TRACKING.md` on completion

---

## Must Not Do

- Do not renormalize allocations
- Do not deploy reserve capital to negative-sentiment pairs
- Do not bypass the sentiment threshold for new pairs

---

## Success Criteria

- Capital is automatically redeployed after liquidations and during rebalancing
- Deployment decisions follow the documented rules exactly
- Logs clearly show why capital was (or was not) deployed
- No manual intervention required for redeployment

---

## Deliverables

- Updated `phase6_runner.py` with integration calls
- Unit tests for `deploy_capital()`
- Updated `CAPITAL_DEPLOYMENT.md` with integration notes
- Completed entry in `MASTER_TASK_TRACKING.md`

---

**Handoff complete. Begin with locating call sites in the runner.**
