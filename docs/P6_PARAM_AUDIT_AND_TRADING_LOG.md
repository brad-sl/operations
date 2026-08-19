# P6 Param Audit & Scalable Trading Logs

## Account scope (1000-trader)

- One **Trading Bot API key** maps to one **Coinbase portfolio / account** (`portfolio_uuid`).
- Reconciliation (`reconcile_trading_bot_ledger`) assumes the **FILLED order pull is the full tradable surface** for that key — not a subset of the exchange.
- Scale-out: set `PHASE6_ACCOUNT_ID` / `COINBASE_PORTFOLIO_UUID` and `PHASE6_TRADER_ID` per worker; each worker owns one account partition.

## Log layout (high volume)

| Stream | Path | Rows |
|--------|------|------|
| **Canonical verified fills** | `data/state/trading_log/{account_id}/verified_fills_{YYYY-MM}.jsonl` | **1 row / order_id** |
| Order dedup index | `data/state/trading_log/{account_id}/order_id_index.json` | Set of order_ids |
| Param audit runs | `data/state/param_audit/{account_id}/audits_{run_id}.jsonl` | Many findings / run |
| Latest scorecard | `data/state/param_audit/{account_id}/latest_summary.json` | 1 / run |
| Legacy dashboard | `trades/phase6_trades.jsonl` | May duplicate; prefer verified store for audit |

**Rule:** Optimization and ANALYST-OPT should read **verified fills** + **param audit**, not unbounded legacy runner noise.

## Param audit rules

| Fill type | Checks |
|-----------|--------|
| `rebalance_buy` | In basket; `fill_verified` |
| `rotation_exchange` | MARKET sell; optional decision_context window (8h) |
| `stop_loss_exchange` | Loss vs `sl_min_pct` / `sl_max_pct`; registry stop price if present. **Gap band:** `SLIPPAGE_TOLERANCE_PCT=2.0%` beyond `sl_max` (was 0.5%) — stop-limit fills on alts that gap 1–2% past the placed stop are warn/pass band, not permanent promotion blocks. Losses past `sl_max + 2%` still **fail**. |

Config source: `config/trading_config_phase6.json` (`stop_loss_pct`, `sl_*`, basket, reserve).

## Decision context (rebalance)

Every daily rebalance writes `data/state/decision_context_log.jsonl` with `actions_taken` so rotation MARKET sells pass param audit.

```bash
.venv/bin/python scripts/phase6/backfill_decision_context_from_trades.py  # historical
```

Forward path: automatic via `RebalanceCoordinator` after plan execution.

## Optimize gate (ANALYST-OPT)

Scenario leaderboard and promotion require:

- `fail_count == 0`
- `confidence_score >= 0.85`
- `verified_fills >= 1`

Enforced in `run_scenario_leaderboard.py` (exit **3** if blocked) and `promotion_gates.evaluate_promotion_gates`. Weekly cron passes `--refresh-param-audit`.

Dev bypass: `--skip-live-param-audit-gate` (smoke packs only).

## Commands

```bash
# Migrate legacy verified rows + audit
.venv/bin/python scripts/phase6/run_param_audit.py

# Audit only (store already populated)
.venv/bin/python scripts/phase6/run_param_audit.py --no-migrate

# Reconcile then audit
.venv/bin/python scripts/phase6/reconcile_exchange_fills.py --full --backfill-days 120
.venv/bin/python scripts/phase6/run_param_audit.py
```

Exit code **2** if any **fail** findings.

## Confidence score

`latest_summary.json` → `confidence_score` ∈ [0,1] from pass/warn/fail mix. Use as gate before parameter optimization loops.