# Handoff: CW-4 Live B micro sleeve path (armed, money OFF)

**Epic:** `REGIME-CLIMATE-WEATHER-REMAINING-20260921`  
**Card:** CW-4 · P1 engineering (parents: CW-2)  
**Assignee:** crypto-engineer  
**Plan:** `docs/plans/2026-09-21-climate-weather-remaining-four.md`  
**Spec:** `docs/research/BULL_REENTRY_LAYERED_SPEC.md`

## Goal
Close the **engineering gap** for Job B (weather micro): a live-capable path that is **armed for dry-run/plan** but **money OFF** until separate Brad GO — same pattern as `tryout_scale_up_live`.

## Depends on
- **CW-2** hysteresis design committed (so B vs climate confirm interaction is written)
- Paper B cron already running (`phase6-bull-reentry-layered-paper`) — read crumbs; do not require promote-ready N to ship path OFF

## Pattern to copy
- `phase6/core/tryout_scale_up_live.py` + approval CLI + `data/state/*_brad_decision.json` with `live_apply: false`
- Dry-run default; `--apply --go --no-dry-run` for money
- Hard daily caps; kill switch; uses existing buy/SL stack if ever applied

## Product constraints (frozen)
- Climate bear park veto: **no** new alt risk from B while `allow_new_buys=false` **unless** design in CW-2 explicitly defines a capped exception (default: **no exception** under full bear — B arms for soft_down/flat exit strip)
- Cap: $75-class or current tryout shell — not full ticket
- Structure: breakout ON + RSI band [50,70] per layered spec
- **No auto-promote**; no climate threshold rewrite

## Must do
1. Core module + CLI + isolation tests
2. Brad decision state file gitignored; default `live_apply=false`
3. Optional approval ping cron (silent unless plan non-empty + armed)
4. Wire measure crumbs; document GO menu for money arm
5. Commit; leave money OFF

## Must not
- Set `live_apply=true` without Brad GO in card comments + decision file
- Place orders in CI or first ship
- Weaken 30d park law “so B can fire in deep bear”

## Done when
- Path ships, tests green, money OFF proven (dry-run only)
- Kanban complete; separate future GO for arm

## Skills
`phase6-bull-reentry-timing`, `trading-bot-operations`, `code-isolation-testing`, `phase6-luck-ladder-refine` (path pattern)
