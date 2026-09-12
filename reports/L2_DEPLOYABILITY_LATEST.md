# L2 deployability (PC-04) — rel_btc_stable

**As of:** 2026-09-12T04:39:44.869264+00:00
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
| VVV-USD | 0.00 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| DOT-USD | -7.25 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| RAY-USD | 11.54 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| LIGHTER-USD | -3.81 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| ARB-USD | -13.62 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| AERO-USD | 3.96 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| WLD-USD | -13.98 | — | 52.0 | FAIL | recovery_soft_down quality_tryout_v2 tier_c_o... |
| TIA-USD | -14.19 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| OP-USD | -8.44 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| ASTER-USD | -7.43 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |
| NEAR-USD | 18.60 | — | 40.4 | FAIL | recovery_soft_down quality_tryout_v2 tier_c_o... |
| STX-USD | -5.37 | — | — | FAIL | recovery_soft_down quality_tryout_v2 outside_... |

## Promote gate reminder

- Do **not** treat L1 CF excess as deployable.
- Require L2 pass (or explicit Brad override) in promote packets.
- No live membership swap from this board.

State: `data/state/l2_deployability_latest.json`
