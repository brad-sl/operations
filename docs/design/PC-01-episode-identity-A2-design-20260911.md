# PC-01 Episode Identity A2 — Short Design / Grill Note (2026-09-11)

**Objective:** Full bag_id propagation so SL/TP/ratchet/peaks/ledger/blocks treat every lot by its identity `{pair}:{buy_order_id}`. New buy never inherits prior-bag stop/peak/lockout.

**Bag ID Schema (frozen from thin slice A1/A3/A4):**
- `bag_id = f"{pair}:{buy_order_id}"` where buy_order_id is the filled BUY order_id from exchange (or client_order_id for limit).
- Stable per lot/episode. New buy (after flat or re-entry) = new bag_id.
- Never reuse across rebuys on same pair.

**Why needed (from incidents):**
- UNI 2026-08-23: stale peak_r from prior lot survived fresh rebalance lot → premature trail exit at loss.
- LINK same-session: ghost registry stop (high floor) imported to new bag via ratchet → wound.
- Naked bag + ghost registry close (A4) + fill-recon (A3) landed but full filter not wired.

**Changes (must, in order):**
1. **Ledger:** Add `"bag_id"` to all BUY (and SELL closing that lot) rows in:
   - `build_ledger_row_from_market_buy`
   - `build_ledger_row_from_market_sell` / fill
   - direct `log_trade` BUY records in `phase6_runner.py` (and any other direct paths)
   - Back-compat: old rows without bag_id treated as "legacy" (pair-only for filter).

2. **Ratchet (sl_floor_ratchet.py + callers):**
   - Extend `usable_existing_stop_for_ratchet(..., bag_id: Optional[str]=None, registry_bag_id: Optional[str]=None)`
   - If `bag_id and registry_bag_id and bag_id != registry_bag_id`: return None (ignore prior-bag floor).
   - Update `apply_ratchet_to_stop_bundle` to accept/pass `bag_id`.
   - In `stop_loss_manager.py`: compute current `bag_id` from `fresh_buy_order_id` (already done for registry), pass it; use registry row's bag_id when deciding continuous_bag.
   - Keep `fresh_buy` + `continuous_bag` as input for now (additive).

3. **Peaks / live_state (shadow_tp.py):**
   - Enhance `sanitize_peak_r_for_lots(..., current_bag_id: Optional[str]=None)` or embed bag in peak_lot meta.
   - Store in `peak_lot[pair]`: add `"bag_id": ...`
   - On sanitize: if held lot's bag_id (from registry or ledger last buy for pair) != peak_lot's bag → reset peak_r := current r; update lot bag.
   - Unbound or entry-drift still reset (keep rules).
   - Clear on flat exit already does.
   - Update live_state consumers (refresh_dashboard etc) no schema break.

4. **Protective registry:** Already emits bag_id on register. Enhance lookups (e.g. `_latest_registry_stop_for_pair`) to expose bag_id. (used by ratchet).

5. **Other:** 
   - position_cost_basis / average_cost may benefit from bag filter in future, but not now (use for lot basis).
   - No change to park/PAXG unless collision (explicit must-not).
   - No live knobs.

**Migration / compat:**
- No DB migration (jsonl append-only).
- Functions that read ledger/peak/registry: tolerate missing bag_id (treat as None → legacy behavior or pair-key only).
- On write always emit bag_id when buy_order_id present.
- Isolation will cover cross-bag vs same-bag.

**Isolation test (new):**
`scripts/phase6/test_isolation_episode_identity_a2.py`
- Prove: fresh bag (new buy_order) gets genesis stop (no ratchet from prior).
- Prove: new bag gets peak_r = current r (not prior higher).
- Prove: ledger rows carry bag_id.
- Prove: same continuous bag (reattach same buy) keeps prior floor/peak.
- Prove: flat pair clears only its bag's protectives.
- Use mocks/patches, real functions, no net.

**Validation (per handoff):**
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_episode_identity_a2.py
... + naked + sl_ratchet + pre_ship_quality.sh

**Risks / must-not:**
- Half-refactor: wire bag_id everywhere touched for protect/ratchet/peak/ledger in this slice.
- Do not touch force_rebalance, live config, park.
- After: update MASTER_TASK_TRACKING.md + this handoff with SHA.

**Grill notes (self):**
- bag_id on SELL: include the bag_id of the lot being exited (from matching buy ledger or registry).
- For adds to same lot: same bag_id (top-up uses same buy_order? or new? — per current, fresh buy_order for new attach? but identity of position lot is the opening buy.
  Current thin: uses the buy_order_id at attach time. Assume for rebalance adds it's new? No: episode is the open position's opening buy id.
  Decision: bag_id keyed to the BUY that opened or last? For now stick to per-buy_order as "lot start".
- If partial sells, bag remains until flat.
- live_state sanitize: when holdings update after buy, marks will reflect new entry? (via cost basis), but explicit bag better.

**Next after green:** update MASTER, handoff with commands + git sha; parent epic.

This note written before any multi-file patch. 2026-09-11
