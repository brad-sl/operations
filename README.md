# Operations Repository — Crypto Trading Bot (Phase 6)

Active, production-oriented crypto trading system. Legacy Phase 5 and earlier logic is archived. **Canonical trading code** lives in `phase6/` with the **ARCH-4 platform boundary** in `trading/`.

**Git remote:** `https://github.com/brad-sl/operations.git` — branch **`phase-6.1`**.

**Current status:** Phase 6 runner is live (shadow + selective live). Rebalance windows **09:00 and 21:00 PT** (see `config/trading_config_phase6.json`).

## Canonical structure

```
crypto-trading-bot/          # local clone name (repo: operations)
├── phase6/
│   ├── core/
│   │   ├── phase6_runner.py      # Main orchestrator (ARCH-4 wiring)
│   │   ├── exchange_client.py
│   │   ├── order_executor.py     # Legacy execution fallback
│   │   ├── allocation/           # New allocator (ARCH-4)
│   │   └── ...
│   ├── scripts/                  # Phase6-adjacent runners, reports
│   └── tests/                    # test_isolation_*.py
├── trading/                      # Platform TradeExecutor + factory (P4-04)
├── scripts/
│   ├── phase6/                   # Monitors, harnesses, start scripts
│   │   └── start_phase6_runner.sh
│   ├── phase6_runner.py          # Legacy standalone runner (older imports)
│   └── hermes/                   # Git mirror sync, daily management
├── hermes/                       # Git-tracked sanitized ~/.hermes mirror
├── hermes-state/                 # Phase 1 baseline + verify_baseline.py
├── hermes/git-workflows/         # Agent git standards
├── config/
│   └── trading_config_phase6.json
├── docs/
│   ├── MASTER_TASK_TRACKING.md
│   ├── GIT_REPO_DAILY_MANAGEMENT.md
│   └── phase6/                   # Architecture, specs
├── archive/
├── data/                         # Runtime state (gitignored)
├── logs/                         # (gitignored)
└── requirements.txt
```

## Solid git regimen

- `.gitignore` — venvs, logs, secrets, `data/state/`, pycache; **do not** `git add -A` blindly.
- **Branch:** `phase-6.1` tracks `origin/phase-6.1`.
- **Auth:** GitHub CLI (`gh auth login`) + HTTPS credential helper.
- `docs/MASTER_TASK_TRACKING.md` — durable task record.
- `docs/GIT_REPO_DAILY_MANAGEMENT.md` — daily cron, Hermes mirror, agent rules.
- `hermes/git-workflows/AGENT_GIT_WORKFLOWS.md` — branch/commit/handoff standard.
- Hermes skill **`git-repo-management`** for sync/tracking work.

**Daily automation:** Hermes job `daily-git-hermes-management` at `30 4 * * *` → `scripts/hermes/git-daily-management.sh`. Verify: `hermes cron list`.

### Typical workflow

```bash
git checkout phase-6.1 && git pull origin phase-6.1
git checkout -b feat/<task-id>-<short-desc>
# ... change + isolation tests ...
git add <paths>    # intentional paths only
git commit -m "feat(phase6): ..."
git push -u origin feat/<task-id>-<short-desc>
# merge to phase-6.1 via PR or local merge, then:
git push origin phase-6.1
```

## Moving to a new machine

### 1. Clone

```bash
git clone https://github.com/brad-sl/operations.git crypto-trading-bot
cd crypto-trading-bot
git checkout phase-6.1
```

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

- Primary config: `config/trading_config_phase6.json`
- Copy/edit for experiments: `config/my_config.json`
- **Secrets (never in git):** `.env`, `cb_key.pem`, API keys

### 4. Hermes agent environment

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup
```

Export/import profiles (`crypto-orchestrator`, `crypto-engineer`, etc.) and restore provider auth via `hermes auth` / `.env`.

Restore Hermes state from git mirror when needed:

```bash
./scripts/hermes/restore-hermes.sh   # see script header
```

Re-create crons from `hermes cron list` on the old host or use `docs/GIT_REPO_DAILY_MANAGEMENT.md`.

### 5. Verify runner

```bash
cd /path/to/crypto-trading-bot
PYTHONPATH=. python3 -m phase6.core.phase6_runner --help
# Shadow smoke (config-dependent):
# PYTHONPATH=. python3 -m phase6.core.phase6_runner --mode shadow --config config/trading_config_phase6.json
```

Production start (singleton checks):

```bash
./scripts/phase6/start_phase6_runner.sh
```

## Key active components

| Role | Location |
|------|----------|
| **Runner (canonical)** | `python3 -m phase6.core.phase6_runner` |
| **Start script** | `scripts/phase6/start_phase6_runner.sh` |
| **Config** | `config/trading_config_phase6.json` |
| **ARCH-4 execution** | `trading/executor.py` (`TradeExecutor`) when `use_platform_executor` |
| **Legacy execution** | `phase6/core/order_executor.py` |
| **Ledger / P&L** | `trade_ledger.py`, `performance_calculator.py` |
| **Monitor** | `scripts/phase6/monitor_phase6_runner.py` |
| **Dashboard** | `serve_dashboard.py`, `phase6_dashboard.html` |

## Notes

- Production paths use **real data only** — no placeholders for prices, positions, or fills.
- Sensitive files stay gitignored; use secure transfer for keys on migration.
- `scripts/phase6_runner.py` at repo root is an **older entry** with different import paths; prefer **`phase6.core.phase6_runner`** for current ARCH-4 behavior.

---

*Legacy Phase 4/5 artifacts archived June 2026. Phase 6 is the single source of truth for trading.*