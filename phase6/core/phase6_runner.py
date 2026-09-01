#!/usr/bin/env python3
"""
Phase 6 Production Runner (Canonical)

This is the primary Phase 6 orchestrator.

Location: phase6/core/phase6_runner.py
This file is the single source of truth for the Phase 6 runtime.

Key design decisions:
- mode is NEVER defaulted inside the class (must be passed explicitly)
- CLI defaults to "shadow" for safety
- Supports Fresh Start deployment + daily rebalancing
- Works with allocation_engine and sentiment modules

Do not create parallel runners. Extend this file or its supporting modules in core/.
"""

import argparse
import json
import logging
import os
import time
import requests
from datetime import datetime, date, time as dt_time, timezone
from typing import Dict, List, Optional, Any

from .config_loader import ConfigLoader
from .allocation_engine import compute_inverse_vol_allocations, rebalance_plan
from .rebalancing.hybrid_rebalancer import HybridRebalancer, RebalanceDecision
from .risk.atr_calculator import ATRCalculator
from .risk.regime_detector import RegimeDetector
from .signal_generator import SignalGenerator
from .price_history_manager import PriceHistoryManager
from .rebalance_logger import log_rebalance_event
from .sentiment_scorer import load_sentiment_scores, get_sentiment_adjusted_weights
from .stop_loss_manager import StopLossManager
from .exchange_client import CoinbaseExchangeClient
from .live_portfolio_manager import LivePortfolioManager
from pathlib import Path
from .trade_ledger import TradeLedger

# T0-02: AccountContext injection (feature flag MULTI_TENANT_ENABLED) + dual legacy path
try:
    from .context import (
        AccountContext,
        get_current_context,
        with_account,
        create_legacy_context,
        is_multi_tenant_enabled,
        create_test_context,
    )
except Exception:  # pragma: no cover - pure legacy fallback
    AccountContext = None
    get_current_context = lambda: None
    with_account = lambda ctx: (lambda f: f)  # identity no-op
    create_legacy_context = lambda account_id="brad-primary", **kw: None
    is_multi_tenant_enabled = lambda default=False: False
    create_test_context = lambda account_id="test", **kw: None

# Early dotenv for runner (project .env has the trading keys)
from dotenv import load_dotenv
load_dotenv()
load_dotenv("/home/brad/projects/crypto-trading-bot/.env", override=False)


def calculate_rsi(prices, period=14):
    """Wilder's RSI - pure Python, no external deps."""
    if len(prices) < period + 1:
        return []
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(round(rsi, 2))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return rsi_values

CACHE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
from .order_executor import OrderExecutor
from .error_notifier import Phase6Notifier
from .stop_loss_coordinator import StopLossCoordinator
from src.capital_allocation.withdrawal_reserve import enforce_withdrawal_reserve
from phase6.scripts.deploy_capital import deploy_capital

# ARCH-4 wiring: new unified evaluation + allocator stack
try:
    from phase6.core.evaluation import evaluate_universe
    from phase6.core.allocator import create_allocator, AllocatorConfig
    NEW_ALLOCATOR_AVAILABLE = True
except ImportError:
    NEW_ALLOCATOR_AVAILABLE = False


# P4-04: Platform executor (trading.factory + TradeExecutor) default for ARCH-4
try:
    from trading.factory import create_trading_client
    from trading.executor import TradeExecutor
    PLATFORM_EXECUTOR_AVAILABLE = True
except ImportError as e:
    PLATFORM_EXECUTOR_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("phase6.runner")


