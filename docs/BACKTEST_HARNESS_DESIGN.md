# Backtest Harness Design – Volatile Pair Expansion Comparison

**Status:** Design Phase  
**Date:** 2026-06-05  
**Owner:** Brad  
**Related Documents:**  
- `PAIR_SELECTION_MATRIX.md`  
- `PHASE_6_REBALANCING.md`

---

## 1. Purpose

Create a reproducible backtesting framework to compare two trading strategies:

- **Baseline**: Current Phase 6 implementation (fixed 5-pair universe, no pair expansion).
- **Expanded**: Phase 6 + Volatile Pair Expansion using the `PAIR_SELECTION_MATRIX`.

The goal is to quantify whether the added complexity of proactive pair discovery and a larger candidate universe delivers a meaningful, persistent improvement in risk-adjusted returns.

**Guiding Principle**: Complication = Fragility. Only accept added complexity if backtests demonstrate clear value.

---

## 2. High-Level Requirements

- Use **daily** price data for the initial harness.
- Support **real historical data** when available; allow **synthetic sentiment** for controlled early runs.
- Build a **more complete** harness (not minimal).
- Focus on **console + markdown reports** only (no dashboard at this stage).
- Design must be recoverable — hence this document.

---

## 3. Architecture Overview

```
Historical Data Loader
        ↓
Sentiment Provider (real or synthetic)
        ↓
Backtest Engine
    ├── Baseline Mode (FIXED_UNIVERSE only)
    ├── Expanded Mode (PAIR_SELECTION_MATRIX + scoring)
    └── Position & Capital Tracker
        ↓
Metrics Collector
        ↓
Comparison Report Generator
```

---

## 4. Core Components

### 4.1 Historical Data Loader
- Daily OHLCV for all pairs in both universes.
- Source: Coinbase historical data (preferred) or cached CSV/Parquet.
- Must support at least 12–18 months of data for meaningful comparison.

### 4.2 Sentiment Provider
- **Real mode**: Replay from `unified_sentiment_cache.json` (time-decayed).
- **Synthetic mode**: Controllable sentiment signals for early validation.
- Must support both long and short sentiment values.

### 4.3 Backtest Engine
- Event-driven daily loop.
- Supports two modes via configuration flag (`enable_pair_expansion`).
- Handles:
  - Rebalancing decisions
  - Capital deployment via `deploy_capital()` logic
  - Pair addition/removal using the selection matrix
  - Position tracking and P&L

### 4.4 Pair Selection Module (Expanded Mode Only)
- Implements the full `PAIR_SELECTION_MATRIX`:
  - Pre-filters
  - Composite scoring
  - Diversification constraints
  - Final selection rules

### 4.5 Metrics Collector
Collects per-run and comparative metrics:

| Category              | Metrics |
|-----------------------|---------|
| **Returns**           | Annualized return, Total return |
| **Risk**              | Max drawdown, Sharpe ratio, Sortino |
| **Activity**          | Number of rebalances, Turnover %, Avg pairs held |
| **Expansion Specific**| New pairs added, Success rate of expansions, Avg holding period of new pairs |

### 4.6 Comparison Report Generator
- Side-by-side table (Baseline vs Expanded)
- Key deltas highlighted
- Summary narrative (e.g., "Expanded mode improved Sharpe by X but increased turnover by Y")

---

## 5. Comparison Modes

| Mode       | Universe Size | Pair Discovery | Rebalance Cap Scope | Notes |
|------------|---------------|----------------|---------------------|-------|
| **Baseline** | 5 pairs      | None           | Narrow (USD only)   | Current production behavior |
| **Expanded** | 10–20 pairs  | Full matrix    | Configurable        | Includes composite scoring + constraints |

---

## 6. Data & Configuration

- **Primary data frequency**: Daily
- **Sentiment**: Real data preferred; synthetic allowed for first runs
- **Config-driven**:
  - `candidate_universe` list
  - `enable_pair_expansion`
  - Rebalance cap behavior (narrow vs broad)
  - Segment diversity limits

---

## 7. Implementation Phases

### Phase 1 – Foundation (Daily Data)
- Historical daily data loader
- Basic BacktestEngine with Baseline mode
- Metrics collection + simple report

### Phase 2 – Expansion Logic
- Implement Pair Selection Module from `PAIR_SELECTION_MATRIX.md`
- Add Expanded mode
- Composite scoring + constraints

### Phase 3 – Comparison & Reporting
- Side-by-side metrics
- Synthetic sentiment support
- Markdown report generation

### Phase 4 – Validation & Extension (Future)
- Real sentiment replay
- 15-minute data support (if daily results look promising)
- Parameter sweep capability

---

## 8. Non-Goals (for now)

- No live trading integration
- No dashboard
- No multi-regime automated parameter optimization
- No short-side execution simulation (long/short matrix logic only)

---

## 9. Success Criteria

A successful harness will allow us to answer:

1. Does the Expanded mode improve risk-adjusted returns enough to justify the added complexity?
2. What is the impact on turnover and number of pairs held?
3. How sensitive are results to the correlation threshold and volatility weighting?
4. Does the expansion logic add pairs that actually perform well out-of-sample?

---

## 10. Open Decisions

- Exact list of 10–20 candidate pairs to use in Expanded mode.
- Whether to start with synthetic or real sentiment in Phase 1.
- How strictly to enforce the “max 1 new pair per rebalance” rule during backtesting.

---

*This document is the single source of truth for the backtest harness design. Any implementation should reference this document to avoid drift.*