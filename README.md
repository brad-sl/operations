# Crypto Trading Bot (Phases 4-6)

Clean, maintainable home for the full crypto trading system developed across Phases 4, 5, and 6.

**Current Status**: LIVE (minimal runner) — Phase 6 production runner in active development.

---

## Directory Structure

```
crypto-trading-bot/
├── README.md
├── src/
│   ├── core/              # Portfolio manager, risk engine, order executor, etc.
│   ├── analyzers/         # Multi-pair, sentiment, correlation
│   ├── strategies/        # Dynamic RSI, sentiment-driven logic
│   └── utils/
├── config/                # trading_config_phase6.json + others
├── scripts/
│   ├── phase4/
│   ├── phase5/
│   └── phase6/            # phase6_runner.py (primary live runner)
├── backtests/             # Historical OHLCV data + backtest scripts
├── docs/                  # All markdown documentation & specs
├── data/                  # Live state, logs, DBs (mostly gitignored)
└── tests/
```

---

## Key Files

- **Primary runner**: `scripts/phase6/phase6_runner.py`
- **Single source of truth**: `docs/PHASE6.md`
- **Config**: `config/trading_config_phase6.json`

---

## Getting Started

```bash
cd /home/brad/projects/crypto-trading-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run in shadow mode first:
```bash
python scripts/phase6/phase6_runner.py --config config/trading_config_phase6.json --mode shadow
```

---

## GitHub

Repository: `brad-sl/operations`

---

*This project was migrated and cleaned up on 2026-05-14 from the original scattered locations inside .openclaw/workspace.*