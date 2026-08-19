# Kimi platform code review — triage (2026-07-08)

**Run:** `scripts/hermes/run_platform_code_review_all.sh` (exit 0, ~25 min)  
**Artifacts:** `data/state/code_review/out/S1.md` … `S8.md`, `PLATFORM_REVIEW_ROLLUP.md`

## Slice status

| Slice | Status | Notes |
|-------|--------|--------|
| S1 Foundation | REVIEWED \| BLOCKED | Path/synthetic-price concerns (partial false positive on `paths.py` — uses `__file__`, not only hardcode) |
| S2 Runner | REVIEWED | Coordinators OK; thin vs monolithic runner split |
| S3 Execution | **REVIEWED** (re-run 2026-07-08 post-P0) | Prior BLOCKED: shadow SL, double poll, ledger — fixed + tests PASS |
| S4 Stop-loss | REVIEWED | CR-03 verify wired in coordinator (ENG-S4-01) |
| S5 Allocation | REVIEWED | Stale mtime, drawdown window, deploy_capital bypass |
| S6 ANALYST-OPT | REVIEWED | Gate tests + arch4 `min_move_usd` gap |
| S7 Intel | REVIEWED | **ENG-S7-01 DONE** — title/semantic dedup vs backlog + deployed |
| S8 Cross-cut | REVIEWED (thin) | Kimi did not run `rg` successfully — re-run S8 locally if needed |

## P0 backlog (live money / trust)

1. **ENG-S3-01 — Shadow `execute_buy` must not call live SL/TP**  
   `order_executor.py`: gate `attach_stop_loss` / `attach_take_profit` when `mode=="shadow"` or SL manager is shadow-only.

2. **ENG-S3-02 — Single authoritative settlement poll**  
   Remove redundant `poll_for_settlement` in `order_executor` *or* in `stop_loss_manager` when `order_id` already polled; document one owner.

3. **ENG-S3-03 — Ledger exchange confirm (optional async)**  
   `trade_ledger.py`: before append, optionally verify fill via `get_order_fill_details` for live trades.

4. **ENG-S3-04 — Remove duplicate `log_influence_stack`** in `trade_ledger.py`.

5. **ENG-S4-01 — CR-03 verify in coordinator**  
   `stop_loss_coordinator.suspend_reattach_context`: call `verify_reconciliation` on success path.

6. **ENG-S4-02 — Stop vs stale `entry_price` after market rebase**  
   `stop_loss_manager.py` ~173–181: compare against `calc_base`, not raw `entry_price`.

## P1 backlog (reliability / OPT)

7. **ENG-S5-01** — Per-pair stale flags in pre-rebal refresh (not whole-file mtime).  
8. **ENG-S5-02** — Trailing-window drawdown in `RotationStrategy._compute_drawdowns`.  
9. **ANALYST-OPT-R2c** — Unit tests: `sharpe < 0`, skipped sim, max-dd slack block promotion.  
10. **ANALYST-OPT-R5** — Pass `min_move_usd` into `run_arch4_backtest` or drop from params.  
11. ~~**ENG-S7-01**~~ — **DONE 2026-07-08:** `normalize_proposal_title` + `collect_known_proposal_titles` / `collect_deployed_proposal_titles`; suppress re-minting IDs for SL pre-flight, data refresh, OPT Sharpe themes already in backlog. Test: `test_isolation_intel_proposal_dedup.py`.

## P2 / hygiene

- S1: Audit `get_price()` stub paths in live mode (assert non-stub when `mode=live`).  
- S6: Gap-matrix checksum at promotion gate.  
- S8: Re-run with fixed packet (`docs/DATA_FLOW_AND_LOCATIONS.md` path typo confused reviewer).

## Recommended next execution order

1. ~~ENG-S3-01 + ENG-S3-02~~ **DONE 2026-07-08**
2. ~~ENG-S4-01 + ENG-S4-02~~ **DONE 2026-07-08**
3. ~~ENG-S7-01~~ **DONE 2026-07-08**
4. ANALYST-OPT-R2c tests

### P0 implementation (2026-07-08)
- `order_executor.py`: shadow skips SL/TP; removed duplicate `poll_for_settlement` before attach
- **2026-07-08 follow-up:** removed parallel 30s fill poll in executor; `fresh_buy=True` on attach; post-SL verified fill → ledger
- `sl_preflight.py`: `fetch_verified_order_fill`, `SETTLEMENT_POLL_OWNER`
- `stop_loss_manager.py`: verified fill after settlement poll; no market SL anchor on fresh buy without fill
- `trade_ledger.py`: single `log_influence_stack`; `log_trade(..., exchange=)` fill verify
- `stop_loss_coordinator.py`: `verify_reconciliation` after reattach
- `stop_loss_manager.py`: stop vs `calc_base` anchor
- Tests: `test_isolation_order_executor_p0.py`, `test_isolation_cr03_verify.py` — PASS
- **Ledger wired (2026-07-08):** `TradeLedger.log_execution_result`; `OrderExecutor(trade_ledger=…)` auto-logs buy/sell; `phase6_runner` logs platform `TradeExecutor` paths (`arch4_rebalance`, `phase6_fresh_start`) with `exchange=` for live fill verify.
- **S3 re-review:** `run_platform_code_review_slice.sh S3` → `SLICE_STATUS: REVIEWED` (log `data/state/code_review/out/S3_rerun_20260708.log`).
- **ENG-S7-01:** `generate_trading_intelligence_report.py` title dedup; `test_isolation_intel_proposal_dedup.py` PASS.

## Re-run

```bash
scripts/hermes/run_platform_code_review_slice.sh S3   # after ENG-S3 fixes
```

**Do not** interpret this review as “platform approved for capital increase.” It is a prioritized defect list.