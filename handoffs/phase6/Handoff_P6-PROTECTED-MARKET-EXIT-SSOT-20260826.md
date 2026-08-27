# Handoff: P6-PROTECTED-MARKET-EXIT-SSOT-20260826

## Objective
Single protected market-exit module (cancel stop → poll free → sell → reattach SL) used by lifecycle + live TP so Coinbase hold locks cannot miss profit exits.

## Must Do
- Implement `phase6/core/protected_market_exit.py`
- Wire `apply_lifecycle_exits_live` + `execute_live_tp_exits`
- Isolation tests PASS; restart live runner

## Must Not
- Change buy path / rebalance allocator
- Leave bag naked after cancel-on-fail
- Fake prices or live book without go

## Deliverables
- Module + callers + tests + MASTER DONE + Kanban complete

## Validation
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 scripts/phase6/test_isolation_protected_market_exit.py
PYTHONPATH=. python3 scripts/phase6/test_isolation_run_lifecycle_p12.py
PYTHONPATH=. python3 phase6/core/test_isolation_live_tp_exit.py
```
