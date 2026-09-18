# Handoff — OPS-P0-4 Runner ctl — 2026-09-18

**MASTER:** `OPS-P0-4-RUNNER-CTL-20260918`  
**Parent epic:** `OPS-ONE-CALL-P0-20260918`  
**Assignee:** `crypto-engineer`  
**Priority:** P0  
**Workspace:** `dir:/home/brad/projects/crypto-trading-bot`  
**Kanban tag:** `[STAGED]`

### Objective

One-call runner control that ends pidfile thrash (`exit -15/-1` restart loops). Default **status only**.

### Must Do

1. CLI: `scripts/phase6/ops_runner_ctl.py` + `phase6/scripts/runner_ctl.sh {status|restart|stop}`  
2. Hermes: `~/.hermes/scripts/phase6_runner_ctl.sh`  
3. Implement the **known good** restart sequence only (from ops runbooks):  
   - clear known pid files: `logs/phase6_runner.pid`, `phase6_live.pid`, `data/state/phase6_runner.pid` as applicable  
   - stop gracefully then start via `bash scripts/phase6/start_phase6_runner.sh`  
   - verify process + recent log heartbeat  
4. Default command = `status` (pid, uptime/heartbeat, last cycle line if cheap)  
5. `restart` / `stop` require `--go` flag **and** skill text that Brad asked  
6. JSON: `data/state/ops_runner_ctl_latest.json`  
7. Isolation: mock process layer where possible; never kill live runner inside unit test  
8. Skill: `phase6-ops-runner-ctl` — hard rule: no restart from triage cron / no_agent  
9. Commit

### Must Not

- Restart from measurement crons  
- `pkill -9` as first resort  
- Change trading config during restart  
- Kill unrelated python processes

### Success Criteria

- `bash phase6/scripts/runner_ctl.sh status` always safe  
- Isolation PASS without touching live PID  
- Restart path documented + dry logic tested; live restart only when Brad GO on a staffed run

### Validation

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_ops_runner_ctl.py
bash phase6/scripts/runner_ctl.sh status
# DO NOT restart in CI/isolation
```

### Skills

`phase6-ops-triage`, `trading-bot-operations`, `code-isolation-testing`  
Ref: `references/manual-rebalance-and-cron-pid.md` (restart section if present)
