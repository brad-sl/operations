# NEEDLE-04 — SL × fee geometry (proposal, not live)

**Status:** isolation guard shipped; **geometry APPLIED 2026-09-30** (Brad GO live knobs). See `docs/NEEDLE_04_APPLY.md`.

## Attach path that fired Sep 9 (LINK 16:01 buy → 16:07 SL void)

`phase6.core.order_executor.OrderExecutor._finalize_buy_fill`
→ `StopLossManager.attach_stop_loss(..., fresh_buy=True)`
immediately after a **limit_first** fill.

`same_session_sl.py` is a **ledger metric only**. It did not block attach. Several P6-OPS same-session cards closed while this path still fired.

Guard now: `phase6.core.same_session_sl_guard` — after `limit_post_only` / limit_first fill, **no SL attach for 60 minutes**. A −3% print at +6m cannot void the bag because no native stop exists yet. Runner tick `process_deferred_sl_attaches` attaches after the window. Core BTC/ETH stay on NEEDLE-03 skip (no 3%).

## Geometry (draft — do not write `trading_config_phase6.json`)

| Sleeve | Live today | Proposal |
|---|---|---|
| Tryout (LINK $25) | `stop_loss_pct` **3%** | Floor **6–8%** *or* drop hard stop and let dual-peak / 4% TP-arm be the exit |
| Core BTC/ETH | no 3% (skip_sl) | Structure stop **~8%** or dual-peak only — never 3% |
| Fees | Intro **0.9% taker / 0.5% maker** | Maker exits only; market rotation sells pay 0.9% |

Why 3% is −EV: stop 3% + taker ~0.9% on the void ≈ 4% scratch before spread. Lifetime **82 SL vs 4 TP**. Dual-peak/TP arm is 4% — the stop is tighter than the take.

## Must not (this card)

- Live `stop_loss_pct` write
- Live orders to change LINK/PAXG stops
- `enforce: false`
