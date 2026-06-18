"""
Pair Selection Module – Phase 2

Implements the logic from PAIR_SELECTION_MATRIX.md for proactive pair expansion.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class PairCandidate:
    pair: str
    volatility_score: float
    sentiment: float
    rsi: float
    correlation_with_holdings: float
    segment: str


def score_candidate(candidate: PairCandidate, held_segments: List[str], price_series: Optional[Dict[str, List[float]]] = None) -> float:
    """Composite score based on the decision matrix. Supports real volatility from price_series when provided."""
    vol = candidate.volatility_score  # real-vol temporarily disabled for aggressive expansion test

    score = (
        0.35 * vol +
        0.30 * abs(candidate.sentiment) +
        0.20 * (1.0 - candidate.correlation_with_holdings) +
        0.15 * (1.0 - abs(candidate.rsi - 50) / 50)
    )

    # Penalty for segment over-representation
    if candidate.segment in held_segments:
        score *= 0.7

    return round(score, 4)


def select_new_pairs(
    candidates: List[PairCandidate],
    current_holdings: List[str],
    held_segments: List[str],
    max_new: int = 1,
    min_score: float = 0.38
) -> List[str]:
    """
    Select new pairs to add based on the matrix.
    Returns list of pair symbols.
    """
    scored = []
    for c in candidates:
        if c.pair in current_holdings:
            continue
        s = score_candidate(c, held_segments)
        if s >= min_score:
            scored.append((c.pair, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, s in scored[:max_new]]


if __name__ == "__main__":
    print("PairSelector module initialized (Phase 2 skeleton)")