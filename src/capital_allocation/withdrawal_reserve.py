#!/usr/bin/env python3
"""
Withdrawal Reserve Mechanism - Phase 6.1 spec

Implements flagging and enforcement for minimum withdrawal reserve (min_reserve_usd).
This protects against deploying capital that would prevent user withdrawals without forced liquidation.

Permanent location: src/capital_allocation/withdrawal_reserve.py
"""

import json
import os
from typing import Dict, Any, Tuple


def load_withdrawal_reserve_config(config_path: str = None) -> Dict[str, Any]:
    """Load or return default withdrawal reserve config."""
    if config_path is None:
        config_path = '/home/brad/projects/crypto-trading-bot/config/capital_allocation_config.json'
    
    default = {
        "min_reserve_usd": 50.0,
        "reserve_breach_action": "flag_and_adjust",  # options: flag_only, flag_and_adjust, stop_trading
        "alert_threshold_pct": 1.1,  # alert if reserve < min * 1.1
    }
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            cfg = json.load(f)
            # Merge withdrawal specific keys
            for k in default:
                if k not in cfg:
                    cfg[k] = default[k]
            return cfg
    return default


def flag_withdrawal_reserve(current_reserve_usd: float, min_reserve_usd: float) -> Dict[str, Any]:
    """
    Flag the current reserve status.
    Returns dict with:
      - flagged: bool
      - status: 'OK' | 'WARNING' | 'CRITICAL'
      - shortfall_usd: float (positive if below min)
      - message: str
    """
    shortfall = max(0.0, min_reserve_usd - current_reserve_usd)
    if current_reserve_usd < min_reserve_usd:
        status = "CRITICAL"
        flagged = True
        message = f"RESERVE BREACH: ${current_reserve_usd:.2f} < min ${min_reserve_usd:.2f} (short ${shortfall:.2f})"
    elif current_reserve_usd < min_reserve_usd * 1.1:
        status = "WARNING"
        flagged = True
        message = f"Reserve approaching minimum: ${current_reserve_usd:.2f} (min ${min_reserve_usd:.2f})"
    else:
        status = "OK"
        flagged = False
        message = f"Reserve healthy: ${current_reserve_usd:.2f}"
    
    return {
        "flagged": flagged,
        "status": status,
        "shortfall_usd": round(shortfall, 2),
        "current_reserve_usd": round(current_reserve_usd, 2),
        "min_reserve_usd": round(min_reserve_usd, 2),
        "message": message
    }


def enforce_withdrawal_reserve(
    target_allocations_usd: Dict[str, float],
    current_reserve_usd: float,
    min_reserve_usd: float,
    total_capital: float
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Enforce min reserve by adjusting target allocations if necessary.
    Returns (adjusted_allocations, enforcement_info)
    """
    flag = flag_withdrawal_reserve(current_reserve_usd, min_reserve_usd)
    
    if not flag["flagged"]:
        return target_allocations_usd, {"enforced": False, "reason": "No enforcement needed"}
    
    # Calculate how much we must protect
    protected_reserve = min_reserve_usd
    available_for_deploy = max(0.0, total_capital - protected_reserve)
    
    current_deployed = sum(target_allocations_usd.values())
    
    if current_deployed <= available_for_deploy:
        return target_allocations_usd, {"enforced": False, "reason": "Targets already respect reserve"}
    
    # Scale down allocations proportionally to respect reserve
    scale = available_for_deploy / current_deployed if current_deployed > 0 else 0
    adjusted = {k: round(v * scale, 2) for k, v in target_allocations_usd.items()}
    
    enforcement_info = {
        "enforced": True,
        "original_deploy_total": round(current_deployed, 2),
        "adjusted_deploy_total": round(sum(adjusted.values()), 2),
        "protected_reserve": round(protected_reserve, 2),
        "scale_factor": round(scale, 4),
        "flag": flag
    }
    
    return adjusted, enforcement_info


if __name__ == "__main__":
    # Quick self-test
    cfg = load_withdrawal_reserve_config()
    print("Config:", cfg)
    print(flag_withdrawal_reserve(450.0, 500.0))
    print(enforce_withdrawal_reserve({"BTC": 2000}, 450.0, 500.0, 2500.0))