"""
Central path definitions and project root derivation for Phase 6.

See docs/DATA_FLOW_AND_LOCATIONS.md for full rules, canonical locations,
loading conventions, and drift-prevention policy.

All code must:
- Derive PROJECT_ROOT using get_project_root() (or equivalent relative to __file__).
- Use relative paths like Path("data/state/...") when CWD==project root, or PROJECT_ROOT / ...
- NEVER hardcode absolute paths like "/home/brad/projects/crypto-trading-bot/..."
- Create dirs on demand as needed.
- Reference this module + DATA_FLOW_AND_LOCATIONS.md in headers/docstrings.
- Import constants (PHASE6_*, *_CACHE, SENTIMENT_*) from here for state files.

For modules in phase6/core/*.py or phase6/*/ :
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
"""

from pathlib import Path
from typing import List
import os
import json
from dotenv import load_dotenv


def get_project_root() -> Path:
    """Return canonical project root.

    Per DATA_FLOW_AND_LOCATIONS.md:
    - Execute with CWD = project root when possible.
    - Derive as parents[2] from phase6/core or equivalent.
    """
    # Works for any file under .../phase6/<subdir>/<file>.py
    # parents[2] lands on the project root containing phase6/
    try:
        here = Path(__file__).resolve()
        # Walk up until we find 'phase6' dir in path, then take its parent
        for parent in here.parents:
            if parent.name == 'phase6':
                return parent.parent
        # Fallback for unusual layouts
        return here.parents[2]
    except Exception:
        # Last resort: CWD or known default (but prefer not to)
        return Path.cwd()


PROJECT_ROOT = get_project_root()

# Canonical dirs per DATA_FLOW
DATA_DIR = PROJECT_ROOT / "data"
STATE_DIR = DATA_DIR / "state"
LOGS_DIR = PROJECT_ROOT / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"
PHASE6_DIR = PROJECT_ROOT / "phase6"

# Key state files (primary live sources)
PHASE6_LIVE_STATE = STATE_DIR / "phase6_live_state.json"
PHASE6_RUNNER_STATE = STATE_DIR / "phase6_runner_state.json"
PRICE_HISTORY = STATE_DIR / "price_history.json"
RSI_CACHE = STATE_DIR / "rsi_cache.json"
REBALANCE_HISTORY = STATE_DIR / "rebalance_history/default.jsonl"
INTEL_BRIEF = STATE_DIR / "intel_strategic_brief.json"
RECOVERY_STATE = STATE_DIR / "recovery_state.json"
OPPORTUNITY_PROPOSALS = STATE_DIR / "opportunity_proposals.jsonl"

# Sentiment caches (standardized per DATA_FLOW_AND_LOCATIONS.md)
SENTIMENT_CACHE = STATE_DIR / "sentiment_cache.json"
X_SENTIMENT_CACHE = STATE_DIR / "x_sentiment_cache.json"
REDDIT_SENTIMENT_CACHE = STATE_DIR / "reddit_sentiment_cache.json"

# DB and other
PHASE6_DB = DATA_DIR / "phase6.db"  # or logs/phase6/phase6_monitor.db per some

# Config
TRADING_CONFIG_PHASE6 = CONFIG_DIR / "trading_config_phase6.json" if (CONFIG_DIR / "trading_config_phase6.json").exists() else PROJECT_ROOT / "trading_config_phase6.json"
ENV_FILE = PROJECT_ROOT / ".env"

# Ensure common dirs exist (idempotent)
for d in (STATE_DIR, LOGS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def resolve_path(rel: str) -> Path:
    """Resolve a relative path string against PROJECT_ROOT."""
    return PROJECT_ROOT / rel.lstrip("/")


# === Centralized dotenv loader (config hygiene) ===
def load_project_dotenv(override: bool = False) -> bool:
    """Centralized .env loader.

    Per DATA_FLOW_AND_LOCATIONS.md + exchange_client robust loading:
    - project .env (canonical)
    - hermes profile .env (~/.hermes/.env)
    - $HOME/.env
    - also default load_dotenv() for cwd .env if present

    Call this EARLY (module top level or main()) in runners, clients, sentiment collectors etc.
    Use override=True only when you explicitly want to override existing env vars.
    Returns True if at least one .env contributed values.
    """
    any_loaded = False
    try:
        # default (respects .env in CWD or dotenv defaults)
        if load_dotenv(override=override):
            any_loaded = True

        # canonical project
        if ENV_FILE.exists():
            if load_dotenv(str(ENV_FILE), override=override):
                any_loaded = True

        # hermes profile (for cron/no_agent etc)
        hermes_env = Path.home() / ".hermes" / ".env"
        if hermes_env.exists():
            if load_dotenv(str(hermes_env), override=override):
                any_loaded = True

        # user home
        home_env = Path.home() / ".env"
        if home_env.exists():
            if load_dotenv(str(home_env), override=override):
                any_loaded = True

        if not any_loaded:
            # no logger yet, silent is ok for this helper
            pass
        return any_loaded
    except Exception as e:
        # safe, non-fatal
        import logging
        logging.getLogger(__name__).warning(f"Non-fatal dotenv issue in load_project_dotenv: {e}")
        return any_loaded


# Usage example in other modules:
# from .paths import PROJECT_ROOT, PHASE6_LIVE_STATE, get_project_root, load_project_dotenv
# load_project_dotenv()
# state = json.loads(PHASE6_LIVE_STATE.read_text())


def load_trading_basket() -> List[str]:
    """Single source of truth for the active trading basket.
    Loads from config (global_settings.pairs preferred, then opportunity_pool).
    All code (runner, evaluation, sentiment, fetchers, refresher, reports) MUST use this
    or the per-module loaders that delegate to it.
    This ensures any pair added/removed in config is automatically a first-class member
    for signals, proposals, rebalancing, and cycling decisions.
    """
    try:
        cfg_path = TRADING_CONFIG_PHASE6
        with open(cfg_path) as f:
            cfg = json.load(f)
        pairs = cfg.get("global_settings", {}).get("pairs", [])
        if not pairs:
            pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool", [])
        if pairs:
            return [str(p) for p in pairs]
    except Exception:
        pass
    # Safe fallback to current 11-pair basket (matches user query)
    return ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
            "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD"]
