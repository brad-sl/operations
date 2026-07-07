# Handoff: ANALYST-OPT R1b — Path B leaderboard

**Date:** 2026-07-07  
**Status:** Complete

## Delivered

- `phase6/research/arch4_scenario_runner.py` — single-scenario ARCH-4 run + metric normalization
- `run_scenario_leaderboard.py` branches on `ScenarioKnobs.engine` (`simple` | `arch4`)
- Pack `r1_arch4_smoke_three.json` with `default_engine: arch4`
- Harness returns full `equity_curve` for Sharpe on Path B

## Run (promotion-eligible ranking)

```bash
python3 phase6/research/run_scenario_leaderboard.py \
  --pack phase6/research/scenarios/r1_arch4_smoke_three.json \
  --record-learning
```

## Verification

- `test_isolation_scenario_knob_parity.py` includes R1b arch4 runner smoke (PASS)
- Full pack run writes `analyst_scenario_leaderboard_latest.json` with `engine_mode: arch4`

## Still required before live param change

- Gap matrix gates (clock vs stride, proxy sentiment vs live caches)
- Shadow trial with `to_live_config_overlay()` + monitor green
- Cited `run_id` in ANALYST proposal

**Next:** R2 weekly cron + optimization section in intelligence brief.