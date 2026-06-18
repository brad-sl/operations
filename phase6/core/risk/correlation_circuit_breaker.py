#!/usr/bin/env python3
"""
Correlation Circuit Breaker for Phase 6 Risk Engine

Detects pairs exceeding configurable correlation threshold (default 0.85),
flags for 30% position reduction + 15% reserve redeploy.
Returns structured action dict.

Location: phase6/core/risk/correlation_circuit_breaker.py
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CorrelationBreakerConfig:
    """Configuration for correlation circuit breaker."""
    threshold: float = 0.85
    reduction_pct: float = 0.30
    reserve_redeploy_pct: float = 0.15
    min_pair_correlation_for_flag: float = 0.80


@dataclass
class CorrelationAction:
    """Structured action output."""
    pair: tuple
    correlation: float
    action: str  # e.g. "reduce_and_redeploy"
    reduction_pct: float
    reserve_redeploy_pct: float
    reason: str


class CorrelationCircuitBreaker:
    """High-correlation circuit breaker module."""

    def __init__(self, config: Optional[CorrelationBreakerConfig] = None):
        self.config = config or CorrelationBreakerConfig()
        logger.info(f"CorrelationCircuitBreaker initialized with threshold={self.config.threshold}")

    def evaluate(self, correlation_matrix: Dict[tuple, float]) -> List[Dict[str, Any]]:
        """
        Evaluate correlations and return list of action dicts for pairs exceeding threshold.
        Input: dict of (sym1, sym2) -> corr (assume sym1 < sym2 for uniqueness)
        """
        actions = []
        for pair, corr in correlation_matrix.items():
            if corr >= self.config.threshold:
                action = {
                    "pair": list(pair),
                    "correlation": float(corr),
                    "action": "reduce_and_redeploy",
                    "reduction_pct": self.config.reduction_pct,
                    "reserve_redeploy_pct": self.config.reserve_redeploy_pct,
                    "reason": f"Correlation {corr:.2f} exceeds threshold {self.config.threshold}",
                    "flags": ["high_correlation_risk"]
                }
                actions.append(action)
                logger.warning(f"High correlation detected: {pair}={corr:.3f} -> action triggered")
        return actions


# Embedded test cases
def _run_embedded_tests():
    """Run 3 embedded test cases."""
    config = CorrelationBreakerConfig(threshold=0.85)
    breaker = CorrelationCircuitBreaker(config)

    # Test 1: above threshold
    corr_above = {("BTC", "ETH"): 0.92}
    actions = breaker.evaluate(corr_above)
    assert len(actions) == 1
    assert actions[0]["action"] == "reduce_and_redeploy"
    print("Test 1 (above threshold): PASS")

    # Test 2: below threshold
    corr_below = {("BTC", "ETH"): 0.70}
    actions = breaker.evaluate(corr_below)
    assert len(actions) == 0
    print("Test 2 (below threshold): PASS")

    # Test 3: edge threshold
    corr_edge = {("BTC", "ETH"): 0.85}
    actions = breaker.evaluate(corr_edge)
    assert len(actions) == 1
    print("Test 3 (edge threshold): PASS")

    print("All 3 embedded tests PASSED")


if __name__ == "__main__":
    _run_embedded_tests()
