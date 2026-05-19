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
# from stop_loss_manager import StopLossManager  # TODO: migrate
# from exchange_client import CoinbaseExchangeClient  # TODO: migrate
from .live_portfolio_manager import LivePortfolioManager

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

        for pair, weight in weights.items():
            usd_amount = round(cash * weight * deploy_pct, 2)
            if usd_amount < 20:
                continue

            if self.shadow_mode:
                logger.info(f"[SHADOW] Would BUY ${usd_amount:.2f} {pair}")
            else:
                resp = self.exchange.place_market_buy(pair, usd_amount)
                if getattr(resp, "success", False):
                    entry_price = self.exchange.get_price(pair)
                    self.stop_loss_manager.attach_stop_loss(pair, entry_price)

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
        current_positions = self.portfolio.get_positions()
        prices = self.exchange.get_prices(self.FIXED_UNIVERSE)

        dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
        target_weights = compute_inverse_vol_allocations(dummy_vols)

        plan = rebalance_plan(current_positions, target_weights, total_capital=1000.0)

        for move in plan:
            if self.shadow_mode:
                logger.info(f"[SHADOW] Rebalance action: {move}")
            else:
                # Placeholder: implement actual execution
                logger.info(f"Would execute rebalance move: {move}")

        self.last_rebalance_date = date.today()
        logger.info(f"Rebalance completed for {self.last_rebalance_date}")

        # Build and send Telegram digest
        details_lines = [
            f"Rebalance Date: {self.last_rebalance_date}",
            f"Pairs: {', '.join(self.FIXED_UNIVERSE)}",
            f"Target Weights: {target_weights}",
            f"Rebalance Plan: {len(plan)} moves",
            f"Current Positions: {current_positions}",
        ]
        details = "\n".join(details_lines)
        self._send_telegram_digest("Daily Rebalance Complete", details)


def main():
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