# BTC ROTATE_OUT dig + rebuy clear — 2026-10-02

Brad GO: **A + C**

## A — Why score 0.4 on green BTC

**Not a bug in the arithmetic. Bug is the *product rule*.**

1. `SignalGenerator._weighted_signal`: if `rsi > 70` → `score -= 0.4`, reason `RSI overbought`.
2. With exit RSI **71.96** and weak/flat sent (~0.08, not >0.2), internal score = **-0.4**.
3. `score < -0.25` → signal **SELL**, confidence = `abs(score)` = **0.4**.
4. `evaluation._signal_to_proposal`: SELL → **ROTATE_OUT**, proposal score = confidence **0.4**.
5. `RotationStrategy` (`allocator.py`): any held pair with side in `{ROTATE_OUT, SELL}` is **weak** → full `exit_weak_for_rotation` (no “are we green?” gate).
6. Redeploy failed: scanner ADA **0.499** and LINK **0.314** both **below** normal `min_buy_score` **0.55** → **sell-only**, cash parked.
7. Runner capital disposition mis-tagged the fill as `manual_liquidation_to_cash` and applied **48h rebuy block** (same path as human eject).

### What this means

- Score **0.4 is mean-reversion confidence**, not “BTC weakest vs ETH/SOL book”.
- Peers on HOLD got default confidence **0.5** (neutral), so BTC looked “weakest” only because overbought fired SELL.
- Rotation shadow correctly flagged `sell_stoch_overbought` (stoch 100, RSI 72) — aligned with mean-reversion exit, **not** with “ride continuation”.
- Chart felt wrong because **30m continuation** and **RSI>70 sell** are opposite product intents.

### Intended vs actual

| Layer | Claimed job | What ran |
|---|---|---|
| SignalGenerator | structure+sent | pure RSI>70 mean-reversion SELL |
| Allocator rotation | free weak → buy strong | freed BTC; **no** strong cleared 0.55 |
| Capital events | manual sell discipline | **auto rotation** got manual 48h block |

## C — Rebuy block lift (Brad GO)

- Cleared BTC-USD manual_sell_cooldown on account stores + request flag for runner.
- `load_buy_block_status()['BTC-USD']` → `None`
- `pair_process_tax_lockout_reasons('BTC-USD')` → `[]`
- Seat plan probe (lab gates): status planned / entry_allowed (not an order).
- **No buy placed.** Cooloff lift ≠ chase. Next rebalance/RSI path may consider BTC under normal gates.

## Residual risks / follow-ups (not done unless GO)

1. **Product:** stop treating RSI>70 SELL as full-bag rotation on core BTC while dual-peak/meat gates exist — or require green-meat / structure-break for core sleeve exits.
2. **Capital taxonomy:** rotation/executor sells must not inherit `manual_liquidation_to_cash` + 48h block.
3. **Sell-only rotation:** if no ROTATE_IN ≥ 0.55, prefer hold weak core over naked cash (or lower recycle bar explicitly).
4. **Holdings_before $0.023 vs $369 sell** — map/unit bug worth a separate ticket.

## JSON receipt

```json
{
  "ts": "2026-10-02T05:00:42.573450+00:00",
  "brad_go": "A+C 2026-10-02",
  "A_root_cause": {
    "score_0_4": "SignalGenerator weighted: RSI>70 \u2192 score -= 0.4 \u2192 SELL conf 0.4 \u2192 Proposal ROTATE_OUT",
    "not_a_relative_weakness_rank": true,
    "rsi_at_exit": 71.96,
    "stoch_k": 100.0,
    "sentiment_at_exit": 0.080919,
    "reason_string": "RSI overbought",
    "allocator": "explicit ROTATE_OUT always weak if held; exit_weak_for_rotation full bag",
    "no_recycle": "ADA ROTATE_IN 0.499 and LINK 0.314 both < min_buy_score 0.55 \u2192 sell-only cash park",
    "false_manual_tag": "capital event tagged rotation sell as manual_liquidation_to_cash + 48h block",
    "holding_bug_note": "decision holdings_before BTC-USD showed $0.023 while sell usd $369 \u2014 display/map bug; exchange qty real"
  },
  "C_actions": {
    "cleared_accounts": [
      "3176ac3f-deca-4fca-9c67-87ba91f96558",
      "brad-primary"
    ],
    "btc_block_after": null,
    "lockout_after": [],
    "no_order_placed": true,
    "rebuy_not_forced": true
  }
}
```
