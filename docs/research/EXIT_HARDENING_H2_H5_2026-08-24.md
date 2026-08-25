# Exit hardening H2–H5 — 2026-08-24

## H5 qty SSOT
- Module: `phase6/core/position_qty.py`
- Writers: `phase6_runner` dashboard build, `refresh_dashboard_live_state.py`
- Readers: lifecycle exits, shadow_tp live exits
- Aliases: `amount` = `qty` = `quantity`

## H4 post-TP structure-aware
- `runner_capital_events._apply_post_tp_structure_early_release`
- Only affects `post_tp_rebuy_block` (not SL blocks)
- Floor 4h; release if run phase ∈ {1,2} and structure_ok_for_entry

## H2 attach-on-buy
- Path wired via `effective_tp_pct_for_buy` → `OrderExecutor.execute_buy`
- Default `live_attach_on_buy=false` (software trail primary)
- Flip only with eyes open (exchange limit TP + software trail)

## H3 hard exit auto
- Ready: set regime_cash_policy.hard_exit operator_approve=false, live_apply=true, shadow_only=false
- Default remains human loop + TG notify
