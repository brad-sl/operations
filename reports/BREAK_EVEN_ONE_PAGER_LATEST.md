# Break-even one-pager

**As of (PT):** `2026-09-23T10:32:20.288193-07:00`
**Window:** `2026-09-22T17:32:20.288193+00:00` → `2026-09-23T17:32:20.288193+00:00` (1d) · week_start_pt=`2026-09-23`
**Bar:** ≥ **$150.0/mo** take-home

> Measure-only. No knobs. No edge claim from thin N.

## Go / no-go vs bar

- **Verdict:** `N_INSUFFICIENT_path_proof_only`
- **Gross RT PnL (window):** `$1.4776` · n=1
- **Process tax:** n=0 · `$0.0`
- **Non-tax exits:** n=1 · `$1.4776`
- **Est X to date:** `$3.57` (assumption $25.0/wk)
- **Net RT − est X (to date):** `$-2.09`
- **Illustrative gross run-rate $/mo:** `44.33`
- **Illustrative gap after est X vs BE:** `214.0`
- **Edge claim:** `False` — No edge claim: need n_rt_primary≥20 with solid stamps

## Book / regime

- Portfolio ~`$105.09` · holdings ~`$105.09` · risk seats open≈2
- Regime: `flat` / `None` · cap=`None` · allow_new_buys=`True`
- Fees: maker=`None` taker=`None` (None)

## X activity

- Today pair-queries: 1 (rsi=1 rebal=0)
- Probe events in week window: 1
- Primary schedule: 2x/day 09:00+21:00 PT (phase6-x-sentiment-live-2x)
- Note: operator estimate (~$25/wk) until X billing SSOT; not invoice-read

## Buckets

```json
{
  "tp_profit": 1
}
```

State: `data/state/break_even_one_pager_latest.json`
Report: `reports/BREAK_EVEN_ONE_PAGER_LATEST.md`

Run-rate is days-scaled illustration only — not a forecast. Thin N → no edge claim. X $ is assumption until billing SSOT.
