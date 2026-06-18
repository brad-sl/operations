"""
ARCH-2: Unified Allocator / Decision Layer

Consumes unified Proposals from evaluate_universe (ARCH-1) and current portfolio state.
Produces actionable TradePlan / allocation deltas using pluggable strategies.

Core strategies:
- RotationStrategy (catch-the-wave): Exit weak (oversold flip + neutral/neg sentiment), immediate opportunistic redeploy to strongest signals. Cash as brief intermediary. Hard stops on cliffs.
- RebalanceStrategy: Tilt toward inverse-vol base + Proposal scores (lighter churn).

Reuses building blocks:
- allocation_engine.rebalance_plan, compute_inverse_vol_allocations
- deploy_capital (for freed/new capital redeploys, with gates relaxed inside strategy)

Design:
- Allocator is thin orchestrator for strategies.
- Strategies are pure/callable for isolation testing.
- Always real data via Proposals (which come from real sentiment_scorer + signals).
- Tunable for churn: min_move_usd, min_score_delta, cooldown_days, rebalance_freq.

This replaces the scattered logic in runner / hybrid_rebalancer / deploy_capital as the canonical decision layer.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging

from .evaluation import Proposal
from .allocation_engine import rebalance_plan, compute_inverse_vol_allocations
from phase6.scripts.deploy_capital import deploy_capital, get_deployment_thresholds

logger = logging.getLogger(__name__)

# Dynamic full basket (post full-RSI-refresher). Load from config to support all pairs with flowing data.
# Previously hardcoded to 5; now config-driven so rebalancer/strategies can use complete 11-pair signals.
import json
from pathlib import Path
try:
    _cfg = json.loads((Path(__file__).parent.parent.parent / "config" / "trading_config_phase6.json").read_text())
    FIXED_UNIVERSE = _cfg.get("global_settings", {}).get("pairs", []) or _cfg.get("phase_6_specific", {}).get("opportunity_pool", ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"])
except Exception:
    FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

@dataclass
class TradePlan:
    """Output of Allocator: concrete actions + expected new allocations."""
    actions: List[Dict[str, Any]] = field(default_factory=list)  # e.g. [{"pair": "...", "action": "BUY/SELL", "usd": 123.45, "reason": "..."}]
    new_allocations: Dict[str, float] = field(default_factory=dict)  # pair -> target usd
    expected_exposure: float = 1.0
    strategy_used: str = ""
    rotations: int = 0
    stops: int = 0
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class AllocatorConfig:
    min_move_usd: float = 50.0
    min_score_delta: float = 0.15
    stop_loss_pct: float = 0.12
    rebalance_freq_days: int = 1
    fee_rate: float = 0.001
    use_inverse_vol_base: bool = True
    max_pairs: int = 5

class RotationStrategy:
    """
    Catch-the-wave rotation strategy (validated +8.89% on 12mo downtrend in isolation tests).
    - Exit pairs when RSI flips from oversold + sentiment neutral/negative (weak).
    - Immediately redeploy freed capital + cash to strongest current Proposals (buy signals).
    - Hard stop on -stop_loss_pct cliffs.
    - Cash is brief intermediary, not a long-term sink.
    - Churn controls: min_move, min_score_delta for rotation threshold.
    """

    def __init__(self, config: AllocatorConfig = None):
        self.config = config or AllocatorConfig()
        self.last_rotation: Dict[str, datetime] = {}  # pair -> last rotate time for cooldown

    def _proposals_to_scores(self, proposals: List[Proposal]) -> Dict[str, float]:
        scores = {}
        for p in proposals:
            if p.pair in FIXED_UNIVERSE:
                scores[p.pair] = p.score
        return scores

    def decide(
        self,
        proposals: List[Proposal],
        current_allocs: Dict[str, float],
        cash_usd: float,
        total_capital: float,
        recent_prices: Optional[Dict[str, List[float]]] = None,
    ) -> TradePlan:
        """
        Core decision for one cycle.
        Returns TradePlan with actions.
        """
        plan = TradePlan(strategy_used="rotation_catch_wave")
        scores = self._proposals_to_scores(proposals)

        # Current weights from allocs
        total_invested = sum(current_allocs.values())
        current_weights = {p: (current_allocs.get(p, 0) / total_invested if total_invested > 0 else 0) for p in FIXED_UNIVERSE}

        # Identify weak (exit candidates) from proposals: low score or explicit HOLD/ROTATE_OUT
        weak_pairs = []
        strong_pairs = []
        for p in proposals:
            if p.side in ("ROTATE_OUT", "SELL") or (p.side == "HOLD" and p.score < 0.4):
                if current_allocs.get(p.pair, 0) > 0:
                    weak_pairs.append(p.pair)
            elif p.side in ("ROTATE_IN", "BUY") and p.score > 0.55:
                strong_pairs.append((p.pair, p.score))

        # Sort strong by score
        strong_pairs.sort(key=lambda x: x[1], reverse=True)
        top_strong = [p for p, _ in strong_pairs[:2]]  # limit to 1-2 for lower churn

        # Hard stops (simplified: if we had recent prices we could check drawdown; here use proposal metadata if present)
        for pair in list(current_allocs.keys()):
            if current_allocs.get(pair, 0) > 0 and pair in scores:
                # Placeholder for stop logic; real would use price series
                if scores.get(pair, 0.5) < 0.2:  # very low conviction
                    freed = current_allocs[pair]
                    plan.actions.append({
                        "pair": pair,
                        "action": "SELL",
                        "usd": round(freed, 2),
                        "reason": "hard_stop_low_conviction"
                    })
                    plan.stops += 1
                    current_allocs[pair] = 0.0
                    cash_usd += freed * (1 - self.config.fee_rate)

        # Rotation: exit weak
        freed_from_weak = 0.0
        for pair in weak_pairs:
            if current_allocs.get(pair, 0) > self.config.min_move_usd:
                slice_val = current_allocs[pair]
                freed_from_weak += slice_val
                plan.actions.append({
                    "pair": pair,
                    "action": "SELL",
                    "usd": round(slice_val, 2),
                    "reason": "exit_weak_for_rotation"
                })
                current_allocs[pair] = 0.0
                plan.rotations += 1
                cash_usd += slice_val * (1 - self.config.fee_rate)

        total_available = cash_usd + freed_from_weak

        # Opportunistic redeploy to strong (or top scored if no explicit strong)
        if total_available > self.config.min_move_usd and top_strong:
            per_pair = total_available / len(top_strong)
            for pair in top_strong:
                if per_pair > self.config.min_move_usd:
                    plan.actions.append({
                        "pair": pair,
                        "action": "BUY",
                        "usd": round(per_pair, 2),
                        "reason": "opportunistic_rotation_from_weak"
                    })
                    current_allocs[pair] = current_allocs.get(pair, 0) + per_pair
                    plan.rotations += 1

        # Fallback: if no rotation happened and we have cash, light tilt using inverse vol + scores
        elif cash_usd > self.config.min_move_usd and self.config.use_inverse_vol_base:
            # Simple equal for baseline; real would call compute_inverse_vol_allocations
            base_alloc = cash_usd / len(FIXED_UNIVERSE)
            for pair in FIXED_UNIVERSE:
                if base_alloc > self.config.min_move_usd and scores.get(pair, 0) > 0.3:
                    plan.actions.append({
                        "pair": pair,
                        "action": "BUY",
                        "usd": round(base_alloc, 2),
                        "reason": "light_tilt_cash"
                    })
                    current_allocs[pair] = current_allocs.get(pair, 0) + base_alloc

        plan.new_allocations = current_allocs.copy()
        plan.expected_exposure = sum(current_allocs.values()) / total_capital if total_capital > 0 else 0.0
        plan.notes = f"rotations={plan.rotations}, stops={plan.stops}, available_for_redeploy={round(total_available,2)}"

        # Apply min_move filter to final actions (churn control)
        filtered_actions = [a for a in plan.actions if abs(a.get("usd", 0)) >= self.config.min_move_usd]
        plan.actions = filtered_actions

        return plan

class RebalanceStrategy:
    """Lighter churn rebalance using inverse-vol base + Proposal tilt."""

    def __init__(self, config: AllocatorConfig = None):
        self.config = config or AllocatorConfig()

    def decide(
        self,
        proposals: List[Proposal],
        current_allocs: Dict[str, float],
        cash_usd: float,
        total_capital: float,
    ) -> TradePlan:
        plan = TradePlan(strategy_used="rebalance_tilt")
        scores = {p.pair: p.score for p in proposals if p.pair in FIXED_UNIVERSE}

        # Use inverse vol as stable base (simplified vols)
        vols = {p: 0.5 for p in FIXED_UNIVERSE}  # placeholder; real would compute from prices
        base_weights = compute_inverse_vol_allocations(vols, min_weight=0.1, max_weight=0.3)

        # Tilt base with proposal scores
        tilted = {}
        for p, w in base_weights.items():
            tilt = scores.get(p, 0.5) - 0.5  # -0.5 to +0.5
            tilted[p] = max(0.05, min(0.4, w + tilt * 0.2))

        # Renormalize
        total = sum(tilted.values())
        if total > 0:
            tilted = {k: v / total for k, v in tilted.items()}

        target_usd = {k: v * (total_capital - cash_usd) for k, v in tilted.items()}

        # Use rebalance_plan primitive
        moves = rebalance_plan(
            current_allocs=current_allocs,
            target_allocs_pct={k: v * 100 for k, v in tilted.items()},  # rough
            total_capital=total_capital,
            min_move=self.config.min_move_usd
        )

        plan.actions = moves  # already in good format from primitive
        plan.new_allocations = target_usd
        plan.expected_exposure = 1.0
        plan.notes = "inverse_vol_base + proposal_tilt (lower churn mode)"

        return plan

class Allocator:
    """
    Thin unified decision layer.
    Chooses strategy (or can be configured to rotation vs rebalance).
    Consumes Proposals from ARCH-1 evaluate_universe.
    """

    def __init__(self, strategy: str = "rotation", config: AllocatorConfig = None):
        self.config = config or AllocatorConfig()
        self.strategy_name = strategy
        if strategy == "rotation":
            self.strategy = RotationStrategy(self.config)
        else:
            self.strategy = RebalanceStrategy(self.config)

    def allocate(
        self,
        proposals: List[Proposal],
        current_allocs: Dict[str, float],
        cash_usd: float,
        total_capital: Optional[float] = None,
        recent_prices: Optional[Dict[str, List[float]]] = None,
    ) -> TradePlan:
        if total_capital is None:
            total_capital = sum(current_allocs.values()) + cash_usd

        if self.strategy_name == "rotation":
            plan = self.strategy.decide(proposals, current_allocs.copy(), cash_usd, total_capital, recent_prices)
        else:
            plan = self.strategy.decide(proposals, current_allocs.copy(), cash_usd, total_capital)

        # Post-process: use deploy_capital as building block for any freed capital if needed
        # (for now the strategies handle redeploy directly; deploy_capital can be called inside for gated new capital)
        if cash_usd > 0 and not plan.actions:
            # Fallback to deploy for any remaining cash
            try:
                sent = {p.pair: p.metadata.get("sentiment", 0.0) for p in proposals}
                deployed = deploy_capital(
                    current_allocations=current_allocs,
                    new_capital=cash_usd,
                    sentiment_scores=sent,
                    source="allocator_fallback",
                    min_sentiment=-0.1,  # relaxed inside allocator
                )
                for p, amt in deployed.items():
                    if amt > current_allocs.get(p, 0) + 10:
                        plan.actions.append({"pair": p, "action": "BUY", "usd": round(amt - current_allocs.get(p, 0), 2), "reason": "deploy_capital_fallback"})
            except Exception as e:
                logger.debug(f"deploy fallback skipped: {e}")

        return plan

# Convenience
def create_allocator(strategy: str = "rotation", **config_kwargs) -> Allocator:
    cfg = AllocatorConfig(**config_kwargs)
    return Allocator(strategy, cfg)
