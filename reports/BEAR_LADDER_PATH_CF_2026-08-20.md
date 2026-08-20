# Bear ladder path CF (P2)

**As of:** 2026-08-20T23:59:22.109658+00:00
**Recommendation:** `pursue_shadow`
**Live money:** False

## Plain English

Ladder beats ride-to-SL by ~0.94% mean R on N=276. Keep Phase-1 shadow; **not** a live promote. Absolute ladder mean R is still negative (-0.96%) — this is **less-loss vs ride-SL**, not a profit engine. Sample is **synthetic bear entries on real daily bars** (0 ledger legs entered in bear) — treat as design evidence, not live book proof. Note: full +6% TP mean R (-0.88%) also beats ride-SL here; ladder is not uniquely magical vs one-shot TP on this tape.

## Setup

- SL floor: 0.03
- Ladder: [{"level": 1, "r_pct": 0.03, "sell_frac": 0.25, "label": "first_slice"}, {"level": 2, "r_pct": 0.05, "sell_frac": 0.25, "label": "second_slice"}, {"level": 3, "r_pct": 0.08, "sell_frac": 0.25, "label": "third_slice"}]
- Moon bag: 0.25
- BTC bars: 2093
- Ledger rounds (all regimes): 0 `{}`
- Ledger bear legs scored: 0
- Synthetic bear paths: 276
- Combined: 276

## Results by sample

### ledger_bear
- N=0 · call **inconclusive**
- Only 0 paths (need ≥15). Keep shadow; do not promote.
- sl_ride mean R: None
- ladder mean R: None
- full_tp_06 mean R: None
- Δ ladder−SL mean: None · ladder beats SL on None
- mean ladder slices/path: None

### synthetic_bear
- N=276 · call **pursue_shadow**
- Ladder beats ride-to-SL by ~0.94% mean R on N=276. Keep Phase-1 shadow; **not** a live promote. Absolute ladder mean R is still negative (-0.96%) — this is **less-loss vs ride-SL**, not a profit engine. Sample is **synthetic bear entries on real daily bars** (0 ledger legs entered in bear) — treat as design evidence, not live book proof. Note: full +6% TP mean R (-0.88%) also beats ride-SL here; ladder is not uniquely magical vs one-shot TP on this tape.
- sl_ride mean R: -0.019062
- ladder mean R: -0.00964
- full_tp_06 mean R: -0.008848
- Δ ladder−SL mean: 0.009421 · ladder beats SL on 0.942
- mean ladder slices/path: 0.917

### combined_bear
- N=276 · call **pursue_shadow**
- Ladder beats ride-to-SL by ~0.94% mean R on N=276. Keep Phase-1 shadow; **not** a live promote. Absolute ladder mean R is still negative (-0.96%) — this is **less-loss vs ride-SL**, not a profit engine. Sample is **synthetic bear entries on real daily bars** (0 ledger legs entered in bear) — treat as design evidence, not live book proof. Note: full +6% TP mean R (-0.88%) also beats ride-SL here; ladder is not uniquely magical vs one-shot TP on this tape.
- sl_ride mean R: -0.019062
- ladder mean R: -0.00964
- full_tp_06 mean R: -0.008848
- Δ ladder−SL mean: 0.009421 · ladder beats SL on 0.942
- mean ladder slices/path: 0.917

## Per-pair (combined)

| Pair | N | call | mean Δ ladder−SL | ladder mean R | sl mean R |
|------|---|------|------------------|---------------|-----------|
| ARB-USD | 9 | inconclusive | 0.015754 | -0.009992 | -0.025747 |
| AVAX-USD | 43 | pursue_shadow | 0.008495 | -0.012491 | -0.020986 |
| BTC-USD | 50 | pursue_shadow | 0.011034 | -0.008878 | -0.019911 |
| DOGE-USD | 9 | inconclusive | 0.00876 | 0.001599 | -0.007161 |
| ETH-USD | 50 | pursue_shadow | 0.005206 | -0.005002 | -0.010208 |
| LINK-USD | 50 | pursue_shadow | 0.008274 | -0.008891 | -0.017165 |
| NEAR-USD | 9 | inconclusive | 0.014889 | -0.017111 | -0.032 |
| SOL-USD | 47 | pursue_shadow | 0.013553 | -0.018447 | -0.032 |
| XRP-USD | 9 | inconclusive | 0.00196 | 0.012384 | 0.010423 |

## Notes

- Optimistic threshold fills when day's high tags level; SL same-day wins on residual.
- Synthetic entries: close on bear-regime day, path up to 45d, stride 14d — real bars only.
- Not a live promote. Shadow collection still required in live bear.

## Next

- If `pursue_shadow`: keep P1 runner shadow; do **not** live_apply.
- If `drop`: disable ladder enabled or redesign tranches after review.
- If `inconclusive` / `no_clear_edge`: hold shadow, no edge marketing.