class Phase6Runner:
    """
    Main Phase 6 orchestrator.

    mode must be passed explicitly from the caller (CLI, deployment script, or test harness).
    The class itself does not decide safety defaults.
    """

    # Dynamic full basket loaded from config (post full-RSI-refresher fix).
    # Was hardcoded to 6 pairs (original mock set). Now uses global_settings.pairs or opportunity_pool
    # so rebalance, signals, stops, and all logic see the complete 11-pair basket with flowing data.
    # Fallback to 6 for safety if config load fails.
    def _load_full_universe(self, config_path: str):
        try:
            from phase6.core.paths import TRADING_CONFIG_PHASE6, load_trading_basket

            if Path(config_path).resolve() == Path(TRADING_CONFIG_PHASE6).resolve():
                return load_trading_basket()
            with open(config_path) as f:
                cfg = json.load(f)
            pairs = cfg.get("global_settings", {}).get("pairs", [])
            if not pairs:
                pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool", [])
            return pairs or ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"]
        except Exception:
            return ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"]

    def __init__(self, config_path: str, mode: str, account_context: Optional["AccountContext"] = None):
        """
        :param config_path: Path to trading_config_phase6.json
        :param mode: "shadow" or "live" - required, no default inside the class
        """
        self.mode = mode.lower().strip()
        if self.mode not in ("shadow", "live"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'shadow' or 'live'")

        self.shadow_mode = (self.mode == "shadow")
        self.shadow_params = {}  # For IDEALOOP-005 A/B: e.g. {'rsi_threshold': 45, 'sentiment_tilt': 0.1, 'test_alloc_pair': 'DOGE-USD'}
        self.config_path = config_path
        self._basket_config_mtime = None

        # Load configuration
        cfg_loader = ConfigLoader(config_path)
        self.config_dict = cfg_loader._config          # raw dict for convenience
        try:
            from phase6.core.config_overlay import apply_analyst_overlays, shadow_params_from_overlay

            self.config_dict = apply_analyst_overlays(self.config_dict)
            sp = shadow_params_from_overlay()
            if sp:
                self.shadow_params.update(sp)
                logger.info("[ANALYST-OPT] shadow overlay active: %s", sp.get("proposal_id"))
        except Exception as e:
            logger.warning("analyst shadow overlay skipped: %s", e)
        self.config = cfg_loader.get_config()

        # T0-02: AccountContext (shadow injection, dual path - legacy preserved)
        self.account_context = account_context
        if self.account_context is None:
            # Legacy single-account path (Brad api_key direct) - behavior unchanged when flag off
            self.account_context = create_legacy_context(
                account_id="brad-primary",
                tier="elite",
                config=self.config_dict,
                flags={"multi_tenant_enabled": bool(getattr(self.config, "MULTI_TENANT_ENABLED", False) or is_multi_tenant_enabled(False))},
            )
        self.account_id = getattr(self.account_context, "account_id", "default") if self.account_context else "default"
        try:
            is_mt = bool(
                (self.account_context and getattr(self.account_context, "flags", {}).get("multi_tenant_enabled", False))
                or is_multi_tenant_enabled(False)
            )
        except Exception:
            is_mt = False
        if is_mt:
            logger.info(f"[T0-02 CONTEXT] multi-tenant active for account_id={self.account_id}")
        else:
            logger.info(f"[T0-02 LEGACY] single-account Brad path preserved for account_id={self.account_id}")


        # Set dynamic full universe from config (replaces previous class-level 6-pair hardcoded FIXED_UNIVERSE)
        self.FIXED_UNIVERSE = self._load_full_universe(config_path)
        try:
            self._basket_config_mtime = Path(config_path).stat().st_mtime
        except OSError:
            self._basket_config_mtime = None

        # ARCH-4: primary allocator path (P4-01) — default on when config omits flag
        gs_flags = self.config_dict.get("global_settings", {})
        self.use_new_allocator = bool(gs_flags.get("use_new_allocator", True))
        if self.use_new_allocator and not NEW_ALLOCATOR_AVAILABLE:
            logger.warning("use_new_allocator requested but ARCH-4 modules not importable — falling back to legacy")
            self.use_new_allocator = False

        # P4-02: mid-cycle shadow allocator (default off for live safety)
        self.mid_cycle_allocator_enabled = bool(gs_flags.get("mid_cycle_allocator_enabled", False))
        self._last_proposals = []
        self._last_plan = None
        self._last_mid_cycle_plan = None
        self._last_signal_mtime = 0.0

        # P4-04: Platform executor default when ARCH-4 active (use_new_allocator); legacy OrderExecutor only on explicit fallback
        # use_platform_executor: true makes trading.factory + TradeExecutor the execution boundary for rebalance plans
        self.use_platform_executor = bool(
            self.config_dict.get("global_settings", {}).get(
                "use_platform_executor", self.use_new_allocator
            )
        )
        if self.use_platform_executor and not PLATFORM_EXECUTOR_AVAILABLE:
            logger.warning("use_platform_executor requested but platform modules not importable — falling back to legacy OrderExecutor")
            self.use_platform_executor = False

        # Ensure daily_rebalance_time is always available (fixes AttributeError in _should_rebalance)
        scheduler = self.config_dict.get("scheduler", {})
        rebalance_cfg = scheduler.get("daily_rebalance_times") or [scheduler.get("daily_rebalance_time", "09:00")]
        self.daily_rebalance_times = rebalance_cfg if isinstance(rebalance_cfg, list) else [rebalance_cfg]
        self.daily_rebalance_time = self.daily_rebalance_times[0]  # backward compat

        # Load last rebalance date from state to fix AttributeError in _should_rebalance
        state_path = Path("data/state/phase6_runner_state.json")
        self.last_rebalance_date = None
        self._rebalance_slots_completed: set = set()
        # Quality-gate deferrals (cycle_coordinator calls these when gate blocks/allows)
        self._deferred_rebalance_slots: dict = {}
        self.state_file = str(state_path)  # ensure attr always present for _save_state / _load_state (prevents AttributeError on unconditional saves)
        if state_path.exists():
            try:
                with open(state_path) as f:
                    state = json.load(f)
                if "last_rebalance_date" in state and state["last_rebalance_date"]:
                    self.last_rebalance_date = datetime.strptime(state["last_rebalance_date"], "%Y-%m-%d").date()
            except Exception as e:
                logger.warning(f"Failed to load runner state for last_rebalance_date: {e}")
        else:
            logger.info("No previous runner state found; last_rebalance_date remains None")

        # Hybrid Rebalancer (new primary rebalancing engine)
        self.hybrid_rebalancer = HybridRebalancer(config=self.config_dict, account_context=self.account_context)
        self.atr_calculator = ATRCalculator()
        self.regime_detector = RegimeDetector()
        self.signal_generator = SignalGenerator()

        # P6-HC-01: max_deployable_usd with live balance safety cap
        gs = self.config_dict.get("global_settings", {})
        max_deployable = gs.get("max_deployable_usd", gs.get("total_capital", 1000.0))

        if self.mode == "live":
            # Query real USD balance and cap it by the configured max_deployable
            self.exchange = CoinbaseExchangeClient(mode=self.mode)
            self.exchange._ensure_live_client()
            actual_usd = self.exchange.get_account_balance("USD")
            effective_capital = min(max_deployable, actual_usd)
        else:
            self.exchange = CoinbaseExchangeClient(mode=self.mode, initial_capital=max_deployable)
            effective_capital = max_deployable

        self.portfolio = LivePortfolioManager(self.exchange, initial_capital=effective_capital)
        self.stop_loss_manager = StopLossManager(
            self.exchange, self.config_dict, mode=self.mode
        )
        self.stop_loss_coordinator = StopLossCoordinator(
            self.stop_loss_manager,
            exchange_client=self.exchange,
            config=self.config_dict,
        )
        # Structured logging initialization
        self.notifier = Phase6Notifier(log_dir="logs/phase6")
        self.trade_ledger = TradeLedger(account_context=self.account_context)
        self.price_history = PriceHistoryManager(max_history=100, persist_path="data/state/price_history.json")
        self.rsi_values = {}

        self.order_executor = OrderExecutor(
            exchange=self.exchange,
            stop_loss_manager=self.stop_loss_manager,
            mode=self.mode,
            logger=logger,
        )
        self.logger = logger

        # P4-04: initialize platform TradeExecutor (default boundary for ARCH-4 rebalance)
        self.trade_executor = None
        if getattr(self, "use_platform_executor", False):
            try:
                trading_client = create_trading_client(
                    mode=self.mode,
                    exchange="coinbase",
                    config=self.config_dict,
                    initial_capital=effective_capital,
                )
                self.trade_executor = TradeExecutor(
                    client=trading_client,
                    stop_loss_coordinator=getattr(self, "stop_loss_coordinator", None),
                    logger=logger,
                    config_dict=self.config_dict,
                    order_executor=self.order_executor,  # Phase D limit-first path
                )
                self.logger.info(
                    "[P4-04] Platform TradeExecutor initialized (OrderExecutor wired for limit-first D)"
                )
            except Exception as e:
                self.logger.warning(f"[P4-04] Failed to init TradeExecutor (falling back to OrderExecutor): {e}")
                self.use_platform_executor = False
                self.trade_executor = None

        # New: Structured event logger
        self.db_path = "/home/brad/projects/crypto-trading-bot/data/phase6.db"

        self._force_next_rebalance = False
        self.state_file = "data/state/phase6_runner_state.json"
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._load_state()
        self._sync_hybrid_rebalance_cooldown()

        from phase6.core.cycle_coordinator import CycleCoordinator

        self._cycle_coordinator = CycleCoordinator()  # T0-02 ctx via runner or param
        from phase6.core.rebalance_coordinator import RebalanceCoordinator

        self._rebalance_coordinator = RebalanceCoordinator()  # T0-02 ctx support
        self._recent_buy_order_ids: Dict[str, str] = {}
        self._data_coverage: Dict[str, Any] = {}

        logger.info(
            f"Phase6Runner initialized | mode={self.mode} | shadow={self.shadow_mode} | "
            f"rebalance_time={self.daily_rebalance_time} | use_new_allocator={self.use_new_allocator} | "
            f"mid_cycle_shadow={self.mid_cycle_allocator_enabled}"
        )

    def _use_primary_allocator_path(self) -> bool:
        """P4-01 single decision path when flag true and modules available."""
        return bool(getattr(self, "use_new_allocator", True) and NEW_ALLOCATOR_AVAILABLE)

    def persist_facts_to_db(self, usd_balance: float, usdc_balance: float, holdings: dict, price_snapshot: dict):
        """Persist raw facts to phase6.db for SQL VIEW consumption. Dual-write with JSON.
        Called from _write_dashboard_cache. Real data only.
        """
        import sqlite3
        from datetime import datetime
        db_path = Path("data/phase6.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        ts = datetime.utcnow().isoformat() + "Z"

        # Balances
        conn.execute("INSERT OR REPLACE INTO account_balances (ts, currency, balance, available, hold, source) VALUES (?, 'USD', ?, ?, 0, 'live')", (ts, usd_balance, usd_balance))
        if usdc_balance and usdc_balance > 0:
            conn.execute("INSERT OR REPLACE INTO account_balances (ts, currency, balance, available, hold, source) VALUES (?, 'USDC', ?, ?, 0, 'live')", (ts, usdc_balance, usdc_balance))

        # Holdings (flat currency->qty or pair->enriched dict from dashboard)
        for currency, amount in (holdings or {}).items():
            if str(currency).upper() in ("USD", "USDC", "POSITIONS", "VERIFIED", "ERROR", "VALUE_USD"):
                continue
            if isinstance(amount, dict):
                cur = str(amount.get("pair") or currency).replace("-USD", "").upper()
                if not cur or cur in ("USD", "USDC"):
                    cur = str(currency).replace("-USD", "").upper()
                amt = float(amount.get("amount", 0) or 0)
            else:
                cur = str(currency).replace("-USD", "").upper()
                try:
                    amt = float(amount or 0)
                except (TypeError, ValueError):
                    continue
            if amt > 0:
                conn.execute(
                    "INSERT OR REPLACE INTO holdings (ts, currency, amount, available, hold, source) VALUES (?, ?, ?, 0, ?, 'live')",
                    (ts, cur, amt, amt),
                )

        # Prices from snapshot
        for pair, price in (price_snapshot or {}).items():
            if isinstance(price, (int, float)) and str(pair).endswith("-USD"):
                conn.execute("INSERT OR REPLACE INTO prices (ts, pair, price, source) VALUES (?, ?, ?, 'price_snapshot')", (ts, pair, price))

        conn.commit()
        conn.close()
        self.logger.info(f"[DB] Facts persisted to {db_path} at {ts}")

    # ------------------------------------------------------------------
    # Persistence helpers (restart-safe scheduler)
    # ------------------------------------------------------------------
    def _load_state(self):
        """Load last rebalance date from disk (restart-safe)."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                last_str = state.get("last_rebalance_date")
                if last_str:
                    self.last_rebalance_date = datetime.strptime(last_str, "%Y-%m-%d").date()
                    logger.info(f"State loaded: last_rebalance_date={self.last_rebalance_date}")
                completed = state.get("rebalance_slots_completed") or []
                self._rebalance_slots_completed = set(completed) if isinstance(completed, list) else set()
        except Exception as e:
            logger.warning(f"Could not load state file {self.state_file}: {e}")

    def _sync_hybrid_rebalance_cooldown(self) -> None:
        """Prevent hybrid trigger from firing every 60s cycle after a calendar rebalance."""
        hr = getattr(self, "hybrid_rebalancer", None)
        if not hr or not self.last_rebalance_date:
            return
        hr.last_rebalance_time = datetime.combine(self.last_rebalance_date, dt_time(12, 0))
        logger.debug(
            "Hybrid rebalance cooldown seeded from last_rebalance_date=%s",
            self.last_rebalance_date,
        )



    def _write_recovery_state(self, cooldown_pairs: list):
        """Write lightweight recovery state for dashboard."""
        try:
            state = {
                "mode": "emergency" if len(getattr(self, "portfolio", {}).get_positions() or {}) <= 2 else "normal",
                "cooldown_pairs": cooldown_pairs,
                "last_update": datetime.now().isoformat()
            }
            Path("data/state/recovery_state.json").write_text(json.dumps(state))
        except Exception:
            pass

    def _get_recently_stopped_pairs(self, hours: int = 72) -> List[str]:
        """Return pairs that had stop-loss exits in the last N hours."""
        if not hasattr(self, "trade_ledger"):
            return []
        try:
            recent_trades = self.trade_ledger.get_recent_trades(hours=hours)
            stopped = []
            stop_reasons = {
                "stop_loss",
                "sl",
                "stoploss",
                "stop_loss_exchange",
            }
            for trade in recent_trades:
                reason = str(trade.get("reason") or trade.get("exit_reason") or "").lower()
                if reason in stop_reasons or "stop_loss" in reason:
                    pair = trade.get("pair")
                    if pair:
                        stopped.append(pair)
            return list(set(stopped))
        except Exception:
            return []

    def _save_state(self):
        """Persist last rebalance date to disk."""
        try:
            if not hasattr(self, "state_file") or not getattr(self, "state_file", None):
                self.state_file = "data/state/phase6_runner_state.json"
                os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            state = {}
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
            if self.last_rebalance_date:
                state["last_rebalance_date"] = self.last_rebalance_date.isoformat()
            if getattr(self, "_rebalance_slots_completed", None):
                state["rebalance_slots_completed"] = sorted(self._rebalance_slots_completed)
            state["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.warning("Could not write state file %s: %s" % (getattr(self, "state_file", "?"), e))

    # ------------------------------------------------------------------
    # Telegram Digest Reporting
    # ------------------------------------------------------------------
    def _send_telegram_digest(self, title: str, details: str):
        """Send a formatted digest to Telegram after rebalance cycle."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.warning("Telegram credentials not set (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
            return

        message = f"🤖 <b>{title}</b>\n\n{details}\n\n<i>Mode: {self.mode} | {datetime.now().isoformat(timespec='seconds')}</i>"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Telegram digest sent successfully")
            else:
                logger.warning(f"Telegram send failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Telegram digest error: {e}")

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def run(self):
        logger.info("Phase 6 runner starting...")

        has_positions = self.portfolio.has_open_positions()
        if has_positions is None:
            logger.error("Failed to verify portfolio holdings; skipping Fresh Start.")
        elif not has_positions:
            self._handle_fresh_start()
        else:
            logger.info("Takeover scenario detected — existing holdings respected.")

        # One-time dashboard cache write on startup
        self._write_dashboard_cache()

        # Pre-seed price history with recent candles so RSI is available immediately
        logger.info("[RSI] Pre-seeding price history from exchange (lookback)...")
        seeded = 0
        for pair in self.FIXED_UNIVERSE:
            try:
                recent = self.exchange.get_recent_prices(pair, limit=20)
                if recent:
                    for price in recent:
                        self.price_history.add_price(pair, price)
                    seeded += 1
                    logger.info(f"[RSI] {pair}: seeded {len(recent)} historical prices")
            except Exception as e:
                logger.warning(f"[RSI] Failed to seed {pair}: {e}")
        logger.info(f"[RSI] Pre-seeding complete for {seeded} pairs")

        cycle = 0
        while True:
            try:
                cycle += 1
                self._run_cycle(cycle)
                self._write_dashboard_cache()
                try:
                    from phase6.core.shadow_tp import apply_shadow_tp_from_runner

                    apply_shadow_tp_from_runner(self)
                except Exception as _stp_e:
                    logger.debug("shadow_tp cycle: %s", _stp_e)
                try:
                    from phase6.core.regime_exit_shadow import apply_regime_exit_shadow_from_runner

                    apply_regime_exit_shadow_from_runner(self)
                except Exception as _rex_e:
                    logger.debug("regime_exit_shadow cycle: %s", _rex_e)
                try:
                    from phase6.core.bear_profit_take_shadow import (
                        apply_bear_profit_take_from_runner,
                    )

                    apply_bear_profit_take_from_runner(self)
                except Exception as _bpt_e:
                    logger.debug("bear_profit_take_shadow cycle: %s", _bpt_e)
                try:
                    from phase6.core.structure_bos_exit import apply_structure_bos_from_runner

                    apply_structure_bos_from_runner(self)
                except Exception as _bos_e:
                    logger.debug("structure_bos_exit cycle: %s", _bos_e)
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.exception(f"Cycle error: {e}")
                time.sleep(60)

    def _update_price_history_and_calculate_rsi(self):
        """Fetch current prices every cycle; RSI may come from 15m cache without skipping prices.

        BUGFIX 2026-07-19: previously `if pair in self.rsi_values: continue` skipped
        exchange price updates whenever RSI cache was fresh, freezing price_history
        last_updated and blanking dashboard PnL (price_stale / pnl_unreliable).
        """
        rsi_from_cache = set()
        try:
            cache_path = Path("/home/brad/projects/crypto-trading-bot/data/state/rsi_cache.json")
            if cache_path.exists():
                with open(cache_path) as f:
                    cache = json.load(f)
                for pair, data in cache.get("rsi", {}).items():
                    if pair in self.FIXED_UNIVERSE and data.get("fresh"):
                        self.rsi_values[pair] = data["rsi"]
                        rsi_from_cache.add(pair)
        except Exception as e:
            logger.debug(f"Canonical RSI cache load failed (falling back): {e}")

        for pair in self.FIXED_UNIVERSE:
            try:
                # Always refresh spot for dashboard PnL / snapshot freshness
                price = self.exchange.get_price(pair)
                if price and price > 0:
                    self.price_history.add_price(pair, price)

                # RSI already fresh from decoupled cache — no local RSI recompute
                if pair in rsi_from_cache:
                    continue

                # Primary path: 15-minute candles when history is short
                if not self.price_history.has_enough_data(pair, 15):
                    try:
                        candles = self.exchange.get_recent_prices(pair, limit=30, granularity=900)
                        if candles and len(candles) >= 15:
                            rsi_series = calculate_rsi(candles, period=14)
                            if rsi_series and len(rsi_series) > 0:
                                self.rsi_values[pair] = rsi_series[-1]
                                continue
                    except Exception:
                        pass

                if self.price_history.has_enough_data(pair, 15):
                    prices = self.price_history.get_prices(pair)
                    rsi_series = calculate_rsi(prices, period=14)
                    if rsi_series and len(rsi_series) > 0:
                        self.rsi_values[pair] = rsi_series[-1]

            except Exception as e:
                logger.debug(f"RSI/price update failed for {pair}: {e}")
                if pair not in self.rsi_values:
                    self.rsi_values[pair] = 50.0

        # Persist price history so dashboard quote ages stay current
        try:
            self.price_history.flush()
        except Exception:
            pass

        # Persist occasionally
        if len(self.rsi_values) > 0:
            self.price_history.flush()

    def _run_cycle(self, cycle_num: int):
        """P4-05: delegate per-cycle orchestration to CycleCoordinator."""
        try:
            from phase6.core.basket_hot_reload import maybe_reload_trading_basket

            maybe_reload_trading_basket(self, getattr(self, "config_path", None))
        except Exception as e:
            logger.warning("[BASKET-RELOAD] cycle hook failed: %s", e)
        self._cycle_coordinator.run_cycle(self, cycle_num, getattr(self, "account_context", None))

    def _due_rebalance_slot_id(self, now: Optional[datetime] = None) -> Optional[str]:
        """Latest configured daily slot whose local time has passed (for 1x or 2x daily)."""
        now = now or datetime.now()
        current_date = now.date()
        current_t = now.time()
        times = getattr(self, "daily_rebalance_times", [self.daily_rebalance_time])
        if not isinstance(times, list):
            times = [times]
        parsed: List[tuple[str, dt_time]] = []
        for t_str in times:
            try:
                parsed.append((t_str, dt_time.fromisoformat(t_str)))
            except ValueError:
                parsed.append((t_str, dt_time(9, 0)))
        parsed.sort(key=lambda x: x[1])
        due: Optional[tuple[str, dt_time]] = None
        for t_str, target in parsed:
            if current_t >= target:
                due = (t_str, target)
            else:
                break
        if due is None:
            return None
        return f"{current_date.isoformat()}|{due[0]}"

    def _should_rebalance(self, now: datetime) -> bool:
        if getattr(self, "_force_next_rebalance", False):
            self._force_next_rebalance = False
            return True

        # One-time manual force via flag file
        force_flag = Path("data/state/force_rebalance.flag")
        if force_flag.exists():
            force_flag.unlink()
            logger.info("[FORCE] Manual rebalance triggered via flag file")
            return True

        slot_id = self._due_rebalance_slot_id(now)
        if not slot_id:
            return False

        completed = getattr(self, "_rebalance_slots_completed", set()) or set()
        if slot_id in completed:
            return False

        current_date = now.date()
        if self.last_rebalance_date is None:
            return True
        if current_date > self.last_rebalance_date:
            return True
        # Same calendar day: only the not-yet-completed slot (e.g. 21:00 after 09:00)
        if self.last_rebalance_date == current_date:
            return True

        return False

    def _evaluate_hybrid_rebalance(self) -> bool:
        """Use HybridRebalancer to decide if rebalancing is needed."""
        try:
            decision: RebalanceDecision = self.hybrid_rebalancer.evaluate(
                universe=self.FIXED_UNIVERSE,
                previous_sentiment=None,
                volatility=None,
                drawdown=None,
            )
            if decision.should_rebalance:
                logger.info(f"[HYBRID REBALANCE] Reason: {decision.reason}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Hybrid rebalance evaluation failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Fresh Start
    # ------------------------------------------------------------------
    def _handle_fresh_start(self):
        logger.info("=== Fresh Start Deployment ===")
        cash = self.exchange.get_account_balance("USD")
        if cash < 800:
            logger.warning(f"Insufficient cash for Fresh Start: ${cash:.2f}")
            return

        # Wire CR-03 suspend/re-attach logic around Fresh Start rebalancing (CR-04.3)
        logger.info("[CR-03 START] Fresh Start: Detect(03.1) → Suspend(03.2) → Buy+Re-attach(03.4) → Verify(03.5)")
        basket = self.FIXED_UNIVERSE
        active_stops = self.stop_loss_manager.detect_active_protective_orders(basket)
        logger.info(f"[CR-03.1] Active protective orders returned: {len(active_stops)} pairs affected")
        suspended = self.stop_loss_manager.suspend_active_protective_orders(active_stops)
        suspended_count = sum(len(v) for v in suspended.values())
        suspended_ids = {k: v for k, v in suspended.items() if v}
        logger.info(f"[CR-03.2] Suspended {suspended_count} protective orders. Order IDs by pair: {suspended_ids}")

        # Load sentiment and compute base inverse-vol weights, then adjust
        # P6-004: Removed hardcoded 0.65 volatility
        # Use atr as a proxy/scaling component, or fetch real volatility if available
        # Placeholder for dynamic vol: 
        logger.info("[P6-004] Fresh Start: Using real ATR for volatility scaling")
        
        # Calculate recent ATR for universe
        try:
             # Just take a snapshot for now
             recent_prices = {pair: self.price_history.get_prices(pair, n=14) for pair in self.FIXED_UNIVERSE}
             # Basic ATR calculator
             from phase6.core.risk.atr_calculator import ATRCalculator
             calc = ATRCalculator()
             vols = {}
             for p, prices in recent_prices.items():
                 if len(prices) >= 14:
                      vols[p] = calc.calculate_atr(prices, prices, prices, period=14)
                 else:
                      vols[p] = 0.5 # fallback safe
             weights = compute_inverse_vol_allocations(vols)
             base_weights = weights # Needed for downstream adjustment
        except Exception as e:
             logger.warning(f"[P6-004] ATR fallback: {e}")
             dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
             base_weights = compute_inverse_vol_allocations(dummy_vols)
             weights = base_weights

        sentiment_scores = load_sentiment_scores(universe=self.FIXED_UNIVERSE)
        weights = get_sentiment_adjusted_weights(base_weights, sentiment_scores)

        deploy_pct = self.config_dict.get("risk_management", {}).get("deploy_pct", 0.72)
        # Withdrawal reserve guard — config SSOT (not $200 hardcode)
        from phase6.core.runtime_knobs import min_reserve_usd as _min_reserve_usd

        min_reserve = _min_reserve_usd(self.config_dict)
        deployable_cash = max(0, cash - min_reserve)
        if deployable_cash < cash * 0.1:
            logger.warning(f"Reserve guard active: only ${deployable_cash:.2f} deployable after ${min_reserve} reserve")

        logger.info(f"Fresh start: cash=${cash:.2f} | deploy_pct={deploy_pct} | universe={self.FIXED_UNIVERSE}")
        logger.info(f"Computed weights: {weights}")

        buy_attempts = 0
        successful_buys = 0
        skipped = []

        for pair, weight in weights.items():
            usd_amount = round(cash * weight * deploy_pct, 2)
            if usd_amount < 20:
                skip_reason = f"below minimum ($20 threshold): ${usd_amount:.2f}"
                logger.info(f"[SKIP] {pair}: {skip_reason}")
                skipped.append({"pair": pair, "reason": skip_reason})
                continue

            buy_attempts += 1
            logger.info(f"[ATTEMPT {buy_attempts}] {pair}: weight={weight:.4f} | attempting BUY ${usd_amount:.2f}")

            try:
                # P4-04: prefer platform TradeExecutor (default for ARCH-4) ; legacy only on explicit fallback
                if getattr(self, "use_platform_executor", False) and getattr(self, "trade_executor", None):
                    result = self.trade_executor.execute_buy(pair, usd_amount)
                    self.logger.info("[P4-04] Fresh start BUY via platform TradeExecutor")
                else:
                    result = self.order_executor.execute_buy(pair, usd_amount)
                    self.logger.info("[P4-04] Fresh start BUY via legacy OrderExecutor (fallback)")
                if result.get('success'):
                    successful_buys += 1
                    # Log to trade ledger
                    try:
                        trade_record = {
                            "pair": pair,
                            "side": "BUY",
                            "qty": result.get("size", 0),
                            "entry_price": result.get("price", 0),
                            "exit_price": None,
                            "pnl": 0.0,
                            "pnl_pct": 0.0,
                            "signal_source": "phase6_fresh_start"
                        }
                        self.trade_ledger.log_trade(trade_record)
                    except Exception as e:
                        logger.warning(f"Ledger logging failed for {pair}: {str(e) if not isinstance(e, dict) else e}")
                    if result.get('sl_attached'):
                        price = result.get('price')
                        oid = result.get('order_id')
                        logger.info(f"[SUCCESS] {pair}: bought ${usd_amount:.2f} @ ${price} | SL attached | order_id={oid}")
                else:
                    logger.error(f"[FAILURE] {pair}: buy failed - {result.get('error')}")
                    skipped.append({"pair": pair, "reason": f"buy failed: {result.get('error')}"})
            except Exception as e:
                logger.exception(f"[EXCEPTION] {pair}: unexpected error during buy: {e}")
                skipped.append({"pair": pair, "reason": f"exception: {str(e)}"})

        logger.info(f"Fresh start summary: attempts={buy_attempts} | successful={successful_buys} | skipped={len(skipped)}")
        if skipped:
            logger.info(f"Skipped pairs: {skipped}")

        self.last_rebalance_date = date.today()
        self._save_state()
        logger.info("Fresh start rebalance recorded.")
        self.portfolio.refresh()  # ensure dashboard sees new holdings

        # Log Fresh Start event
        try:
            log_rebalance_event({
                "pairs_before": 0,
                "pairs_after": buy_attempts,
                "capital_deployed_usd": sum([30.0] * successful_buys),  # approximate
                "executed": successful_buys,
                "skipped": len(skipped),
                "reason": "fresh_start",
                "mode": getattr(self, "mode", "live")
            })
        except Exception:
            pass

        # Send digest for fresh start too
        details = "Fresh start deployment completed.\nPositions initialized based on inverse volatility."
        self._send_telegram_digest("Phase 6 Fresh Start", details)

    # ------------------------------------------------------------------
    # Daily Rebalancing
    # ------------------------------------------------------------------
    def _finalize_daily_rebalance(self, executed: int, skipped: list, **kwargs):
        """Shared post-rebalance bookkeeping (ARCH-4 + legacy)."""
        from datetime import date

        try:
            self.portfolio.refresh()
        except Exception:
            pass
        self.last_rebalance_date = date.today()
        slot_id = self._due_rebalance_slot_id()
        if slot_id:
            if not hasattr(self, "_rebalance_slots_completed"):
                self._rebalance_slots_completed = set()
            self._rebalance_slots_completed.add(slot_id)
        if getattr(self, "hybrid_rebalancer", None):
            self.hybrid_rebalancer.last_rebalance_time = datetime.now()
        self._save_state()
        logger.info(f"Daily rebalance completed. Executed={executed}, Skipped={len(skipped)}")
        try:
            log_rebalance_event(
                {
                    "pairs_before": kwargs.get("pairs_before", 0),
                    "pairs_after": kwargs.get("pairs_after", 0),
                    "capital_deployed_usd": float(kwargs.get("capital_deployed_usd", 0.0)),
                    "executed": executed,
                    "skipped": len(skipped),
                    "reason": "daily_rebalance",
                    "mode": getattr(self, "mode", "live"),
                }
            )
        except Exception:
            pass
        details = f"Rebalance completed.\nExecuted: {executed} moves\nSkipped: {len(skipped)}"
        if executed > 0 or len(skipped) > 0:
            self._send_telegram_digest("Daily Rebalance Complete", details)
        else:
            logger.info("[TELEGRAM] Skipping digest for no-op rebalance (0 executed, 0 skipped)")

    def _defer_rebalance_slot(self, slot_id: Optional[str], reasons=None) -> None:
        """Record a quality-gate deferral so we retry next cycle without crashing."""
        if not slot_id:
            return
        if not hasattr(self, "_deferred_rebalance_slots") or self._deferred_rebalance_slots is None:
            self._deferred_rebalance_slots = {}
        reason_list = list(reasons) if reasons else []
        self._deferred_rebalance_slots[slot_id] = {
            "reasons": reason_list,
            "deferred_at": datetime.now().isoformat(timespec="seconds"),
        }
        logger.warning(
            "[REBALANCE DEFER] slot=%s reasons=%s",
            slot_id,
            reason_list or ["unspecified"],
        )

    def _clear_deferred_rebalance_slot(self, slot_id: Optional[str] = None) -> None:
        """Clear gate deferral for slot (or all) once the gate allows rebalance."""
        if not hasattr(self, "_deferred_rebalance_slots") or self._deferred_rebalance_slots is None:
            self._deferred_rebalance_slots = {}
            return
        if slot_id is None:
            if self._deferred_rebalance_slots:
                logger.info("[REBALANCE DEFER] cleared all deferred slots")
            self._deferred_rebalance_slots = {}
            return
        if slot_id in self._deferred_rebalance_slots:
            self._deferred_rebalance_slots.pop(slot_id, None)
            logger.info("[REBALANCE DEFER] cleared slot=%s", slot_id)

    def _perform_daily_rebalance(self):
        """P4-05b: delegate daily rebalance body to RebalanceCoordinator."""
        self._rebalance_coordinator.perform_daily(self, getattr(self, "account_context", None))

    # ------------------------------------------------------------------
    # Data Enrichment Helpers
    # ------------------------------------------------------------------
    def _calculate_average_entry_prices(
        self, qty_by_pair: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """Lot-aware average entry per pair (FIFO + LIFO-to-exchange-qty).

        Do **not** lifetime-average BUYs only — that ignored SELLs and inflated
        legacy bags (e.g. BTC entry ~43k vs true current lot ~63k).
        """
        averages: Dict[str, float] = {}
        try:
            from phase6.core.position_cost_basis import average_cost_for_pair

            pairs = set((qty_by_pair or {}).keys())
            for t in self.trade_ledger.get_recent_trades(limit=2000):
                p = t.get("pair")
                if p:
                    pairs.add(str(p))
            for pair in pairs:
                eq = None
                if qty_by_pair and pair in qty_by_pair:
                    try:
                        eq = float(qty_by_pair[pair])
                    except (TypeError, ValueError):
                        eq = None
                entry, _basis = average_cost_for_pair(
                    self.trade_ledger, pair, expected_qty=eq
                )
                if entry and float(entry) > 0:
                    averages[pair] = float(entry)
        except Exception as e:
            self.logger.warning(f"Error calculating entry prices: {e}")
        return averages
    def _write_dashboard_cache(self):
        """Write current live state to the dashboard cache file.
        Uses prices exclusively from self.price_history (runner's snapshot).
        """
        try:
            # Ensure price history is fresh before building snapshot (DASH-006 fix)
            self._update_price_history_and_calculate_rsi()

            usd_raw = self.exchange.get_account_balance("USD")
            usd_unknown = usd_raw is None
            usd = float(usd_raw or 0) if not usd_unknown else 0.0
            try:
                usdc_raw = self.exchange.get_account_balance("USDC")
                usdc_unknown = usdc_raw is None
                usdc = float(usdc_raw or 0) if not usdc_unknown else 0.0
            except Exception:
                usdc = 0.0
                usdc_unknown = True
            if usd_unknown:
                self.logger.warning(
                    "[DASHBOARD] USD balance fetch returned None (API failure) — "
                    "NAV guard will refuse cash wipe if prior exists"
                )

            # Build price snapshot for enrichment (basket + preserve sleeve asset)
            price_snapshot = {}
            pairs_for_px = list(self.FIXED_UNIVERSE or [])
            try:
                from phase6.core.preserve_hold import load_preserve_config, load_state

                pcfg = load_preserve_config(getattr(self, "config_dict", None) or {})
                pst = load_state()
                pax = str(pst.get("asset") or pcfg.get("asset") or "PAXG-USD")
                if pax not in pairs_for_px:
                    pairs_for_px.append(pax)
            except Exception:
                if "PAXG-USD" not in pairs_for_px:
                    pairs_for_px.append("PAXG-USD")
            for pair in pairs_for_px:
                latest = self.price_history.get_latest_price(pair)
                if latest is not None:
                    price_snapshot[pair] = latest
                else:
                    try:
                        px = self.exchange.get_price(pair)
                        if px and float(px) > 0:
                            price_snapshot[pair] = float(px)
                            continue
                    except Exception:
                        pass
                    logger.warning(f"[DASHBOARD] No recent price for {pair} in history; skipping snapshot only")
                    continue

            
            # SL/TP metadata (item 3)
            sl_tp_info = {
                "active_protective_orders": 0,
                "last_reattach": str(getattr(self, "last_rebalance_date", "")),
                "coordinator_mode": getattr(getattr(self, "stop_loss_coordinator", None), "mode", "unknown")
            }
            try:
                if hasattr(self, "stop_loss_coordinator"):
                    suspended = getattr(self.stop_loss_coordinator, "_suspended_orders", {})
                    sl_tp_info["active_protective_orders"] = len(suspended)
            except Exception:
                pass

            enriched = {}
            # Prefer cached portfolio state to avoid rate limits
            try:
                # Pass snapshot to get_enriched_positions
                portfolio_enr = self.portfolio.get_enriched_positions(force_refresh=False, price_snapshot=price_snapshot)
                if isinstance(portfolio_enr, dict) and portfolio_enr:
                    enriched = portfolio_enr
                else:
                    enriched = self.exchange.get_enriched_positions(force_refresh=False, price_snapshot=price_snapshot)
            except Exception:
                try:
                    enriched = self.exchange.get_enriched_positions(force_refresh=False, price_snapshot=price_snapshot)
                except Exception:
                    enriched = {"positions": {}, "verified": False, "error": "fetch failed"}

            # Normalize: manager returns wrapped {"positions": {pair: data}, ...}; direct exchange returns flat {pair: data}
            if isinstance(enriched, dict):
                if "positions" in enriched and isinstance(enriched.get("positions"), dict):
                    pos_map = enriched["positions"]
                else:
                    pos_map = enriched  # flat { "BTC-USD": {...} or "BTC": amount }
            else:
                pos_map = {}

            # Exchange qtys first so lot-aware basis can LIFO-slice to current size
            qty_by_pair: Dict[str, float] = {}
            for key, data in pos_map.items():
                if key in ("USD", "USDC", "positions", "verified", "error", "value_usd"):
                    continue
                if isinstance(key, str) and key.endswith("-USD"):
                    pair_name = key
                else:
                    pair_name = f"{key}-USD"
                if isinstance(data, (int, float)):
                    amt = float(data)
                elif isinstance(data, dict):
                    amt = float(data.get("amount", 0) or 0)
                else:
                    amt = 0.0
                if amt > 0:
                    qty_by_pair[pair_name] = amt

            avg_entries = self._calculate_average_entry_prices(qty_by_pair)

            positions = []
            total_holdings_value = 0.0
            for key, data in pos_map.items():
                if key in ("USD", "USDC", "positions", "verified", "error", "value_usd"):
                    continue
                # key may be base currency ("BTC") or full pair ("BTC-USD")
                if isinstance(key, str) and key.endswith("-USD"):
                    pair_name = key
                else:
                    pair_name = f"{key}-USD"

                if isinstance(data, (int, float)):
                    amount = float(data)
                    price = price_snapshot.get(pair_name, 0.0)
                    value = amount * price
                    entry = avg_entries.get(pair_name, price)
                elif isinstance(data, dict):
                    amount = float(data.get("amount", 0))
                    price = price_snapshot.get(pair_name) or data.get("current_price", data.get("price", 0)) or 0.0
                    value = float(data.get("value_usd", amount * price))
                    entry = avg_entries.get(pair_name, data.get("entry_price", price) or price)
                else:
                    amount = 0.0
                    price = 0.0
                    value = 0.0
                    entry = 0.0

                pnl_pct = ((price - entry) / entry) if entry and entry > 0 else 0.0

                positions.append({
                    "pair": pair_name,
                    "amount": amount,
                    "qty": amount,
                    "quantity": amount,
                    "available": float(data.get("available", amount)) if isinstance(data, dict) else amount,
                    "hold": float(data.get("hold", 0) or 0) if isinstance(data, dict) else 0.0,
                    "current_price": price,
                    "value_usd": value,
                    "entry_price": float(entry) if entry else 0.0,
                    "unrealized_pnl_pct": round(pnl_pct, 4),
                    "price_as_of": (
                        self.price_history.quote_timestamp(pair_name)
                        if hasattr(self.price_history, "quote_timestamp")
                        else datetime.now(timezone.utc).isoformat()
                    ),
                    "side": "long",
                    "sleeve": "preserve" if pair_name.upper().startswith("PAXG") else "trade",
                })
                if amount > 0 and value >= 0:
                    total_holdings_value += value

            # Canonical lot math (merge fills + LIFO to exchange qty) — never trust
            # lifetime BUY-only averages left on state for open-book PnL / shadow TP.
            try:
                from phase6.core.position_cost_basis import recompute_trading_positions_pnl

                positions = recompute_trading_positions_pnl(positions, self.trade_ledger)
            except Exception as _basis_e:
                logger.warning("[DASHBOARD] position cost basis recompute failed: %s", _basis_e)

            # EXIT-H5: qty SSOT aliases after basis recompute
            try:
                from phase6.core.position_qty import normalize_positions_list

                positions = normalize_positions_list(positions)
            except Exception:
                pass

            raw_total = float(usd or 0) + float(usdc or 0) + float(total_holdings_value or 0)
            total_usd = raw_total
            try:
                from phase6.core.live_state_nav_guard import guard_live_nav

                prior_state = {}
                if CACHE_PATH.exists():
                    try:
                        with open(CACHE_PATH, "r") as _pf:
                            prior_state = json.load(_pf) or {}
                    except Exception:
                        prior_state = {}
                prior_cash = prior_state.get("cash_usd")
                if prior_cash is None:
                    prior_cash = sum(
                        float(b.get("balance") or 0)
                        for b in (prior_state.get("balances") or [])
                        if str(b.get("currency") or "").upper() in ("USD", "USDC")
                    )
                guarded_total, guarded_cash, guarded_hold, gmeta = guard_live_nav(
                    new_total=raw_total,
                    new_cash=float(usd or 0) + float(usdc or 0),
                    new_holdings=float(total_holdings_value or 0),
                    prior_total=prior_state.get("total_usd") or prior_state.get("total_balance"),
                    prior_cash=prior_cash,
                )
                if gmeta.get("guarded"):
                    self.logger.warning(
                        "[DASHBOARD] NAV guard blocked cash/API cliff raw=$%.2f kept=$%.2f reason=%s",
                        raw_total,
                        guarded_total,
                        gmeta.get("reason"),
                    )
                    # Restore USD cash from prior; leave usdc as fetched if any
                    usd = float(prior_state.get("cash_usd") or guarded_cash or usd or 0)
                    for b in prior_state.get("balances") or []:
                        if str(b.get("currency") or "").upper() == "USD":
                            usd = float(b.get("balance") or usd)
                        if str(b.get("currency") or "").upper() == "USDC" and float(usdc or 0) <= 0:
                            usdc = float(b.get("balance") or 0)
                    if float(total_holdings_value or 0) <= 0 and guarded_hold > 0:
                        total_holdings_value = guarded_hold
                    total_usd = float(usd or 0) + float(usdc or 0) + float(total_holdings_value or 0)
            except Exception as _nav_g:
                self.logger.warning("[DASHBOARD] nav guard skipped: %s", _nav_g)

            # Recent activity from TradeLedger (newest-first)
            recent_trades = self.trade_ledger.get_recent_trades(6)
            bought_recently = []
            sold_recently = []
            for t in recent_trades:
                side = t.get("side", "").upper()
                if side == "BUY":
                    bought_recently.append(t.get("pair"))
                elif side == "SELL":
                    sold_recently.append(t.get("pair"))

            daily_pnl_est = round(sum(t.get("pnl", 0) or 0 for t in recent_trades), 2)
            win_rate = round(
                sum(1 for t in recent_trades if (t.get("pnl") or 0) > 0) / max(1, len([t for t in recent_trades if t.get("pnl") is not None])),
                4
            ) if recent_trades else 0.0

            state = {
                "balances": [
                    {"currency": "USD", "balance": usd, "available": usd, "hold": 0},
                    {"currency": "USDC", "balance": usdc, "available": usdc, "hold": 0}
                ],
                "positions": positions,
                "active_positions": len(positions),
                "bought_indicators": bought_recently[:3],
                "sold_indicators": sold_recently[:3],
                "total_usd": total_usd,
                "total_holdings_value": total_holdings_value,
                "cash_usd": usd,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "data_as_of": datetime.now(timezone.utc).isoformat(),
                "rsi": self.rsi_values,
                "performance_metrics": {
                    "daily_pnl_est": daily_pnl_est,
                    "win_rate": win_rate,
                    "total_trades": len(recent_trades),
                },
                "arch4": {
                    "use_new_allocator": getattr(self, "use_new_allocator", False),
                    "mid_cycle_shadow": getattr(self, "mid_cycle_allocator_enabled", False),
                    "last_strategy": getattr(getattr(self, "_last_plan", None), "strategy_used", None),
                    "last_exposure": getattr(getattr(self, "_last_plan", None), "expected_exposure", None),
                    "last_rotations": getattr(getattr(self, "_last_plan", None), "rotations", 0),
                    "last_stops": getattr(getattr(self, "_last_plan", None), "stops", 0),
                    "proposals_summary": [
                        {"pair": p.pair, "side": p.side, "score": round(p.score, 3), "source": p.source}
                        for p in getattr(self, "_last_proposals", [])[:5]
                    ]
                    if getattr(self, "_last_proposals", None)
                    else [],
                },
            }


            # Ensure ARCH-4 data is in state for dashboard (new code feed)
            if "arch4" not in state:
                last_plan = getattr(self, "_last_plan", None)
                last_props = getattr(self, "_last_proposals", [])
                state["arch4"] = {
                    "use_new_allocator": getattr(self, "use_new_allocator", False),
                    "last_strategy": getattr(last_plan, "strategy_used", None) if last_plan else None,
                    "last_exposure": getattr(last_plan, "expected_exposure", None) if last_plan else None,
                    "last_rotations": getattr(last_plan, "rotations", 0) if last_plan else 0,
                    "last_stops": getattr(last_plan, "stops", 0) if last_plan else 0,
                    "proposals_summary": [
                        {"pair": getattr(p, "pair", ""), "side": getattr(p, "side", ""), "score": round(getattr(p, "score", 0), 3), "source": getattr(p, "source", "")}
                        for p in last_props[:5]
                    ]
                }

            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_PATH, "w") as f:
                json.dump(state, f, indent=2)

            self.logger.info(f"[DASHBOARD] Cache written (using price snapshot): {len(positions)} positions, holdings=${total_holdings_value:.2f}, total=${total_usd:.2f}")

            # Persist facts to DB for SQL views (DASH-SQL-006)
            try:
                self.persist_facts_to_db(usd, usdc, pos_map or {}, price_snapshot or {})
            except Exception as e:
                self.logger.warning(f"[DASHBOARD] DB persist failed (non-fatal): {e}")

        except Exception as e:
            self.logger.warning(f"[DASHBOARD] Failed to write cache: {e}")




    def _execute_trade_plan(self, trade_plan):
        """ARCH-4: Execute TradePlan. Prefer platform TradeExecutor when use_platform_executor (P4-04 default for ARCH-4); legacy OrderExecutor only on fallback."""
        if not trade_plan or not getattr(trade_plan, "actions", None):
            self.logger.info("[ARCH-4] No actions in TradePlan")
            return 0, []
        exec_plan = []
        # Preserve RSI-primary entry tags for post-fill lot recording
        action_by_pair = {}
        for a in trade_plan.actions:
            pair = a.get("pair")
            row = {
                "pair": pair,
                "action": str(a.get("action", "")).upper(),
                "usd_amount": float(a.get("usd", a.get("usd_amount", 0))),
            }
            exec_plan.append(row)
            if pair:
                action_by_pair[str(pair)] = a
        if self.shadow_mode:
            self.logger.info(f"[ARCH-4 SHADOW EXEC] Plan: {exec_plan}")
            return len(exec_plan), []
        try:
            if getattr(self, "use_platform_executor", False) and getattr(self, "trade_executor", None):
                results = self.trade_executor.execute_rebalance_plan(exec_plan)
                self.logger.info("[P4-04] Executed via platform TradeExecutor")
            else:
                results = self.order_executor.execute_rebalance_plan(exec_plan)
                self.logger.info("[P4-04] Executed via legacy OrderExecutor (fallback)")
            executed = sum(1 for r in results if r.get("success"))
            skipped = [r for r in results if not r.get("success")]
            if not hasattr(self, "_recent_buy_order_ids"):
                self._recent_buy_order_ids = {}
            cycle_ids: Dict[str, str] = {}
            for r in results:
                if r.get("success") and str(r.get("side", r.get("action", ""))).upper() == "BUY":
                    pair = r.get("pair")
                    oid = r.get("order_id") or r.get("id")
                    if pair and oid:
                        cycle_ids[pair] = str(oid)
                    # P1: durable entry-driver lot tag (sentiment-led fade needs this)
                    if pair:
                        try:
                            from phase6.core.rsi_primary_deploy import record_entry_from_buy_action

                            src = action_by_pair.get(str(pair)) or {}
                            tagged = dict(src)
                            tagged.setdefault("pair", pair)
                            if r.get("usd_amount") is not None:
                                tagged["usd"] = r.get("usd_amount")
                            elif r.get("usd") is not None:
                                tagged["usd"] = r.get("usd")
                            ep = float(r.get("entry_price") or 0.0)
                            record_entry_from_buy_action(
                                tagged,
                                entry_price=ep,
                                order_id=str(oid) if oid else None,
                                qty=r.get("size") or r.get("qty"),
                            )
                        except Exception as tag_e:
                            self.logger.debug("[RSI-PRIMARY] entry lot tag skipped: %s", tag_e)
            self._recent_buy_order_ids = cycle_ids
            if getattr(self, "stop_loss_coordinator", None):
                self.stop_loss_coordinator.set_buy_order_ids(cycle_ids)
            # Persist raw rebalance fact (DASH-VIEWS-01) - ensure for both paths
            try:
                self.persist_rebalance_to_db({"actions": exec_plan, "results": [r.get("pair") for r in results if r.get("success")]}, executed)
            except Exception:
                pass
            return executed, skipped
        except Exception as e:
            self.logger.exception(f"[ARCH-4] Execution error: {e}")
            return 0, [{"error": str(e)}]


    def _get_latest_signal_mtime(self) -> float:
        """Return the most recent mtime of primary signal caches (sentiment + RSI).
        Used to decide if full proposal evaluation is warranted (freshness guard).
        """
        candidates = [
            "sentiment_cache.json",
            "data/state/rsi_cache.json",
            os.path.expanduser("~/.trading-bot/sentiment_cache.json"),
            "reddit_sentiment_cache.json",
        ]
        mtimes = []
        for p in candidates:
            if os.path.exists(p):
                try:
                    mtimes.append(os.path.getmtime(p))
                except Exception:
                    pass
        return max(mtimes) if mtimes else 0.0

    def _should_run_full_evaluation(self) -> bool:
        """Lightweight freshness guard (Option #1).
        Only run expensive evaluate_universe + allocator logic when primary signals have updated.
        Daily rebalance can force it.
        """
        latest = self._get_latest_signal_mtime()
        last = getattr(self, "_last_signal_mtime", 0.0)
        if latest > last:
            self._last_signal_mtime = latest
            return True
        return False

    def log_critical(self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Wrapper for critical notifications."""
        self.notifier.notify_critical(error_type, message, context)


def main():
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Phase 6 Production Runner")
    parser.add_argument("--config", default="config/trading_config_phase6.json",
                        help="Path to trading configuration file")
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow",
                        help="Runtime mode. 'shadow' = log only (default/safe). 'live' = real orders.")
    parser.add_argument("--confirm-live", action="store_true", default=False,
                        help="Required when --mode=live to reduce accidental real trading")
    parser.add_argument("--account-id", default=None, help="T0-02 stub per-account (if MULTI_TENANT_ENABLED)")
    args = parser.parse_args()

    if args.mode == "live" and not args.confirm_live:
        parser.error("--mode=live requires --confirm-live flag for safety")

    runner = Phase6Runner(config_path=args.config, mode=args.mode, account_context=None)  # T0-02: pass ctx in full impl
    runner.run()


if __name__ == "__main__":
    main()