"""
P4-05: Thin cycle orchestrator.

Coordinates per-cycle: RSI refresh, unified evaluation (P4-02), optional mid-cycle
shadow allocator, rebalance triggers, state/dashboard hooks. Phase6Runner delegates
here to shrink the runner and keep one decision contract.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)


class CycleCoordinator:
    """Scheduler-facing cycle logic (evaluation → optional shadow plan → rebalance gate)."""

    def run_cycle(self, runner: Phase6Runner, cycle_num: int) -> None:
        now = datetime.now()
        rebalance_needed = runner._should_rebalance(now) or runner._evaluate_hybrid_rebalance()
        runner._update_price_history_and_calculate_rsi()

        self._run_unified_evaluation(runner)
        if not rebalance_needed:
            self._maybe_mid_cycle_shadow(runner)

        logger.info(
            f"[CYCLE {cycle_num}] {now.isoformat(timespec='seconds')} | "
            f"rebalance_needed={rebalance_needed} | "
            f"last_rebalance={runner.last_rebalance_date or 'never'}"
        )

        if rebalance_needed:
            runner._perform_daily_rebalance()

        runner._save_state()
        runner._write_dashboard_cache()

    def _run_unified_evaluation(self, runner: Phase6Runner) -> None:
        """P4-02: one evaluate_universe snapshot per cycle on primary path (freshness-guarded)."""
        from phase6.core.phase6_runner import NEW_ALLOCATOR_AVAILABLE

        if not runner._use_primary_allocator_path():
            self._legacy_signal_logging(runner)
            return

        try:
            recent_prices = []
            for pair in runner.FIXED_UNIVERSE:
                prices = runner.price_history.get_prices(pair, n=20)
                if prices:
                    recent_prices.append(prices[-1])

            atr = None
            if len(recent_prices) >= 14:
                atr = runner.atr_calculator.calculate_atr(
                    recent_prices, recent_prices, recent_prices, period=14
                )
                runner.regime_detector.detect(recent_prices, atr)

            if runner._should_run_full_evaluation():
                from phase6.core.evaluation import evaluate_universe
                from phase6.core.sentiment_scorer import load_sentiment_scores

                sentiment_scores = load_sentiment_scores(universe=runner.FIXED_UNIVERSE)
                runner._last_proposals = evaluate_universe(
                    basket=runner.FIXED_UNIVERSE,
                    sentiment=sentiment_scores,
                    rsi_values=runner.rsi_values,
                    mode="weighted",
                    include_scanner=True,
                )
                for p in runner._last_proposals:
                    if p.side not in ("HOLD", "hold"):
                        logger.info(
                            f"[ARCH-4 PROPOSAL] {p.pair}: {p.side} score={p.score:.2f} src={p.source}"
                        )
                logger.debug("[FRESHNESS] Full evaluation run due to new signal data")
            else:
                logger.debug("[FRESHNESS] Skipping full evaluation - signals not updated since last pass")
        except Exception as e:
            logger.debug(f"Unified evaluation error: {e}")

    def _legacy_signal_logging(self, runner: Phase6Runner) -> None:
        """Emergency fallback when use_new_allocator=False."""
        try:
            from phase6.core.sentiment_scorer import load_sentiment_scores

            recent_prices = []
            for pair in runner.FIXED_UNIVERSE:
                prices = runner.price_history.get_prices(pair, n=20)
                if prices:
                    recent_prices.append(prices[-1])
            atr = 0.0
            if len(recent_prices) >= 14:
                atr = runner.atr_calculator.calculate_atr(
                    recent_prices, recent_prices, recent_prices, period=14
                )
            sentiment_scores = load_sentiment_scores(universe=runner.FIXED_UNIVERSE)
            for pair in runner.FIXED_UNIVERSE:
                rsi_val = runner.rsi_values.get(pair, 50.0)
                sentiment = (
                    sentiment_scores.get(pair, 0.0)
                    if isinstance(sentiment_scores, dict)
                    else 0.0
                )
                signal = runner.signal_generator.generate_signal(
                    pair, rsi_val, atr, sentiment, mode="weighted"
                )
                if signal.signal != "HOLD":
                    logger.info(
                        f"[LEGACY FALLBACK SIGNAL] {pair}: {signal.signal} | "
                        f"conf={signal.confidence:.2f} | {signal.reason}"
                    )
        except Exception as e:
            logger.debug(f"Legacy signal logging error: {e}")

    def _maybe_mid_cycle_shadow(self, runner: Phase6Runner) -> None:
        """P4-02 shadow-only: allocator plan between rebalance windows (no live execution)."""
        if not getattr(runner, "mid_cycle_allocator_enabled", False):
            return
        if not runner.shadow_mode:
            logger.warning(
                "[P4-02] mid_cycle_allocator_enabled but not shadow_mode — skipping (live blocked)"
            )
            return
        if not runner._use_primary_allocator_path():
            return
        proposals = getattr(runner, "_last_proposals", None) or []
        if not proposals:
            return

        try:
            from phase6.core.allocator import create_allocator

            raw_pos = (
                getattr(runner, "portfolio", None)
                and runner.portfolio.get_enriched_positions()
                or {}
            )
            if isinstance(raw_pos, dict) and "positions" in raw_pos:
                current_positions = raw_pos.get("positions") or raw_pos.get("value_usd") or {}
            else:
                current_positions = raw_pos or {}

            norm_allocs = {}
            for k, v in (current_positions or {}).items():
                if isinstance(v, dict):
                    norm_allocs[k] = float(v.get("value_usd", v.get("amount", 0.0)))
                else:
                    norm_allocs[k] = float(v) if v else 0.0

            cash = float(runner.exchange.get_account_balance("USD") or 0.0)
            total_cap = cash + sum(norm_allocs.values())

            allocator = create_allocator(
                "rotation",
                min_move_usd=50.0,
                min_score_delta=0.05,
                stop_loss_pct=0.12,
            )
            plan = allocator.allocate(
                proposals=proposals,
                current_allocs=norm_allocs,
                cash_usd=cash,
                total_capital=total_cap or cash,
            )
            actions = getattr(plan, "actions", []) or []
            num_props = len(proposals)
            action_pairs = {a.get("pair") for a in actions if isinstance(a, dict)}
            accepted = sum(
                1 for p in proposals if getattr(p, "pair", None) in action_pairs
            )
            accept_rate = (accepted / num_props) if num_props else 0.0
            util = getattr(plan, "expected_exposure", 0.0)

            logger.info(
                f"[P4-02 MID-CYCLE SHADOW] actions={len(actions)} "
                f"accept_rate={accept_rate:.2%} exposure={util:.1%} "
                f"strategy={getattr(plan, 'strategy_used', 'n/a')}"
            )
            runner._last_mid_cycle_plan = plan
            # Shadow only — log would-be execution, never call _execute_trade_plan in live
            if actions:
                logger.info(f"[P4-02 SHADOW EXEC] Would execute {len(actions)} legs (not sent)")
        except Exception as e:
            logger.warning(f"[P4-02] Mid-cycle shadow failed: {e}")