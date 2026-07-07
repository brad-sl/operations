# Handoff: ANALYST-OPT Kickoff (R0)

**Epic:** `docs/epics/ANALYST-OPT_EPIC.md`  
**Assignee:** crypto-analyst + platform (Scotty chains R1+ after ARCH baseline)  
**Date:** 2026-07-07

## Scope (R0 — complete in this handoff)

1. Scenario schema + memory/learning doc  
2. Isolation harness `phase6/research/run_scenario_leaderboard.py`  
3. Smoke pack `r0_smoke_three.json`  
4. Verify: real OHLCV → leaderboard + jsonl ledger  

## Success criteria

- [ ] `python3 phase6/research/run_scenario_leaderboard.py` exit 0 — **done 2026-07-07**
- [ ] `data/state/analyst_scenario_leaderboard_latest.json` exists with `run_id`, `ranking`, metrics — **OPT-20260707-194045**
- [ ] `data/state/analyst_scenario_runs.jsonl` appended one line — **done**
- [ ] MASTER updated with evidence (paste command output) — **done**

## Out of scope (R1+)

- Live allocator / signal weights in scenarios  
- Cron + brief section  
- Shadow promotion  
- Dedup fix for duplicate learnings (R2)  

## Context for delegate

- Backtest engine: `phase6/backtest/backtest_engine.py` — expansion path uses **stub** sentiment/RSI in engine (lines ~108); R1 must replace with real cached series.  
- ARCH initiative still required so optimization optimizes code that **actually trades** in shadow/live.  
- User: mandatory honest assessment; 21:00 PT rebalance anchor; no fake data.  

## Next task after R0 verified

**ANALYST-OPT-R1:** Document gap matrix (backtest vs `phase6_runner` / ARCH-4 allocator) and add one isolation test that calls the same `BacktestConfig` fields the runner will expose post-ARCH-1.