# Code review follow-up — analyst 004/005/006 integration fixes

Date: 2026-07-08
Reviewer experiment: Kimi via `code-reviewer` (session 20260708_081602_6c412a)

## Changes
- `stop_loss_manager.py`: `sanitize_reattach_order_id` before poll; abort SL on fill-tied poll failure; early hold→cancel; warning-level pre-flight errors
- `pre_rebalance_data_refresh.py`: refresher subprocess exit code + stderr; 5s cap on `load_sentiment_scores` fallback
- `sl_preflight.py`: increment-aware market buffer in `ensure_stop_below_market`
- `run_scenario_leaderboard.py`: warn when scenario `date_range` outside pack
- `test_isolation_sl_preflight.py`: manager sanitize integration test

## Verification
```
.venv/bin/python3 phase6/tests/test_isolation_sl_preflight.py
.venv/bin/python3 phase6/tests/test_isolation_pre_rebalance_refresh.py
.venv/bin/python3 phase6/tests/test_scenario_date_range_override.py
```
All exit 0 (2026-07-08).