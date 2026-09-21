# Climate vs weather — dial regime boundaries (Brad GO E 2026-09-21)

**Status:** SHIPPED measure spine (P1+P2) · paper layered refresh · **no live knobs**  
**Quote law:** Heinlein — *Climate is what you expect; weather is what you get.*  
**Product:** Regime = climate. Emergent tape = weather. Ready for both — weather must not silently rewrite climate law.

## Problem

30d REGIME-CASH is a convenient climate smoother, not a leg timer. Waiting only for 30d to realign can bench through whole ~2–3 week moves. A green day is not a climate flip — but pure climate-as-door wastes opportunity time.

## Job split (do not collapse)

| Job | Role | Tool |
|-----|------|------|
| **A Survival** | Park when dump risk is climate-real | Slow 30d bear ≤ −10% veto |
| **B Opportunity** | Micro sleeve when structure allows | Layered breakout+RSI (spec 2026-07-30) |
| **C Size-up** | Larger risk only on climate confirm | 30d bull ≥ +15% |

## Shipped this package

1. **`phase6/core/regime_climate_weather.py`** — multi-horizon 7/14/30 + dwell episodes + layered structure snapshot  
2. **CLI** `scripts/phase6/run_regime_climate_weather.py`  
3. **Isolation** `test_isolation_regime_climate_weather.py`  
4. **Cron** `phase6-regime-climate-weather` (measure, quiet/local by default)  
5. **Layered paper shadow refreshed** + cron re-armed (`phase6-bull-reentry-layered-paper`)  
6. **Gap-honest weather** — OHLCV lag + live append no longer collapses 7d=14d silently; bar lookbacks preferred when sparse

## Must not (yet)

- Flip `allow_new_buys` / rewrite `regime_cash_policy` thresholds from this board  
- Treat green day or 7d bounce as climate = flat  
- Size-up off weather alone  
- Promote B micro live without Brad GO + gate N

## Next (after crumbs accumulate)

- Counterfactual: if micro B had been on when climate still bear/soft_down, 5d/10d path vs full park  
- Optional hysteresis design (doc only) for bear→soft_down→flat  
- BTC daily OHLCV backfill (sensor quality) so calendar weather matches bars  

## Artifacts

- `data/state/regime_climate_weather_latest.json`  
- `data/state/regime_climate_weather_crumbs.jsonl`  
- `reports/REGIME_CLIMATE_WEATHER_LATEST.md`  
- `data/state/bull_reentry_layered_paper_shadow.json`  
- Spec: `docs/research/BULL_REENTRY_LAYERED_SPEC.md`
