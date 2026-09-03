# Decide packet — P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816

**Date:** 2026-08-18  
**Outcome enum:** **`inconclusive`**  
**Live promote:** false (hard)  
**Live book / config:** unchanged

## Hypothesis
72h hold-cash ISO ≠ proven less-loss. Need second-SL rate and $ recycle under enforce hold on real ledger.

## Evidence (real ledger)

| Gate | Result |
|------|--------|
| min_n re-entry ≥15 | **PASS** (n=34) |
| rebuy@24/48/72h | 0.1136 / 0.1591 / 0.3636 (of core SL) |
| second SL rate (of rebuys) | **0.8529** |
| early rebuy &lt;72h frac | **0.4706** |
| recycle stack $ | -488.9608 |

Artifacts:
- `data/state/post_sl_reentry_eff_latest.json`
- `reports/POST_SL_REENTRY_EFF_LATEST.md`
- `scripts/phase6/run_post_sl_reentry_eff.py`
- `scripts/phase6/test_isolation_post_sl_reentry_eff.py`

## Decision
- **CR:** `inconclusive`
- **Reasons:** mixed early/second-SL pattern without clear less-loss proof; recycle_stack_pnl_usd=-488.9608 with elevated second SL
- **Must not:** shorten cooldown to catch bounce; live promote; capital rewrite

## Follow-on
- If `tighten`: offline design only for stronger post-SL block / pair cooldown — **Brad gate** before any config write
- If `hold_ok`: keep 72h; monitor weekly re-run of this script
- If `inconclusive`: collect more episodes; do not flip policy
- Staged next fleet lever: GAP-03 cap scope matrix (from BoN runner-up)
