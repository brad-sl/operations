# Handoff — PC-02 Exit stack proof — 2026-09-11

**MASTER:** `PC-02-EXIT-STACK-PROOF-20260911`  
**Parent epic:** `PLATFORM-COMPLETENESS-20260911`  
**Assignee when staffed:** `crypto-engineer` (impl) + `crypto-analyst` (scoreboard read)  
**Priority:** P0  
**Kanban tag:** `[STAGED]`

### Objective

Prove exit paths bank progress more than process tax; produce go/no-go packet for any live exit promote (TP/hard_exit). **No silent live flips.**

### Must Do

1. Inventory live vs shadow exits (trail TP, dual_peak, hard_exit, exchange SL).
2. Ledger RT scoreboard: TP bank vs SL bank 7d/30d deposit-adj.
3. Disposition honesty (TP not stamped manual; SL policy cooloff correct).
4. Tie to existing gated cards: profit-exit live gates, hard-exit auto-apply — **do not bypass**.
5. Report: `reports/EXIT_STACK_PROOF_LATEST.md`

### Must Not

- `live_apply` / hard_exit promote without Brad GO
- Claim path CF without stops as edge
- Widen entries to “create TP samples”

### Success Criteria

- Honest scoreboard on disk
- Explicit list: safe-as-is / needs fix / promote-ready (likely empty)
- Links to SOP `docs/sop/TRUST_FIRST_TRADING_ENGINE.md`

### Validation

```bash
# existing exit / disposition isolations as applicable
ls reports/EXIT_STACK_PROOF_LATEST.md
rg -n "live_apply|shadow_only" config/exit_automation.json config/*.json | head
```

### Skills

`phase6-exit-automation`, `phase6-exit-profit-shadow`, `offline-strategy-honesty`, `phase6-sl-exits-and-dust`
