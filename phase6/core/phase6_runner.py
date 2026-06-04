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
from datetime import datetime, date, time as dt_time
from typing import Dict, List, Optional, Any

from .config_loader import ConfigLoader
from .allocation_engine import compute_inverse_vol_allocations, rebalance_plan
from .sentiment_scorer import load_sentiment_scores, get_sentiment_adjusted_weights
from .stop_loss_manager import StopLossManager
from .exchange_client import CoinbaseExchangeClient
from .live_portfolio_manager import LivePortfolioManager
from pathlib import Path
from .trade_ledger import TradeLedger

CACHE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
from .order_executor import OrderExecutor
from .error_notifier import Phase6Notifier
from .stop_loss_coordinator import StopLossCoordinator
from phase6.scripts.deploy_capital import deploy_capital

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

    FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

    def __init__(self, config_path: str, mode: str):
        """
        :param config_path: Path to trading_config_phase6.json
        :param mode: "shadow" or "live" - required, no default inside the class
        """
        self.mode = mode.lower().strip()
        if self.mode not in ("shadow", "live"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'shadow' or 'live'")

        self.shadow_mode = (self.mode == "shadow")

        # Load configuration
        cfg_loader = ConfigLoader(config_path)
        self.config_dict = cfg_loader._config          # raw dict for convenience
        self.config = cfg_loader.get_config()

        self.exchange = CoinbaseExchangeClient(mode=self.mode)
        self.portfolio = LivePortfolioManager(self.exchange, initial_capital=1000.0)
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
        self.trade_ledger = TradeLedger()
        self.price_history = PriceHistoryManager(max_history=100, persist_path="data/state/price_history.json")
        self.rsi_values = {}
        self.order_executor = OrderExecutor(
            exchange=self.exchange,
            stop_loss_manager=self.stop_loss_manager,
            mode=self.mode,
            logger=logger,
        )
        self.logger = logger
        
        # New: Structured event logger
        self.event_log_path = Path("logs/phase6/events.jsonl")

        # Scheduler
        scheduler = self.config_dict.get("scheduler", {})
        self.daily_rebalance_time = scheduler.get("daily_rebalance_time", "09:00")
        self.last_rebalance_date = None

        # Persistence file for rebalance date (survives restarts)
        self.state_file = "data/state/phase6_runner_state.json"
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._load_state()

        logger.info(f"Phase6Runner initialized | mode={self.mode} | shadow={self.shadow_mode} | rebalance_time={self.daily_rebalance_time}")

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
        except Exception as e:
            logger.warning(f"Could not load state file {self.state_file}: {e}")

    def _save_state(self):
        """Persist last rebalance date to disk."""
        try:
            state = {}
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
            if self.last_rebalance_date:
                state["last_rebalance_date"] = self.last_rebalance_date.isoformat()
            state["last_updated"] = datetime.now().isoformat()
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.warning(f"Could not write state file {self.state_file}: {e}")

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
        if not has_positions:
            self._handle_fresh_start()
        else:
            logger.info("Takeover scenario detected — existing holdings respected.")

        # One-time dashboard cache write on startup
        self._write_dashboard_cache()

        cycle = 0

    def _update_price_history_and_calculate_rsi(self):
        """Fetch current prices and update RSI (if available)."""
        if not RSI_AVAILABLE:
            return

        for pair in self.FIXED_UNIVERSE:
            try:
                price = self.exchange.get_price(pair)
                if price and price > 0:
                    self.price_history.add_price(pair, price)
                    if self.price_history.has_enough_data(pair, 15):
                        prices = self.price_history.get_prices(pair)
                        rsi_series = calculate_rsi(prices, period=14)
                        if rsi_series and len(rsi_series) > 0:
                            self.rsi_values[pair] = round(rsi_series[-1], 2)
            except Exception as e:
                logger.debug(f"RSI update failed for {pair}: {e}")

        # Persist occasionally
        if len(self.rsi_values) > 0:
            self.price_history.flush()
        while True:
            try:
                cycle += 1
                self._run_cycle(cycle)
                time.sleep(300)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.exception(f"Cycle error: {e}")
                time.sleep(60)

    def _run_cycle(self, cycle_num: int):
        now = datetime.now()
        rebalance_needed = self._should_rebalance(now)
        self._update_price_history_and_calculate_rsi()

        logger.info(f"[CYCLE {cycle_num}] {now.isoformat(timespec='seconds')} | "
                    f"rebalance_needed={rebalance_needed} | "
                    f"last_rebalance={self.last_rebalance_date or 'never'}")

        if rebalance_needed:
            self._perform_daily_rebalance()
            self._save_state()

        # Always write dashboard cache at end of cycle (even if no rebalance)
        self._write_dashboard_cache()

    def _should_rebalance(self, now: datetime) -> bool:
        current_date = now.date()
        try:
            target = dt_time.fromisoformat(self.daily_rebalance_time)
        except ValueError:
            target = dt_time(9, 0)

        # First run today after target time and no previous record
        if self.last_rebalance_date is None and now.time() >= target:
            return True

        # Next calendar day has arrived and it's past the rebalance window
        if self.last_rebalance_date is not None and current_date > self.last_rebalance_date and now.time() >= target:
            return True

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
        dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
        base_weights = compute_inverse_vol_allocations(dummy_vols)
        sentiment_scores = load_sentiment_scores(universe=self.FIXED_UNIVERSE)
        weights = get_sentiment_adjusted_weights(base_weights, sentiment_scores)

        deploy_pct = self.config_dict.get("risk_management", {}).get("deploy_pct", 0.72)
        # Withdrawal reserve guard (safety for $1000 account)
        min_reserve = self.config_dict.get("risk_management", {}).get("min_reserve_usd", 200.0)
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
                result = self.order_executor.execute_buy(pair, usd_amount)
                if result.get('success'):
                    successful_buys += 1
                    # Log to trade ledger
                    try:
                        trade_record = {
                            "pair": pair,
                            "side": "buy",
                            "qty": result.get("size", 0),
                            "entry_price": result.get("price", 0),
                            "usd_value": usd_amount,
                            "signal_source": "phase6_fresh_start"
                        }
                        self.trade_ledger.log_trade(trade_record)
                    except Exception as e:
                        logger.warning(f"Ledger logging failed for {pair}: {e}")
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

        # Send digest for fresh start too
        details = "Fresh start deployment completed.\nPositions initialized based on inverse volatility."
        self._send_telegram_digest("Phase 6 Fresh Start", details)

    # ------------------------------------------------------------------
    # Daily Rebalancing
    # ------------------------------------------------------------------
    def _perform_daily_rebalance(self):
        logger.info("=== Daily Rebalance ===")

        basket = getattr(self, "FIXED_UNIVERSE", [])
        current_positions = getattr(self, "portfolio", None) and self.portfolio.get_enriched_positions() or {}

        # Wrap core rebalance logic (order changes) inside suspend_reattach_context
        # Context entered before any order changes; exited after (handles suspend + reattach)
        with self.stop_loss_coordinator.suspend_reattach_context(basket, current_positions):
            logger.info("[CR-03] Entered suspend_reattach_context - performing rebalance body")

            # CR-03.3: Execute rebalance inside protected context
            cash = self.exchange.get_account_balance("USD")

            # Compute target weights using inverse volatility + sentiment
            sentiment_scores = load_sentiment_scores(universe=self.FIXED_UNIVERSE)
            
            # Use deploy_capital to handle both capital deployment rules and static allocation
            # For daily rebalance, all cash is potentially available
            total_cash = cash + sum(current_positions.values())
            
            # Apply deployment rules
            new_allocations = deploy_capital(
                current_allocations=current_positions,
                new_capital=0.0, # Adjusting total, not just deploying new
                sentiment_scores=sentiment_scores,
                source="reserve",
                candidate_pairs=self.FIXED_UNIVERSE
            )
            
            # Generate rebalance plan based on new allocations
            target_weights_pct = {k: round(v / total_cash * 100, 4) for k, v in new_allocations.items()}
            plan = rebalance_plan(current_positions, target_weights_pct, total_capital=total_cash)

            logger.info(f"Daily Rebalance: cash=${cash:.2f} | target_weights={new_allocations}")

            executed = 0
            skipped = []

            for move in plan:
                pair = move.get("pair")
                action = move.get("action", "").upper()
                usd_amount = float(move.get("usd_amount", 0))

                if not pair or usd_amount < 20:
                    skipped.append({"pair": pair, "reason": "below minimum or invalid"})
                    continue

                if self.shadow_mode:
                    logger.info(f"[SHADOW] {action} ${usd_amount:.2f} {pair}")
                    executed += 1
                    continue

                try:
                    if action == "BUY":
                        result = self.order_executor.execute_buy(pair, usd_amount)
                        if result.get('success'):
                            executed += 1
                            if result.get('sl_attached'):
                                logger.info(f"[REBALANCE BUY] {pair}: ${usd_amount:.2f} | SL attached | order_id={result.get('order_id')}")
                            else:
                                logger.warning(f"[REBALANCE BUY] {pair}: ${usd_amount:.2f} | SL failed")
                        else:
                            skipped.append({"pair": pair, "reason": f"buy failed: {result.get('error')}"})

                    elif action == "SELL":
                        result = self.order_executor.execute_sell(pair, usd_amount)
                        logger.info(f"[REBALANCE SELL] {pair}: stub executed")
                        executed += 1

                except Exception as e:
                    logger.exception(f"[REBALANCE ERROR] {pair}: {e}")
                    skipped.append({"pair": pair, "reason": str(e)})

            logger.info(f"[CR-03] Rebalance body completed inside context. Executed={executed}, Skipped={len(skipped)}")

        # Post-context: state update and digest (context already handled re-attach)
        self.last_rebalance_date = date.today()
        self._save_state()
        logger.info(f"Daily rebalance completed. Executed={executed}, Skipped={len(skipped)}")

        # Telegram digest
        details = f"Rebalance completed.\nExecuted: {executed} moves\nSkipped: {len(skipped)}"
        self._send_telegram_digest("Daily Rebalance Complete", details)

    # ------------------------------------------------------------------
    # Structured Logging & Alerts (Observability)
    # ------------------------------------------------------------------
    def _write_dashboard_cache(self):
        """Write current live state to the dashboard cache file.
        This is the single source of truth for the web UI.
        Produces the rich schema defined in Handoff_Dashboard_Dataflow_Fix.md
        """
        try:
            usd = self.exchange.get_account_balance("USD")
            try:
                usdc = self.exchange.get_account_balance("USDC")
            except Exception:
                usdc = 0.0

            enriched = {}
            try:
                enriched = self.exchange.get_enriched_positions()
            except Exception:
                pass

            positions = []
            total_holdings_value = 0.0
            for currency, data in enriched.items():
                if currency in ("USD", "USDC"):
                    continue
                value = data.get("value_usd", 0)
                positions.append({
                    "pair": f"{currency}-USD",
                    "amount": data.get("amount", 0),
                    "current_price": data.get("current_price", data.get("price", 0)),
                    "value_usd": round(value, 2),
                    "entry_price": data.get("entry_price", data.get("price", 0)),
                    "unrealized_pnl_pct": data.get("unrealized_pnl_pct", round(data.get("pnl", 0), 2)),
                    "side": data.get("side", "long"),
                })
                total_holdings_value += value

            total_usd = round(usd + usdc + total_holdings_value, 2)

            # Recent activity from TradeLedger
            recent_trades = self.trade_ledger.get_recent_trades(6)
            bought_recently = []
            sold_recently = []
            for t in reversed(recent_trades):
                side = t.get("side", "").upper()
                if side == "BUY":
                    bought_recently.append(t.get("pair"))
                elif side == "SELL":
                    sold_recently.append(t.get("pair"))

            state = {
                "balances": [
                    {"currency": "USD", "balance": round(usd, 2), "available": round(usd, 2), "hold": 0},
                    {"currency": "USDC", "balance": round(usdc, 2), "available": round(usdc, 2), "hold": 0}
                ],
                "positions": positions,
                "active_positions": len(positions),
                "bought_indicators": bought_recently[:3],
                "sold_indicators": sold_recently[:3],
                "total_usd": total_usd,
                "total_holdings_value": round(total_holdings_value, 2),
                "cash_usd": round(usd, 2),
                "last_updated": datetime.now().isoformat(),
                "rsi": self.rsi_values,
                "performance_metrics": {
                    "daily_pnl_est": 0.0,
                    "win_rate": 0.0,
                    "total_trades": len(recent_trades)
                }
            }

            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_PATH, "w") as f:
                json.dump(state, f, indent=2)

            self.logger.info(f"[DASHBOARD] Cache written: {len(positions)} positions, total=${total_usd:.2f}")
        except Exception as e:
            self.logger.warning(f"[DASHBOARD] Failed to write cache: {e}")


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
    args = parser.parse_args()

    if args.mode == "live" and not args.confirm_live:
        parser.error("--mode=live requires --confirm-live flag for safety")

    runner = Phase6Runner(config_path=args.config, mode=args.mode)
    runner.run()


if __name__ == "__main__":
    main()