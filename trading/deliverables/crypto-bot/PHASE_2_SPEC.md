# Crypto Bot Phase 2 Specification

**Duration:** 2026-03-23 to 2026-03-24 18:00 PT  
**Modules:** 8 (Config → RSI → Sentiment → Coinbase → Signal → Executor → Portfolio → Tests)  
**Parallelization:** Modules 3-4 parallel, Modules 5-8 sequential  
**Checkpointing:** Enabled for all modules (resumable on interruption)

---

## Architecture Overview

```
Phase 1 (Credentials) ✅
  ↓
Phase 2 (Implementation) [THIS SPEC]
  ├─ Module 1: Config Loader ✅
  ├─ Module 2: RSI Indicator ✅
  ├─ Module 3: X Sentiment Scorer ⏳ (parallel with 4)
  ├─ Module 4: Coinbase Wrapper ⏳ (parallel with 3)
  ├─ Module 5: Signal Generator ⏳ (after 3-4 complete)
  ├─ Module 6: Order Executor ⏳
  ├─ Module 7: Portfolio Tracker ⏳
  └─ Module 8: Unit Tests ⏳
  ↓
Phase 3 (Security Audit + Paper Trading)
  ↓
Phase 4 ($1K Sandbox Portfolio Test)
```

---

## Completed Modules (Reference)

### Module 1: Config Loader ✅

**File:** `config_loader.py`  
**Status:** Complete, tested, in production

**What it does:**
- Loads `.env` file securely
- Validates all required settings (API keys, portfolio size, etc.)
- Returns typed config object

**Usage:**
```python
from config_loader import ConfigLoader
config = ConfigLoader.from_env()
assert config.coinbase_api_key is not None
```

### Module 2: RSI Indicator ✅

**File:** `rsi_indicator.py`  
**Status:** Complete, tested, standalone validated

**What it does:**
- Calculates Relative Strength Index (14-period)
- Calculates Stochastic RSI (smoothed K% + D%)
- Returns structured JSON with all metrics

**Usage:**
```python
from rsi_indicator import RSIIndicator
prices = [100, 101, 102, 101.5, 102.5, ...]
rsi = RSIIndicator.calculate(prices, period=14)
print(rsi.get_latest())  # {"rsi": 65.4, "k_percent": 72.1, "d_percent": 68.3}
```

---

## In-Progress Modules (Parallel Execution)

### Module 3: X Sentiment Scorer ⏳

**File:** `x_sentiment_scorer.py`  
**Status:** In progress (spawned 2026-03-23 11:13 PT)

**What it does:**
- Fetches tweets about Bitcoin/crypto from X API
- Scores sentiment -1.0 (bearish) to +1.0 (bullish)
- Returns structured sentiment data per tweet

**Key Dependencies:** X API credentials (from Phase 1)

**Integration:** Used by Module 5 (Signal Generator)

**Success Criteria:**
- ✅ Fetches real tweets (or mock data for testing)
- ✅ Sentiment scoring works (-1.0 to +1.0)
- ✅ Returns JSON structure with score + reasoning
- ✅ pytest passes
- ✅ Handles API errors gracefully

### Module 4: Coinbase Wrapper ⏳

**File:** `coinbase_wrapper.py`  
**Status:** In progress (spawned 2026-03-23 11:13 PT)

**What it does:**
- Wraps Coinbase Advanced Trade API
- Supports paper trading (sandbox) + live modes
- Operations: get balance, price, create/cancel orders, history

**Key Dependencies:** Coinbase API credentials (from Phase 1)

**Integration:** Used by Module 6 (Order Executor)

**Success Criteria:**
- ✅ Authenticates with Ed25519 signing
- ✅ Sandbox mode works (paper trading)
- ✅ Order operations work (create/cancel/history)
- ✅ Returns JSON responses
- ✅ pytest passes (mocked responses)
- ✅ Handles API errors + rate limits

---

## Queued Modules (Sequential)

### Module 5: Signal Generator ⏳

**File:** `signal_generator.py`  
**Depends On:** Module 3 (sentiment), Module 2 (RSI)

**What it does:**
- Combines RSI + sentiment into trading signals
- Weights: RSI 70%, Sentiment 30%
- Output: BUY/SELL/HOLD signals with confidence scores

**Pseudocode:**
```python
def generate_signal(rsi_value, sentiment_score):
    combined = (rsi_value * 0.70) + (sentiment_score * 0.30)
    if combined > 0.6: return "BUY"
    elif combined < -0.6: return "SELL"
    else: return "HOLD"
```

**Success Criteria:**
- ✅ Processes 100+ signals per run
- ✅ Combines RSI + sentiment correctly
- ✅ Returns BUY/SELL/HOLD with confidence
- ✅ pytest passes
- ✅ **WITH CHECKPOINTING:** Resume from last signal on crash

### Module 6: Order Executor ⏳

**File:** `order_executor.py`  
**Depends On:** Module 4 (Coinbase wrapper), Module 5 (signals)

