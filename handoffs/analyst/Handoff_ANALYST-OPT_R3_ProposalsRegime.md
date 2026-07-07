# Handoff: ANALYST-OPT R3 — Gated proposals + regime procedure

**Date:** 2026-07-07  
**Status:** Complete

## Procedure answer (multi-regime)

**Yes — compare bull / bear / flat / recent**, but use them as **stress gates**, not a single “pick the bull winner” leaderboard.

Documented: `docs/research/REGIME_SCENARIO_PROCEDURE.md`  
Runner: `phase6/research/run_regime_scorecard.py`  
Template: `phase6/research/scenarios/regime_quad_template.json`

Promotion requires bear **or** flat to beat baseline when scorecard exists — addresses bull overconfidence + SL failures on regime shift.

## R3 deliverables

| Piece | Role |
|-------|------|
| `promotion_gates.py` | arch4, beat baseline, DD slack, Sharpe ≥ 0, prod overlap, regime scorecard |
| `proposal_from_leaderboard.py` | `ANALYST-YYYYMMDD-NNN` → backlog + MASTER |
| `run_analyst_opt_weekly.py` | ingest after leaderboard |
| `test_isolation_promotion_gates.py` | PASS |

## Verified

Current weekly winner (`rebalance_7d`, Sharpe **-2.12**) → **gates FAIL** → **no bogus proposal** (correct).

## Next (R4)

Shadow config overlay, monitor rollback, shadow vs backtest drift → learnings.