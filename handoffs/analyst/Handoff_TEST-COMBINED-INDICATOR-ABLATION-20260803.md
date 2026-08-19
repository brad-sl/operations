# Handoff — combined ablation

**Status:** CLOSED (drop)
**Decision:** drop @ 2026-08-03T22:40:52.038506+00:00
**Note:** Brad 2026-08-03: drop. Short-window ~+5% F2 did not survive Coinbase long-tape walk-forward (2021-2026 EW mean -20%, BTC F2 -53%). No standard opt / no live. Keep lessons: kill 4-way AND stack; RSI filter > MACD-only; no Stoch/BB required entry. Residual regime-gate idea only if Brad reopens.

---
(prior content below)

# Handoff — TEST-COMBINED-INDICATOR-ABLATION-2026-08

**Status:** REPORT_READY (multi-pair pass)
**Trial:** `TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL`
**Source TUI:** @session:default/20260731_152450_773d89
**Generated:** 2026-08-03T21:27:40.223995+00:00

## Intent
Offline multi-pair ablation + entry/exit/SL enhancements. North star: returns AND less loss.

## Artifacts
- Runner: `phase6/research/combined_strategy_backtest.py`
- Report: `reports/COMBINED_INDICATOR_ABLATION_MULTIPAIR_2026-08-03.md`
- JSON: `reports/COMBINED_INDICATOR_ABLATION_MULTIPAIR_2026-08-03.json` + `data/state/trials/TEST_COMBINED_INDICATOR_ABLATION.json`
- Trades: `reports/COMBINED_INDICATOR_ABLATION_TRADES_2026-08-03.csv`
- Protocol: `docs/testing/trials/TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL_PROTOCOL.md`

## Plain-English
- Full 4-way confluence (A0) = **N=0** everywhere → kill as ops strategy.
- Best path: **relax entry** (MACD× + RSI&lt;40) + **ATR trail** (E3/E0 family).
- Beats equal-weight multi-asset BH on less-loss in this alt-heavy drawdown tape, but **absolute returns still weak** → `dig_further` not promote.
- **Do not** promote live RSI+Stoch combo.

## Suggested decide
`dig_further` → if using trial_cycle decide enum, map dig_further→continue_observe_only or extend; drop→drop.
