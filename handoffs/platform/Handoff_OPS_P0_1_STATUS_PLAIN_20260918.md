# Handoff — OPS-P0-1 Status plain — 2026-09-18

**MASTER:** `OPS-P0-1-STATUS-PLAIN-20260918`  
**Parent epic:** `OPS-ONE-CALL-P0-20260918`  
**Assignee:** `crypto-engineer`  
**Priority:** P0  
**Workspace:** `dir:/home/brad/projects/crypto-trading-bot`  
**Branch:** stay on `phase-6.1` (no worktree required)  
**Kanban tag:** `[STAGED]`

### Objective

One-call plain-English status pack from existing LATEST artifacts. **Read-only.** Kills “what’s going on” main-agent digs.

### Must Do

1. CLI: `scripts/phase6/ops_status_plain.py` + wrapper `phase6/scripts/status_plain.sh`
2. Hermes wrapper: `~/.hermes/scripts/phase6_status_plain.sh`
3. Inputs (best-effort, tolerate missing):  
   - `reports/PLATFORM_METRICS_SPINE_LATEST.md` / `data/state/platform_metrics_spine_latest.json`  
   - `reports/PROMOTE_GRADUATION_CHART_LATEST.md`  
   - `data/state/phase6_live_state.json` (cash, positions, runner)  
   - runner pid / `logs/phase6_runner.pid`  
   - door/thaw expiry if present in `config/regime_cash_policy.json`  
4. Output: 8–12 plain lines covering: machine health · money path choke · seats · open risk (PAXG park note only) · next natural rebalance · auto-promote OFF honesty  
5. JSON receipt: `data/state/ops_status_plain_latest.json`  
6. Optional short MD: `reports/OPS_STATUS_PLAIN_LATEST.md`  
7. Isolation test: `scripts/phase6/test_isolation_ops_status_plain.py` (fixtures only; no live network required for unit path; live smoke optional)  
8. Skill: `phase6-ops-status-plain` — trigger on “status plain / what’s going on / spine plain english”  
9. Commit on `phase-6.1`

### Must Not

- Restart runner  
- Force rebalance  
- Change any config knobs  
- Claim edge / live PnL guarantees  
- Dump full JSON to Telegram (short board only)

### Success Criteria

- `bash phase6/scripts/status_plain.sh` exits 0 and prints ≤15 lines  
- Isolation PASS  
- Skill loads and points at the CLI  
- No live writes

### Validation

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_ops_status_plain.py
bash phase6/scripts/status_plain.sh
test -f data/state/ops_status_plain_latest.json
```

### Skills to force-load

`phase6-ops-triage`, `ui-expectation-honesty`, `code-isolation-testing`
