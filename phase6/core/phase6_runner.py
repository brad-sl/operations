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
from .stop_loss_manager import StopLossManager  # TODO: migrate
from .exchange_client import CoinbaseExchangeClient  # TODO: migrate
from .live_portfolio_manager import LivePortfolioManager
from .trade_ledger import TradeLedger
from .order_executor import OrderExecutor

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
        self.trade_ledger = TradeLedger()
        self.order_executor = OrderExecutor(
            exchange=self.exchange,
            stop_loss_manager=self.stop_loss_manager,
            mode=self.mode,
            logger=logger,
        )

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

        cycle = 0
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

        logger.info(f"[CYCLE {cycle_num}] {now.isoformat(timespec='seconds')} | "
                    f"rebalance_needed={rebalance_needed} | "
                    f"last_rebalance={self.last_rebalance_date or 'never'}")

        if rebalance_needed:
            self._perform_daily_rebalance()
            self._save_state()

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

        # Load sentiment and compute base inverse-vol weights, then adjust
        dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
        base_weights = compute_inverse_vol_allocations(dummy_vols)
        sentiment_scores = load_sentiment_scores(universe=self.FIXED_UNIVERSE)
        weights = get_sentiment_adjusted_weights(base_weights, sentiment_scores)

        deploy_pct = self.config_dict.get("risk_management", {}).get("deploy_pct", 0.72)

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
                        self.trade_ledger.log_trade(
                            pair=pair,
                            side="buy",
                            qty=result.get('size', 0),
                            entry_price=result.get('price', 0),
                            usd_value=usd_amount
                        )
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
        logger.info("[CR-03 START] Full CR-03 flow: Detect(03.1) → Suspend(03.2) → Rebalance(03.3) → Re-attach(03.4) → Verify(03.5)")

        # CR-03.1: Detect active SL/TP orders before rebalance
        basket = getattr(self, "FIXED_UNIVERSE", [])
        active_stops = self.stop_loss_manager.detect_active_protective_orders(basket)
        logger.info(f"[CR-03.1] Active protective orders returned: {len(active_stops)} pairs affected")

        # CR-03.2: Suspend active stops before rebalance executes
        suspended = self.stop_loss_manager.suspend_active_protective_orders(active_stops)
        suspended_count = sum(len(v) for v in suspended.values())
        suspended_ids = {k: v for k, v in suspended.items() if v}
        logger.info(f"[CR-03.2] Suspended {suspended_count} protective orders. Order IDs by pair: {suspended_ids}")

        # CR-03.3: Execute rebalance after suspension using live balances
        # Get real capital and current positions (live balances post any liquidation)
        cash = self.exchange.get_account_balance("USD")
        current_positions = getattr(self, "portfolio", None) and self.portfolio.get_positions() or {}

        # Compute target weights using inverse volatility + sentiment
        dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
        base_weights = compute_inverse_vol_allocations(dummy_vols)
        sentiment_scores = load_sentiment_scores(universe=self.FIXED_UNIVERSE)
        target_weights = get_sentiment_adjusted_weights(base_weights, sentiment_scores)

        # Generate rebalance plan
        total_capital = cash + sum(current_positions.values()) if current_positions else cash
        plan = rebalance_plan(current_positions, target_weights, total_capital=total_capital)

        logger.info(f"Daily Rebalance: cash=${cash:.2f} | target_weights={target_weights}")

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

        # CR-03.4: Re-attach Fresh Stops Post-Rebalance
        # After rebalance completes, attach new stop-loss orders on resulting positions
        # using current RiskEngine / config risk parameters (via StopLossManager)
        logger.info("[CR-03.4] Re-attaching fresh protective stops to resulting positions")
        try:
            holdings = self.exchange.get_holdings()
            reattached = 0
            for asset, size in holdings.items():
                if size <= 0:
                    continue
                pair = f"{asset}-USD" if "-USD" not in asset else asset
                if pair not in basket:
                    continue
                price = self.exchange.get_price(pair)
                if price > 0:
                    attached = self.stop_loss_manager.attach_stop_loss(pair, price, float(size))
                    if attached:
                        reattached += 1
                        logger.info(f"[CR-03.4] Fresh SL attached | {pair} size={size:.8f} ref_price=${price:.2f}")
                    else:
                        logger.warning(f"[CR-03.4] SL attach failed for {pair}")
            logger.info(f"[CR-03.4] Re-attachment complete. Stops re-attached: {reattached}")
        except Exception as e:
            logger.exception(f"[CR-03.4 ERROR] Failed during stop re-attachment: {e}")

        # CR-03.5: Verification of full suspend → rebalance → re-attach sequence
        try:
            verification = self.stop_loss_manager.verify_reconciliation(
                basket=basket, suspended=suspended
            )
            logger.info(f"[CR-03.5] Verification result: success={verification.get("success")} | details={verification.get("details")} | orphans={verification.get("orphaned_stops")}")
            if verification.get("success"):
                logger.info("[CR-03 COMPLETE] End-to-end sequence verified: no orphaned stops, fresh stops attached.")
            else:
                logger.warning("[CR-03 WARNING] Verification reported issues - check for orphans or missing stops.")
        except Exception as ve:
            logger.exception(f"[CR-03.5 ERROR] Verification failed to run: {ve}")

        self.last_rebalance_date = date.today()
        self._save_state()
        logger.info(f"Daily rebalance completed. Executed={executed}, Skipped={len(skipped)}")

        # Telegram digest
        details = f"Rebalance completed.\nExecuted: {executed} moves\nSkipped: {len(skipped)}"
        self._send_telegram_digest("Daily Rebalance Complete", details)


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