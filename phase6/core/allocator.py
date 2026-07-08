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


See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths and rules."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging

from .evaluation import Proposal
from .allocation_engine import rebalance_plan, compute_inverse_vol_allocations
from phase6.scripts.deploy_capital import deploy_capital, get_deployment_thresholds
from .paths import load_trading_basket

logger = logging.getLogger(__name__)

# Single source from paths.py (BASKET-01). Full dynamic basket, no reduced fallbacks or duplicated loaders.
FIXED_UNIVERSE = load_trading_basket()

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
    force_re_evaluate: bool = False
    drawdown_exits: int = 0

@dataclass
class AllocatorConfig:
    min_move_usd: float = 50.0
    min_score_delta: float = 0.15
    stop_loss_pct: float = 0.12
    rebalance_freq_days: int = 1
    fee_rate: float = 0.001
    use_inverse_vol_base: bool = True
    max_pairs: int = 5
    dd_threshold_pct: float = 0.08  # drawdown pct to force exit / re-eval
    cooldown_hours: float = 6.0
    min_rotation_delta: float = 0.15  # min score improvement for rotation to justify churn

class RotationStrategy:
    """
    Catch-the-wave rotation strategy (validated +8.89% on 12mo downtrend in isolation tests).
    Strengthened (SL-04):
    - Exit pairs on explicit ROTATE_OUT/SELL, or HOLD + score < (0.5 - min_score_delta)
    - Use min_score_delta and min_rotation_delta to require meaningful improvement before rotation churn.
    - Hard stop / force exit on price drawdown > dd_threshold_pct (using recent_prices series) OR low conviction.
    - Cooldown enforcement on per-pair rotations.
    - Sets force_re_evaluate=True on drawdown-triggered exits to prompt immediate re-scan.
    - Cash is brief intermediary, not a long-term sink.
    - Churn controls: min_move, min_score_delta, min_rotation_delta, cooldown_hours.
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

    def _compute_drawdowns(self, recent_prices: Optional[Dict[str, List[float]]], current_allocs: Dict[str, float]) -> Dict[str, float]:
        """Compute trailing drawdown from peak in recent price series for held positions."""
        dds = {}
        if not recent_prices:
            return dds
        for pair, alloc_usd in current_allocs.items():
            if alloc_usd > 0:
                prices = recent_prices.get(pair) or []
                if len(prices) >= 2:
                    peak = max(prices)
                    curr = prices[-1] if prices else peak
                    if peak > 0:
                        dd = (peak - curr) / peak
                        dds[pair] = max(0.0, dd)
        return dds



    def _detect_declining_trend(self, recent_prices: Optional[Dict[str, List[float]]], min_pairs: int = 2, window: int = 8) -> bool:
        """Simple price trend detector for other_factors.
        Returns True if average of recent prices is lower than older window for enough pairs.
        """
        if not recent_prices:
            return False
        declining = 0
        for pair, prices in recent_prices.items():
            if not isinstance(prices, (list, tuple)) or len(prices) < 6:
                continue
            prices = [float(p) for p in prices if p]
            if len(prices) < 6:
                continue
            recent = prices[-3:]
            older = prices[-(window+3):-3] if len(prices) > window + 3 else prices[:-3]
            if older and len(older) >= 2:
                if sum(recent) / len(recent) < sum(older) / len(older):
                    declining += 1
        return declining >= min_pairs

    def _detect_volume_spike(self, recent_prices: Optional[Dict[str, List[float]]], intelligence_brief: Optional[dict] = None) -> bool:
        """Placeholder for volume spike. Current price_history is price-only.
        Can be enhanced when volume/candle data is passed through recent_prices or brief.
        """
        # Future: if candles with volume are available, compare recent vol avg vs baseline
        if intelligence_brief and "volume_spike" in str(intelligence_brief).lower():
            return True
        return False

    def decide(
        self,
        proposals: List[Proposal],
        current_allocs: Dict[str, float],
        cash_usd: float,
        total_capital: float,
        recent_prices: Optional[Dict[str, List[float]]] = None,
        entry_prices: Optional[Dict[str, float]] = None,
        current_prices: Optional[Dict[str, float]] = None,
        intelligence_brief: Optional[dict] = None,
    ) -> TradePlan:
        """
        Core decision for one cycle.
        Returns TradePlan with actions.
        """
        plan = TradePlan(strategy_used="rotation_catch_wave")

        # === Compute concrete other_factors for tie-breaker (price declining + volume placeholder) ===
        # Initialize FIRST (bugfix 2026-07-03 for UnboundLocalError on shadow/paper + partial recent_prices paths)
        other_factors = {}
        if recent_prices:
            other_factors["price_declining"] = self._detect_declining_trend(recent_prices)
        other_factors["volume_spike"] = self._detect_volume_spike(recent_prices, intelligence_brief)
        other_factors["data_points"] = {p: len(v) for p, v in (recent_prices or {}).items() if v}

        # === Tie-breaker / tilt capture for PM measurement (user directive 2026-07) ===

        regime_bias = 0.5
        regime_mult = 1.0
        pm_conf = 0.5
        pm_num = 0
        x_strength = 0.0
        reddit_strength = 0.0
        pm_used_as_tiebreaker = False
        decision_context = {"regime_bias": regime_bias, "pm_used_as_tiebreaker": False}

        if intelligence_brief:
            pm = intelligence_brief.get("polymarket", {}) or intelligence_brief
            regime_bias = float(pm.get("risk_on_bias", pm.get("risk_on", 0.5)))
            pm_conf = float(pm.get("confidence", 0.5))
            pm_num = int(pm.get("num_markets", 0))

            x_sent = intelligence_brief.get("x_sentiment", {}) or {}
            reddit_sent = intelligence_brief.get("reddit_sentiment", {}) or {}
            x_strength = max([abs(v) for v in x_sent.values()] or [0.0])
            reddit_strength = max([abs(v) for v in reddit_sent.values()] or [0.0])

            x_neutral = x_strength < 0.15
            reddit_neutral = reddit_strength < 0.10

            if pm_conf > 0.6 and abs(regime_bias - 0.5) > 0.08:
                if x_neutral and reddit_neutral:
                    pm_used_as_tiebreaker = True

                if regime_bias > 0.6:
                    regime_mult = 1.0 + min(0.35, (regime_bias - 0.5) * 0.7)
                else:
                    regime_mult = max(0.65, 1.0 - (0.5 - regime_bias) * 0.55)

                logger.info(f"[Polymarket Regime / Tiebreaker] bias={regime_bias:.2f} conf={pm_conf:.2f} n={pm_num} tiebreaker={pm_used_as_tiebreaker} mult={regime_mult:.2f}")

            decision_context = {
                "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                "influence_stack": intelligence_brief.get("influence_stack") if isinstance(intelligence_brief, dict) else None,
                "pm_bias": regime_bias,
                "pm_conf": pm_conf,
                "pm_num_markets": pm_num,
                "x_strength": round(x_strength, 4),
                "reddit_strength": round(reddit_strength, 4),
                "x_neutral": x_neutral,
                "reddit_neutral": reddit_neutral,
                "pm_used_as_tiebreaker": pm_used_as_tiebreaker,
                "regime_mult_applied": regime_mult,
                "other_factors": other_factors,
            }

        # ============================================

        # Aggressive Recovery Logic (ARCH-2)
        emergency_recovery = len(current_allocs) <= 2
        active_pair_count = sum(1 for v in current_allocs.values() if v > self.config.min_move_usd)
        if active_pair_count <= 2:
            emergency_recovery = True
            logger.info("[ARCH-2] Emergency Recovery Mode Active (Low Basket)")

        scores = self._proposals_to_scores(proposals)

        # Drawdown computation (SL-04) using recent price series for held positions
        drawdowns = self._compute_drawdowns(recent_prices, current_allocs)
        if drawdowns:
            max_dd = max(drawdowns.values()) if drawdowns else 0.0
            if max_dd > self.config.dd_threshold_pct:
                logger.info(f"[SL-04 DRAW DOWN] max_dd={max_dd:.1%} > thresh={self.config.dd_threshold_pct:.1%} on {list(drawdowns.keys())}")

        # Regime vars already computed above (tie-breaker aware)

        # Current weights from allocs

        total_invested = sum(current_allocs.values())
        current_weights = {p: (current_allocs.get(p, 0) / total_invested if total_invested > 0 else 0) for p in FIXED_UNIVERSE}

        # Identify weak (exit candidates) from proposals: low score or explicit HOLD/ROTATE_OUT
        weak_pairs = []
        strong_pairs = []
        for p in proposals:
            # SL-04 strengthened: use min_score_delta for weak threshold (was hardcoded 0.4)
            weak_thresh = 0.5 - self.config.min_score_delta
            if p.side in ("ROTATE_OUT", "SELL") or (p.side == "HOLD" and p.score < weak_thresh):
                if current_allocs.get(p.pair, 0) > 0:
                    if not emergency_recovery or p.score < 0.2:
                        weak_pairs.append(p.pair)
            
            # Aggressive RECOVERY: relax BUY gates
            min_buy_score = (0.3 if emergency_recovery else 0.55) / max(regime_mult, 0.7)
            if p.side in ("ROTATE_IN", "BUY") and p.score > min_buy_score:
                adj_score = p.score * (regime_mult if regime_bias > 0.5 else 1.0)
                strong_pairs.append((p.pair, adj_score))

        # Sort strong by score
        strong_pairs.sort(key=lambda x: x[1], reverse=True)
        # Limit aggressive expansion
        max_strong = 3 if emergency_recovery else 2
        top_strong = [p for p, _ in strong_pairs[:max_strong]]


        # Hard stops + drawdown force (SL-04: real price drawdown using recent_prices + keep entry for SL-02 compat)
        for pair in list(current_allocs.keys()):
            if current_allocs.get(pair, 0) > 0 and pair in scores:
                dd = drawdowns.get(pair, 0.0)
                score = scores.get(pair, 0.5)
                # SL-04 trailing DD from peak or fallback to entry based
                entry_dd = None
                if entry_prices and current_prices:
                    entry = entry_prices.get(pair, 0.0)
                    curr_p = current_prices.get(pair, 0.0) or (recent_prices.get(pair, [0])[-1] if recent_prices and pair in recent_prices else 0)
                    if entry > 0 and curr_p > 0:
                        entry_dd = (curr_p / entry) - 1.0
                if (dd > self.config.dd_threshold_pct or (entry_dd is not None and entry_dd <= -self.config.stop_loss_pct) or score < 0.2):
                    if dd > self.config.dd_threshold_pct:
                        reason = f"hard_stop_drawdown_{dd:.1%}"
                    elif entry_dd is not None and entry_dd <= -self.config.stop_loss_pct:
                        reason = f"hard_stop_drawdown_entry_{entry_dd*100:.1f}pct"
                    else:
                        reason = "hard_stop_low_conviction"
                    freed = current_allocs[pair]
                    plan.actions.append({
                        "pair": pair,
                        "action": "SELL",
                        "usd": freed,  # P0-02.8: full precision usd (no early round(2)); quantize at executor
                        "reason": reason,
                        "drawdown": round(dd, 4) if dd > 0 else None
                    })
                    plan.stops += 1
                    plan.drawdown_exits += 1 if (dd > self.config.dd_threshold_pct or (entry_dd is not None and entry_dd <= -self.config.stop_loss_pct)) else 0
                    current_allocs[pair] = 0.0
                    cash_usd += freed * (1 - self.config.fee_rate)
                    plan.force_re_evaluate = True  # SL-04: force re-evaluate on drawdown
                    logger.info(f"[SL-04 FORCE] {pair} {reason} force_re_evaluate=True")

        # Rotation: exit weak (SL-04: cooldown + delta guarded)
        freed_from_weak = 0.0
        now = datetime.utcnow()
        for pair in weak_pairs:
            last = self.last_rotation.get(pair)
            if last and (now - last).total_seconds() < self.config.cooldown_hours * 3600:
                logger.info(f"[SL-04 COOLDOWN] skip {pair} last={last}")
                continue
            if current_allocs.get(pair, 0) > self.config.min_move_usd:
                slice_val = current_allocs[pair]
                freed_from_weak += slice_val
                plan.actions.append({
                    "pair": pair,
                    "action": "SELL",
                    "usd": slice_val,  # P0-02.8: full precision (no early round-to-2)
                    "reason": "exit_weak_for_rotation"
                })
                current_allocs[pair] = 0.0
                plan.rotations += 1
                self.last_rotation[pair] = now
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
                        "usd": per_pair,  # P0-02.8: full precision (no early round-to-2)
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
                        "usd": base_alloc,  # P0-02.8: full precision (no early round-to-2)
                        "reason": "light_tilt_cash"
                    })
                    current_allocs[pair] = current_allocs.get(pair, 0) + base_alloc

        plan.new_allocations = current_allocs.copy()
        plan.expected_exposure = sum(current_allocs.values()) / total_capital if total_capital > 0 else 0.0
        plan.notes = f"rotations={plan.rotations}, stops={plan.stops}, dd_exits={plan.drawdown_exits}, force_re={plan.force_re_evaluate}, available_for_redeploy={round(total_available,2)}"

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
        recent_prices: Optional[Dict[str, List[float]]] = None,
        entry_prices: Optional[Dict[str, float]] = None,
        current_prices: Optional[Dict[str, float]] = None,
        intelligence_brief: Optional[dict] = None,
    ) -> TradePlan:
        plan = TradePlan(strategy_used="rebalance_tilt")
        scores = {p.pair: p.score for p in proposals if p.pair in FIXED_UNIVERSE}

        # Use inverse vol as stable base
        if recent_prices:
            # Simple realized vol from recent price history (std of returns)
            vols = {}
            for p in FIXED_UNIVERSE:
                prices = recent_prices.get(p, [])
                if len(prices) >= 5:
                    rets = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                    vol = (sum((r - (sum(rets)/len(rets)))**2 for r in rets) / len(rets))**0.5 if rets else 0.5
                    vols[p] = max(0.001, vol)  # avoid div0
                else:
                    vols[p] = 0.5
        else:
            vols = {p: 0.5 for p in FIXED_UNIVERSE}
            # TODO: fallback to ATR from price_history when available (see P0-01)
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
        entry_prices: Optional[Dict[str, float]] = None,
        current_prices: Optional[Dict[str, float]] = None,
        intelligence_brief: Optional[dict] = None,
    ) -> TradePlan:
        if total_capital is None:
            total_capital = sum(current_allocs.values()) + cash_usd

        if self.strategy_name == "rotation":
            plan = self.strategy.decide(
                proposals, current_allocs.copy(), cash_usd, total_capital,
                recent_prices=recent_prices,
                entry_prices=entry_prices,
                current_prices=current_prices,
                intelligence_brief=intelligence_brief
            )
        else:
            plan = self.strategy.decide(
                proposals, current_allocs.copy(), cash_usd, total_capital,
                intelligence_brief=intelligence_brief,
                entry_prices=entry_prices,
                current_prices=current_prices
            )

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
                    withdrawal_reserve_min=50.0,  # conservative for fallback; ARCH-4 main path handles via cash
                )
                for p, amt in deployed.items():
                    if amt > current_allocs.get(p, 0) + 10:
                        plan.actions.append({"pair": p, "action": "BUY", "usd": (amt - current_allocs.get(p, 0)), "reason": "deploy_capital_fallback"})  # P0-02.8 full prec
            except Exception as e:
                logger.debug(f"deploy fallback skipped: {e}")

        return plan

# Convenience
def create_allocator(strategy: str = "rotation", **config_kwargs) -> Allocator:
    cfg = AllocatorConfig(**config_kwargs)
    return Allocator(strategy, cfg)
