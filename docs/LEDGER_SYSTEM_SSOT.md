# Ledger System SSOT

**Status:** authoritative for Phase 6 trade journal / holdings basis  
**Incident anchor:** 2026-09-07 LINK rebalance BUY never journaled → live TP sold on ghost lot  
**Plan:** `docs/plans/2026-09-07-ledger-ssot-and-tp-lot-bind.md`

## 1. Purpose

The trade journal is the **source of truth** for:

- What traders executed (pair, side, qty, fill px, order_id, time)
- Open inventory cost basis (FIFO layers)
- Exit attribution (TP / SL / rebalance / operator)
- Dashboard Trades + Rebalances views
- Live take-profit lot identity (fail-closed)

If the exchange filled it and we claim to manage the bag, **it must be in the journal**.

## 2. Canonical paths

| Artifact | Path |
|----------|------|
| Primary JSONL journal | `trades/phase6_trades.jsonl` |
| Daily CSV (lite) | `trades/phase6_trades_YYYY-MM-DD.csv` |
| Exchange fill mirror | `trades/phase6_exchange_fills.jsonl` |
| Verified fills | `data/state/trading_log/**/verified_fills_*.jsonl` |
| Protective order registry | `data/state/protective_orders_registry.jsonl` |
| Live TP state | `data/state/shadow_tp_status.json` |
| Live TP exits log | `data/state/shadow_tp_live_exits.jsonl` |
| Influence / decision context | `data/state/influence_stack_log.jsonl`, decision context log |

Multi-tenant non-default accounts: `trades/<account_id>/phase6_trades.jsonl`.

Cross-links: `docs/DATA_FLOW_AND_LOCATIONS.md`, `docs/PHASE6_DASHBOARD_DATA_SPEC.md`.

## 3. Writers (must journal successful live fills)

| Writer | When | `signal_source` examples | Required fields |
|--------|------|--------------------------|-----------------|
| `OrderExecutor` | BUY/SELL success | `order_executor_buy`, `_sell`, `_rebalance` | pair, side, qty, fill px, order_id, mode |
| `TradeExecutor` (ARCH-4) | BUY/SELL success | `trade_executor_buy`, `_sell`, `_buy_via_oe` | same |
| `Phase6Runner._ensure_results_ledgered` | Post-plan defense | `runner_ensure_ledger` | same (idempotent by order_id) |
| Protected / dust / SL exit paths | When they market-exit | path-specific | SELL must carry **exit_price** |
| Operator scripts | Manual trims | `operator_*` | qty + exit_price or entry_price fallback |

**Rules:**

1. Prefer fill-verified `average_filled_price` + `filled_size`.
2. SELL rows **must** carry `exit_price` (fill). Do not omit price and expect inventory math to skip the SELL.
3. Ledger write failure must **not** unwind the exchange fill — log **ERROR**; fill already happened.
4. Same `order_id` must not double-count (`TradeLedger.log_trade` idempotent tail check + cost-basis dedupe).

## 4. Readers

| Reader | Uses journal for |
|--------|------------------|
| Dashboard Trades / Rebalances | Display, newest-first |
| `position_cost_basis` | FIFO open lot avg cost |
| `shadow_tp.resolve_entry` | Entry for r / TP |
| Buy-block / post-TP | Recent SELL reasons |
| Performance / ANALYST digs | Realized path, process tax |

## 5. Entry authority (live TP)

Locked Brad 2026-09-07:

1. **Verified fill / position lot** with trusted `entry_basis` (`ledger_avg_cost`, `test_fixture`, fill-verified, protective registry when appropriate)
2. **FIFO** `average_cost_for_pair` → basis `ledger_avg_cost` only when open ledger qty ≈ exchange qty

**Not trusted for live execute:**

- `last_buy_flat`, `last_buy_ledger_drift`, `ledger_last_buy`
- `ledger_flat_exchange_open`, `ledger_exchange_qty_mismatch`
- `ledger_lifo_exchange_qty` (ghost-layer slice — soft dash only)
- bare `position.entry_price` without trusted basis stamp

Gate: `entry_source_trusted_for_live` + `filter_live_exit_signals_by_entry_trust` in `shadow_tp.py`.  
Log line: `[LIVE-TP] blocked PAIR reason=untrusted_entry src=...`

Shadow mode may still **show** would-fire on untrusted basis for observability; **live market exit will not**.

## 6. FIFO inventory rules

- **Qty-first:** SELL with `qty>0` always reduces layers, even if exit price missing (operator-trim class).
- Price on SELL is for realized cost / display; absence must not resurrect inventory.
- When ledger flat but `expected_qty>0` → `None, ledger_flat_exchange_open` (never invent last buy as open lot).
- When drift ≫ tol and LIFO cannot cover → `None, ledger_exchange_qty_mismatch`.

## 7. Failure modes (this incident) → prevention

| Failure | Layer that stops it |
|---------|---------------------|
| Platform `TradeExecutor` BUY never journaled | **A** wire ledger on TE + OE + runner ensure |
| Operator SELL missing `exit_price` left phantom layers | **B** qty-first FIFO |
| Live TP used ghost LIFO / last_buy as entry | **C** fail-closed trust gate |
| Residual ghost inventory after A+B | **D** scheduled repair (separate go) |

## 8. How to verify a fill is journaled

```bash
# By order id
rg "ORDER_ID" trades/phase6_trades.jsonl

# Isolation proofs
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 phase6/core/test_isolation_ledger_write_path.py
PYTHONPATH=. python3 phase6/core/test_isolation_position_cost_basis_sell_qty.py
PYTHONPATH=. python3 phase6/core/test_isolation_live_tp_lot_bind_entry.py
```

After deploy: next successful micro BUY must appear in JSONL **before** the next live TP cycle can exit that bag on fixed_tp.

## 9. What is NOT SSOT

- `capital_events` alone (mis-tags happen)
- `recovery_state.json` alone
- Dashboard UI slice bugs (wrong number = bug, but path still ledger)
- Soft LIFO dash estimates under mismatch
- Time buffers as a substitute for lot identity

## 10. Ops restart note

Code wires load at runner process start. **Restart phase6 live runner** after deploy so OrderExecutor/TradeExecutor receive `trade_ledger`. Live TP stays ON (fail-closed is safe-fail: fewer bad exits).
