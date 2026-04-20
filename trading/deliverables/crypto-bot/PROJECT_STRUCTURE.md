# Crypto Trading Bot — Project Structure

**Location:** `/home/brad/.openclaw/workspace/operations/crypto-bot/`  
**Architecture:** Local-first, VPS-migration-ready  
**Status:** Ready for Phase 2 implementation

---

## Directory Layout

```
crypto-bot/
├── .env                        # Your credentials (git-ignored, create this)
├── .env.example               # Template (this is safe to commit)
├── .gitignore                 # Excludes .env, logs, db, __pycache__
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Deploy anywhere (ready for VPS)
├── docker-compose.yml         # Local dev setup
├── Makefile                   # Convenience commands
│
├── config/
│   ├── __init__.py
│   ├── settings.py            # Load .env & validate config
│   └── constants.py           # RSI levels, trading pairs, etc.
│
├── src/
│   ├── __init__.py
│   ├── main.py                # Entry point (CLI)
│   ├── indicators/
│   │   ├── __init__.py
│   │   └── rsi.py             # Stochastic RSI calculator
│   ├── sentiment/
│   │   ├── __init__.py
│   │   ├── x_api.py           # X/Twitter API wrapper
│   │   └── scorer.py          # Sentiment analysis
│   ├── exchange/
│   │   ├── __init__.py
│   │   ├── coinbase.py        # Coinbase Pro API wrapper
│   │   └── interface.py       # Abstract exchange interface (for multi-exchange)
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── signals.py         # Combine RSI + sentiment → buy/sell signal
│   │   ├── executor.py        # Execute trades (papertrader first)
│   │   └── backtester.py      # Simulate on historical data
│   └── portfolio/
│       ├── __init__.py
│       ├── models.py          # SQLAlchemy ORM (Trade, Portfolio)
│       ├── tracker.py         # P&L calculation, stats
│       └── db.py              # Database init & session management
│
├── tests/
│   ├── __init__.py
│   ├── test_indicators.py     # Unit: RSI calculation
│   ├── test_sentiment.py      # Unit: Sentiment scoring
│   ├── test_signals.py        # Unit: Signal generation
│   ├── test_exchange.py       # Integration: Coinbase mock
│   └── conftest.py            # Pytest fixtures & setup
│
├── logs/
│   └── .gitkeep               # Directory placeholder (ignored in git)
│
├── docs/
│   ├── ARCHITECTURE.md        # High-level design
│   ├── API_REFERENCE.md       # Function signatures
│   ├── DEPLOYMENT.md          # Local → VPS migration
│   └── TROUBLESHOOTING.md     # Common issues
│
└── README.md                  # Quick start guide
```

---

## Key Design Decisions

### 1. **Modular Architecture**
- Each component (RSI, sentiment, exchange) is independent
- Easy to test, swap, or replace
- Example: Replace Coinbase with Kraken = swap `exchange/coinbase.py`

### 2. **Environment-Agnostic**
```
Local (HP 8000)          VPS (Linode/AWS)
├── SQLite               └── PostgreSQL
├── .env in repo         └── .env in secrets manager
└── Python venv          └── Docker container
```
**Same code, different config.** Change `.env` or Docker image, redeploy.

### 3. **Testable at Every Layer**
```
Unit tests (fast, no API calls):
  ├── RSI calculation (mock prices)
  ├── Sentiment scoring (mock tweets)
  └── Signal generation (mock inputs)

Integration tests (real APIs, sandbox):
  ├── Coinbase sandbox trades
  └── X API rate limits

E2E tests (full flow):
  ├── Backtesting (historical data)
  └── Paper trading (live sentiment, fake money)
```

### 4. **Database Flexibility**
- ORM (SQLAlchemy) = swap database without code changes
- Local: `sqlite:///trading.db` (one file)
- VPS: `postgresql://user@db:5432/trading` (hosted DB)

---

## What Gets Built in Phase 2

| Module | Time | Complexity | Testable |
|--------|------|-----------|----------|
| RSI indicator | 1 hr | Low | ✅ Yes |
| X sentiment scorer | 2 hrs | Med | ✅ Yes (mock tweets) |
| Coinbase exchange wrapper | 2 hrs | Med | ✅ Yes (sandbox) |
| Signal generator | 1 hr | Low | ✅ Yes |
| Order executor | 2 hrs | High | ✅ Yes (papertrader first) |
| Portfolio tracker | 1.5 hrs | Med | ✅ Yes |
| **Total** | **~9.5 hrs** | | |

---

## Migration Path (When Ready)

### Day 1: Local to VPS (No Code Changes)
```bash
# Local (HP 8000)
python -m src.main --capital 1000

# VPS (e.g., Linode)
docker build -t trading-bot .
docker run --env-file .env trading-bot
```

### Day 2: SQLite → PostgreSQL (One Config Change)
```bash
# .env on VPS
DATABASE_URL=postgresql://user@postgres:5432/trading
# Redeploy. Same code.
```

### Day 3: Add Monitoring (New Containers)
```bash
# Same docker-compose, add services:
# - prometheus (metrics)
# - grafana (dashboard)
# - alertmanager (telegram notifications)
```

---

## Next Steps

✅ **Brad's Tasks (Phase 1):**
1. Get X Bearer Token
2. Get Coinbase Pro API credentials
3. Reply "Credentials ready"

✅ **My Tasks (Phase 2):**
1. Create config loader (`settings.py`)
2. Scaffold all modules
3. Implement RSI calculator
4. Implement sentiment scorer
5. Implement Coinbase wrapper
6. Implement signal generator
7. Implement executor (papertrader first)
8. Write unit tests

---

**Questions?** Ask before you start Phase 1. Otherwise, go grab those credentials! 👍
