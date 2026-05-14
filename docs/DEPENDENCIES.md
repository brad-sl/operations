# Module Dependencies & Integration Map

## Active Production Graph

```
MAIN RUNTIME
└── phase5_multi_pair.py (ENTRY POINT)
    ├── price_wrapper.py
    │   └── Coinbase Public API (get_price, get_historical)
    │
    ├── sentiment_aggregator_v2.py (runs async every 30 min)
    │   ├── fetch_x_sentiment.py
    │   │   └── X API (real trader sentiment)
    │   └── Reddit API (fallback, r/cryptocurrency)
    │
    ├── checkpoint_manager.py
    │   └── position_state.json (atomic writes)
    │
    ├── coinbase_wrapper.py
    │   └── Coinbase Advanced Trade API (ES256 JWT auth)
    │
    └── prometheus_client (optional metrics)
        └── Prometheus scraper
```

## File Status

### Active (8 files)
- `phase5_multi_pair.py` — ✅ Main runtime
- `price_wrapper.py` — ✅ Price fetching
- `sentiment_aggregator_v2.py` — ✅ Sentiment (30-min cron)
- `fetch_x_sentiment.py` — ✅ X API batch queries
- `checkpoint_manager.py` — ✅ State persistence
- `coinbase_wrapper.py` — ✅ Coinbase API abstraction
- `config_loader.py` — ✅ Config management
- `position_state_manager.py` — ✅ Position tracking

### Orphaned But Production-Ready (2 files)
- `order_executor.py` — ⚠️ **READY TO INTEGRATE** (Phase 6)
  - Full order placement pipeline
  - BUY/SELL logic
  - Spend tracking + budget enforcement
  - Transaction cost tracking
  - NOT currently wired into phase5_multi_pair.py

- `portfolio_tracker.py` — ⚠️ **STATUS UNKNOWN**
  - Expected handoff from order_executor.py
  - Needs inspection before Phase 6 integration

### Archived/Experimental (26 files)
- `archived/apify_*.py` — Reddit scraper R&D
- `archived/sentiment_*.py` — Sentiment engine experiments (v1, decay, etc.)
- `archived/correlation_*.py` — Correlation analysis
- `archived/bot_monitor.py` — Old monitoring (use SMART Health Monitor)
- `archived/dashboard.py` — Legacy dashboard
- `archived/bootstrap_*.py` — Bootstrap utilities
- `archived/debug_*.py` — Diagnostic tools

### Deleted (60 files)
- All phase3_*, phase4_*, phase4b_* variants
- All backtest_* files (replaced with real-data versions)
- Legacy backtests + experimental code

---

## Integration Roadmap (Phase 6)

```
Current Flow (Phase 5):
price_wrapper → RSI signal → position_state.json → [DONE - no execution]

Phase 6 Flow (Target):
price_wrapper → RSI signal → order_executor → portfolio_tracker → [LIVE TRADING]
                    ↓
            sentiment_aggregator (confidence boost)
```

**Phase 6 Tasks:**
1. Inspect `order_executor.py` — Confirm integration API
2. Inspect `portfolio_tracker.py` — Verify completeness
3. Wire `order_executor.into phase5_multi_pair.py` execution flow
4. Add portfolio_tracker handoff after order fills
5. Integration test with sandbox capital

---

## External Dependencies

### APIs
- **Coinbase Public API** — Price data (unauthenticated)
- **Coinbase Advanced Trade API** — Orders (ES256 JWT auth)
- **X API** — Sentiment (authenticated, batch-optimized)
- **Reddit API** — Sentiment fallback (via praw)

### Libraries
- `numpy` — Numerical calculations (RSI, ATR)
- `pandas` — Data manipulation
- `requests` — HTTP client
- `python-dotenv` — Credential management
- `prometheus-client` — Metrics (optional)

---

## No Circular Dependencies

Each module has single responsibility:
- `phase5_multi_pair.py` — Orchestration only
- `price_wrapper.py` — Data fetching only
- `sentiment_aggregator_v2.py` — Sentiment only
- `coinbase_wrapper.py` — API abstraction only
- `order_executor.py` — Order execution only (ready to integrate)

Safe to test, mock, or swap individual modules.

---

## Cleanup Summary

| Action | Files | Result |
|--------|-------|--------|
| Deleted | 60 | 8 active + 2 ready + 26 archived |
| Archived | 26 | Cleans root, preserves history |
| Active | 8 | Production runtime |
| Ready | 2 | Phase 6 integration targets |

**Root directory:** Now has only relevant .py files + archived/ subdirectory.
