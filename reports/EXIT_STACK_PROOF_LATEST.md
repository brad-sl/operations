# Exit stack proof — 2026-09-12T01:44:56.346480+00:00

**Headline:** NO-GO further live exit knob expansion without Brad

> NO-GO further live exit knob expansion without Brad. 30d TP bank $88.38 (n=6) vs SL bank $-84.61 (n=9). Blank tags 30d: 0/42.

## Live vs shadow inventory

| Layer | State | Live orders | Notes |
|-------|-------|-------------|-------|
| stop_loss_exchange | live | True | Exchange SL + A1 settle/naked-bag fail-closed |
| take_profit_trail_fixed | live | True | LIVE trail primary (arm+4%/trail 2%), fixed +6% software fallback. live_attach_o |
| hard_exit_rsi_sent | live_cautious_flat | False | H3 cautious flat (2026-08-25): operator_approve remains true globally; flat may  |
| dual_peak_lifecycle | live | — |  P0-20260826: no red half-trim; max 1 dual_peak/lot until new peak. |
| regime_exit_map | shadow | False | Global trail/fixed live via exit_automation; map stays shadow unless live_apply |

## Ledger RT banks

### 7d
- sells=14 buys=11 · tp:sl counts=2:2
- TP bank `$8.1783` · SL bank `$-3.9689` · process_tax `$-4.0458` · net `$4.119`
- buckets: `{'rotation': 7, 'dust_sweep': 3, 'sl_exchange': 2, 'tp_profit': 2}`

### 30d
- sells=42 buys=26 · tp:sl counts=6:9
- TP bank `$88.381` · SL bank `$-84.6149` · process_tax `$-86.3263` · net `$2.9516`
- buckets: `{'dust_sweep': 10, 'rotation': 9, 'sl_exchange': 9, 'tp_profit': 6, 'dual_peak': 4, 'operator_manual': 3, 'lifecycle_partial': 1}`

## Disposition honesty
- ok: `True`
- issues: []

## Go / no-go packet
- brad_required_for_any_live_flip: `True`

- **take_profit_live_keep**: `KEEP_AS_IS` — Already mode=live, live_market_exit=True; auto_promote=False. No silent flip.
- **hard_exit_global_auto**: `NO-GO` — operator_approve=True, live_apply=False, shadow_only=True. Need clear CF edge vs ride-to-SL + Brad GO before global auto.
- **hard_exit_cautious_flat**: `KEEP_AS_IS` — Cautious flat path already staged; do not widen regimes without evidence.
- **live_attach_on_buy_h2**: `NO-GO` — live_attach_on_buy=False — wired default false; software market exit primary.
- **process_tax_pressure**: `WATCH` — 30d SL bank $-84.61 (n=9) vs TP bank $88.38 (n=6); process_tax_usd=-86.33; net=2.95.
- **window_7d**: `INFO` — 7d sells=14 tp:sl=2:2 tp_bank=$8.18 sl_bank=$-3.97
- **disposition_tags**: `OK` — blank/ambiguous tags within tolerance

## Must not
- Flip live TP/hard_exit without Brad GO
- Claim CF without stops as edge
- Treat would-fire tick spam as N
