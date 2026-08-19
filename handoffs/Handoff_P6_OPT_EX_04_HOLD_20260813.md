# Task Handoff Document

**Task ID:** `P6-OPT-EX-04-HOLD-20260813`  
**Parent Task:** `P6-OPT-EXAMINE-PACK-20260813`  
**Assigned To:** crypto-analyst  
**Date Assigned:** 2026-08-13  

### Objective
Produce a **do-not-reopen** list of already-decided holds, and flag only items whose review date is actually due.

### Context
Stoch CLOSED observe_only 2026-08-04 (30d reeval). USDC park OFF until gates. W0 OFF. Live profit-exit not flipped. Reddit sentiment OFF. 20%/mo avg is not a KPI.

### Must Do
- Check MASTER + trial INDEX for stoch parent/child status and reeval date vs today (2026-08-13)
- Confirm USDC / W0 / live TP / Reddit still off in config or docs
- Table: item | status | review_due | due_now? | action
- Call: `watch` if nothing due / `pursue` only for items whose date has passed
- Write `reports/OPT_EX_04_HOLD_2026-08-13.md`

### Must Not
- Reopen stoch as a new mashup
- Enable USDC or live TP
- Invent new holds

### Success
Brad can scan the table in 30 seconds. Default expected call: `watch` (nothing due).

### Skills
`offline-strategy-honesty`, `analyst-test-cycle`
