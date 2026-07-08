# LIVE_CUTOVER.md — Phase 6 Final Prep for Live Deployment (2026-07-03)

**Task:** LIVE-PREP-03 (t_19b7fbf5)
**Status:** Tested + Ready for live cutover
**Key Config:** global_settings.use_new_allocator=True (primary ARCH-4 path)
**Verified:** force_rebalance.flag handling, full 11-pair basket, shadow/paper runs

## Summary of Final Verification
- **use_new_allocator**: Confirmed True in config + runner init. Primary path: evaluate_universe + Allocator + RotationStrategy (catch-the-wave) + TradePlan.
- **force_rebalance.flag**: Explicitly tested — touch creates it; _should_rebalance detects, logs "[FORCE] Manual rebalance triggered via flag file", unlinks it, forces rebalance. Also used in prior shadow cycles.
- **Basket/Uniformity**: 11 pairs from load_trading_basket() (central in paths.py). All components (fetchers, scorer, evaluate, allocator, DB, brief) use full dynamic basket. No hardcodes left in core.
- **Shadow + Paper Runs (this session)**: Full cycles executed successfully post-prep.
  - Shadow (run_shadow_rebalance_cycle.py --mode shadow --new-allocator): 11/11 coverage, 11 proposals, ARCH-4 plan with rotations (SELL 1 + BUY 3), exposure=100%, strategy=rotation_catch_wave, SL re-attach for 3 pairs, intelligence brief generated.
  - Paper (run_paper.py --cycles=3): 2 simulated trades executed, portfolio sim OK.
  - Direct runner cycles and flag test also confirmed.
- **Evidence Artifacts**: phase6_live_state.json, runner logs, DB proposals (11-packs), brief, handoff prep.

## Production Readiness Items Noted
- **SL Cancel-First (CR-03 pattern)**: Mandatory before sells or rebalance rotations. Code: stop_loss_coordinator.suspend_protective_orders + stop_loss_manager CR-03 suspend/cancel active SLs for affected pairs (releases holds to avoid INSUFFICIENT_FUND on subsequent sells/buys). Verified in logs: [CR-03] Entered suspend_reattach_context, suspended/re-attached stops, [SL-ANCHOR]. Always poll/confirm before re-attach on new positions. (See systematic-debugging notes for full pattern.)
- **Quantization & Dynamic Metadata**: Use exchange.get_product_metadata(pair) for real price_increment / base_increment (quote for BUY sizes, base for SELL). Strict quantization (e.g. _quantize_price, Decimal/ROUND_DOWN patterns in wrappers/executor/SL). Prevents PREVIEW_INVALID_STOP_PRICE_PRECISION and size errors. Fallbacks in old wrappers; phase6 SL uses live meta. Dynamic /products fetch recommended pre-trade in live paths.
- **Other**:
  - Config: trading_config_phase6.json / .yaml have use_new_allocator: true, full 11 pairs, rebalance_cap, risk params, _live_deployment notes.
  - rebalance_style: "permissive_deploy" (with new allocator primary).
  - Scheduler: daily 09:00/21:00 via crons + --rebalance-only or flag.
  - Live command: `python3 phase6/core/phase6_runner.py --mode live --confirm-live` (after shadow).
  - Monitor: order IDs/tx success on fills, DB proposals, SL attachments, cash/holds.
  - Fresh start / hybrid guards preserved.
  - No legacy bypass when flag true.

## Handoff / Cutover Steps
1. Review this + Live_Cutover_Prep_2026-07-03.md + recent MASTER.
2. One final shadow (already done in this prep).
3. Ensure no blocking force_rebalance.flag or stale state.
4. Trigger live with confirm: python phase6/core/phase6_runner.py --mode live --confirm-live (or via cron wrapper).
5. Immediate post-first-cycle: check Coinbase for real orders (tx IDs), positions, attached SLs (use cancel-first for any manual).
6. Update MASTER with live results (fills, P&L impact, any issues).
7. Enable monitoring/dashboard, analyst briefs.
8. If issues: revert to shadow, debug with isolation tests.

## Key Files
- phase6/core/phase6_runner.py (flag logic lines ~574, use_new_allocator ~134, _perform_daily_rebalance ARCH-4 ~978+)
- phase6/core/paths.py (load_trading_basket)
- config/trading_config_phase6.json (use_new_allocator: true, pairs:11)
- phase6/core/stop_loss_coordinator.py + stop_loss_manager.py (CR-03 cancel/suspend)
- scripts/run_shadow_rebalance_cycle.py
- run_paper.py
- handoffs/phase6/Live_Cutover_Prep_2026-07-03.md (prior batch evidence)
- docs/MASTER_TASK_TRACKING.md (final entry)

## Evidence Snippets from Final Runs (2026-07-03)
[From shadow run]
[WIRING-01] use_new_allocator=True (NEW_ALLOCATOR_AVAILABLE=True)
[PRE-REBAL REFRESH #2] Full coverage 11/11
[ARCH-4] Using new Allocator + RotationStrategy path (replacing direct deploy_capital). Central basket + TradePlan.
[OBS] proposals_generated=11 accepted=4 acceptance_rate=36.36% utilization=23.55%
[DB] Persisted 11 proposals
[ARCH-4 SHADOW EXEC] Plan: [{'pair': 'ETH-USD', 'action': 'SELL', ...}, ...]
[ARCH-4] Rebalance complete via new stack. Strategy=rotation_catch_wave, actions=4, exposure=100.0%
[SL-ANCHOR] ... Re-attached stops for 3 pairs
[ANALYST] Intelligence brief generated...
[FORCE test separate run] [FORCE] Manual rebalance triggered via flag file ; flag unlinked; should=True

[From paper]
Trades recorded: 2 (BTC/ETH buys)
Final simulated portfolio value: $10,000.00

**Ready for live cutover.** Code tested, configs set, docs updated. Proceed with user confirmation and monitoring.

References: Parent Kanban t_82d7ed7a + recent LIVE-PREP cards, systematic-debugging for SL/quant patterns, polymarket/analyst for intelligence.
