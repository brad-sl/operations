# Crypto Trading Bot — Phase 6

Active, production-oriented crypto trading system. All legacy Phase 5 and earlier logic has been archived. The canonical implementation lives in `phase6/`.

**Current Status**: Phase 6 runner is live (shadow + selective live). Daily rebalance anchored around 21:00 PT.

## Canonical Structure (Post-Cleanup)

```
crypto-trading-bot/
├── phase6/                    # Active core (phase6/core/*.py, runner)
│   ├── core/
│   │   ├── phase6_runner.py
│   │   ├── exchange_client.py
│   │   ├── order_executor.py
│   │   ├── stop_loss_manager.py
│   │   ├── trade_ledger.py
│   │   ├── performance_calculator.py
│   │   └── ...
│   └── tests/
├── scripts/phase6/            # Runners, monitors, smoke, diagnostics
│   ├── phase6_runner.py (entry)
│   ├── monitor_phase6_runner.py
│   └── ...
├── config/
│   └── trading_config_phase6.json   # Primary live config
├── docs/
│   └── MASTER_TASK_TRACKING.md      # Single source of truth for tasks
├── archive/
│   └── legacy-phase4-and-earlier/   # Archived old phases (git-tracked or ignored)
├── backtests/
├── data/                        # Runtime state (gitignored)
├── logs/                        # (gitignored)
├── requirements.txt
├── .gitignore
└── README.md
```

## Solid Git Regimen

This repo follows these practices for portability and cleanliness:

- Comprehensive `.gitignore` (venvs, logs, secrets, data/, pycache, archive optional).
- `.gitattributes` for consistent LF line endings.
- Only active Phase 6 code + essential support (coinbase wrappers that are current, configs) are tracked.
- Legacy code is in `archive/`.
- `docs/MASTER_TASK_TRACKING.md` is the durable task record.
- **`docs/GIT_REPO_DAILY_MANAGEMENT.md`** — daily Hermes cron, mirror sync, agent git rules.
- **`hermes/git-workflows/AGENT_GIT_WORKFLOWS.md`** — branch/commit/handoff standard.
- Hermes skill **`git-repo-management`** — load for any git sync or tracking work.
- Never commit `.env`, `*.pem`, auth files, or live state.

**Daily automation:** Hermes job `daily-git-hermes-management` at `30 4 * * *` runs `scripts/hermes/git-daily-management.sh` (health + `hermes/` mirror). Verify with `hermes cron list`.

### Typical Workflow
```bash
git status
git add -A
git commit -m "chore: archive legacy + improve git hygiene for portability"
git push
```

## Moving to a New Machine (Minimal Effort)

### 1. Clone the code
```bash
git clone <your-repo-url> crypto-trading-bot
cd crypto-trading-bot
```

### 2. Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration
- Copy and edit: `cp config/trading_config_phase6.json config/my_config.json`
- Update keys, basket, risk params, etc.
- **Secrets** (never in git):
  - Coinbase API keys / private key (`cb_key.pem`)
  - Any `.env` files

### 4. Hermes Agent Environment (the full AI collaborator)

Hermes is the agent running this setup. To replicate the full environment:

```bash
# On new machine
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup   # or hermes doctor
```

Export your active profiles from the old machine:
```bash
hermes profile list
hermes profile export crypto-orchestrator --output crypto-orchestrator.tar.gz
hermes profile export crypto-engineer --output crypto-engineer.tar.gz
# Also default if customized
```

Transfer the `.tar.gz` files + this repo securely.

On new machine:
```bash
hermes profile import crypto-orchestrator.tar.gz
hermes profile import crypto-engineer.tar.gz
hermes profile use crypto-orchestrator   # or your preferred
```

Restore credentials:
- Use `hermes auth add ...` for providers
- Or manually place sanitized `.env` / keys (use `hermes config env-path`)

Key Hermes paths that travel with profiles:
- `~/.hermes/config.yaml`
- Skills (re-install via `hermes skills install` or copy `~/.hermes/skills/`)
- Cron jobs (re-create with `hermes cron`)

### 5. Verify
```bash
python scripts/phase6/phase6_runner.py --config config/trading_config_phase6.json --mode shadow --help
# Then run smoke or monitor
```

## Key Active Components

- **Runner**: `scripts/phase6/phase6_runner.py` or `phase6/core/phase6_runner.py`
- **Config**: `config/trading_config_phase6.json`
- **Ledger / P&L**: `phase6/core/trade_ledger.py` + `performance_calculator.py`
- **SL & Execution**: `phase6/core/order_executor.py`, `stop_loss_manager.py`
- **Dashboard / State**: `serve_dashboard.py` + phase6_dashboard.html (or equivalent)

## Notes on Secrets & Portability

- All sensitive files are gitignored.
- On new machine, re-authenticate via Hermes or copy keys manually (use secure transfer).
- Trading uses **real data only** — no placeholders in production paths.
- For full cron + gateway: use `hermes cron list` on old machine and recreate on new, or use profile export which includes some state.

This setup is designed so `git clone` + Hermes profile import + minimal secret restore gets you back to a working state quickly.

---

*Legacy Phase 4/5 and earlier artifacts archived June 2026. Phase 6 is the single source of truth.*
