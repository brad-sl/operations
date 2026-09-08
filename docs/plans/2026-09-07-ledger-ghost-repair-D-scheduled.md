# Ledger ghost repair (D) — scheduled, not this ship

**Parent:** `docs/plans/2026-09-07-ledger-ssot-and-tp-lot-bind.md`  
**Status:** scheduled after A+B+C land and soak  
**Do not run destructive repair without Brad go**

## Why D still exists

A+B stop **new** holes (missing writes; SELL qty skipped).  
C stops live TP on bad basis.  
Historical phantom layers (e.g. LINK operator trim 32.34 missing from FIFO before B, other incomplete SELLs) may still make **dashboard** open-qty / soft LIFO estimates noisy until repaired.

## Outline (future go)

1. Script: for each held pair, compare FIFO open qty vs exchange qty.
2. List pairs where ledger_open ≫ exchange (ghost) or ≪ exchange (missing buys).
3. Emit **proposed** compensating rows or `ops_correction` events — audit trail, no silent history rewrite.
4. Default **dry-run**; `--execute` only on Brad go.
5. LINK: ensure Aug 24 32.34-class trim is reflected once B is live; add explicit correction only if still drifting.

## Out of scope for D card

- Auto-rebuild full Coinbase history on every runner boot
- Changing TP knobs
- Discretionary live sells to “fix” basis

## Trigger to open D

After A+B+C deploy + ≥1 clean journaled rebalance cycle, if `average_cost_for_pair` still returns `ledger_lifo_exchange_qty` / mismatch on held bags → start D.
