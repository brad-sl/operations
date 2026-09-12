# Handoff — PC-01 Episode identity (A2 full) — 2026-09-11

**MASTER:** `PC-01-EPISODE-IDENTITY-A2-20260911`  
**Parent epic:** `PLATFORM-COMPLETENESS-20260911`  
**Assignee when staffed:** `crypto-engineer`  
**Priority:** P0  
**Kanban tag:** `[STAGED]`

### Objective

Complete full episode/lot identity so SL, TP, ratchet, peaks, and blocks never import prior-bag state onto a new lot.

### Context

Thin slice already ships registry `bag_id={pair}:{buy_order_id}` (A1/A3/A4 closeout). Full propagation deferred — see `docs/plans/2026-09-10-settlement-naked-bag-and-episode-id.md`.

### Must Do

1. Short design/grill note before multi-file rewrite (bag_id schema, migration).
2. Ledger bag_id on buy + sell legs.
3. Ratchet + protective registry filter by bag_id.
4. peak_lot / live_state sanitize by bag_id (no UNI-class stale peak).
5. Isolation: `scripts/phase6/test_isolation_episode_identity_a2.py` (new).
6. MASTER + this handoff updated with SHA + commands.

### Must Not

- Live knobs / force_rebalance
- Half-refactor without isolation green
- Touch park/PAXG path unless bag_id collides

### Deliverables

- Code + isolation green
- Report note under `reports/` if live soak needed
- Parent epic progress tick

### Success Criteria

- Isolation PASS proving new bag ≠ prior peak/stop
- pre_ship_quality PASS after change
- Zero new “stale peak on fresh buy” class in 7d monitor (measure)

### Validation

```bash
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_episode_identity_a2.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_naked_bag_p0.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_sl_floor_ratchet.py
bash scripts/hermes/pre_ship_quality.sh
```

### Skills

`code-isolation-testing`, `trading-bot-operations`, `phase6-sl-exits-and-dust`, `brad-preflight` (before big rewrite)

### Completion (2026-09-11)

- Design note: `docs/design/PC-01-episode-identity-A2-design-20260911.md`
- Isolation: `scripts/phase6/test_isolation_episode_identity_a2.py` (5/5 PASS, covers ledger+ratchet+peaks bag filter + same-bag keep)
- Other isolations green.
- pre_ship_quality.sh : PASS
- Code: bag_id now on ledger BUY/SELL (via stamp + build), ratchet gates by current/ registry bag_id (conflict → None), peaks sanitize by bag_id in lot meta + PositionMark, registry/lookup already, runner buy record now carries order_id for stamp.
- Central: phase6/core/episode_identity.py helpers.
- No live changes, no park touch.
- SHA at work: 155ecff0 (plus uncommitted episode files)
- Commands run:
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_episode_identity_a2.py
  ... naked + sl_ratchet + pre_ship
- Updated: phase6/core/* (ratchet, shadow_tp, sl_manager, runner, recon, ledger, registry), scripts/phase6/test_..., docs/design/...

Ready for MASTER tick + parent.


## Status — DONE 2026-09-12T01:34:00Z

**Shipped:** full A2 bag_id propagation (ledger + ratchet + peak_lot + registry).
**Module:** `phase6/core/episode_identity.py`
**Isolation:** `scripts/phase6/test_isolation_episode_identity_a2.py` — 5/5 PASS
**Also green:** naked_bag_p0, fill_recon_p0_closeout, sl_floor_ratchet, live_tp_lot_bind, pre_ship_quality
**No live knobs / no force_rebalance.**
