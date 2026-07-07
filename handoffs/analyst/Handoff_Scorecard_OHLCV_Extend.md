# Handoff: Scorecard + OHLCV extend (2026-07-07)

**Status:** Complete

## OHLCV extend

- Script: `phase6/research/extend_backtest_ohlcv.py` (Coinbase **public** daily candles)
- **9 pairs** extended; `data_end=2026-07-07` (+79–80 bars each)
- Manifest: `data/state/ohlcv_extension_manifest.json`
- Pack ends synced: `sync_pack_dates_to_ohlcv.py` → `r1_arch4_smoke_three.json`, `regime_quad_template.json`

## Regime scorecard

- `run_regime_scorecard.py` → `analyst_regime_scorecard_latest.json`
- All four windows: winner **`rebalance_7d`** (beats baseline on max_drawdown primary)
- `apply_regime_knob_map_from_scorecard.py` → **`config/regime_knob_map.json`** (scorecard-sourced, bear adds `sl_max_pct=0.04`)

## Production overlap (improved)

Latest leaderboard `OPT-20260707-214630`:

| Field | Value |
|-------|--------|
| Pack window | 2025-04-20 → **2026-07-07** |
| Prod overlap | **partial** 2026-06-06 → 2026-07-07 |
| Prod since go-live | **-28.23%** |
| Scenario winner | `rebalance_7d` Sharpe **-0.73**, return **-1.69%** on full pack |

**Shadow (#3):** Still **hold** — gates block negative Sharpe. Regime map is ready for `--regime-adaptive` when a gated proposal exists.

## Commands

```bash
python3 phase6/research/extend_backtest_ohlcv.py
python3 phase6/research/sync_pack_dates_to_ohlcv.py
python3 phase6/research/run_regime_scorecard.py
python3 phase6/research/apply_regime_knob_map_from_scorecard.py
python3 phase6/research/test_isolation_ohlcv_extend.py
```