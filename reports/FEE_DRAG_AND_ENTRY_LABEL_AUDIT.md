# Fee drag + entry label audit

**As of:** 2026-08-31T07:26:07.248928+00:00  
**NAV snapshot:** $2,294.77

Read-only. No live changes. Full JSON: `reports/FEE_DRAG_AUDIT_LATEST.json`.

## Headline (plain English)

- **Last 30d Coinbase fees paid: $138.89** on ~$16,766 notional (**0.8284% of notional**).
- That is **~6.052% of current book NAV** (~$2,295) in one month of **house cut alone** — before spreads/slippage.
- **90d fees: $217.90** (~9.496% of NAV).
- Fill mix 30d: **{'taker_stop': 13, 'taker': 41}** — order types are **MARKET + STOP_LIMIT only** in verified set (no LIMIT/maker path observed here).
- Median fee rate on sized fills: **0.8%** (p75 0.8%) → sits in **taker / high-tier retail** territory, not maker 0.05–0.25%.

### What this means for the macro discussion

1. **The house is already winning on this book via turnover style** — even when individual trades look small.
2. **Aspiration ‘we are makers’ ≠ realized path** on verified fills (rebalance buys as MARKET; exits often STOP_LIMIT).
3. Cutting **unnecessary round-trips** and preferring true maker entries is direct edge vs the toll booth — independent of signal IQ.

## Fee drag detail

### 30d
- Fills: 54 (~1.8/day)
- Fees by class: `{'taker_stop': 38.1693, 'taker': 100.7174}`
- Reasons: `[['rebalance_buy', 35], ['stop_loss_exchange', 13], ['rotation_exchange', 6]]`
- Order types: `[['MARKET', 41], ['STOP_LIMIT', 13]]`
- Top pairs by fee: `[['LINK-USD', 56.4387, 9, 6546.72], ['BTC-USD', 34.603, 10, 4325.38], ['UNI-USD', 21.4854, 9, 2685.67], ['ICP-USD', 13.0377, 4, 1629.72], ['RAVE-USD', 7.76, 6, 883.1], ['SOL-USD', 2.6206, 7, 327.58], ['OP-USD', 1.4739, 2, 184.24], ['PAXG-USD', 1.4673, 6, 183.41], ['ADA-USD', 0.0, 1, 0.0]]`
- By month (inside 90d window): `{'2026-06': {'fees': 26.3562, 'n': 43, 'notional': 3080.2403}, '2026-07': {'fees': 52.659, 'n': 78, 'notional': 5606.0815}, '2026-08': {'fees': 138.8867, 'n': 54, 'notional': 16765.8211}}`

### Method caveats

- Maker/taker from **order_type heuristic** (LIMIT→maker, STOP→taker_stop, MARKET→taker). Coinbase liquidity flag not present on these rows.
- Deduped `phase6_exchange_fills.jsonl` + `verified_fills_*.jsonl` by `order_id`.
- August notional/fees jumped vs June–July — check whether larger tickets or more churn.

## Entry labels (90d)

Frozen rules:

- **heat_reaction:** 24h return ≥12% OR (24h ≥8% and RSI ≥70) OR 6h return ≥8% at buy time
- **process:** signal/source hints rebalance/runner/rsi/… AND 24h return <5%
- **process_in_elevated_tape:** process machinery but tape already up
- **ambiguous:** else (often fill-reconcile without clean source tag)

**Counts:** `{'ambiguous': 70, 'heat_reaction': 2, 'process': 121, 'process_in_elevated_tape': 5}`  
**Buys labeled:** 198

**Crude exit outcome** (first verified SELL same pair within 21d): `{'ambiguous': {'n_with_exit': 57, 'win_rate': 0.404, 'sum_pnl': 81.08, 'avg_pnl': 1.42}, 'heat_reaction': {'n_with_exit': 2, 'win_rate': 0.0, 'sum_pnl': -24.59, 'avg_pnl': -12.29}, 'process': {'n_with_exit': 111, 'win_rate': 0.378, 'sum_pnl': -24.95, 'avg_pnl': -0.22}, 'process_in_elevated_tape': {'n_with_exit': 5, 'win_rate': 0.0, 'sum_pnl': -108.25, 'avg_pnl': -21.65}}`

### Read of labels

- **Heat-chase buys are rare** under these thresholds (good vs pure FOMO narrative).
- Large **process** bucket is mostly `phase6_fresh_start` / `arch4_rebalance` / reconcile — machinery entries, not Twitter-chase. Still can be *late* on a name without tripping heat rules.
- **ambiguous** needs cleaner `signal_source` on ledger rows for future audits.
- Outcome PnL is **lot-imperfect**; use as directional only. phase6.db `trades` table is BUY-heavy and not usable for exit WR here.

