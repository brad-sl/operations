#!/usr/bin/env python3
"""
Capital Deployment Module (Standalone)

Purpose:
    Handles allocation of new or freed capital (deposits, liquidations, reserve redeployment)
    using sentiment-driven logic with smart pair selection.

Design Goals:
    - Standalone and reusable across multiple runners/monitors
    - Smart selection of new pairs when the basket is weak or small
    - Strict quality control on new pairs (higher sentiment threshold)
    - Preserves total capital (does not renormalize to 1.0)
    - Minimizes idle capital while respecting risk signals

Usage Examples:

    # Basic usage (new capital from liquidation)
    from phase6.scripts.deploy_capital import deploy_capital

    new_allocs = deploy_capital(
        current_allocations={"BTC-USD": 120.0, "ETH-USD": 90.0},
        new_capital=200.0,
        sentiment_scores={"BTC-USD": 0.6, "ETH-USD": -0.2, "SOL-USD": 0.45},
        source="liquidation",
        candidate_pairs=["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"]
    )

    # Reserve redeployment (only deploy to positive sentiment pairs)
    new_allocs = deploy_capital(
        current_allocations=...,
        new_capital=reserve_amount,
        sentiment_scores=...,
        source="reserve",
        min_sentiment=0.0
    )
"""

import logging
from typing import Dict, List, Optional

def get_deployment_thresholds() -> dict:
    """Return current active deployment rules (used by reports & debugging)."""
    return {
        "min_sentiment": -0.30,
        "min_new_pair_sentiment": 0.20,
        "min_rsi": 30.0,
        "new_capital_cap": 50.0,
        "withdrawal_reserve_min": 250.0,
    }

# Recovery mode constants
RECOVERY_CANDIDATES = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
    "ADA-USD", "AVAX-USD", "LINK-USD", "NEAR-USD", "ARB-USD"
]
RECOVERY_TARGET_PAIRS = 5
RECOVERY_MIN_NEW_PAIR_SENTIMENT = 0.10  # relaxed but still has a quality gate

logger = logging.getLogger(__name__)


