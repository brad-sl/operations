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

    total_capital = sum(current_allocations.values()) + new_capital
    current_pairs = list(current_allocations.keys())

    # Filter existing pairs
    if source == "reserve":
        eligible = [p for p in current_pairs if sentiment_scores.get(p, 0.0) >= min_sentiment]
    else:
        eligible = current_pairs[:]

    new_pairs_added = []

    # Smart selection for new pairs (stricter filter)
    if allow_new_pairs and candidate_pairs:
        weak_existing = sum(1 for p in current_pairs if sentiment_scores.get(p, 0.0) < 0.0)
        if len(eligible) < 3 or weak_existing >= 2:
            good_new = [
                p for p in candidate_pairs
                if p not in current_pairs
                and sentiment_scores.get(p, 0.0) >= min_new_pair_sentiment
            ]
            for p in good_new[:max_new_pairs]:
                eligible.append(p)
                new_pairs_added.append(p)

    if not eligible:
        logger.warning(f"No eligible pairs for deployment (source={source})")
        return current_allocations

    # Weighting
    adjusted = {}
    total_weight = 0.0

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
        adjusted = {k: round(v / total_weight * total_capital, 2) for k, v in adjusted.items()}

    logger.info(f"Deployed ${new_capital:.2f} from {source} | New pairs: {new_pairs_added}")
    return adjusted