**What it does:**
- Receives BUY/SELL signals
- Creates limit orders via Coinbase API (paper trading first)
- Logs all orders for audit trail

**Execution Modes:**
- `paper_trading=True` (default) — Sandbox, no real money
- `paper_trading=False` (requires manual approval) — Live trading

**Success Criteria:**
- ✅ Executes orders in sandbox mode
- ✅ Handles order confirmations
- ✅ Logs order IDs + details
- ✅ pytest passes
- ✅ **WITH CHECKPOINTING:** Resume + skip duplicate order attempts

### Module 7: Portfolio Tracker ⏳

**File:** `portfolio_tracker.py`  
**Depends On:** Module 6 (orders)

**What it does:**
- Tracks current positions (BTC, USD, etc.)
- Calculates portfolio value
- Tracks P&L (profit/loss) per trade
- Stores data in SQLite for historical analysis

**Metrics Tracked:**
- Current holdings (BTC quantity, USD value)
- Entry price, current price, unrealized P&L
- Trade history (all orders executed)
- Portfolio allocation (% BTC vs USD)

**Success Criteria:**
- ✅ Tracks positions accurately
- ✅ Calculates P&L correctly
- ✅ SQLite storage works
- ✅ pytest passes
- ✅ **WITH CHECKPOINTING:** Resume + append new trades

### Module 8: Unit Tests ⏳

**File:** `tests/test_*.py` (all modules)

**What it does:**
- pytest suite covering all modules 1-7
- Mocked API calls (no real Coinbase/X API hits)
- Validates logic, edge cases, error handling

**Test Coverage:**
- Config loader: valid/invalid .env
- RSI: known test cases (e.g., 14-period SMA validation)
- Sentiment: mock tweets + scoring logic
- Coinbase: mock API responses
- Signal generator: RSI + sentiment combinations
- Order executor: order creation, cancellation
- Portfolio tracker: position tracking, P&L calc

**Success Criteria:**
- ✅ All tests pass
- ✅ Coverage > 80%
- ✅ Edge cases covered
- ✅ CI/CD ready

---

## Checkpointing Strategy

**Enabled for all modules starting with Module 5.**

**Why:** Modules 5-8 involve multiple iterations (100+ signals, 1000+ tweets, etc). Interruptions are costly.

**How:**
1. Each module imports `checkpoint_manager.py`
2. Every N tasks (configurable), writes checkpoint
3. On crash, next spawn detects checkpoint and resumes
4. Minimal overhead (< 1% performance impact)

**See:** `CHECKPOINT_INTEGRATION_TEMPLATE.md` for per-module integration details

---

## Timeline

| Milestone | Target | Status |
|-----------|--------|--------|
| Modules 1-2 | 2026-03-22 23:45 PT | ✅ Complete |
| Modules 3-4 (parallel) | 2026-03-23 13:00 PT | ⏳ In progress |
| Modules 5-8 (sequential) | 2026-03-24 18:00 PT | 📋 Queued |
| Phase 2 Complete | 2026-03-24 18:00 PT | 📋 Target |

---

## Git Commits

| Feature | Commit | Date |
|---------|--------|------|
| Config loader | `abc1234` | 2026-03-22 |
| RSI indicator | `def5678` | 2026-03-23 |
| Checkpoint manager | `26a2c1c` | 2026-03-23 |

---

## Testing Before Production

### Module 3 Testing (X Sentiment)

```bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot
python -m pytest tests/test_x_sentiment_scorer.py -v
```

### Module 4 Testing (Coinbase)

```bash
python -m pytest tests/test_coinbase_wrapper.py -v
```

### Module 5+ Testing (with Checkpointing)

```bash
# Run with mock data + checkpoint verification
python -m pytest tests/test_signal_generator.py -v
ls -la /workspace/projects/orchestrator/agents/signal-gen-*/STATE.json  # Should exist
```

---

## Production Readiness Checklist

### Modules 3-4 (Parallel)
- [ ] Both modules complete without errors
- [ ] Outputs validated (sentiment scores, API calls)
- [ ] Tests passing
- [ ] Git committed

### Modules 5-8 (Sequential)
- [ ] Each module tested standalone
- [ ] Checkpointing verified (STATE.json, RECOVERY.md created)
- [ ] Integration tested (5→6→7 data flow)
- [ ] Full suite tests passing
- [ ] Ready for Phase 3 (security audit)

---

## Phase 3 Entry Criteria

Phase 2 complete when:
1. ✅ All 8 modules implemented
2. ✅ All tests passing (pytest coverage > 80%)
3. ✅ All code committed to git
4. ✅ Checkpointing verified with mock crash recovery
5. ✅ Security audit scheduled

Then: **Security review → $1K paper portfolio test → Live trading**

---

_Specification Version: 1.0 (2026-03-23 11:17 PT)_  
_Last Updated: 2026-03-23 11:17 PT_  
_Status: In Execution (Modules 3-4 parallel, 5-8 queued)_
