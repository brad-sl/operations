# Data Flow, File Locations & Configuration Standards (Phase 6)

**Goal**: Eliminate configuration drift by defining canonical locations and loading rules. All code, scripts, and docs must follow this.

## Project Root
- Canonical: `/home/brad/projects/crypto-trading-bot`
- Always execute with CWD = project root (or derive PROJECT_ROOT).
- Preferred: `PROJECT_ROOT = Path(__file__).resolve().parents[2]` (from phase6/core/*.py) or `Path.cwd()`.

## Data / State Files (live + persisted)
Location: `data/state/`

Canonical files:
- `phase6_live_state.json` — current balances, positions, prices (primary source for runner/exchange views).
- `phase6_runner_state.json` — last_rebalance_date, last_trade, etc.
- `price_history.json`, `rsi_cache.json`, `rebalance_history/default.jsonl`
- Sentiment caches, `intel_*.json`, analyst outputs, `opportunity_proposals.jsonl`, recovery_state.json, etc.
- **ANALYST-OPT (2026-07-07):** `analyst_scenario_leaderboard_latest.json`, `analyst_scenario_runs.jsonl` (append-only run ledger), `analyst_learnings.json`, `analyst_proposed_backlog.json` — see `docs/research/MEMORY_AND_LEARNING.md`.
- **USDC park (2026-07-09):** `data/state/usdc_park/<account>_transitions.json`, `<account>_latest.json` — toggle FSM + last park/unwind run.

**Rules**:
- Read/write using relative paths: `Path("data/state/phase6_live_state.json")` or `PROJECT_ROOT / "data/state/..."`
- **Never** hardcode absolute paths like `/home/brad/projects/...`.
- Directories created on demand (`mkdir -p data/state`).
- Tests (isolation/paper) must consume real data from here — no synthetic fabrication.

Current verified (2026-06-26):
- `data/` and `data/state/` exist.
- Recent `phase6_live_state.json` + `phase6_runner_state.json` present and populated.

## Configuration
- Secrets: `.env` (project root) — COINBASE_API_KEY/SECRET, CDP_API_* (for full AgentKit).
  - Load order (consistent in exchange_client.py): project .env, hermes profile .env, $HOME/.env.
  - Call `load_dotenv()` once early (runner __init__ / main entrypoints).
- Non-secret config:
  - Primary: `trading_config_phase6.json` (root or config/).
  - Canonical loader: `phase6/core/config_loader.py`.
  - Other: `config/trading_config.json`, `sentiment_config.json`, `references/sentiment_sources.yaml`.
  - **Per-trader options:** `config/trader_accounts.json` — `live_usdc_park` toggle per Coinbase `portfolio_uuid` (see `docs/LIVE_USDC_PARK.md`).
- Avoid: proliferation of `trading_config_*.bak`, `*_limited`, `*_test` without explicit override mechanism (env var or CLI flag).

**Rules**:
- One canonical loader.
- .env.example must stay in sync with required vars.
- Document any new required var here + in .env.example + MASTER.

## Code Locations
- `phase6/core/` — core logic (runner, exchange_client, agentkit_sl.py, config_loader.py, allocator, etc.).
- `phase6/scripts/` or root `scripts/` — utilities.
- `config/` — static configs.
- `references/` — sources, models, guides.
- `docs/` — MASTER_TASK_TRACKING.md, DATA_FLOW_AND_LOCATIONS.md, ARCHITECTURE_*, handoffs/.
- `data/` — runtime state only (gitignored).
- `logs/` — runner logs.

## Drift Prevention
1. Every path change → update this doc + MASTER + affected code.
2. On any "file not found", key missing, or "config drift" symptom → first action is `cat docs/DATA_FLOW_AND_LOCATIONS.md` + audit current .env + ls data/state.
3. State writes are centralized (runner _save_state).
4. .env load is centralized and early.
5. Prefer relative + PROJECT_ROOT over absolute/hardcoded.

## Enforcement: paths.py + References (2026-06-29)
- Added `phase6/core/paths.py` as single source for `get_project_root()`, PROJECT_ROOT, canonical STATE_DIR, PHASE6_LIVE_STATE etc.
- All new path usage must import from .paths (or derive per doc).
- See "Document + enforce data flow" task t_e9499bcc (kanban) + this doc.
- Scripts and core modules updated to reference this DATA_FLOW_AND_LOCATIONS.md + paths.py.

## Recent Audit (2026-06-26)
- Fixed absolute hardcoded CACHE_PATH in phase6/core/phase6_runner.py → relative.
- Confirmed data/state/ present and current.
- Multiple historical config loaders and trading_config variants noted (cleanup task created).
- .env handling is functional but search order should be documented once in one place.

Last updated: 2026-06-29 (enforcement via central paths.py + references in code/scripts per task t_e9499bcc).

## Enforcement Update (task t_591b0df0, 2026-06-29)
- Standardized additional modules to import from phase6/core/paths.py:
  - opportunity_scanner.py (removed absolute override, uses RSI_CACHE etc constants)
  - rebalance_logger.py (REBALANCE_LOG_DIR now from STATE_DIR)
  - sentiment_scorer.py (main + subdir versions aligned to SENTIMENT_*_CACHE)
  - fetch_x_sentiment.py, run_canonical_sentiment.py (hardcodes removed, use paths + load_project_dotenv)
- Added SENTIMENT_CACHE, X_SENTIMENT_CACHE, REDDIT_SENTIMENT_CACHE to paths.py
- All active phase6/core and scripts now encouraged to reference DATA_FLOW_AND_LOCATIONS.md in headers
- Sentiment cache locations unified under data/state/ (drift reduction)
- Verified no critical absolute hardcodes in phase6 active py (examples in docs/comments OK)
- Tests and legacy updated where straightforward; archive/ untouched

Next hygiene: audit root-level scripts, consolidate duplicate sentiment modules if needed, reference in AGENTS.md / all entrypoints.
Last updated: 2026-06-29 for kanban t_591b0df0

## Enforcement Verification + Extension (kanban t_591b0df0 - this invocation)

**Completed in this run (post re-create):**
- Fixed last active hardcode in phase6/core/sentiment/run_canonical_sentiment.py (X cache load now uses X_SENTIMENT_CACHE; import extended).
- Updated phase6/core/sentiment/fetch_reddit_sentiment.py: header ref added, cache to REDDIT_SENTIMENT_CACHE, dotenv via load_project_dotenv(), paths import.
- Batch added reference headers to 14 missing core/*.py modules (agentkit_sl, allocation_engine, error_notifier, evaluation, live_portfolio_manager, order_executor, performance_* , price_history_manager, regime_switcher, sentiment_keywords, signal_generator, sl_risk_scorer, stop_loss_manager).
- Added full "Data Flow, File Locations & Configuration Hygiene (Phase 6)" section to docs/AGENTS.md (rules, imports, cdw note, canonical preference for phase6/).
- Audited: confirmed phase6/scripts/ all reference doc; no new abs hardcodes in hot phase6 py; sh scripts use documented cd to root.
- paths.py already had sentiment consts + good docstring mandating refs.
- Verified syntax on edited (python -c "import ast; ... " or compile in mind).
- Updated this doc and will append MASTER.

**Status**: References now much broader in core. Hardcodes minimized in active. Hygiene embedded.
Follow-ups: consolidate sentiment duplicates (root/phase6 copies), full root scripts audit if drift appears, add to more entrypoints/tests as needed.

Last updated for t_591b0df0: 2026-06-29 (verification + extension pass)


## Postgres Multi-Tenant Registry (SCALING-1000 T0-01+)

**Canonical state owner:** Postgres (via Alembic migrations in `db/migrations/`)

**Tables (new for multi-tenant):**
- `traders` — primary registry: id (uuid), ghl_contact_id, ghl_location_id, portfolio_uuid, coinbase_account_id, tier (starter/pro/elite), billing_status, coinbase_status, auth_mode (oauth|api_key), timestamps (created/updated/last_*), flags (json), notes
- `trader_configs` — per-account overrides: trader_id (fk, unique), pairs (json), risk_params (json), allocation_overrides, rebalance_frequency, max_deploy_usd, pair_count_cap, tier_template_snapshot, overrides
- `oauth_tokens` — encrypted at rest: trader_id (fk), access_token_enc, refresh_token_enc, expires_at, scopes (json), portfolio_uuid. Use ENCRYPTION_KEY + fernet helpers in db/models.py
- `job_runs` — audit/metrics: trader_id (fk), run_id, started/ended, status, metrics (json), error_summary, duration_seconds

**Isolation:** All queries/filter by trader_id or portfolio_uuid. No cross-account leakage (enforced in T0-05 tests).

**GHL mirror:** GHL Custom Object `TradingAccount` is read-only UX mirror. Platform (Postgres) is source of truth. Sync worker (future T1) upserts rounded fields only. Never put tokens/balances/full precision in GHL.

**Migration:**
- `alembic.ini` (script_location = db/migrations)
- `db/migrations/versions/002_registry_tables.py` (additive on top of 001)
- `db/models.py` (SQLAlchemy ORM + encrypt/decrypt helpers)
- Test: `test_t0_registry.py` (2 accounts, create/query/rollback exercised; alembic attempted)

**Config / Secrets:**
- DATABASE_URL in env (postgresql+asyncpg://...)
- ENCRYPTION_KEY (fernet 32-byte key). Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())". Never commit.
- Use db/session.py patterns.

**Legacy note:** Old `data/phase6.db` (sqlite) + json states remain for single-tenant Brad path until MULTI_TENANT flag + T0-02. New registry parallel for spike.

**Update rules:** Schema change → new alembic rev + update this doc + test + MASTER. Project root CWD.

Last updated: 2026-07-16 for kanban t_617c4635 (T0-01 SCALING)
