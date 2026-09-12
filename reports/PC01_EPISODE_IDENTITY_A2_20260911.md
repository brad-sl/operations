# PC-01 Episode Identity A2 — Completion Report (2026-09-11)

**Kanban:** t_7d1d15c6  
**Status:** DONE  
**Isolation:** scripts/phase6/test_isolation_episode_identity_a2.py → 5/5 PASS  
**Pre-ship:** bash scripts/hermes/pre_ship_quality.sh → PASS ("isolation ok (5 scripts)")  
**Other isolations:** naked_bag_p0 + sl_floor_ratchet → OK (no regressions)

## What shipped (full A2 propagation)

- **bag_id schema SSOT:** `{PAIR}:{buy_order_id}` via `phase6/core/episode_identity.py` (make, coerce, conflict, stamp, bag_id_from_*)
- **Ledger:** BUY/SELL rows carry `bag_id` + `buy_order_id` (build_* in exchange_fill_reconciler; stamp inside TradeLedger.log_trade; runner fresh-start now emits order_id)
- **Ratchet:** `usable_existing_stop_for_ratchet` + `apply_ratchet...` accept `current_bag_id` / `registry_bag_id`; hard reject on `bag_ids_conflict` (prior ghost never floors new lot). StopLossManager wires the ids + uses conflict for continuous_bag.
- **Peaks / live_state:** `sanitize_peak_r_for_lots` now checks bag via `bag_ids_conflict(lot_bag, mark_bag)` (in addition to entry tol / orphan). `PositionMark` carries `bag_id`; `marks_from_holdings` populates from registry or pos; `peak_lot` meta stores it. Reset on bag change even with same entry_px (UNI-class fixed).
- **Registry:** already emitted; enhanced lookups + helpers.
- **No other changes:** live knobs untouched, no force_rebalance, no park/PAXG.

## Design / preflight
- Short grill note before edits: `docs/design/PC-01-episode-identity-A2-design-20260911.md`
- TDD: wrote failing isolation first (then green), followed existing isolation patterns + TDD skill.
- Updated handoff + MASTER closeout section.

## Verification commands (all green)
```bash
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_episode_identity_a2.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_naked_bag_p0.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_sl_floor_ratchet.py
bash scripts/hermes/pre_ship_quality.sh
```

## Files touched (this run)
- phase6/core/episode_identity.py (new central)
- phase6/core/exchange_fill_reconciler.py
- phase6/core/phase6_runner.py (order_id for stamp)
- phase6/core/shadow_tp.py (bag in marks + sanitize)
- phase6/core/sl_floor_ratchet.py (bag params + conflict)
- phase6/core/stop_loss_manager.py (pass bags)
- phase6/core/trade_ledger.py (already stamped)
- scripts/phase6/test_isolation_episode_identity_a2.py (new, 5/5)
- handoffs/... + docs/MASTER... + reports/...

**Next:** PC-02 (exit stack), parent PLATFORM-COMPLETENESS tick, 7d monitor for zero stale-peak class.

All per handoff + plan + .hermes rules (isolation first, no live).
