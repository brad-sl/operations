# Regime bear park test — 20260920

**As of:** `2026-09-20T07:07:32.180718+00:00`  
**Plan:** `PLAN-BEAR-PARK-001`  
**Live writes:** none  
**Policy sha256:** `f8c586e2697a8d08712be27d82feb32336e342b0a3cd4071857b2c57c10a5707`  

## Live fingerprint

- regime: **bear** · mode `usdc_park`
- allow_new_buys: **False** · cap `0.0`
- BTC 30d: `-14.699` · conf `0.467`
- live_is_bear: **True**

## Outcome

- class: `HIT_CRITERIA` · primary_pass: **True**
- enum: `propose_scoped_experiment` · N_days=442 · eps=59
- Bear premise HOLDS on 442d / 59 episodes: full park ret=4.2509% dd=0.0% vs tactical ret=-59.9482% dd=60.1954% vs BTC ret=-98.2137% dd=98.2565%.

## Bear paths (labeled days)

| Arm | util | ret% | maxDD% |
|-----|------|------|--------|
| full_park_usdc | 0.0 | 4.2509 | 0.0 |
| tactical_util_0_25 | 0.25 | -59.9482 | 60.1954 |
| flat_like_0_65 | 0.65 | -92.0176 | 92.1433 |
| full_btc | 1.0 | -98.2137 | 98.2565 |

## Decision

**No live promote.** Hist premise + live fingerprint only.
Follow-on: `scoped_shadow`.

JSON: `reports/REGIME_BEAR_PARK_TEST_20260920.json`

