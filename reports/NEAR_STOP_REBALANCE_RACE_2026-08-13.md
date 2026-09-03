# P6-NEAR-STOP-REBALANCE-RACE-20260813 Fix Report

**Date:** 2026-08-13
**Kanban:** t_f1d02d37
**Ops:** P6-OPS-20260813-004 (GH #22)
**Status:** FIXED + VERIFIED

## Summary
Extended the near-stop filter to hard-block any BUY (including rebalance plans with empty or "rebalance_buy" reason) when the pair has an open armed stop in the protective registry and current position >= min.

This closes the race where rebalance added size minutes before an existing stop fired (RAVE 08-12, LINK 08-04, etc), manufacturing SL loss on the injected capital.

## Changes
- `phase6/core/runner_capital_events.py`: added hard [ARMED-STOP] early return in `filter_trade_plan_near_open_stop` (before soft evaluate). Uses existing `_latest_registry_stop_for_pair` + position check. Updated docstring.
- `scripts/phase6/test_isolation_near_stop_add_block.py`: added `test_armed_stop_blocks_rebalance_add`, updated integration and other-reason test doc; now exercises rebal-style adds + asserts drop + PASS.

## Reproduction (real data)
Ledger query post-Aug1:
- RAVE-USD 2026-08-12T04:00:59 rebalance_buy + 04:06:28 rebalance_buy → 04:06:57 stop_loss_exchange (0.5-6min)
- LINK-USD 2026-08-04T16:16:34 rebalance_buy → 16:17:03 stop (0.5min)

Current registry (live state):
LINK-USD, BTC, ADA, PAXG have "open" stops.

Filter sim before: rebal no-reason BUY kept into armed LINK.
After: [ARMED-STOP] logged + dropped.

## Test run
```
$ PYTHONPATH=. python3 scripts/phase6/test_isolation_near_stop_add_block.py
... [ARMED-STOP] blocked BUY RAVE-USD ...
... [ARMED-STOP] blocked rebalance_buy RAVE-USD ...
... [ARMED-STOP] blocked light_tilt_cash LINK-USD ...
PASS near_stop_add_block isolation (armed + soft)
```

## Live / Audit
- `python3 scripts/phase6/audit_rebalance_sl_gaps.py` → 0 (last 72h)
- No restart of runner required for verification (import-time module exercised in test).
- No prices/positions faked. No config changes. No scope creep.
- Next daily rebalance will exercise the path in context.

## MASTER / Ops
- MASTER updated to DONE for this id.
- Registry close will be done via `python3 scripts/phase6/ops_triage_tasks.py close --id P6-OPS-20260813-004 --note 'Hard armed gate + isolation PASS; see report and kanban t_f1d02d37'`

## Evidence files
- reports/NEAR_STOP_REBALANCE_RACE_2026-08-13.md (this)
- handoffs/Handoff_P6_NEAR_STOP_REBALANCE_RACE_20260813.md
- reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md
- trades/phase6_trades.jsonl (incidents)
- data/state/protective_orders_registry.jsonl
- phase6/core/runner_capital_events.py (fix)
- scripts/phase6/test_isolation_near_stop_add_block.py (test)

Target: 0 new manufactured add→SL post-deploy.

## Re-verify (kanban t_f1d02d37 retry)
- 2026-08-13: test PASS + [ARMED-STOP] logs
- audit 0
- GH closed + comment added
- registry re-closed via script
- MASTER + SPECS + ops_triage updated
- All real ledger/registry data
