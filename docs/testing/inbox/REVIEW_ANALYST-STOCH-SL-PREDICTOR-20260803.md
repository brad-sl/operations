# Review — ANALYST-STOCH-SL-PREDICTOR-20260803

**Status:** REPORT_READY  
**Suggested decide:** `no_utility_drop`  
**Generated:** 2026-08-03T17:53:27.381398+00:00

## Plain English
We asked: does low Stoch at *buy* mean you're more likely to get stopped out later?

- **Strict window (since Stoch trial launch):** only 6 buys with entry Stoch — too few to call.
- **Dig (history overlap from 2026-07-11):** 29 buys with entry Stoch. Low Stoch entries stopped **less often** than high Stoch (38% vs 50% at 7d) — lift **0.77x (wrong direction)**.
- At stop time, Stoch often looks terrible (trailing). That does **not** make it a leading SL predictor.
- Thin RSI-neutral sub-split looked slightly hot but n too small to trust.

**Utility call:** no leading SL-prediction utility for threshold rules. Keep Stoch on risk **narrative/scorer labels**. Do **not** gate SL distance or entries on Stoch.

## Paths
- `reports/STOCH_SL_PREDICTOR_DIG_2026-08-03.md`
- `reports/STOCH_SL_PREDICTOR_OFFLINE_2026-08-03.md`

## Decide
```bash
.venv/bin/python3 phase6/research/trial_cycle.py decide ANALYST-STOCH-SL-PREDICTOR-20260803 no_utility_drop --note 'entry stoch not predictive of SL; trailing only'
```
