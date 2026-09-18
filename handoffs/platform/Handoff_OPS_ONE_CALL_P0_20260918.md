# Handoff — OPS-ONE-CALL-P0 hub — 2026-09-18

**MASTER:** `OPS-ONE-CALL-P0-20260918`  
**Board:** `crypto-bot-project`  
**Assignee (hub):** tracking only — do not claim hub for impl  
**Plan:** `docs/plans/2026-09-18-ops-one-call-p0.md`  
**Related skill pattern:** `phase6-dual-agree-brad-go-swap` + `scripts/phase6/basket_swap.py`

### Objective

Staff four independent P0 operator one-call CLIs so main agent stops re-digging status / funnel / force-rebal / runner restart.

### Children (staff these, not the hub)

1. OPS-P0-1 status plain  
2. OPS-P0-2 funnel why  
3. OPS-P0-3 force rebalance  
4. OPS-P0-4 runner ctl  

### Must not on hub

- Implement code on hub card  
- Auto-pickup  
- Live trading changes  

### Success

All four children complete with isolation green + short report receipts + umbrella skill `phase6-ops-one-call` indexing them.
