# Regime climate vs weather (measure-only)

**As of:** `2026-09-21T19:14:18.674557+00:00`  
**Live writes:** `False` · **schema:** `regime_climate_weather_v1`

> Climate is what you expect; weather is what you get.  
> **Regime = climate. Emergent tape = weather.** Ready for both — weather must not silently rewrite climate law.

## Plain English

Climate (30d SSOT): bear · BTC30d=-13.292%. Weather 7d/14d: -16.771% / -8.491% (mode bars). Structure sleeve cap would be $0.0 (paper only). Green day ≠ climate flip. DATA: OHLCV gap ~18d before last bar — short calendar horizons collapsed; weather uses bar lookbacks. Fast horizons disagree with climate — expected emergent weather; do not auto-flip money path. Dwell med days bear/flat/bull: 3/4.0/2.0 (means 7.49/7.42/8.1).

## Climate (job A/C — slow)

| Field | Value |
|-------|-------|
| regime | `bear` |
| layer | `bear` |
| BTC 30d % | `-13.292` |
| confidence | `0.433` |
| lookback | `30` |

## Weather horizons (measure)

| Horizon | BTC ret % | Would-label regime | layer |
|---------|-----------|-------------------|-------|
| 7d | -16.771 | `bear` | `bear` |
| 14d | -8.491 | `soft_down` | `soft_down` |
| 30d | 4.312 | `flat` | `flat` |

## Weather structure (job B — layered paper signal)

```json
{
  "ok": true,
  "as_of": "2026-09-21",
  "breakout_on": false,
  "rsi": 38.42,
  "ret14": -13.363,
  "ret30": -13.292,
  "regime_label": "bear",
  "cap_usd": 0.0,
  "layer": "bear_park",
  "allow_new_buys": false,
  "allocator_preference": "park",
  "reasons": [
    "bear_veto"
  ]
}
```

## Disagree flags

```json
{
  "climate_vs_7d": false,
  "climate_vs_14d": true,
  "climate_vs_30d_layer": true,
  "weather_would_micro": false,
  "weather_park": true,
  "green_day_is_not_climate_flip": true
}
```

## Dwell board (climate episodes on long tape)

Tape: `2020-11-22` → `2026-08-15` · labeled days `2092`

### Coarse regime episodes

| Regime | days | eps | mean | median | p90 | min | max |
|--------|------|-----|------|--------|-----|-----|-----|
| bear | 442 | 59 | 7.49 | 3 | 24 | 1 | 42 |
| bull | 421 | 52 | 8.1 | 2.0 | 28 | 1 | 46 |
| flat | 905 | 122 | 7.42 | 4.0 | 17 | 1 | 33 |
| soft_down | 75 | 62 | 1.21 | 1.0 | 2 | 1 | 3 |
| transition | 249 | 99 | 2.52 | 2 | 6 | 1 | 11 |

### Layer episodes

| Layer | days | eps | mean | median | p90 |
|-------|------|-----|------|--------|-----|
| bear | 442 | 59 | 7.49 | 3 | 24 |
| bull | 421 | 52 | 8.1 | 2.0 | 28 |
| climb | 145 | 85 | 1.71 | 1 | 3 |
| flat | 905 | 122 | 7.42 | 4.0 | 17 |
| pre_bull | 29 | 24 | 1.21 | 1.0 | 2 |
| soft_down | 75 | 62 | 1.21 | 1.0 | 2 |
| soft_up | 75 | 52 | 1.44 | 1.0 | 2 |

## Must not

- Treat green day or 7d bounce as climate flip
- Write `regime_cash_policy` / `allow_new_buys` from this board
- Size-up off weather alone

Artifacts: `/home/brad/projects/crypto-trading-bot/data/state/regime_climate_weather_latest.json` · `/home/brad/projects/crypto-trading-bot/data/state/regime_climate_weather_crumbs.jsonl` · layered paper: `data/state/bull_reentry_layered_paper_shadow.json`

