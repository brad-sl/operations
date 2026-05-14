#!/usr/bin/env python3
"""
Phase 6 Production Runner (Updated)

Clean, maintainable orchestrator that works with the existing modules
in this repository.

Key design decisions:
- mode is NEVER defaulted inside the class (must be passed explicitly)
- CLI defaults to "shadow" for safety
- Config file can contain "mode" or "shadow_mode.default"
- Future deployment scripts can set the mode based on PHASE6_ENV (dev/test/prod)
"""

import argparse
import logging
import os
import time
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Any

from config_loader import ConfigLoader
from allocation_engine import compute_inverse_vol_allocations, rebalance_plan
from stop_loss_manager import StopLossManager
from exchange_client import CoinbaseExchangeClient
from live_portfolio_manager import LivePortfolioManager

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

        logger.info(f"Phase6Runner initialized | mode={self.mode} | shadow={self.shadow_mode}")

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

        while True:
            try:
                self._run_cycle()
                time.sleep(300)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.exception(f"Cycle error: {e}")
                time.sleep(60)

    def _run_cycle(self):
        now = datetime.now()
        if self._should_rebalance(now):
            self._perform_daily_rebalance()

    def _should_rebalance(self, now: datetime) -> bool:
        current_date = now.date()
        try:
            target = dt_time.fromisoformat(self.daily_rebalance_time)
        except ValueError:
            target = dt_time(9, 0)

        if self.last_rebalance_date is None and now.time() >= target:
            return True
        if current_date > self.last_rebalance_date and now.time() >= target:
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

        # TODO: replace placeholder volatility with real 24h/7d volatility
        dummy_vols = {p: 0.65 for p in self.FIXED_UNIVERSE}
        weights = compute_inverse_vol_allocations(dummy_vols)

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

        self.last_rebalance_date = datetime.now().date()

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

        self.last_rebalance_date = datetime.now().date()


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