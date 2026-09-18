# Handoff — OPS-P0-3 Force rebalance — 2026-09-18

**MASTER:** `OPS-P0-3-FORCE-REBALANCE-20260918`  
**Parent epic:** `OPS-ONE-CALL-P0-20260918`  
**Assignee:** `crypto-engineer`  
**Priority:** P0  
**Workspace:** `dir:/home/brad/projects/crypto-trading-bot`  
**Kanban tag:** `[STAGED]`

### Objective

One-call force rebalance: dry-run/status by default; `--go` only when Brad already asked to force. Wait for cycle, parse outcome, print structured receipt. Kills touch-flag → sleep → log scrape digs.

### Must Do

1. CLI: `scripts/phase6/ops_force_rebalance.py` + wrapper `phase6/scripts/force_rebalance.sh`
2. Hermes wrapper: `~/.hermes/scripts/phase6_force_rebalance.sh`
3. Default (no `--go`): show whether flag exists, runner alive, last rebalance crumbs if cheap — **do not place flag**
4. `--go` path:
   - Use existing force path (`phase6/scripts/cron_rebalance.py` / `data/state/force_rebalance.flag` — match current SSOT)
   - Wait up to `--wait-s` (default 180) for flag clear / cycle complete
   - Parse runner log window for: plan pairs, Executed/Skipped, fills, limit_unfilled_skip, SL attach lines
5. Optional `--pair PAIR` filters summary focus (still full cycle)
6. JSON receipt: `data/state/ops_force_rebalance_latest.json`
7. Short MD optional: `reports/OPS_FORCE_REBALANCE_LATEST.md`
8. Isolation test: fixture log snippets + flag lifecycle mock; **must not** fire live `--go` in unit test
9. Skill: `phase6-ops-force-rebalance` — hard rule: never `--go` unless user message this turn is force/rebalance GO
10. Commit on `phase-6.1`

### Must Not

- Auto `--go` from cron / triage / no_agent
- Market fallback flips
- Door/thaw/config knob changes
- Restart runner as part of this card (that's P0-4)
- Claim fill = edge

### Success Criteria

- `bash phase6/scripts/force_rebalance.sh` (no args) is safe read/status, exit 0 or 4
- Isolation PASS without live force
- `--go` documented; live smoke only if Brad GO comment on card during staffed run
- Receipt has structured fields: `go`, `flag_seen`, `wait_s`, `executed`, `skipped`, `pairs`, `notes`

### Validation

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_ops_force_rebalance.py
bash phase6/scripts/force_rebalance.sh
# DO NOT --go in isolation/CI
```

### Skills to force-load

`phase6-ops-triage`, `trading-bot-operations`, `code-isolation-testing`  
Ref: `~/.hermes/skills/trading-bot-operations/references/manual-rebalance-and-cron-pid.md`
