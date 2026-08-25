# Run Lifecycle P1 + P2 — 2026-08-24

## RSI pairing (MA / Fib) — design take

RSI **in isolation** is a momentum oscillator: it tells *heat*, not *location in the move*.
Pairing with structure reduces false reactions:

| Tool | Role |
|------|------|
| **RSI** | Is momentum turning or stretched? (band 45–68 for entries) |
| **SMA 20 / 50** | Is trend structure intact? (above rising fast MA) |
| **Fib 38.2–61.8** | Is this a pullback in a leg, or already at/through the swing high? |
| **Run phase** | Ignition/trend vs extension/distribution (P0 hard gate) |
| **Sentiment** | Timing reinforce only — never sole entry driver |

We implement **RSI × structure** as a joint score: high RSI without structure → **0**. Structure late (Fib ≥ 1.0) → **0**. Sentiment can add a small boost only after structure clears.

## P1 — Ignition scout

- Module: `phase6/core/run_lifecycle.py`
- Board: `data/state/ignition_scout_board.json`
- Mode: **`shadow`** default (board + monitor notes). Set `run_lifecycle.ignition_scout.mode=propose` to append capped BUY hints on rebalance (still pass RSI-primary + run-phase gates).
- Only phases **1–2**, `require_structure_ok=true`, `min_score=0.55`, `proposal_usd_cap=150`.

## P2 — Dual-peak exit shadow

- Same module; events: `data/state/dual_peak_exit_shadow_events.jsonl`
- **dual_peak**: (failed high / MFE stall / climax / distribution) **AND** (sent fade Δ≥0.30 or sent≤0.20)
- **extension_partial**: phase ≥ extension with MFE — suggest 33% trim (shadow)
- Wired into `monitor_reentry_sl_tp.py` (with sentiment-fade)
- **No live sells** until Brad promotes mode (same trust path as fade)

## Entry lot enrichment

`record_entry_lot` now tags `run_phase_at_entry`, swing refs, structure snapshot, `peak_price` / `entry_sent_peak` tracking on dual-peak ticks.

## Validation

```bash
PYTHONPATH=. python3 scripts/phase6/test_isolation_run_lifecycle_p12.py
PYTHONPATH=. python3 scripts/phase6/backtest_run_lifecycle_p12_cf.py
```

Report: `data/state/run_lifecycle_p12_cf_report.json`

## Config

`run_lifecycle` block in `config/trading_config_phase6.json`.