def deploy_capital(
    current_allocations: Dict[str, float],
    new_capital: float,
    sentiment_scores: Dict[str, float],
    source: str = "unknown",
    min_sentiment: float = -0.30,
    min_new_pair_sentiment: float = 0.20,
    max_pairs: int = 8,
    allow_new_pairs: bool = True,
    candidate_pairs: Optional[List[str]] = None,
    min_new_pair_allocation: float = 30.0,
    max_new_pairs: int = 2,
    rsi_values: Optional[Dict[str, float]] = None,
    min_rsi: float = 30.0,
    cooldown_pairs: Optional[List[str]] = None,   # pairs on 24h cooldown after stop-loss
) -> Dict[str, float]:
    """
    Deploy new capital using sentiment-driven allocation.

    Parameters
    ----------
    current_allocations : dict
        Current pair -> dollar allocation.
    new_capital : float
        Amount of capital to deploy.
    sentiment_scores : dict
        Pair -> sentiment score (-1.0 to +1.0).
    source : str
        "deposit", "liquidation", "reserve", or "takeover".
    min_sentiment : float
        Minimum sentiment to keep existing pairs (default -0.30).
    min_new_pair_sentiment : float
        Stricter threshold for opening new pairs (default +0.20).
    max_pairs : int
        Maximum total pairs allowed.
    allow_new_pairs : bool
        Whether to consider opening new pairs.
    candidate_pairs : list, optional
        List of pairs to consider for new entries.
    min_new_pair_allocation : float
        Minimum dollar amount for a new pair.
    max_new_pairs : int
        Maximum number of new pairs to open in one deployment.

    Returns
    -------
    dict
        Updated allocations (preserves total capital).

    RSI Hard Gate (added 2026-06-05):
        Pairs with RSI below min_rsi are excluded from deployment.
        Rationale: Oversold conditions (RSI < 30) frequently produce
        misleadingly positive or neutral sentiment during capitulation.
        Deploying capital in this regime increases downside risk.
        RSI acts as a hard pre-filter before sentiment rules are applied.
    """
    if new_capital <= 0:
        return current_allocations


    # === 2-Pair Emergency Recovery Mode ===
    # When critically under-allocated (≤2 pairs), be much more aggressive
    # to get the basket back to a useful size (~5 pairs) where rebalancing
    # can actually do meaningful work.
    emergency_recovery = len(current_allocations) <= 2
    effective_min_new_sentiment = min_new_pair_sentiment
    effective_max_new_pairs = max_new_pairs
    effective_candidate_pairs = candidate_pairs or []

    if emergency_recovery:
        effective_min_new_sentiment = RECOVERY_MIN_NEW_PAIR_SENTIMENT
        effective_max_new_pairs = 3
        effective_candidate_pairs = RECOVERY_CANDIDATES
        if cooldown_pairs:
            effective_candidate_pairs = [p for p in effective_candidate_pairs if p not in cooldown_pairs]
        logger.info(
            f"[EMERGENCY RECOVERY] Activated | holdings={len(current_allocations)} | "
            f"cooldown={cooldown_pairs or []} | min_sentiment={effective_min_new_sentiment}"
        )

    # === RSI Hard Gate ===
    # Exclude pairs that are oversold. Oversold conditions often coincide
    # with temporarily positive sentiment during capitulation, which can
    # lead to deploying capital at unfavorable risk levels.
    if rsi_values:
        current_allocations = {
            p: v for p, v in current_allocations.items()
            if rsi_values.get(p, 100) >= min_rsi
        }
        if candidate_pairs:
            candidate_pairs = [
                p for p in candidate_pairs
                if rsi_values.get(p, 100) >= min_rsi
            ]

    # Calculate total capital BEFORE possibly adding new pairs?
    # Actually, look at the weighting logic. It uses adjusted pairs.
    # The `total_capital` used for constraint is sum(allocs) + new_capital
    total_capital = sum(current_allocations.values()) + new_capital
    current_pairs = list(current_allocations.keys())

    # Filter existing pairs
    if source == "reserve":
        eligible = [p for p in current_pairs if sentiment_scores.get(p, 0.0) >= min_sentiment]
    else:
        eligible = current_pairs[:]

    new_pairs_added = []

    # Smart selection for new pairs (stricter filter)
    if allow_new_pairs and effective_candidate_pairs:
        # Check sentiment of EXTREME EXISTING
        # ... existing logic ...
        good_new = [
            p for p in effective_candidate_pairs
            if p not in current_pairs
            and sentiment_scores.get(p, 0.0) >= effective_min_new_sentiment
        ]
        # ADD NEW PAIRS
        # IMPORTANT: These are added to `eligible`, BUT their weight isn't in `current_allocations`
        # and so they were NOT included in `total_capital` check above?
        # NO, total_capital is fine because we sum existing + new_capital.
        for p in good_new[:effective_max_new_pairs]:
            eligible.append(p)
            new_pairs_added.append(p)

    if not eligible:
        logger.warning(f"No eligible pairs for deployment (source={source})")
        return current_allocations

    # Weighting
    adjusted = {}
    total_weight = 0.0

    print(f"DEBUG: eligible pairs={eligible}")
    for pair in eligible:
        sent = sentiment_scores.get(pair, 0.0)
        existing = current_allocations.get(pair, 0.0)

        if pair in new_pairs_added:
            base = min_new_pair_allocation
        else:
            base = max(existing, 10.0)

        weight = base * (1.0 + 0.30 * sent)
        adjusted[pair] = max(0.01, weight)
        total_weight += adjusted[pair]

    if total_weight > 0:
        # P6-145: Ensure reserve is respected as a global floor.
        
        withdrawal_reserve_min = 500.0 # From config
        
        # Calculate available capital
        # P6-145: Reserve must be respected. Total capital = sum(active) + new_capital
        # Available for DEPLOYMENT is (Total - Reserve)
        available_capital = max(0.0, total_capital - withdrawal_reserve_min)
        
        # Scale down allocations proportionally IF total needed > available
        if sum(adjusted.values()) > available_capital:
            # Scale factor
            scale = available_capital / sum(adjusted.values())
            print(f"DEBUG: reserve breach, scaling by {scale}")
            adjusted = {k: round(v * scale, 2) for k, v in adjusted.items()}
        
        print(f"DEBUG: after scaling available={available_capital} weight={total_weight} adjusted={adjusted}")

    logger.info(f"Deployed ${new_capital:.2f} from {source} | New pairs: {new_pairs_added}")
    return adjusted