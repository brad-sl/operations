# Process-tax clear A + cooloff 24h — Brad GO 2026-10-02

## Ask
- **A:** clear HYPE cooloff (process-tax auto-eject) + clear BTC `$369` cash hold mis-tag  
- Leave LINK/TIA 48h eject cooloffs and SOL real post-TP  
- Set `post_eject_pair_cooloff_hours` **48 → 24**

## Done

| Action | Result |
|--------|--------|
| HYPE cooloff file | Removed from `data/state/tryout_scale_window_cooloff.json` |
| HYPE capital_controls cooldown | Cleared on UUID account |
| HYPE ghost **post_tp** stack | Root-fixed: scale-window eject no longer mints `post_tp_rebuy_block` on top of cooloff SSOT |
| BTC `brad-primary` cash hold | **$369.48 → $0** (state + user_controls + runner_state) |
| Config cooloff | `config/tryout_scale_window.json` **24.0h** (note updated) |
| Code default | `tryout_scale_window.py` default cooloff 24h |

## Bug found mid-clear
Eject reason was in `_reason_is_strategy_profit_exit` **and** `load_buy_block_status` treated that as a **24h post_tp** block. So every scale-window eject got:
1. configured eject cooloff (48h then), **plus**
2. a second ledger TP block (24h)

HYPE after cooloff-file clear was still blocked ~14h via ghost TP. Fix: keep eject as strategy for disposition (not manual cash-park), but **skip** eject rows in the post_tp buy-block loop (`_reason_is_scale_window_eject`).

## Verify (live)
- **HYPE-USD FREE**
- **BTC-USD FREE**; brad-primary hold **$0**
- LINK/TIA still `rebuy_cooldown` ~24h left (intentional)
- SOL still `post_tp_rebuy_block` ~17h (real TP trail — intentional)
- `post_eject_pair_cooloff_hours` = **24.0**
- cooloff file pairs: LINK, TIA only

## Tests
- `test_isolation_tryout_scale_window.py` — 10/10 OK (eject ≠ post_tp block)
- `test_isolation_stop_exchange_disposition.py` — ALL PASS
- `test_isolation_core_sleeve_rotation_guards.py` — ALL PASS

## Not touched
- `live_apply` still ON  
- LINK/TIA cooloffs  
- SOL post-TP  
- `default` account hold $380 / OP-USD (unrelated)  
- No live orders  

## JSON receipt
`data/state/ops_process_tax_clear_latest.json`
