# Cron archive + status SSOT — 2026-08-29

## Trigger

Daily `shadow-tp-validation-daily` Telegram claimed **Live TP: OFF · Ready for review** while product was already **live** (promoted 2026-08-23). Root cause: reporter was a **second control plane** (hardcoded `live_orders=false`, wrote `shadow_tp_status.json`, called `run_shadow_tp_cycle` which persists runtime).

## A — Validation job

| Action | Detail |
|--------|--------|
| Paused | `e7fe6faeebe6` → name `ARCHIVED shadow-tp-validation-daily` |
| Removed | one-shot `shadow-tp-validation-day7-review` `97815c1f5afe` |
| Window | `data/state/shadow_tp_validation_window.json` marked `archived: true` |
| Script | `scripts/phase6/shadow_tp_validation_status.py` rewritten **report-only** |
| Guard | refuses `--start-window`; refuses writes outside validation report paths; open book = **read** `shadow_tp_status.json` only |
| Core | `run_shadow_tp_cycle(..., persist=False)` skips state jsonl + live execute path |
| Verify | sha256 of `shadow_tp_status.json` + `exit_automation.json` **unchanged** across reporter run; stdout `Live TP: ON (policy SSOT) · trial window ARCHIVED` |

## Reporting never writes production settings

| Layer | Path | Writer |
|-------|------|--------|
| Policy | `config/exit_automation.json` | Human / promote only |
| Runtime TP | `data/state/shadow_tp_status.json` | `shadow_tp.py` with `persist=True` only |
| Validation metrics | `shadow_tp_validation_*.json`, `reports/SHADOW_TP_VALIDATION_LATEST.md` | reporter only |

## Cron inventory (default gateway)

- **Before:** 53 jobs (many completed one-shots + sticky junk)
- **After:** 37 jobs (35 enabled, 2 paused)
- **Removed:** 16 completed/stale jobs (tinyfish installs, decline pulls, soft-down one-shots, DOC-BOUNDARY, stoch-trial-health, day7 review, mail ping, H2/H3 remind, unstick kanban, trial-exec, ssh probe)
- **Profiles:** code-reviewer `weekly-backlog-review` paused (dead gateway sticky error). crypto-orchestrator Phase6 copies remain disabled (not SSOT).
- **Linux crontab:** still comment-only.

### Enabled kept (by class)

See `docs/HERMES_CRON_SSOT.md` sections A–E.

Shadow research crons **kept** because they still accumulate evidence into their own state files and do **not** write `config/*` or `shadow_tp_status.json`. Re-audit if Brad wants a thinner research set later.

### Paused kept

| Id | Name | Reason |
|----|------|--------|
| `e7fe6faeebe6` | ARCHIVED shadow-tp-validation-daily | Dual-writer + false authority post-promote |
| `8612a817fe55` | sentiment-30min-refresh | Cost; X 2×/day is SSOT |

## Isolation tests

- `phase6/core/test_isolation_shadow_tp.py` PASS (tmp STATE_PATH)
- `phase6/core/test_isolation_live_tp_exit.py` PASS

## Pass 3 — Brad research decisions (2026-08-29)

1. **Basket swap:** preferred paper arm = `risk_adj_mom`; dual_agree continues 30d → revisit **2026-09-28**. Cron `phase6-basket-swap-cf-shadow` **resumed**. One-shot `basket-swap-30d-revisit` (`38987b457e6c`). **No live membership.**
2. **Volume velocity:** **NO-GO / BUST** as seat/buy. Cron stays paused (`BUST phase6-volume-velocity-shadow`).
3. **Vol-risk scalar:** **KEEP_COLLECTING**. Cron `phase6-vol-risk-scalar-shadow` **resumed**. No live bind.

Artifacts: `data/state/basket_swap_brad_decision.json`, `volume_velocity_brad_decision.json`, `vol_risk_scalar_brad_decision.json`; reports `BASKET_SWAP_BRAD_GO_2026-08-29.md`, `VOLUME_VELOCITY_NOGO_2026-08-29.md`.

## Follow-ups (optional)

1. Dashboard Exit tile: read `exit_automation.json` mode only (surface).
2. Delete long-paused jobs after 30d if unused.
3. `stoch-30d-reeval` remove after 2026-09-03 fire; consider resume bull-reentry then.
4. 2026-09-28 basket swap revisit brief (auto one-shot).
