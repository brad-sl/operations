#!/usr/bin/env python3
"""
Capital Allocation Recurring Job - Phase 6.1 spec v1.1

This module implements the recurring capital allocation engine for the crypto trading bot.
It runs periodically (intended for cron or scheduler) to:
- Fetch current portfolio state
- Compute optimal allocations using inverse volatility and correlation-aware logic
- Generate rebalance plans
- Log decisions and produce reports for auditability

All code lives in permanent directory as specified.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Import existing allocation engine (permanent path)
import sys
sys.path.insert(0, '/home/brad/projects/crypto-trading-bot/src')
from core.allocation_engine import (
    compute_inverse_vol_allocations,
    plan_static_allocations,
    rebalance_plan
)
from capital_allocation.withdrawal_reserve import (
    load_withdrawal_reserve_config,
    flag_withdrawal_reserve,
    enforce_withdrawal_reserve
)

# Configure logging to permanent logs dir (create if needed)
LOG_DIR = '/home/brad/projects/crypto-trading-bot/logs/capital_allocation'
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/capital_allocation_job.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('capital_allocation_recurring_job')

# Config paths (permanent)
CONFIG_PATH = '/home/brad/projects/crypto-trading-bot/config/capital_allocation_config.json'
STATE_PATH = '/home/brad/projects/crypto-trading-bot/state/capital_allocation_state.json'
REPORT_DIR = '/home/brad/projects/crypto-trading-bot/reports'

os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Load or create default capital allocation config."""
    default_config = {
        "version": "1.2",
        "min_reserve_usd": 500.0,
        "min_weight": 0.04,
        "max_weight": 0.20,
        "rebalance_threshold_usd": 50.0,
        "reserve_pct": 0.20,
        "target_pairs": ["BTC", "ETH", "SOL", "XRP"],
        "volatility_lookback_days": 30,
        "schedule": "0 9 * * 1"  # Weekly Monday 9am example
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    else:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(default_config, f, indent=2)
        return default_config


def fetch_portfolio_state() -> Dict[str, float]:
    """Placeholder: In production would query Coinbase or DB for current holdings in USD."""
    # For now, simulate from state or return example
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, 'r') as f:
            state = json.load(f)
            return state.get('current_allocations', {})
    # Default simulation
    return {'BTC': 1200.0, 'ETH': 1100.0, 'SOL': 800.0, 'XRP': 600.0, 'USD': 1300.0}


def compute_volatilities(pairs: list) -> Dict[str, float]:
    """Placeholder: Would fetch real 30d vol from price data or indicators."""
    # Simulated realistic vols (annualized approx)
    base_vols = {'BTC': 0.45, 'ETH': 0.55, 'SOL': 0.85, 'XRP': 0.70}
    return {p: base_vols.get(p, 0.60) for p in pairs}


def run_capital_allocation() -> Dict[str, Any]:
    """Main recurring job entrypoint. Returns execution report."""
    logger.info("Starting Capital Allocation Recurring Job v1.1")
    config = load_config()
    current_alloc = fetch_portfolio_state()
    total_capital = sum(current_alloc.values())

    # Compute inverse vol weights
    vols = compute_volatilities(config['target_pairs'])
    target_weights = compute_inverse_vol_allocations(
        vols,
        min_weight=config['min_weight'],
        max_weight=config['max_weight']
    )

    # Apply reserve
    deployable = total_capital * (1 - config['reserve_pct'])
    target_allocs_pct = {k: round(v * 100, 2) for k, v in target_weights.items()}
    target_allocs_usd = plan_static_allocations(target_allocs_pct, deployable)

    # Generate rebalance plan
    plan = rebalance_plan(
        current_alloc,
        target_allocs_pct,
        total_capital,
        min_move=config['rebalance_threshold_usd']
    )

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "config_version": config['version'],
        "total_capital_usd": round(total_capital, 2),
        "current_allocations": current_alloc,
        "target_weights": target_weights,
        "target_allocations_usd": target_allocs_usd,
        "rebalance_plan": plan,
        "num_moves": len(plan),
        "status": "success"
    }

    # Persist state
    with open(STATE_PATH, 'w') as f:
        json.dump({"last_run": report["timestamp"], "current_allocations": current_alloc}, f, indent=2)

    # Write daily report
    report_file = f"{REPORT_DIR}/capital_allocation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    logger.info(f"Capital allocation complete. Report: {report_file}")
    logger.info(f"Rebalance moves generated: {len(plan)}")

    return report


if __name__ == "__main__":
    result = run_capital_allocation()
    print(json.dumps(result, indent=2))