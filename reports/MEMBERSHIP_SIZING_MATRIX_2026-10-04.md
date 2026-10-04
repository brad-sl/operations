# Membership sizing matrix — Phase 1 ship receipt

**Date:** 2026-10-04  
**Brad GO:** `2026-10-04_membership_sizing_matrix_ssot`  
**Scope:** Measure-only filterable SSOT (class × role × regime × scale-path × live room). **No money knobs changed.**

## Why

“What allows BTC to scale?” took too long because law was scattered. Product fix = one matrix agents and ops query first.

## Delivered

| Layer | Path |
|-------|------|
| Config law | `config/membership_sizing_matrix.json` |
| Compiler | `phase6/core/membership_sizing_matrix.py` |
| CLI | `scripts/phase6/run_membership_sizing_matrix.py` |
| Isolation | `scripts/phase6/test_isolation_membership_sizing_matrix.py` (8/8) |
| API | `GET /api/membership-sizing-matrix` |
| UI | Membership sizing pane + filter chips |
| Spec | `docs/features/MEMBERSHIP_SIZING_MATRIX.md` |
| Index | `docs/SPECS_INDEX.md` · `docs/features/README.md` |
| Snapshot | `data/state/membership_sizing_matrix_latest.json` |

## Live verify (2026-10-04)

```
BTC-USD · sticky_core · ballast_core · add_risk_pyramid · held~$56 · max_add=$0 · block=cash_slice|capped_to_zero
SOL-USD · liquid_core · tryout_shell · kindling_once · held~$25 · eject=Y · remove=dust_only
PAXG-USD · sticky_core · preserve_ballast · scale=none
regime=flat · pyramid=on · k_profit=0.25 · h_add=0.01 · target_w=0.18 · inconsistent=0
```

CLI instant path:

```bash
python scripts/phase6/run_membership_sizing_matrix.py --pair BTC-USD
python scripts/phase6/run_membership_sizing_matrix.py --filter block_max
python scripts/phase6/run_membership_sizing_matrix.py --check
```

## Tests

```
test_isolation_membership_sizing_matrix.py — 8/8 OK
```

## Agent contract

Scale / membership / bag-size questions → matrix first. Reconstruct from skills only if matrix missing or `--check` fails.

## Out of scope

- Raising flat add-risk budgets  
- Auto-orders from matrix  
- Changing tryout/kindling money arms  

## Next (optional)

- Measure cron refresh (optional; dash compiles on poll)  
- Expand universe rows on demand (`include_universe_classes`)  
- Wire MSM badge on Signals pair rows  
