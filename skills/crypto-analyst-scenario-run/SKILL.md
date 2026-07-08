---
name: crypto-analyst-scenario-run
description: Example vertical skill — scenario optimization, honest briefs, promotion gates, shadow trials. Requires crypto-trading-bot repo (or adapt paths). Pair with platform-orchestrator-loop for methodology.
---

# Crypto-Analyst scenario run (example vertical)

**Requires:** [crypto-trading-bot](https://github.com) Phase 6 checkout (or fork with same layout). For methodology only, use `platform-orchestrator-loop` instead.

Persona: `docs/research/CRYPTO_ANALYST_PERSONALITY.md` in the repo.

## When to use

- Weekly/daily optimization vs production
- Interpreting `data/state/analyst_scenario_leaderboard_latest.json`
- Promotion gates, regime scorecard, shadow overlay trials
- Writing proposals that cite `run_id`

## Workflow

1. **Production first** — since-go-live metrics (`production_period_baseline.py` / leaderboard `production_since_go_live`).
2. **Run pack** — `python3 phase6/research/run_scenario_leaderboard.py --pack <pack> --compare-production`
3. **Regime stress** — `python3 phase6/research/run_regime_scorecard.py` before trusting bull winners.
4. **Gates** — `promotion_gates.evaluate_promotion_gates`; never ingest proposals when failures include negative Sharpe.
5. **Brief** — `analyst_narrative.format_honest_assessment`; no sugarcoating.
6. **Shadow only** — `activate_shadow_trial.py` after gated proposal; `--regime-adaptive` only with filled `config/regime_knob_map.json`.
7. **MASTER** — proposals via `analyst_proposed_backlog.json`; live config changes need user approval.

## Key paths (this repo)

| Artifact | Path |
|----------|------|
| Leaderboard | `data/state/analyst_scenario_leaderboard_latest.json` |
| Runs ledger | `data/state/analyst_scenario_runs.jsonl` |
| Learnings | `data/state/analyst_learnings.json` |
| Gap matrix | `docs/research/BACKTEST_LIVE_GAP_MATRIX.md` |
| Epic | `docs/epics/ANALYST-OPT_EPIC.md` |

## Pitfalls

- OHLCV pack dates may not overlap live go-live — headline production return separately.
- Path B harness uses proxy sentiment/RSI — flag gaps before live promotion.
- Bull-only winners often fail after regime shift; require bear/flat scorecard.
- Extend OHLCV periodically: `phase6/research/extend_backtest_ohlcv.py`.

## Verification

```bash
python3 phase6/research/test_isolation_promotion_gates.py
python3 phase6/research/test_isolation_shadow_r4.py
python3 phase6/research/test_isolation_analyst_narrative.py
```

After changing this workflow, patch pitfalls via `skill_manage(patch)` or repo `sync_analyst_skill_pitfall.py`.