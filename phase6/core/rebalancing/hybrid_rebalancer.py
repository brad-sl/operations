#!/usr/bin/env python3
"""
Hybrid Rebalancer - Threshold + AI Filter for Phase 6

Combines hard thresholds (sentiment delta, volatility, drawdown) with a lightweight
rule-based AI filter layer. Integrates time-decayed sentiment from the restored
sentiment system (15min X, 60min Reddit half-life).

This replaces pure correlation rebalancing with signal-tied logic that is more
reliable across regimes.

Location: phase6/core/rebalancing/hybrid_rebalancer.py
"""

from ..paths import PROJECT_ROOT  # per DATA_FLOW_AND_LOCATIONS.md


import json
import logging
from ..sentiment_scorer import load_sentiment_scores
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(PROJECT_ROOT / "data/state/sentiment_cache.json")  # per DATA_FLOW
DEFAULT_CONFIG = {
    "sentiment_delta_threshold": 0.15,  # absolute change to trigger consideration
    "volatility_spike_threshold": 0.25,  # e.g. 25% vol increase
    "drawdown_threshold": 0.08,          # 8% portfolio DD
    "min_rebalance_interval_hours": 24,  # at least daily
    "sentiment_weight": 0.25,
    "ai_filter_enabled": True,
    "ai_confidence_threshold": 0.6,
}


@dataclass
class RebalanceDecision:
    """Structured decision output."""
    should_rebalance: bool
    reason: str
    sentiment_deltas: Dict[str, float] = field(default_factory=dict)
    triggered_thresholds: List[str] = field(default_factory=list)
    ai_filter_passed: bool = False
    confidence: float = 0.0
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)


