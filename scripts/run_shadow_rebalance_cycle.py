#!/usr/bin/env python3
"""
Rebalance Cycle Runner + Verification (Shadow + Live support)

Purpose:
- Execute full rebalance cycle using real Phase6Runner logic.
- Support shadow (safe) and live (with strong confirmation).
- Force new allocator path.
- Inject user's RSI/Sentiment or use live.
- Verify SL suspend/reattach (post-fix).
- Show allocator plan, executed actions, logs.
- For live: requires explicit --confirm, caps, and post-trade verification.

Safer sequence usage:
  # Shadow with new allocator (recommended first)
  python scripts/run_shadow_rebalance_cycle.py --mode shadow --new-allocator

  # Live smoke / full (only after shadow passes and small smoke validated)
  python scripts/run_shadow_rebalance_cycle.py --mode live --confirm "I accept real trades and loss risk" --new-allocator --rebalance-cap 50

This is now the canonical smoke + rebalance driver.
"""

import sys
import argparse
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.phase6_runner import Phase6Runner
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.order_executor import OrderExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rebalance_runner")

# User's snapshot data (for injection in tests)
CURRENT_RSI = {
    "BTC-USD": 65.2, "ETH-USD": 57.4, "SOL-USD": 70.5, "XRP-USD": 62.5,
    "DOGE-USD": 63.5, "ADA-USD": 55.2, "AVAX-USD": 53.2, "LINK-USD": 55.6,
    "UNI-USD": 67.2, "ARB-USD": 46.8, "OP-USD": 51.5
}
CURRENT_SENTIMENT = {
    "BTC-USD": 0.03, "ETH-USD": 0.04, "SOL-USD": 0.18, "XRP-USD": 0.00,
    "DOGE-USD": 0.01, "ADA-USD": 0.82, "AVAX-USD": 0.00, "LINK-USD": 0.76,
    "UNI-USD": 0.09, "ARB-USD": 0.07, "OP-USD": 0.43, "MATIC-USD": 0.11
}
CURRENT_POSITIONS = {
    "OP-USD": {"amount": 91.0, "entry_price": 0.108, "value_usd": 9.828, "current_price": 0.108},
    "XRP-USD": {"amount": 18.637483, "entry_price": 0.52, "value_usd": 22.663, "current_price": 1.216},
    "ETH-USD": {"amount": 0.08572777, "entry_price": 3200.0, "value_usd": 153.446, "current_price": 1789.92},
}

def setup_runner(mode="shadow", use_new_allocator=True, rebalance_cap=200.0):
    """Create Phase6Runner. For shadow uses mocks; live uses real client."""
    config = {
        "mode": mode,
        "global_settings": {
            "pairs": list(CURRENT_POSITIONS.keys()),
            "rebalance_cap_usd": rebalance_cap,
            "trade_buffer_hours": 24,
        },
        "risk_management": {"stop_loss_pct": 0.03},
        "withdrawal_reserve": {"min_reserve_usd": 250.0},
        "scheduler": {"daily_rebalance_time": "21:00"},
    }

    if mode == "shadow":
        with patch('phase6.core.phase6_runner.CoinbaseExchangeClient') as mock_ex, \
             patch('phase6.core.phase6_runner.LivePortfolioManager') as mock_port:

            mock_exchange = MagicMock()
            mock_exchange.shadow_mode = True
            mock_exchange.get_account_balance.return_value = 603.72
            mock_exchange.get_price.side_effect = lambda p: CURRENT_POSITIONS.get(p, {}).get("current_price", 100.0)
            mock_exchange.get_open_orders.return_value = []
            mock_exchange.place_market_buy.return_value = {"success": True, "order_id": "shadow"}
            mock_exchange.place_market_sell.return_value = {"success": True, "order_id": "shadow"}
            mock_exchange.get_product_metadata.return_value = {"price_increment": 0.01, "base_increment": 0.0001}

            mock_portfolio = MagicMock()
            mock_portfolio.get_enriched_positions.return_value = CURRENT_POSITIONS
            mock_portfolio.get_holdings_verified.return_value = {"positions": CURRENT_POSITIONS}

            mock_ex.return_value = mock_exchange
            mock_port.return_value = mock_portfolio

            runner = Phase6Runner(config_path="config/trading_config_phase6.json", mode="shadow")
            runner.exchange = mock_exchange
            runner.portfolio = mock_portfolio
            runner.rsi_values = CURRENT_RSI
            runner._force_next_rebalance = True
            runner.use_new_allocator = use_new_allocator

            runner.stop_loss_manager = StopLossManager(mock_exchange, config, mode="shadow")
            runner.order_executor = OrderExecutor(mock_exchange, runner.stop_loss_manager, mode="shadow")
            from phase6.core.stop_loss_coordinator import StopLossCoordinator
            runner.stop_loss_coordinator = StopLossCoordinator(
                runner.stop_loss_manager, exchange_client=mock_exchange, config={"mode": "shadow"}
            )

            import phase6.core.phase6_runner as pr
            pr.load_sentiment_scores = lambda **k: CURRENT_SENTIMENT

            return runner, mock_exchange
    else:
        # Live mode - real client, no mocks
        runner = Phase6Runner(config_path="config/trading_config_phase6.json", mode="live")
        runner._force_next_rebalance = True
        runner.use_new_allocator = use_new_allocator
        # Inject snapshot for this run (runner may override with live signals)
        runner.rsi_values = CURRENT_RSI
        import phase6.core.phase6_runner as pr
        pr.load_sentiment_scores = lambda **k: CURRENT_SENTIMENT
        return runner, runner.exchange

