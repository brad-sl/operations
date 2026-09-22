# L2 deployability (PC-04) — rel_btc_stable

**As of:** 2026-09-22T21:52:02.549927+00:00
**Schema:** `l2_deployability_v1`
**live_membership_swaps:** `False` (must stay false without Brad GO)

## Summary

- Scored ADDs: **12**
- L2 pass: **0** · fail: **12**
- L2 pass rate: **0.0**
- Verdict: **L2_BLOCKED**
- L1 CF ≠ L2 deploy. Promote packets need L2 pass rate, not paper excess alone.

## Rows (preferred arm ADDs)

| pair | L1 excess% | eng_sent | rsi | L2 | top reason |
|------|------------|----------|-----|----|------------|
| NEAR-USD | 0.00 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| UNI-USD | -3.02 | — | — | FAIL | buy_block_pairs UNI-USD |
| ONDO-USD | -8.01 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| SUI-USD | 4.74 | — | 45.9 | FAIL | sentiment_missing |
| AAVE-USD | -10.45 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| DASH-USD | -18.84 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| LIGHTER-USD | -19.88 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| ARB-USD | 14.28 | — | 49.1 | FAIL | recovery_soft_down quality_tryout_v2 ledger_f... |
| PENDLE-USD | -14.90 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| FIL-USD | -8.72 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| DOT-USD | -0.46 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| REZ-USD | -12.61 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |

## Promote gate reminder

- Do **not** treat L1 CF excess as deployable.
- Require L2 pass (or explicit Brad override) in promote packets.
- No live membership swap from this board.

State: `data/state/l2_deployability_latest.json`
