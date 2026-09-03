# Stand-down filter C — exploitability dig

**As of:** 2026-08-31T17:10:32.519974+00:00  
**NAV:** $2,294.92  
**Window:** 90d buys · exit horizon 21d  
**Mode:** read-only counterfactual · **no live changes**  

## Plain English

**GO/NO-GO:** `SHADOW_ONLY`

ATTENTION_ONLY — C (process on r24>=5) would have avoided net losses on this sample; half-sample both negative avg with n>=3 each. Not HIT abs return. **Shadow gate candidate only** — not live.

- Primary C (process + r24>=5): blocked n=9 with_exit=8 cf_avoided_net=$88.51 (3.86% NAV) class=ATTENTION_ONLY_less_loss_path
- Strict heat process block: n=2 cf=$8.88 class=inconclusive_sparse_N
- Soft elev process block: n=57 cf=$117.12 class=ATTENTION_ONLY_less_loss_path

## What C is

When tape is already elevated, **do not let process machinery enter** (rebalance/allocator/runner buys). Not chase-whale. Not buy-the-FOMO-leg.

## Frozen elevated definitions

- `heat_strict`: r24>=12 OR (r24>=8 & RSI>=70) OR r6>=8
- `elev_r24_5`: r24>=5 (elevated; process-on-heat boundary)
- `elev_r24_8`: r24>=8 OR r6>=5
- `elev_soft`: r24>=3 OR r6>=3 OR RSI>=65

## Baseline (all buys in window)

- Buys: **297** · with exit match: **161**
- All matched outcome: `{'n': 161, 'win_rate': 0.137, 'sum_pnl': -760.89, 'avg_pnl': -4.73, 'median_pnl': -1.88, 'p25': -5.41, 'p75': -0.34}`
- Process-hint buys: **225** (includes `coinbase_fill_reconcile` + reason `rebalance_buy` — intentional)
- Buy fees (used/imputed): **$268.72**
- **Important:** calm process is also red on this sample — C is less-loss on hot tape, not proof process works when calm.

## Calm vs elevated process (`elev_r24_5`)

- Calm process: `{'n': 90, 'win_rate': 0.156, 'sum_pnl': -427.18, 'avg_pnl': -4.75, 'median_pnl': -1.83, 'p25': -4.9, 'p75': -0.33}`
- Elevated process: `{'n': 8, 'win_rate': 0.0, 'sum_pnl': -88.51, 'avg_pnl': -11.06, 'median_pnl': -5.33, 'p25': -8.57, 'p75': -2.74}`
- Δ avg (elev − calm): **-6.32**

## Counterfactuals (process-on-elevated block)

| Def | n_block | n_exit | blocked avg pnl | CF avoided net | %NAV | class |
|-----|---------|--------|-----------------|----------------|------|-------|
| `heat_strict` | 2 | 2 | -4.44 | $8.88 | 0.39% | inconclusive_sparse_N |
| `elev_r24_5` | 9 | 8 | -11.06 | $88.51 | 3.86% | ATTENTION_ONLY_less_loss_path |
| `elev_r24_8` | 5 | 4 | -17.78 | $71.11 | 3.1% | inconclusive_sparse_N |
| `elev_soft` | 57 | 22 | -5.32 | $117.12 | 5.21% | ATTENTION_ONLY_less_loss_path |

### All-elevated block (stricter arm)

| Def | n_block | n_exit | CF avoided net | %NAV | class |
|-----|---------|--------|----------------|------|-------|
| `heat_strict` | 3 | 3 | $11.64 | 0.51% | inconclusive_sparse_N |
| `elev_r24_5` | 12 | 11 | $149.44 | 6.51% | ATTENTION_ONLY_less_loss_path |
| `elev_r24_8` | 8 | 7 | $132.04 | 5.75% | inconclusive_sparse_N |
| `elev_soft` | 63 | 28 | $187.16 | 8.26% | ATTENTION_ONLY_less_loss_path |

## Half-sample stability (primary `elev_r24_5` process block)

- H1: `{'n': 3, 'win_rate': 0.0, 'sum_pnl': -13.39, 'avg_pnl': -4.46, 'median_pnl': -4.53, 'p25': -6.12, 'p75': -2.74}`
- H2: `{'n': 5, 'win_rate': 0.0, 'sum_pnl': -75.12, 'avg_pnl': -15.02, 'median_pnl': -8.57, 'p25': -25.34, 'p75': -2.76}`

## Caveats

- Imperfect lot match (first SELL within 21d)
- Fee imputation when ledger fee blank
- No path simulation of capital reuse after block
- Blocking winners hurts CF — reported honestly
- Not walk-forward optimized; half-sample split only
- No live gate / no promote

## Artifacts

- `reports/STANDDOWN_FILTER_C_DIG.json`
- `reports/STANDDOWN_FILTER_C_DIG.md` (this file)
- `scripts/phase6/dig_standdown_filter_c.py`

## Edge vocabulary

- No `HIT_10/20_*` claimed.
- Best available tag from this dig is `ATTENTION_ONLY` or `inconclusive` / `no_edge`.
- Live gate requires Brad GO + shadow period — not auto from this file.

