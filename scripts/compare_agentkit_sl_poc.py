#!/usr/bin/env python3
"""
Standalone comparison script for AgentKit SL PoC vs current production method.

Run separately:
    PYTHONPATH=. python scripts/compare_agentkit_sl_poc.py --shadow

This exercises:
- Current production: phase6/core/stop_loss_manager.py:StopLossManager
- New separate path:   phase6/core/agentkit_sl.py:AgentKitStopLossManager

Compares:
- Balance resolution (the key mitigation area for INSUFFICIENT_FUND)
- Attach decisions / sizing
- Simulated success

Intended for shadow/paper runs first, then limited live verification.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root on path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.agentkit_sl import AgentKitStopLossManager
from phase6.core.exchange_client import CoinbaseExchangeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("compare_agentkit_sl")

CONFIG_PATH = "config/trading_config_phase6.json"
LIVE_STATE_PATH = "data/state/phase6_live_state.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_sample_positions():
    """Load realistic positions from current live state if available, else synthetic."""
    try:
        with open(LIVE_STATE_PATH) as f:
            state = json.load(f)
        holdings = state.get("holdings", {})
        positions = state.get("positions", [])
        # Build a simple dict of asset -> approx size from holdings or positions
        samples = {}
        for p in positions:
            pair = p.get("pair") or p.get("product_id")
            if not pair or "-" not in pair:
                continue
            asset = pair.split("-")[0]
            size = float(p.get("size") or p.get("base_size") or 0.0)
            if size > 0:
                samples[pair] = {"size": size, "entry": p.get("entry_price") or p.get("avg_price") or 100.0}
        if samples:
            logger.info(f"Loaded {len(samples)} sample positions from live state")
            return samples
    except Exception as e:
        logger.warning(f"Could not load live state ({e}); using synthetic samples")

    # Fallback synthetic (safe for shadow)
    return {
        "UNI-USD": {"size": 45.0, "entry": 7.80},
        "LINK-USD": {"size": 12.5, "entry": 15.20},
        "OP-USD": {"size": 80.0, "entry": 1.85},
    }


def run_comparison(shadow: bool = True):
    config = load_config()
    mode = "shadow" if shadow else "live"

    # Production client (shadow recommended for PoC)
    client = CoinbaseExchangeClient(mode=mode)

    # Current production path
    prod_manager = StopLossManager(exchange_client=client, config=config, mode=mode)

    # Separate AgentKit path (PoC)
    ak_manager = AgentKitStopLossManager(exchange_client=client, config=config, mode=mode)

    samples = load_sample_positions()
    results = []

    print("\n" + "=" * 70)
    print("AGENTKIT SL PoC vs CURRENT PRODUCTION COMPARISON")
    print(f"Mode: {mode}")
    print("=" * 70)

    for pair, data in samples.items():
        size = data["size"]
        entry = data["entry"]

        print(f"\n--- {pair} (size={size}, entry≈${entry}) ---")

        # Current production
        try:
            prod_ok = prod_manager.attach_stop_loss(pair, entry, size)
        except Exception as e:
            prod_ok = False
            logger.error(f"Prod attach error: {e}")
        print(f"  Current (prod StopLossManager): success={prod_ok}")

        # AgentKit separate path
        try:
            ak_ok = ak_manager.attach_stop_loss(pair, entry, size)
        except Exception as e:
            ak_ok = False
            logger.error(f"AgentKit attach error: {e}")
        print(f"  AgentKit PoC:                   success={ak_ok}")

        # Quick balance view comparison (where the mitigation lives)
        asset = pair.split("-")[0]
        try:
            prod_avail = getattr(client, "get_crypto_available", lambda a: 0.0)(asset)
        except Exception:
            prod_avail = "n/a"
        try:
            ak_bal = ak_manager._agentkit_balance_view(asset) if hasattr(ak_manager, "_agentkit_balance_view") else {}
        except Exception:
            ak_bal = {}
        print(f"  Balance view (prod): avail≈{prod_avail}")
        print(f"  Balance view (AgentKit): {ak_bal}")

        results.append({
            "pair": pair,
            "prod_success": prod_ok,
            "agentkit_success": ak_ok,
            "balance_agentkit": ak_bal,
        })

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in results:
        diff = "MATCH" if r["prod_success"] == r["agentkit_success"] else "DIFF"
        print(f"{r['pair']}: prod={r['prod_success']}  agentkit={r['agentkit_success']}  [{diff}]")

    # Simple aggregate
    prod_successes = sum(1 for r in results if r["prod_success"])
    ak_successes = sum(1 for r in results if r["agentkit_success"])
    print(f"\nProd successes:   {prod_successes}/{len(results)}")
    print(f"AgentKit successes: {ak_successes}/{len(results)}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run against live client (use with caution)")
    args = parser.parse_args()
    run_comparison(shadow=not args.live)
