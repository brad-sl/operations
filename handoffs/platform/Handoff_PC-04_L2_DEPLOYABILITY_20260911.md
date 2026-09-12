# Handoff — PC-04 L2 deployability score — 2026-09-11

**MASTER:** `PC-04-L2-DEPLOYABILITY-20260911`  
**Parent epic:** `PLATFORM-COMPLETENESS-20260911`  
**Assignee when staffed:** `crypto-engineer`  
**Priority:** P1  
**Kanban tag:** `[STAGED]`

### Objective

Score paper/CF ADD candidates with **L2 = would live runner buy under evaluate_buy_entry?** Separate from L1 price-path CF.

### Must Do

1. Pure function + isolation fixtures (pass/fail reasons).
2. Attach to basket CF / paper-primary board (`rel_btc_stable` preferred arm).
3. Document: dual_agree ≠ promote; L2 fail ⇒ no promote talk.

### Must Not

- live_membership_swaps true
- Mutate live basket from L2 scores

### Success Criteria

- Isolation green
- CF artifact shows L1 + L2 columns
- Promote packets reference L2

### Skills

`phase6-breadth-and-membership-edge`, `decision-quality-gates`, `code-isolation-testing`
