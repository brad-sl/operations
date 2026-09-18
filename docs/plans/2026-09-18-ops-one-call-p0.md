# OPS-ONE-CALL-P0 — 2026-09-18

**Status:** STAFFED as Kanban (not yet implemented)  
**Board:** `crypto-bot-project`  
**Why:** Brad GO — stop burning main-agent tokens on repeated operator choreography. Same pattern as `basket_swap` / `phase6-dual-agree-brad-go-swap`.

## Goal

Ship four **measure-first one-call CLIs** + thin skills + isolation tests so routine ops are:

```
skill load → one shell call → JSON receipt → ≤15-line TG/plain report
```

No live knobs, no auto-orders, no `live_membership_swaps` flip, no force rebalance unless Brad already said so on that turn.

## Children (P0)

| Tag | CLI | Default | Write path |
|-----|-----|---------|------------|
| P0-1 | `phase6/scripts/status_plain.sh` | always read | none |
| P0-2 | `phase6/scripts/funnel_why.sh [PAIR]` | always read | none |
| P0-3 | `phase6/scripts/force_rebalance.sh` | dry-run / status | `--go` only (Brad already asked force) |
| P0-4 | `phase6/scripts/runner_ctl.sh` | `status` | `restart`/`stop` only on explicit Brad GO |

## Shared contract

- Exit codes: `0` ok · `2` need-go · `3` refuse · `4` blocked/error
- Write JSON under `data/state/ops_one_call_*_latest.json`
- Markdown short board under `reports/OPS_*_LATEST.md` where useful
- Isolation tests under `scripts/phase6/test_isolation_ops_*`
- Skills under `trading-bot-operations/` with trigger ≤57 chars
- Umbrella index skill `phase6-ops-one-call` after children land
- Commit CLIs + tests + docs; do **not** restart runner unless the card is P0-4 and Brad GO is in the card comment

## Must not

- Place orders except force-rebalance path when `--go` and Brad already approved that action
- Change regime/tryout/door knobs
- Touch PAXG E1 sizing as part of these cards
- Auto-promote / flip membership swaps
- Long agent digs when the CLI exists

## Kanban (`crypto-bot-project`)

| Card | id | status at staff |
|------|-----|-----------------|
| HUB | `t_4d89f0c7` | scheduled (tracking) |
| P0-1 status plain | `t_050ea502` | todo → crypto-engineer |
| P0-2 funnel why | `t_91d2b698` | todo → crypto-engineer |
| P0-3 force rebalance | `t_6eb636a3` | todo → crypto-engineer |
| P0-4 runner ctl | `t_bbe2956d` | todo → crypto-engineer |

## Done definition (epic)

All four children DONE + umbrella skill points at them + MASTER updated + one smoke of each CLI on live read paths.
