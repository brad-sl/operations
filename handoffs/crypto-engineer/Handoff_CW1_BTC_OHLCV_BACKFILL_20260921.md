# Handoff: CW-1 BTC daily OHLCV backfill

**Epic:** `REGIME-CLIMATE-WEATHER-REMAINING-20260921`  
**Card:** CW-1 · P0 sensor hygiene  
**Assignee:** crypto-engineer  
**Plan:** `docs/plans/2026-09-21-climate-weather-remaining-four.md`  
**Parent spine:** `docs/plans/2026-09-21-regime-climate-weather-boundaries.md` (`07098d8c`)

## Goal
Make BTC daily OHLCV continuous so climate (30d) and weather (7d/14d) sensors stop lying during gaps. Measure-only. No threshold or buy-knob changes.

## Context
- `phase6/core/regime_climate_weather.py` already prefers **bar** horizons when calendar is sparse.
- Observed gap: last full bar ~2026-09-02 + live append → ~18d hole; calendar 7d collapsed into 14d.
- Loaders: `phase6/research/regime_detector.py` → `_load_btc_closes`; long tape `backtests/data/long/ohlcv_daily_btc.json`; cache `data/ohlcv/BTC-USD_1d_coinbase.json`.

## Must do
1. Discover current merge order and which path REGIME-CASH actually uses.
2. Backfill missing daily bars from Coinbase (or honest public source already used in repo).
3. Write `scripts/phase6/run_btc_ohlcv_daily_backfill.py` (idempotent, dry-run default).
4. Isolation: gap detect + post-backfill `gap_days_tail` assertion.
5. Optional: quiet daily cron + HERMES_CRON_SSOT line.
6. Re-run `run_regime_climate_weather.py`; confirm horizons diverge honestly when tape moves.
7. Commit on `phase-6.1`; comment Kanban with evidence paths.

## Must not
- Edit `config/regime_cash_policy.json` detector bands
- Flip `allow_new_buys` / force rebalance / place orders
- Fabricate bars

## Done when
- Continuous BTC daily through “today”
- Climate/weather board no longer reports multi-week silent gap (or flags venue lag ≤2d)
- Tests green; MASTER CW-1 → DONE

## Skills
`trading-bot-operations`, `regime-premise-and-basket`, `code-isolation-testing`, `phase6-cron-reliability`
