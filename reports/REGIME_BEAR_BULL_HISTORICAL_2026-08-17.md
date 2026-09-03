# Regime bear/bull historical premise dig — 2026-08-17

**Data:** `backtests/data/long/ohlcv_daily_btc.json` · 2093 daily closes · 2020-12-22 → 2026-08-15 (2062d)  
**Detector:** lookback=30d · bull≥15.0% · bear≤-10.0% · flat |r|≤8.0%  
**Live writes:** none  
**Method:** util-blend proxy on labeled BTC days (not full multi-asset book)

## Plain English

### Is 90 days enough?
**Usually no — not by calendar alone.** Adequacy = enough **labeled** bear/bull days inside the window.

| Window | bear days | bull days | adequate (≥20)? |
|--------|-----------|-----------|-------------------------------------|
| Last 90 calendar days | 30 | 0 | bear=True · bull=False |
| Full long tape (primary) | 442 | 415 | primary bar ≥45 labeled days |

90 calendar days is adequate for a regime premise ONLY if it contains ≥20 labeled days of that regime. Otherwise use long tape (primary needs ≥45 labeled days).

### Bear premise (full park vs tactical)
**Bear premise HOLDS on 442d / 59 episodes: full park ret=4.2539% dd=0.0% vs tactical ret=-59.9473% dd=60.1946% vs BTC ret=-98.2137% dd=98.2565%.**  
- class: `HIT_CRITERIA` · primary_pass: **True** · enum: `propose_scoped_experiment`  
- follow_on: `scoped_shadow`

### Bull premise (live-like util vs tight / USDC)
**Bull high-util premise HOLDS on 415d / 52 eps: live0.85 ret=2098.3235% dd=20.6638% vs tight0.65 ret=1005.0112% dd=15.9479% vs USDC 3.9889% (BTC 3538.8998%).**  
- class: `HIT_CRITERIA` · primary_pass: **True** · enum: `propose_scoped_experiment`  
- follow_on: `scoped_shadow`

## Regime mix

| Regime | Full tape days | Last 90d days |
|--------|----------------|---------------|
| bull | 415 | 0 |
| flat | 882 | 58 |
| bear | 442 | 30 |
| transition | 324 | 3 |

## Bear paths (labeled bear days only)

n_days=442 · episodes=59 (sample first 8 in JSON)

| Arm | n | util | ret% | maxDD% |
|-----|---|------|------|--------|
| full_park_usdc | 442 | 0.0 | 4.2539 | 0.0 |
| tactical_util_0.25 | 442 | 0.25 | -59.9473 | 60.1946 |
| flat_like_0.65 | 442 | 0.65 | -92.0176 | 92.1433 |
| full_btc | 442 | 1.0 | -98.2137 | 98.2565 |

## Bull paths (labeled bull days only)

n_days=415 · episodes=52

| Arm | n | util | ret% | maxDD% |
|-----|---|------|------|--------|
| full_park_usdc | 415 | 0.0 | 3.9889 | 0.0 |
| tight_0.65 | 415 | 0.65 | 1005.0112 | 15.9479 |
| live_0.85 | 415 | 0.85 | 2098.3235 | 20.6638 |
| full_btc | 415 | 1.0 | 3538.8998 | 24.1219 |

## Decision guidance (strategy plans stay planned)

| Plan | If primary_pass | If weak / sparse |
|------|-----------------|------------------|
| PLAN-BEAR-PARK-001 | premise validated → keep parked for **live bear** shadow; no live write | stay parked; re-run at live bear or more tape |
| PLAN-BULL-KNOBS-002 | premise validated → keep parked for **live bull** shadow; no live write | stay parked; re-run at live bull |

**Pass** here means *premise supported on historical labeled days* — **not** live promote.
Live knob changes still need Brad + promotion gates.

## Honesty / limits
- Arms are compared on **the same labeled days** (fair relative ranking).
- Absolute % on bull-only days looks huge because the sample is **already** “detector says bull” (30d BTC ≥ +15%) — not a full calendar buy-and-hold.
- Proxy is **BTC util-blend + USDC**, not full multi-asset ARCH-4 / RSI / sentiment book.
- Last **90 calendar days** had **0 bull-labeled days** → 90d alone cannot validate bull; bear had 30 labeled days (borderline OK for a mini check, primary still uses long tape).
- Next step after premise pass: **live-regime shadow confirm** when detector flips — still no live policy write without Brad.

## JSON
`reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.json`
