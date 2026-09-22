# Regime climate vs weather (measure-only)

**As of:** `2026-09-22T21:51:58.844107+00:00`  
**Live writes:** `False` · **schema:** `regime_climate_weather_v1`

> Climate is what you expect; weather is what you get.  
> **Regime = climate. Emergent tape = weather.** Ready for both — weather must not silently rewrite climate law.

## Plain English

Climate (30d SSOT): transition · BTC30d=10.966%. Tape: marketdata_db. Weather 7d/14d: 14.115% / 9.95% (mode calendar). Structure sleeve cap would be $0.0 (paper only). Green day ≠ climate flip. Dwell med days bear/flat/bull: 3/4/2 (means 7.49/7.4/8.49).

## Climate (job A/C — slow)

| Field | Value |
|-------|-------|
| regime | `transition` |
| layer | `climb` |
| BTC 30d % | `10.966` |
| confidence | `1.0` |
| lookback | `30` |

## Weather horizons (measure)

| Horizon | BTC ret % | Would-label regime | layer |
|---------|-----------|-------------------|-------|
| 7d | 14.115 | `transition` | `pre_bull` |
| 14d | 9.95 | `transition` | `soft_up` |
| 30d | 10.966 | `transition` | `climb` |

## Weather structure (job B — layered paper signal)

```json
{
  "ok": true,
  "as_of": "2026-09-22",
  "breakout_on": true,
  "rsi": 71.02,
  "ret14": 9.95,
  "ret30": 10.966,
  "regime_label": "transition",
  "cap_usd": 0.0,
  "layer": "park",
  "allow_new_buys": false,
  "allocator_preference": "park",
  "reasons": [
    "breakout_on_but_rsi_out_of_band rsi=71.02055457054281",
    "transition_or_no_trigger_park"
  ]
}
```

## Disagree flags

```json
{
  "climate_vs_7d": false,
  "climate_vs_14d": false,
  "climate_vs_30d_layer": false,
  "weather_would_micro": false,
  "weather_park": true,
  "green_day_is_not_climate_flip": true
}
```

## Dwell board (climate episodes on long tape)

Tape: `2020-11-22` → `2026-09-22` · labeled days `2130`

### Coarse regime episodes

| Regime | days | eps | mean | median | p90 | min | max |
|--------|------|-----|------|--------|-----|-----|-----|
| bear | 442 | 59 | 7.49 | 3 | 24 | 1 | 42 |
| bull | 450 | 53 | 8.49 | 2 | 29 | 1 | 46 |
| flat | 910 | 123 | 7.4 | 4 | 17 | 1 | 33 |
| soft_down | 75 | 62 | 1.21 | 1.0 | 2 | 1 | 3 |
| transition | 253 | 102 | 2.48 | 2.0 | 5 | 1 | 11 |

### Layer episodes

| Layer | days | eps | mean | median | p90 |
|-------|------|-----|------|--------|-----|
| bear | 442 | 59 | 7.49 | 3 | 24 |
| bull | 450 | 53 | 8.49 | 2 | 29 |
| climb | 148 | 87 | 1.7 | 1 | 3 |
| flat | 910 | 123 | 7.4 | 4 | 17 |
| pre_bull | 29 | 24 | 1.21 | 1.0 | 2 |
| soft_down | 75 | 62 | 1.21 | 1.0 | 2 |
| soft_up | 76 | 53 | 1.43 | 1 | 2 |

## Must not

- Treat green day or 7d bounce as climate flip
- Write `regime_cash_policy` / `allow_new_buys` from this board
- Size-up off weather alone

Artifacts: `/home/brad/projects/crypto-trading-bot/data/state/regime_climate_weather_latest.json` · `/home/brad/projects/crypto-trading-bot/data/state/regime_climate_weather_crumbs.jsonl` · layered paper: `data/state/bull_reentry_layered_paper_shadow.json`

