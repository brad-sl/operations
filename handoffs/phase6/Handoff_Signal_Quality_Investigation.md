# Handoff Document: Signal Quality Investigation

**Work Package**: 3  
**Priority**: Medium-High  
**Status**: Blocked → Ready (after this document)

## Objective
Investigate and quantify the quality of trading signals (especially after restoring the full sentiment system). Compare performance of sentiment-augmented signals vs baseline technical signals.

## Original Source Code (Phase 4/5)
- `phase5/` and Phase 4 backtesting scripts
- `dynamic_backtest.py`
- `phase6_backtest.py`
- Earlier Stochastic RSI vs Standard RSI comparison tests
- `sentiment_aggregator_v2.py` outputs and reports

## Scope & Boundaries

### Must Do
- Define clear signal quality metrics (win rate, Sharpe, max drawdown, profit factor, etc.)
- Run controlled backtests with and without the restored X + Reddit sentiment
- Identify which signals degrade or improve with sentiment overlay
- Document findings in a dedicated report under `reports/`
- Produce recommendations for Phase 6 signal pipeline

### Must Not Do
- Perform full live trading during investigation
- Change production signal generation code until investigation is complete

## Expected Deliverables
1. `reports/Signal_Quality_Investigation_Report.md`
2. Updated backtest scripts or notebooks under `phase6/backtests/`
3. Recommendations section for future signal weighting
4. Update to `PHASE6_RESTORATION_CHECKLIST.md`
5. Git commit referencing this Handoff Document

## Git Requirements
- All work on `phase-6.1` branch
- Explicit commit message linking to `Handoff_Signal_Quality_Investigation.md`

## Verification
- Report contains quantitative comparison (at least 3 metrics)
- Backtest results are reproducible
- Clear before/after sentiment impact numbers
- No data written to ephemeral scratch directories

## Notes
Previously blocked due to insufficient Handoff detail. Document now provides concrete scope and source references.