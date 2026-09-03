# Limit-first buy pilot (Phase D)

**As of:** 2026-09-03T18:45:12.903883+00:00
**UTC day:** 2026-09-03
**Kill switch:** off
**Config mode:** `limit_first_v1` · enabled=`True`
**Caps:** buys/day=3 · usd/day=300
**Policy:** post_only=True · wait=45s · fallback=False · elevated=abort

## Honesty

- Cost-cut pilot only — **not alpha**, not a printer.
- Fill rate at post_only bid is the metric that matters.
- Over-cap / kill → **market IOC** (legacy), not forced skip of all buys.
- Review bar (design): ≥30 limit attempts or 14d before promote talk.

## Today

- Limit attempts: **0**
- Filled: **0** · Unfilled: **0** · Errors: **0**
- Fill rate: **n/a**
- USD attempted (limit): **$0.00**
- USD filled (limit): **$0.00**
- Over-cap → market: **0**
- Kill → market: **0**
- Elevated aborts: **0**

State: `data/state/limit_first_buy_pilot_state.json`
Events: `data/state/limit_first_buy_pilot_events.jsonl`
Kill file: `data/state/limit_first_buy_KILL` (touch to force market)
