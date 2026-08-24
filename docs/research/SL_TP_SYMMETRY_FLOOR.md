# SL / TP economic symmetry floor

**Status:** shipped 2026-08-23  
**Isolation:** `scripts/phase6/test_isolation_sl_tp_symmetry.py`  
**Code:** `phase6/core/sl_risk_scorer.py` → `apply_sl_tp_symmetry` + `get_adaptive_sl_pct`  
**Wire:** `StopLossManager.get_sl_pct`  
**Config:** `risk_management.sl_tp_symmetry` in `config/trading_config_phase6.json`

## Problem

Live trail TP arms at **+4%** (fixed bank **+6%**). Adaptive SL can tighten HIGH/CRITICAL names to **~2.0–2.5%**.

On UNI force re-entry (2026-08-23):

| | |
|--|--|
| Entry | $4.573 |
| Adaptive SL | **~2.23%** → stop $4.469 |
| MFE while held | **~+2.5–2.7%** (never armed trail) |
| Exit | exchange SL **−2.23%** |

Profit path never engaged; stop path fired on ordinary pullback after a wide-range day.  
**Asymmetry:** easy to get stopped, hard to get paid.

## Design (minimal — one floor, no adapters)

**Do not** add ATR/pair/range corner-case adapters. One pure function:

When `take_profit.mode == live` and `sl_tp_symmetry.enabled`:

1. `floor = adaptive`
2. If `never_tighter_than_base_when_live_tp`: `floor = max(floor, base_pct)` (default base **3%**)
3. If trail arm known: `floor = max(floor, trail_arm_pct * min_sl_frac_of_trail_arm)` (default **0.85 × 4% = 3.4%**)
4. Clamp to `[sl_min_pct, sl_max_pct]`

When live TP is **off** or **shadow**: behavior unchanged (legacy adaptive).

### Knobs (only these)

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | true | Master switch |
| `never_tighter_than_base_when_live_tp` | true | Floor at `sl_base_pct` |
| `min_sl_frac_of_trail_arm` | 0.85 | Floor at arm × frac |
| `trail_arm_pct` | (from exit_automation) | Optional override |
| `force_live_tp_active` | (unset) | Test/ops override |

## What this does **not** claim

- Does **not** guarantee survival of −4% wicks (UNI day low after entry was ~−4.2%; need ~5% / structure stops — future research, not this pass).
- Does **not** change trail arm or fixed TP levels.
- Does **not** widen LOW-risk stops beyond adaptive (floor only).
- Preserve / PAXG E1 path unchanged (different attach path).

## UNI counterfactual (same entry)

| Rule | Stop ~ | vs −2.23% actual |
|------|--------|------------------|
| Legacy HIGH adaptive | 2.2% | actual |
| Symmetry (base + arm×0.85) | **~3.4%** | more room; still may die on deep wash |
| 5% sl_max style | 5% | would survive that wash (not this change) |

## Tests required before claim

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 scripts/phase6/test_isolation_sl_tp_symmetry.py
PYTHONPATH=. python3 phase6/core/test_isolation_shadow_tp.py
PYTHONPATH=. python3 phase6/core/test_isolation_live_tp_exit.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_sl_floor_ratchet.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_sl_coordinator_attach.py
```

## Related

- Incident / day review: UNI force SL vs chart (session 2026-08-23)
- Trust SOP: `docs/sop/TRUST_FIRST_TRADING_ENGINE.md`
- Exit automation: `config/exit_automation.json` (`trail.arm_pct`)
- Skill: `phase6-sl-exits-and-dust`
