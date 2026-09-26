# Scale-up investment ladder (R5) — working path 2026-09-25/26

## Intent
Make the mid-flight tryout scale-up ladder **actually work end-to-end**:
seat fill → open-lot registry → kindling plan → TG approval → CLI GO →
after 2 GOs → optional autonomous.

## Why it was idle
- Live book only held **PAXG** (sticky ballast) → `n_planned=0` is correct.
- No tryout shell open → nothing to kindle.
- Ledger often lacked `tryout` reason tags → `not_tryout` even when size matched.

## What ships
| Piece | Path |
|-------|------|
| Open-lot register on seat fill | `register_tryout_open_lot` in `tryout_scale_up_shadow.py`; called from `TryoutSeatBuyAction` on fill |
| Infer honors registry | `infer_open_lot_entry` ORs `tryout_tagged_buy` from open lots |
| Brad ladder | `phase6/core/tryout_scale_up_ladder.py` + `run_tryout_scale_up_ladder.py` |
| Apply counts GOs | `apply_live_steps` → `record_manual_go` on live fill |
| Approval card | Shows ladder line (approval N/2 / ready / autonomous) |
| Cron | `run_tryout_scale_up_live_approval_cron.sh` — quiet TG; auto-apply only if ladder armed |

## Operator ladder
1. **Seat** opens ($25) via RSI-event path / manual seat buy → lot registered.
2. **Plan** when mid-flight bar clears → TG approval (cron).
3. **First 1–2 GOs** (critical path):
   ```bash
   python3 scripts/phase6/run_tryout_scale_up_live.py --apply --go --no-dry-run
   ```
4. **After 2 GOs**:
   ```bash
   python3 scripts/phase6/run_tryout_scale_up_ladder.py --arm-auto
   ```
5. Kill / back to approval:
   ```bash
   python3 scripts/phase6/run_tryout_scale_up_ladder.py --disarm
   # or touch data/state/tryout_scale_up_live_KILL
   ```

## Still required for a live step
- Open **tryout-sized** non-sticky position (not PAXG alone)
- `live_signal` bar: phase ∈ {1,2}, structure_ok, hold/r band
- CF bar or waive remaining
- `decision.live_apply=true`, no KILL, daily caps

## Status now
- Ladder: `mode=approval` · `gos=0/2` · `autonomous_apply=False`
- Plan: `n_planned=0` (no tryout open — honest idle)
- Seat isolation 14/14 · scale-up approval isolation PASS
