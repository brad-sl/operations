# NEEDLE-10 — phase6.db dual-write + util/NAV truth

**Status:** trades dual-write live; util fixed; positions dual-write live (2026-10-14).

## Canonical sources

| Concern | SSOT | Mirror |
|---|---|---|
| Fills / exits | `trades/phase6_trades.jsonl` | `data/phase6.db` `trades` via `TradeLedger._dual_write_phase6_db` (dedupe on `order_id`) |
| Open book | `data/state/phase6_live_state.json` | `data/phase6.db` `current_positions` via `Phase6Runner._dual_write_current_positions` each `persist_facts_to_db` |
| Cash / park | live_state balances (USD + USDC) | `account_balances` |
| Crypto util | `crypto_util_pct_from_live` = non-stable non-PAXG MTM / equity | not `(total - cash_usd)` |
| RSI / X caches | state JSON under `data/state/` | optional db tables |

## Rules

- Do **not** truncate `phase6.db` without a backup.
- Do **not** replay the 121k pre-2026-07 junk trade rows; dual-write is forward + optional unique-oid backfill.
- Dashboard may prefer DB views; if positions look like Jun demo bags, runner has not cycled `persist_facts_to_db` since the dual-write patch — live_state is still truth.
- Util gate: USDC and PAXG are **not** crypto risk.

## Validation

- `scripts/phase6/test_isolation_needle10_positions_dual_write.py`
- `scripts/phase6/test_isolation_needle_remainder.py` (01 util/unwind)
- `SELECT max(ts), count(*) FROM trades` should be recent after fills
- `SELECT pair, source, ts FROM current_positions` should be `live_state` after a runner cycle
