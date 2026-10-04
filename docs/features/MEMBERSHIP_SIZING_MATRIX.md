# Membership × sizing matrix SSOT

**Status:** ACTIVE (measure-only)  
**Brad GO:** 2026-10-04_membership_sizing_matrix_ssot  
**Updated:** 2026-10-04  

## Problem this solves

Scale / membership answers were reconstructed across novelty class, tryout lifecycle, add-risk sizer, regime cash policy, and ballast rules. That latency is a product smell: **if the agent needs minutes to answer “what allows BTC to scale?”, the law is not accessible.**

## Product rule

> One filterable matrix SSOT.  
> Rows = pairs. Columns = class × role × scale-path law × regime × live room.  
> If it’s not on the matrix, it isn’t policy — it’s folklore.

## Notation

| Field | Meaning |
|-------|---------|
| **class** | `sticky_core` / `liquid_core` / `graduated` / `novelty_*` (from novelty_class_gate) |
| **role** | `ballast_core` / `preserve_ballast` / `tryout_shell` / `liquid_held` / `cash_like` |
| **scale_path_law** | What *may* grow the bag: `none` \| `kindling_once` \| `add_risk_pyramid` |
| **kindling_scale_path** | Live tryout shell state if any (`open`/`pending`/`live`/`dead`/`ghost`/`none`) |
| **can_eject_scale_window** | Dead kindling → full flat + cooloff (tryout only) |
| **first_fill_haircut** | Probation size mult applies |
| **membership_remove** | `never` \| `dust_only` \| `m_gate` |
| **max_add_usd** | Live factor add-risk ceiling on *existing* stack; `0` = block-max |
| **block_reason** | Binding budget (`cash_slice`, `profit`, …) and/or sizer detail |
| **inconsistencies[]** | Auto policy-drift flags |

## Role law (config)

SSOT: `config/membership_sizing_matrix.json`  
**Does not duplicate** regime numbers — those stay in `config/regime_cash_policy.json`.

| Role | Scale path | Eject SW | REMOVE |
|------|------------|----------|--------|
| ballast_core (BTC/ETH) | add_risk_pyramid | N | never |
| preserve_ballast (PAXG) | none | N | never |
| tryout_shell | kindling_once | Y | dust_only |
| liquid_held | add_risk_pyramid | N | m_gate |
| cash_like | none | N | never |

## Instant answers

```bash
# One pair
python scripts/phase6/run_membership_sizing_matrix.py --pair BTC-USD

# Filters
python scripts/phase6/run_membership_sizing_matrix.py --filter block_max
python scripts/phase6/run_membership_sizing_matrix.py --filter role=ballast_core
python scripts/phase6/run_membership_sizing_matrix.py --filter inconsistent
python scripts/phase6/run_membership_sizing_matrix.py --filter scale_path=kindling_once

# Regime sheet
python scripts/phase6/run_membership_sizing_matrix.py --regime

# Exit 1 if policy drift
python scripts/phase6/run_membership_sizing_matrix.py --check
```

API: `GET /api/membership-sizing-matrix`  
Query: `pair=BTC-USD` · `block_max=1` · `role=ballast_core` · `scale_path=kindling_once` · `inconsistent=1` · `basket=1` · `check=1`

Dashboard: **Membership sizing** pane (filter chips). Hard-refresh after deploy.

State snapshot: `data/state/membership_sizing_matrix_latest.json`

## Agent contract

**Scale / membership / “why is bag small?” questions → matrix first** (`pair_card` or CLI).  
Do **not** reconstruct from skills + seven files unless the matrix is missing or `--check` fails.

## Inconsistency detectors

- sticky/ballast must not be `kindling_once`
- preserve must not kindle
- scale-window eject false for ballast
- first_fill haircut vs sticky exempt drift
- sticky live kindling path open (registry leak)

## Code map

| Piece | Path |
|-------|------|
| Config law | `config/membership_sizing_matrix.json` |
| Compiler | `phase6/core/membership_sizing_matrix.py` |
| CLI | `scripts/phase6/run_membership_sizing_matrix.py` |
| Tests | `scripts/phase6/test_isolation_membership_sizing_matrix.py` |
| API | `serve_dashboard.py` → `/api/membership-sizing-matrix` |
| UI | `phase6_dashboard.html` Membership sizing section |

## Related

- Tryout process: `docs/features/TRYOUT_LIFECYCLE_PROCESS.md`
- Regime knobs: `config/regime_cash_policy.json`
- Add-room live: `phase6/core/add_risk_sizer.py` `load_add_room_by_pair_for_dashboard`
- Class: `phase6/core/novelty_class_gate.py`
- Membership seats: `phase6/core/membership_manager.py`

## Out of scope (v1)

- Changing money knobs / raising flat `h_add`
- Auto-orders from the matrix
- Full universe scan every poll (basket + held default)