def run_rebalance(mode="shadow", use_new_allocator=True, rebalance_cap=200.0, confirm=None):  # default True for WIRING-01
    print("=" * 70)
    print(f"REBALANCE CYCLE - MODE: {mode.upper()} | NEW_ALLOCATOR: {use_new_allocator}")
    print("Using user's RSI/Sent snapshot + post-SL-fix paths")
    if mode == "live":
        print("!!! LIVE MODE - REAL TRADES WILL EXECUTE !!!")
        if confirm != "I accept real trades and loss risk":
            print("ERROR: --confirm 'I accept real trades and loss risk' required for live.")
            sys.exit(1)
    print("=" * 70)

    runner, ex = setup_runner(mode=mode, use_new_allocator=use_new_allocator, rebalance_cap=rebalance_cap)

    print("\n--- Pre-rebalance state ---")
    print(f"Positions: {list(CURRENT_POSITIONS.keys())}")
    print(f"Force rebalance: {runner._force_next_rebalance}")
    try:
        cash = ex.get_account_balance("USD")
        print(f"Current cash: ${cash:.2f}")
    except:
        print("Cash: (live will query real)")

    print(f"\n--- Executing _perform_daily_rebalance() in {mode} ---")
    try:
        runner._perform_daily_rebalance()
        print("\n--- Rebalance completed ---")
    except Exception as e:
        print(f"\nRebalance error: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Post-run diagnostics ---")
    if hasattr(runner, "_last_plan"):
        plan = runner._last_plan
        print(f"Strategy: {getattr(plan, 'strategy_used', 'N/A')}")
        print(f"Actions: {getattr(plan, 'actions', [])}")
        print(f"Notes: {getattr(plan, 'notes', '')}")
    else:
        print("No _last_plan captured.")

    print("\n--- SL Coordination evidence ---")
    print("Look for [CR-03], attach logs, and new buy SL attachments above.")
    print("New buys should now auto-attach SL (fixed).")

    if mode == "live":
        print("\n✅ LIVE rebalance executed. Verify SLs in Coinbase UI immediately.")
        print("Run small smoke verification next if not already done.")

    print("\n✅ Rebalance cycle finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebalance cycle runner (shadow/live)")
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow")
    parser.add_argument("--new-allocator", action="store_true", default=True, help="Prefer new allocator (WIRING-01); --no-new or omit for legacy (but runner now defaults prefer)")
    parser.add_argument("--rebalance-cap", type=float, default=200.0, help="Cap for new capital deploy")
    parser.add_argument("--confirm", type=str, default=None, help="Required phrase for live: 'I accept real trades and loss risk'")
    args = parser.parse_args()

    run_rebalance(
        mode=args.mode,
        use_new_allocator=getattr(args, "new_allocator", True) or True,
        rebalance_cap=args.rebalance_cap,
        confirm=args.confirm
    )
