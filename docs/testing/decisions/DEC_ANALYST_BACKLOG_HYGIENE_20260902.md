# Analyst backlog hygiene — 2026-09-02

**When:** 2026-09-02T19:26:42.390823Z
**Brad:** hygiene pass — valid open/waiting; archive duplicate spam.

## Stats
- Input: 200
- Unique stems: 14
- Kept: 14 (terminal 7, open 4, waiting 3)
- Archived duplicates: 186
- Archive file: `/home/brad/projects/crypto-trading-bot/data/state/analyst_proposed_backlog_archive_20260902.json`
- Backup: `/home/brad/projects/crypto-trading-bot/data/state/analyst_proposed_backlog.bak_hygiene_20260902.json`

## Open / waiting queue (process these)

- **open** `ANALYST-20260627-024` — Backtest and quantify Polymarket regime influence on trade win rate and ROI (influence stack modeling)
  - Offline backtest allowed under analyst research policy; attach results to CR before promote.
- **open** `ANALYST-20260902-004` — Emit next ungated TEST_STRATEGY plan when capacity free (no live writes)
  - Emit next ungated TEST_STRATEGY plan when capacity free — capacity free now.
- **waiting_dependency** `ANALYST-20260721-STOCH-001` — Finish Stochastic RSI vs RSI comparison (gate before Kelly)
  - Stoch vs RSI — stoch-30d-reeval scheduled 2026-09-03; keep open until reeval lands.
- **waiting_dependency** `ANALYST-20260721-KELLY-001` — Fractional Kelly risk-budget test (post Stoch RSI comparison)
  - Queued behind Stoch RSI comparison / 30d reeval gate.
- **open** `ANALYST-20260902-003` — Refresh OPT pack + re-entry stress on current OHLCV (shadow only)
  - OPT pack refresh + re-entry stress — shadow/offline anytime.
- **open** `ANALYST-20260902-002` — Run trend-repair tier review on deposit-adjusted slope (observe-only)
  - Trend-repair observe-only review — can run anytime offline (no live writes).
- **waiting_regime_bear** `ANALYST-20260709-001` — Shadow trial: scenario 'bear_window_rotation_14d' from r2_defensive_sharpe_gate
  - Shadow/trial tied to bear_window scenario — wait for live bear (or historical-only backtest lane).

## Rules after hygiene
- New proposals still title-dedup against `dedupe_titles` + kept titles.
- `waiting_regime_bear` stays until live bear (offline hist backtest still allowed).
- `open` = can process offline anytime; attach results to CR before live promote.

