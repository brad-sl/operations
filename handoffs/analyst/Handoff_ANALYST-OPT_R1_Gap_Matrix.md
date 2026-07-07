# Handoff: ANALYST-OPT R1 — Gap matrix + knob parity

**Epic:** `docs/epics/ANALYST-OPT_EPIC.md`  
**Date:** 2026-07-07  
**Status:** R1 complete

## Delivered

- Gap matrix: `docs/research/BACKTEST_LIVE_GAP_MATRIX.md`
- Canonical mapper: `phase6/research/scenario_knobs.py`
- Isolation: `phase6/research/test_isolation_scenario_knob_parity.py`
- Leaderboard refactored to use `ScenarioKnobs`
- Parity artifact: `data/state/analyst_scenario_parity_latest.json`

## Verification (2026-07-07)

```text
python3 phase6/research/test_isolation_scenario_knob_parity.py
→ parity mappings OK scenarios=3
→ arch4 smoke OK scenario=baseline_7d return_pct=-27.75 max_dd=29.63 trades=144
→ ANALYST-OPT R1 isolation PASS
```

## Key gaps documented (promotion blockers)

- Path A stub sentiment/RSI; no SL/reserve/fees
- Live **clock** rebalance (09:00/21:00) vs scenario **day stride**
- Path B proxy sentiment vs live caches

## Next: ANALYST-OPT-R1b

- Implement `engine: "arch4"` in `run_scenario_leaderboard.py` (full pack on Path B)
- Optional pack `r1_arch4_baseline.json`

## Next: ANALYST-OPT-R2

- Weekly cron + brief optimization section + learnings dedup

**Delegate crypto-analyst:** Read gap matrix + parity JSON; produce honest assessment proposal only if R1b leaderboard beats baseline on Path B.