# Run Lifecycle LIVE deploy — 2026-08-24

## Loop

1. **Fish early** — ignition scout `mode=propose` on rebalance; phases 1–2 only + structure (RSI×MA/Fib).
2. **Size** — `deploy_frac=0.18` of equity per seat, max 4 non-ballast seats, pair weight ≤30%, free-cash share ≤50%.
3. **Persist** — `hold_while_metrics_and_sent_agree`: no dual-peak exit while phase≤trend and sent not faded.
4. **Jump before dump** — `dual_peak_exit.mode=live` via monitor: dual_peak 50% trim; extension_partial 33% when phase≥3 even if sent still hot.
5. **Still blocked** — run_phase P0 blocks NEW buys phase≥3; rsi_primary caps non-ignition tickets.

## Knobs (`config/trading_config_phase6.json` → `run_lifecycle`)

- `ignition_scout.mode`: propose | shadow | off
- `ignition_scout.deploy_frac`: 0.15–0.20 recommended
- `dual_peak_exit.mode`: live | shadow | off

## Safety

- Max 2 live trims per monitor tick; min trim $40; PAXG ballast excluded.
- Live TP/SL still primary disaster/trail path.
- Sentiment-fade remains **shadow** to avoid double-sell with dual_peak.

## EXIT-H1 — SL reattach (done)

After every live lifecycle **partial** sell:
1. `cancel_open_stops_for_pair`
2. `poll_available_after_cancel` / settle
3. `resolve_sl_attach_size` (exchange free qty; hint = residual)
4. `StopLossManager.attach_stop_loss(pair, lot_entry_anchor, size, fresh_buy=False)`

Full exit (`trim_frac≥0.99`): cancel stops only, no reattach.
Serialized with `live_max_trims_per_tick` (default 2) — still **one pair at a time** inside the loop.