class HybridRebalancer:
    """
    Hybrid scheduler: hard thresholds first, then AI (rule-based) filter.

    NARROW ROLE (post P4-03): This is ONLY the hybrid *trigger* for rebalance decisions
    (via .evaluate() returning RebalanceDecision). It is secondary to calendar _should_rebalance
    in the runner.

    Plan generation is retired here. Canonical plans flow exclusively through
    Allocator + RebalanceStrategy (or RotationStrategy) -> TradePlan in ARCH-4,
    which uses allocation_engine.rebalance_plan under the hood.

    No generate_rebalance_plan; callers must use the unified allocator path.
    """

    def __init__(self, config: Optional[Dict] = None, cache_path: str = DEFAULT_CACHE_PATH, account_context: Optional["AccountContext"] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.cache_path = cache_path
        self.last_rebalance_time: Optional[datetime] = None
        logger.info("HybridRebalancer initialized with thresholds: %s", self.config)
        self.account_context = account_context
        self.account_id = getattr(account_context, "account_id", "default") if account_context else "default"
        if account_context and getattr(account_context, "flags", {}).get("multi_tenant_enabled"):
            # per-account cache for isolation (shadow)
            from pathlib import Path
            p = Path(cache_path)
            self.cache_path = str(p.parent / f"{self.account_id}_{p.name}")
            logger.info(f"[T0-02] per-account cache: {self.cache_path}")

    def _load_sentiment(self, universe: List[str]) -> Dict[str, float]:
        """Canonical delegation for consistency with runner/scorer.
        Uses load_sentiment_scores (full dynamic basket, X primary + real Reddit).
        """
        try:
            return load_sentiment_scores(universe=universe)
        except Exception as e:
            logger.warning("Canonical load failed, neutral: %s", e)
            return {sym: 0.0 for sym in universe}

    def _compute_sentiment_deltas(
        self, current_sentiment: Dict[str, float], previous_sentiment: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate absolute deltas for each symbol."""
        deltas = {}
        for sym in current_sentiment:
            curr = current_sentiment.get(sym, 0.0)
            prev = previous_sentiment.get(sym, 0.0)
            deltas[sym] = abs(curr - prev)
        return deltas

    def _check_hard_thresholds(
        self,
        sentiment_deltas: Dict[str, float],
        volatility: Optional[Dict[str, float]] = None,
        drawdown: Optional[float] = None,
    ) -> Tuple[bool, List[str]]:
        """Return (triggered, list_of_triggered_names)."""
        triggered = []
        sent_thresh = self.config["sentiment_delta_threshold"]
        for sym, delta in sentiment_deltas.items():
            if delta >= sent_thresh:
                triggered.append(f"sentiment_delta_{sym}_{delta:.2f}")

        if volatility:
            vol_thresh = self.config["volatility_spike_threshold"]
            for sym, vol in volatility.items():
                if vol >= vol_thresh:
                    triggered.append(f"vol_spike_{sym}_{vol:.2f}")

        if drawdown is not None and drawdown >= self.config["drawdown_threshold"]:
            triggered.append(f"drawdown_{drawdown:.2f}")

        return len(triggered) > 0, triggered

    def _ai_filter(self, decision_context: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Lightweight rule-based AI filter (no external model call for Phase 6.1).
        Returns (passed, confidence).
        Can be extended later with a small LLM or sklearn model.
        """
        if not self.config.get("ai_filter_enabled", True):
            return True, 1.0

        # Simple heuristic rules combining signals
        sentiment_ok = False
        for delta in decision_context.get("sentiment_deltas", {}).values():
            if delta >= self.config["sentiment_delta_threshold"] * 0.7:
                sentiment_ok = True
                break

        # Example AI-ish rules
        rules_passed = 0
        total_rules = 3

        if sentiment_ok:
            rules_passed += 1
        if decision_context.get("volatility_ok", True):
            rules_passed += 1
        if decision_context.get("drawdown_ok", True):
            rules_passed += 1

        confidence = rules_passed / total_rules
        passed = confidence >= self.config["ai_confidence_threshold"]
        return passed, round(confidence, 2)

    def evaluate(
        self,
        universe: List[str],
        previous_sentiment: Optional[Dict[str, float]] = None,
        volatility: Optional[Dict[str, float]] = None,
        drawdown: Optional[float] = None,
        current_time: Optional[datetime] = None,
    ) -> RebalanceDecision:
        """
        Main evaluation entrypoint.
        Returns structured RebalanceDecision.
        """
        current_time = current_time or datetime.utcnow()

        # Interval guard
        if self.last_rebalance_time:
            hours_since = (current_time - self.last_rebalance_time).total_seconds() / 3600
            if hours_since < self.config["min_rebalance_interval_hours"]:
                return RebalanceDecision(
                    should_rebalance=False,
                    reason=f"Too soon since last rebalance ({hours_since:.1f}h < {self.config['min_rebalance_interval_hours']}h)",
                )

        current_sent = self._load_sentiment(universe)
        if previous_sentiment is None:
            previous_sentiment = {k: 0.0 for k in current_sent}  # first run baseline

        deltas = self._compute_sentiment_deltas(current_sent, previous_sentiment)
        triggered, trigger_names = self._check_hard_thresholds(deltas, volatility, drawdown)

        if not triggered:
            return RebalanceDecision(
                should_rebalance=False,
                reason="No hard thresholds crossed",
                sentiment_deltas=deltas,
            )

        # AI filter
        context = {
            "sentiment_deltas": deltas,
            "volatility_ok": True,  # placeholder, extend as needed
            "drawdown_ok": drawdown is None or drawdown < self.config["drawdown_threshold"] * 1.5,
        }
        ai_passed, confidence = self._ai_filter(context)

        if not ai_passed:
            return RebalanceDecision(
                should_rebalance=False,
                reason="AI filter rejected (low confidence)",
                sentiment_deltas=deltas,
                triggered_thresholds=trigger_names,
                ai_filter_passed=False,
                confidence=confidence,
            )

        # Passed both layers
        self.last_rebalance_time = current_time
        return RebalanceDecision(
            should_rebalance=True,
            reason="Hybrid thresholds + AI filter passed",
            sentiment_deltas=deltas,
            triggered_thresholds=trigger_names,
            ai_filter_passed=True,
            confidence=confidence,
            suggested_actions=[{"type": "rebalance", "trigger": trigger_names[0] if trigger_names else "hybrid"}],
        )

    def generate_rebalance_plan(
        self,
        current_allocs: Dict[str, float],
        target_weights: Dict[str, float],
        total_capital: float,
        min_move_usd: float = 25.0,
        proposals: Optional[List[Any]] = None,
        trade_plan: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        THIN DELEGATE (P4-03 retired stub).
        Rebalance plans flow through Allocator + RebalanceStrategy.
        Hybrid only for .evaluate() trigger.
        This is compat shim only; no dummy vol logic.
        """
        logger.warning("[P4-03] generate_rebalance_plan on HybridRebalancer retired. Use Allocator/RebalanceStrategy for plans.")
        try:
            from ..allocation_engine import rebalance_plan as engine_rebalance_plan
            if trade_plan is not None:
                if hasattr(trade_plan, "actions"):
                    acts = getattr(trade_plan, "actions", []) or []
                    return list(acts)
                if isinstance(trade_plan, (list, tuple)):
                    return list(trade_plan)
            target_pct = {k: float(v) * 100 for k, v in (target_weights or {}).items()}
            return engine_rebalance_plan(current_allocs or {}, target_pct, total_capital, min_move_usd)
        except Exception as e:
            logger.warning("shim failed: %s", e)
            return []

# Convenience for quick testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rebal = HybridRebalancer()
    try:
        from phase6.core.paths import load_trading_basket

        _universe = load_trading_basket()
    except Exception:
        _universe = [
            "BTC-USD",
            "ETH-USD",
            "SOL-USD",
            "XRP-USD",
            "DOGE-USD",
            "ADA-USD",
            "AVAX-USD",
            "LINK-USD",
            "UNI-USD",
            "ARB-USD",
            "ICP-USD",
        ]
    decision = rebal.evaluate(
        universe=_universe,
        previous_sentiment={"BTC-USD": 0.1, "ETH-USD": -0.05, "XRP-USD": 0.2},
        volatility={"BTC-USD": 0.3},
        drawdown=0.05,
    )
    print(decision)
    print("Hybrid rebalancer smoke test complete.")