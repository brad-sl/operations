# Dig-out Practical Sequence — GO path (2026-10-13)

Brad GO on sequence 1–6. **No live money until Sunday weekly review + explicit Brad GO on each live_apply flip.**

## Status snapshot (shipped this session)

| Step | What | State |
|------|------|--------|
| §1 | C1+D1 `would_*` shadow logs + matrix `dig_out_shadow` | **LIVE shadow** |
| §2 | C2/D2 production GO checklist + Sunday followup cron | **Scheduled** — flip only on GO |
| §3 | Residual / partial-trail CF KeyError fix + rerun | **Fixed** · `reports/POST_PROOF_RESIDUAL_GROWTH_CF_2026-10-13.md` |
| §4 | Intake measure (discipline skips) on dig-out board | **Measure** · eng floor already live |
| §5 | 3% fuse `would_arm` 14d shadow logger | **LIVE shadow** · MEASURE_ONLY |
| §6 | Do-not lock + auto-followups | **Locked in board + crons** |

## Artifacts

- Board: `data/state/dig_out_shadow_board_latest.json` · `reports/DIG_OUT_SHADOW_BOARD_LATEST.md`
- History: `data/state/dig_out_shadow_board_history.jsonl`
- SL would-arm: `data/state/sl_width_would_arm_latest.json` · history jsonl
- Residual CF: `scripts/phase6/run_post_proof_residual_cf.py` · report dated 2026-10-13
- Configs (still `live_apply: false`):
  - `config/ballast_under_target_floor.json` (C1→C2)
  - `config/flat_deploy_priority.json` (D1→D2)
  - `config/sl_width_arming_policy.json` (W2 fuse)

## C2 / D2 live GO checklist (Sunday)

Do **not** flip until all boxes true:

1. [ ] Dig-out shadow history ≥5 days with sensible C1/D1 hits (no thrash)
2. [ ] Kill files absent: `data/state/ballast_under_target_floor_KILL`, `flat_deploy_priority_KILL`
3. [ ] Weekly analyst brief reviewed (process tax / ballast gap still the hole)
4. [ ] Explicit Brad message: **GO C2** and/or **GO D2** (can be separate)
5. [ ] Then only: set `live_apply: true` on the matching config(s)
6. [ ] Wire money path (rebalance / add-risk) behind the same helpers — still no global SL change
7. [ ] Kill-file ready; first 24h watch

### Flip commands (after GO only)

```bash
# Example after Brad GO C2 — edit config, do not auto-run from cron
# config/ballast_under_target_floor.json → "live_apply": true, "shadow_only": false
# config/flat_deploy_priority.json → "live_apply": true, "shadow_only": false
```

## W2 3% fuse

- **14d** of `would_arm_3pct` vs `would_arm_8pct` history required
- Live fuse only on dead unproven shells (W2); **W3 never tighten after green**
- Do **not** global 8→3

## Do-not lock (permanent until Brad overturns)

- global_stop_8_to_3
- liquidate BTC/SOL/TIA/PAXG
- PAXG preserve change
- Kelly / deploy_pct promote
- dual_agree auto
- flat cap blowout

## Crons

| Job | Role |
|-----|------|
| `phase6-dig-out-shadow-board` | no_agent every 2h — append board + quiet header |
| `phase6-dig-out-sunday-prod-followup` | agent Sunday AM — production readiness brief + GO prompt |

## Residual / partial trail

CF is measure-only. Partial trail mock currently **halves** booked TP meat without residual path realization — do **not** promote as live TP shape. Kindling-first mock ≈ baseline when eligibility mock is weak. Revisit after path peak + residual hold data.
