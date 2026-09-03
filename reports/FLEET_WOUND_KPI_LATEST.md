# Fleet wound KPI (GAP-02)

**As of:** 2026-08-16T19:01:56.874417Z  
**Decision:** `watch_pre_fix_residual` · **Flag:** `OK`  
**Go/no-go:** WATCH — 7d still shows pre-fix BUY→SL residual; post-fix window clean. Re-check as calendar rolls.  

| Window | Count | Under 5m | Pairs |
|--------|-------|----------|-------|
| 7d | 1 | 1 | RAVE-USD |
| 30d | 3 | 3 | LINK-USD, OP-USD, RAVE-USD |
| post armed-stop fix | 0 | 0 | — |

Armed-stop fix clock: `2026-08-13T00:00:00Z`  
Alert active: **False**  

Manufactured wound = BUY then stop_loss* same pair within window. Single-ledger today; account_id reserved for multi-tenant rollup.

