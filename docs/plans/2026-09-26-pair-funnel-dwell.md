# Pair funnel stage dwell (measure-only)

## Intent
Track how long each pair spends in each funnel stage so we can later spot
behavior patterns (fast SL, dual-clear starve, ladder survivors). **Not a model
and not a trade signal.** Prediction stays OFF until N + Brad GO.

## Stages SSOT
`config/pair_funnel_stages.json` — edit stages / min_n / predict_enabled there.
Do not hardcode stage lists in executables.

Default path:
door_eligible → rsi_wash → dual_clear → tryout_open → ladder → exit_sl|exit_tp|exit_other

## Artifacts
- `data/state/pair_funnel_dwell_latest.json` — open segments + tick
- `data/state/pair_funnel_profiles.json` — per-pair dwell means / outcomes
- `data/state/pair_funnel_dwell_events.jsonl` — transitions
- `reports/PAIR_FUNNEL_DWELL_LATEST.md`

## CLI
```bash
python3 scripts/phase6/run_pair_funnel_dwell.py
python3 scripts/phase6/run_pair_funnel_dwell.py --pair LINK-USD --json
python3 scripts/phase6/run_pair_funnel_dwell.py --monthly
```

## Monthly ping (long-term data exercise)
Quiet TG table once/month — Pair × stage visit counts (not vibes).

```
Pair | door | rsi | dual | try | lad | SL | TP | oth | Σn | cls | open
```

- Cells = closed stage visit counts (`stage_dwell.n`)
- `open` = current segment age only (side column)
- Cron: `phase6-pair-funnel-dwell-monthly` · `0 9 1 * *` · no_agent · deliver=telegram
- Job id `799fee5da628` · next ~1st 09:00 PT
- Artifacts: `reports/PAIR_FUNNEL_DWELL_MONTHLY_LATEST.md`, `data/state/pair_funnel_dwell_monthly_latest.json`
- Knobs: `config/pair_funnel_stages.json` → `monthly`

## Hooks (automatic)
- Composer persist → dwell tick (wash / dual_clear crumbs)
- Tryout seat fill → `tryout_open`
- Live scale apply → `ladder`
- Ledger SELLs (on tick) → terminal exit_* (only if open segment + exit_ts ≥ entered_at)

## Prediction fence
`profile.predict_enabled` in config is **false**. Pattern hints are labels only
(`fast_tryout_exit`, `sl_heavy`, …) after `min_closed_rts_for_pattern`.
No size/block decisions from this module.
