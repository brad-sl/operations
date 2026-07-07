---
name: crypto-analyst-scenario-run
description: Run ANALYST-OPT scenario packs, honest briefs, gates, and shadow proposals for Phase 6. Load before optimization, intelligence brief review, or regime scorecard work.
---

# Crypto-Analyst scenario run

Persona: see `docs/research/CRYPTO_ANALYST_PERSONALITY.md` in the crypto-trading-bot repo.

## When to use

- Weekly/daily optimization vs production
- Interpreting `analyst_scenario_leaderboard_latest.json`
- Promotion gates, regime scorecard, shadow overlay trials
- Writing proposals that cite `run_id`

## Workflow

1. **Production first** — read since-go-live metrics (`production_period_baseline.py` / leaderboard `production_since_go_live`).
2. **Run pack** — `python3 phase6/research/run_scenario_leaderboard.py --pack <pack> --engine arch4 --compare-production`
3. **Regime stress** — `python3 phase6/research/run_regime_scorecard.py` before trusting bull winners.
4. **Gates** — `promotion_gates.evaluate_promotion_gates`; never ingest proposals when failures include negative Sharpe.
5. **Brief** — use `analyst_narrative.format_honest_assessment`; no sugarcoating.
6. **Shadow only** — `activate_shadow_trial.py` after gated proposal; `--regime-adaptive` only with filled `regime_knob_map.json`.
7. **MASTER** — proposals flow through `analyst_proposed_backlog.json`; live config changes need user approval.

## Key paths

| Artifact | Path |
|----------|------|
| Leaderboard | `data/state/analyst_scenario_leaderboard_latest.json` |
| Runs ledger | `data/state/analyst_scenario_runs.jsonl` |
| Learnings | `data/state/analyst_learnings.json` |
| Gap matrix | `docs/research/BACKTEST_LIVE_GAP_MATRIX.md` |

## Pitfalls

- OHLCV pack dates may not overlap live go-live — headline production return separately.
- Path B uses proxy sentiment/RSI in harness — flag gaps before live promotion.
- Bull-only winners often fail after regime shift; require bear/flat scorecard.

## Verification

```bash
python3 phase6/research/test_isolation_promotion_gates.py
python3 phase6/research/test_isolation_shadow_r4.py
python3 phase6/research/test_isolation_analyst_narrative.py
```

After changing this workflow, patch this skill with new pitfalls via `sync_analyst_skill_pitfall.py` or `skill_manage(patch)`.