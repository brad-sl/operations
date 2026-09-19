# Tryout scale-up live path (Option B)

**Status:** SHIPPED path · **live_apply OFF** · 2026-09-19  
**Brad GO:** path build only — **NO-GO money** until separate arm + CF/waive decision.

## Gap closed

Shadow `tryout_scale_up_shadow` could `would_scale` but had **no order path**.  
Live module: `phase6/core/tryout_scale_up_live.py`.

## Hard rules

| Rule | Enforcement |
|------|-------------|
| Default OFF | `tryout_scale_up_brad_decision.json` `live_apply=false` |
| Shadow cfg cannot arm | `load_cfg` pins live_apply false |
| Cron never buys | Only shadow cycle; live CLI is operator |
| Dry-run default | `apply_live_steps(dry_run=True)` |
| Money | `--apply --go --no-dry-run` **and** armed **and** no KILL |
| CF bar | Default require; n≥8; waive only `cf_bar.require=false` |
| Caps | 1 step/UTC day · $50/day · $25 max step |
| Kill | `data/state/tryout_scale_up_live_KILL` |
| Executor | `OrderExecutor.execute_buy` (limit-first fence + SL stack) |

## CLI

```bash
# Plan (safe)
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_scale_up_live.py --plan

# Dry rehearse
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_scale_up_live.py --apply --go --shadow-executor

# REAL money (only after Brad arms decision.live_apply)
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_scale_up_live.py --apply --go --no-dry-run
```

## Arm checklist (future GO — not done)

1. CF n≥8 prefer 12 **or** explicit waive + note  
2. At least one clean would_scale on a live lot  
3. Set `live_apply: true` in decision file  
4. Optional pin `live_safety.allow_pairs`  
5. Operator CLI with `--go --no-dry-run`  
6. Kill file ready; max 1 step that day  

## Isolation

`scripts/phase6/test_isolation_tryout_scale_up_live.py`

## Not this

- Not first_fill `graduate_on_tp` (post-close next seat)  
- Not auto-promote / membership  
- Not cron auto-add  
- Not edge claim from path existence  
