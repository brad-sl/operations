#!/usr/bin/env python3
"""One-off: re-attach SL for open positions (uses SL-ANCHOR-REBASE). Live only with --confirm-live."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(level=logging.INFO)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/trading_config_phase6.json")
    p.add_argument("--mode", default="live", choices=["live", "shadow"])
    p.add_argument("--confirm-live", action="store_true")
    args = p.parse_args()
    if args.mode == "live" and not args.confirm_live:
        print("Refusing live without --confirm-live")
        sys.exit(1)

    from phase6.core.phase6_runner import Phase6Runner

    r = Phase6Runner(config_path=args.config, mode=args.mode)
    positions = r.portfolio.get_enriched_positions() if r.portfolio else {}
    flat = positions.get("positions", positions) if isinstance(positions, dict) else {}
    if isinstance(flat, dict) and "positions" in flat:
        flat = flat["positions"]
    if not flat:
        print("No positions")
        return
    results = r.stop_loss_coordinator.reattach_protective_orders(flat)
    print(results)


if __name__ == "__main__":
    main()