### Newest 15

- `2026-08-29T04:00:44.735378+00:00` **ICP-USD** `ambiguous` r24=0.29 r6=3.01 rsi=72.4 src=`coinbase_fill_reconcile` next_pnl=-1.273484 reason=rotation_exchange
- `2026-08-28T04:02:49.668512+00:00` **ICP-USD** `ambiguous` r24=1.04 r6=-1.32 rsi=37.2 src=`coinbase_fill_reconcile` next_pnl=-14.109459 reason=stop_loss_exchange
- `2026-08-24T16:00:30.645689+00:00` **LINK-USD** `ambiguous` r24=0.8 r6=-0.05 rsi=45.7 src=`coinbase_fill_reconcile` next_pnl=114.117624 reason=stop_loss_exchange
- `2026-08-23T18:04:41.712136+00:00` **UNI-USD** `ambiguous` r24=7.31 r6=5.64 rsi=61.2 src=`coinbase_fill_reconcile` next_pnl=-21.287068 reason=stop_loss_exchange
- `2026-08-23T16:00:56.295906+00:00` **BTC-USD** `ambiguous` r24=0.18 r6=0.76 rsi=51.6 src=`coinbase_fill_reconcile` next_pnl=None reason=None
- `2026-08-23T16:00:35.121552+00:00` **UNI-USD** `heat_reaction` r24=8.62 r6=8.46 rsi=64.2 src=`coinbase_fill_reconcile` next_pnl=-21.287068 reason=stop_loss_exchange
- `2026-08-23T04:00:57.885340+00:00` **RAVE-USD** `ambiguous` r24=-15.34 r6=-0.31 rsi=30.6 src=`coinbase_fill_reconcile` next_pnl=-11.811637 reason=stop_loss_exchange
- `2026-08-21T18:30:08.465572+00:00` **LINK-USD** `ambiguous` r24=8.97 r6=3.07 rsi=59.9 src=`coinbase_fill_reconcile` next_pnl=114.117624 reason=stop_loss_exchange
- `2026-08-15T04:06:42.844049+00:00` **BTC-USD** `ambiguous` r24=-0.49 r6=0.21 rsi=53.7 src=`coinbase_fill_reconcile` next_pnl=2.183961 reason=rotation_exchange
- `2026-08-15T04:01:04.525618+00:00` **BTC-USD** `ambiguous` r24=-0.42 r6=0.19 rsi=53.7 src=`coinbase_fill_reconcile` next_pnl=2.183961 reason=rotation_exchange
- `2026-08-14T16:06:07.200210+00:00` **UNI-USD** `ambiguous` r24=-6.56 r6=-5.6 rsi=37.1 src=`coinbase_fill_reconcile` next_pnl=-1.796031 reason=stop_loss_exchange
- `2026-08-14T16:00:44.360722+00:00` **UNI-USD** `ambiguous` r24=-6.7 r6=-5.63 rsi=37.1 src=`coinbase_fill_reconcile` next_pnl=-1.796031 reason=stop_loss_exchange
- `2026-08-12T16:06:13.951430+00:00` **BTC-USD** `ambiguous` r24=-0.25 r6=-1.03 rsi=32.1 src=`coinbase_fill_reconcile` next_pnl=2.183961 reason=rotation_exchange
- `2026-08-12T16:00:39.467198+00:00` **BTC-USD** `ambiguous` r24=-0.3 r6=-1.07 rsi=32.1 src=`coinbase_fill_reconcile` next_pnl=2.183961 reason=rotation_exchange
- `2026-08-12T04:06:28.774044+00:00` **RAVE-USD** `ambiguous` r24=-0.73 r6=1.52 rsi=46.9 src=`coinbase_fill_reconcile` next_pnl=-0.97043 reason=stop_loss_exchange

## Artifacts

| File | Role |
|------|------|
| `reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md` | This brief |
| `reports/FEE_DRAG_AUDIT_LATEST.json` | Full fee + summary JSON |
| `reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json` | Per-buy labels |
| `scripts/phase6/audit_fee_drag_and_entry_labels.py` | Re-run audit |
| `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md` | Macro discussion SSOT |
| `docs/faq/External_Client_FAQ.md` | Client “who gets paid” |

## Follow-ups (not done tonight)

1. Why verified path is MARKET-heavy — limit entry path regression?  
2. Maker fee tier on live Coinbase account vs 0.8% median realized.  
3. Tighter heat label using discovery score / contender flags.  
4. Proper lot-matched round-trip PnL after fees.

