# Handoff — OPS-P0-2 Funnel why — 2026-09-18

**MASTER:** `OPS-P0-2-FUNNEL-WHY-20260918`  
**Parent epic:** `OPS-ONE-CALL-P0-20260918`  
**Assignee:** `crypto-engineer`  
**Priority:** P0  
**Workspace:** `dir:/home/brad/projects/crypto-trading-bot`  
**Kanban tag:** `[STAGED]`

### Objective

One-call “why no trade / why PAIR blocked” board from scoreboard + RSI + sent age + buy_block + thaw + latch + seats. **Read-only.**

### Must Do

1. CLI: `scripts/phase6/ops_funnel_why.py` + `phase6/scripts/funnel_why.sh [PAIR]`  
2. Hermes: `~/.hermes/scripts/phase6_funnel_why.sh`  
3. Reuse existing readers where possible:  
   - `data/state/recovery_tryout_scoreboard.json`  
   - tryout readiness / latch state  
   - live signals helpers if stable (`dashboard_serve_helpers` patterns — prefer reading state JSON over importing heavy runner)  
4. Per pair (or top blocked list): blocker tags + human reason + next natural clear hint if cheap  
5. JSON: `data/state/ops_funnel_why_latest.json`  
6. Isolation test with fixture scoreboard  
7. Skill: `phase6-ops-funnel-why`  
8. Commit

### Must Not

- Paid X refresh  
- Force rebalance  
- Door/thaw edits  
- “Should buy” advice — blockers only

### Success Criteria

- `bash phase6/scripts/funnel_why.sh` and `... LINK-USD` work  
- Isolation PASS  
- ≤20 line stdout summary

### Validation

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_ops_funnel_why.py
bash phase6/scripts/funnel_why.sh
bash phase6/scripts/funnel_why.sh LINK-USD
```

### Skills

`phase6-dashboard-signals`, `phase6-ops-triage`, `code-isolation-testing`
