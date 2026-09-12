# Handoff — PC-03 Tryout sleeve real — 2026-09-11

**MASTER:** `PC-03-TRYOUT-SLEEVE-REAL-20260911`  
**Parent epic:** `PLATFORM-COMPLETENESS-20260911`  
**Assignee when staffed:** `crypto-engineer`  
**Priority:** P0  
**Kanban tag:** `[STAGED]`

### Objective

Make the open tryout sleeve **operationally real**: eng sentiment clock true; when heat clears floor, buy→protect→exit path works. Do not manufacture green by lowering floors.

### Context (2026-09-11)

- Eligible: ETH, XRP, AVAX (force_eligible)
- All blocked eng_sent &lt; 0.35; free tee warm ≠ gate
- Readiness: `reports/TRYOUT_READINESS_LATEST.md`

### Must Do

1. Maintain/refresh tryout readiness artifact each ops cycle.
2. Prove X aging + reddit bridge (no stuck-zero bug).
3. On first real tryout BUY: A1 SL attach + ledger + no ghost peak.
4. Document floor SSOT; any floor change = Brad GO only.
5. Optional: one-shot TG when eng clears (no_agent) — only if Brad asks.

### Must Not

- Lower entry floors without GO
- force_rebalance to test
- Expand force_eligible list casually
- Treat free/Adanos tee as live gate

### Success Criteria

- 7d: either ≥1 honest protected tryout cycle **or** drought report with sensor_verdict.broken=false
- No process_tax from tryout path

### Validation

```bash
test -f data/state/tryout_readiness_latest.json
PYTHONPATH=. .venv/bin/python3 -c "import json;print(json.load(open('data/state/tryout_readiness_latest.json'))['can_buy_before_next_rebalance'])"
```

### Skills

`phase6-sentiment-pipeline`, `phase6-ops-triage`, `trading-config-path-integrity`, `ui-expectation-honesty`
