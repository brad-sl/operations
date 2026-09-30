"""
P4-05: Thin cycle orchestrator.

Coordinates per-cycle: RSI refresh, unified evaluation (P4-02), optional mid-cycle
shadow allocator, rebalance triggers, state/dashboard hooks. Phase6Runner delegates
here to shrink the runner and keep one decision contract.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
try:
    from .context import AccountContext
except Exception:
    AccountContext = "AccountContext"  # type: ignore

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)


class CycleCoordinator:
    """Scheduler-facing cycle logic (evaluation → optional shadow plan → rebalance gate)."""

    def run_cycle(self, runner: Phase6Runner, cycle_num: int, account_context: Optional["AccountContext"] = None) -> None:
        from phase6.core.runner_capital_events import process_runner_capital_events

        new_capital_events = process_runner_capital_events(runner)
        if new_capital_events:
            logger.info(
                "[CYCLE %s] capital_events=%s",
                cycle_num,
                [e.get("event_type") for e in new_capital_events],
            )

        try:
            from phase6.core.same_session_sl_guard import process_deferred_sl_attaches

            slm = getattr(runner, "stop_loss_manager", None)
            drained = process_deferred_sl_attaches(slm)
            if drained:
                logger.info("[CYCLE %s] deferred_sl=%s", cycle_num, drained)
        except Exception as de:
            logger.debug("[CYCLE] deferred SL drain skipped: %s", de)

        now = datetime.now()
        time_due = runner._should_rebalance(now)
        hybrid_due = False
        if not time_due:
            hybrid_due = runner._evaluate_hybrid_rebalance()
        rebalance_needed = time_due or hybrid_due
        runner._update_price_history_and_calculate_rsi()
        self._maybe_clip_unwind(runner)
        self._maybe_rsi_event_x(runner)

        self._run_unified_evaluation(runner)
        if not rebalance_needed:
            self._maybe_mid_cycle_shadow(runner)

        logger.info(
            f"[CYCLE {cycle_num}] {now.isoformat(timespec='seconds')} | "
            f"rebalance_needed={rebalance_needed} | "
            f"last_rebalance={runner.last_rebalance_date or 'never'}"
        )

        if rebalance_needed:
            from phase6.core.pre_rebalance_data_refresh import ensure_basket_signals_ready
            from phase6.core.rebalance_quality_gate import evaluate_rebalance_gate

            coverage = ensure_basket_signals_ready(runner, cap_sec=15.0, force_refresh=True)
            gate = evaluate_rebalance_gate(runner, coverage)
            runner._last_rebalance_connectivity_ok = gate.connectivity_ok
            runner._last_rebalance_data_ready = gate.data_ready
            if not gate.allowed:
                runner._defer_rebalance_slot(gate.slot_id, gate.reasons)
            else:
                runner._clear_deferred_rebalance_slot(gate.slot_id)
                runner._perform_daily_rebalance()

        runner._save_state()
        self._reconcile_exchange_fills(runner)
        self._maybe_preserve_hold(runner)
        self._maybe_park_package(runner)
        runner._write_dashboard_cache()
        self._maybe_tryout_readiness_board(runner)

    def _maybe_preserve_hold(self, runner: Phase6Runner) -> None:
        """Preserve Hold tick: no-op unless preserve_mode.enabled; never auto-arms."""
        try:
            from phase6.core.preserve_hold import maybe_preserve_hold_tick

            out = maybe_preserve_hold_tick(runner)
            if out.get("ran") and not out.get("skipped"):
                logger.info(
                    "[PRESERVE] tick reason=%s adds_blocked=%s repair=%s e1=%s",
                    out.get("reason"),
                    out.get("adds_blocked"),
                    (out.get("repair") or {}).get("repaired"),
                    out.get("e1_order_id"),
                )
        except Exception as exc:
            logger.debug("[PRESERVE] tick skipped: %s", exc)

    def _maybe_park_package(self, runner: Phase6Runner) -> None:
        """USDC+PAXG package status; optional edge-triggered auto trim B on deploy."""
        try:
            from phase6.core.park_package import maybe_park_package_cycle

            out = maybe_park_package_cycle(runner)
            if out.get("error"):
                logger.debug("[PARK-PACKAGE] %s", out.get("error"))
            else:
                warns = out.get("consistency_warnings") or []
                trim = out.get("auto_trim_execution") or {}
                if trim.get("attempted"):
                    logger.info(
                        "[PARK-PACKAGE] auto_trim attempted ok=%s reason=%s",
                        trim.get("ok"),
                        trim.get("reason"),
                    )
                elif warns:
                    logger.info(
                        "[PARK-PACKAGE] profile=%s warnings=%s",
                        out.get("profile"),
                        warns[:3],
                    )
        except Exception as exc:
            logger.debug("[PARK-PACKAGE] skipped: %s", exc)

    def _maybe_clip_unwind(self, runner: Phase6Runner) -> None:
        """NEEDLE-01: capped USDC→USD when USD is short of wave reserve."""
        try:
            from phase6.core.deploy_clip_unwind import maybe_cycle_clip_unwind

            out = maybe_cycle_clip_unwind(runner)
            if out.get("plan", {}).get("action") == "unwind":
                logger.info(
                    "[NEEDLE-01] unwind=$%s skipped=%s ok=%s reason=%s",
                    (out.get("plan") or {}).get("unwind_usd"),
                    out.get("skipped"),
                    out.get("ok"),
                    out.get("reason"),
                )
        except Exception as exc:
            logger.debug("[NEEDLE-01] clip unwind skipped: %s", exc)

    def _maybe_rsi_event_x(self, runner: Phase6Runner) -> None:
        """NEEDLE-02 live floor: RSI wash → pair-only X. Budget-capped. No orders."""
        try:
            from phase6.core.rsi_event_x_probe import run_probe

            spend = str(getattr(runner, "mode", "") or "") == "live"
            result = run_probe(
                dry_run=not spend,
                spend_x=spend,
                top_k=2,
                floor=0.30,
                rsi_max=40.0,
            )
            if result.get("spend_x_executed") or result.get("fetched"):
                logger.info(
                    "[NEEDLE-02] probe fetched=%s spend=%s %s",
                    result.get("fetched"),
                    result.get("spend_x_executed"),
                    (result.get("plain_english") or "")[:180],
                )
        except Exception as exc:
            logger.debug("[NEEDLE-02] rsi-event X skipped: %s", exc)

    def _maybe_tryout_readiness_board(self, runner: Phase6Runner) -> None:
        """PC-03: refresh tryout sleeve readiness board (floors SSOT, eng clock, can_buy) each cycle."""
        try:
            from phase6.core.tryout_readiness import build_live_tryout_readiness

            payload = build_live_tryout_readiness(write=True)
            if payload.get("can_buy_before_next_rebalance"):
                logger.info(
                    "[TRYOUT-READINESS] can_buy=True eligible=%s",
                    payload.get("eligible_tryout_pairs"),
                )
            # drought is honest output; no log spam
            try:
                from phase6.core.needle08_ignition_rank import rank_from_scout_board

                rank_from_scout_board(write=True)
            except Exception:
                pass
        except Exception as exc:
            logger.debug("[TRYOUT-READINESS] refresh skipped: %s", exc)

    def _reconcile_exchange_fills(self, runner: Phase6Runner) -> None:
        """Ingest Coinbase FILLED orders + optional param audit (P6-FILL-RECON / P6-PARAM-AUDIT)."""
        exchange = getattr(runner, "exchange", None)
        try:
            if not exchange or getattr(exchange, "shadow_mode", True):
                return
            from phase6.core.exchange_fill_reconciler import reconcile_trading_bot_ledger

            result = reconcile_trading_bot_ledger(exchange, backfill_days=14)
            added = (result.get("sells") or {}).get("added", 0) + (result.get("buys") or {}).get("added", 0)
            if added:
                logger.info(
                    "[FILL-RECON] cycle ingest added %s rows (sells=%s buys=%s)",
                    added,
                    (result.get("sells") or {}).get("added"),
                    (result.get("buys") or {}).get("added"),
                )
            from phase6.core.exchange_fill_reconciler import reconcile_stored_exchange_fills_into_ledger

            stored = reconcile_stored_exchange_fills_into_ledger()
            if stored.get("added"):
                logger.info("[FILL-RECON] stored-jsonl backfill added %s rows", stored.get("added"))

            # Orphan dust under USD cap with no open stop (covers pre-fix residuals like LINK 2%)
            try:
                from phase6.core.sl_dust_sweep import load_dust_sweep_config, sweep_orphan_dust
                import json
                from pathlib import Path

                cfg_path = Path(__file__).resolve().parents[2] / "config" / "trading_config_phase6.json"
                full_cfg = {}
                if cfg_path.exists():
                    full_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                dcfg = load_dust_sweep_config(full_cfg)
                if dcfg.get("enabled") and dcfg.get("cycle_orphan_sweep"):
                    orphan = sweep_orphan_dust(
                        exchange,
                        config=full_cfg,
                        dry_run=False,
                    )
                    sold = [
                        r
                        for r in (orphan.get("results") or [])
                        if r.get("success") and not r.get("skipped")
                    ]
                    if sold:
                        logger.info(
                            "[DUST-SWEEP] cycle orphan sold %s pairs: %s",
                            len(sold),
                            [r.get("pair") for r in sold],
                        )
            except Exception as dust_exc:
                logger.debug("[DUST-SWEEP] cycle orphan skipped: %s", dust_exc)
        except Exception as exc:
            logger.warning("[FILL-RECON] cycle ingest skipped: %s", exc)

        try:
            import os
            if os.environ.get("PHASE6_PARAM_AUDIT_EACH_CYCLE", "").lower() in ("1", "true", "yes"):
                from phase6.core.param_audit import run_param_audit, resolve_account_id_from_exchange

                acct = resolve_account_id_from_exchange(exchange) if exchange else None
                audit = run_param_audit(acct, migrate_legacy=False)
                if audit.get("fail_count", 0):
                    logger.warning(
                        "[PARAM-AUDIT] cycle: %s fails, confidence=%s",
                        audit.get("fail_count"),
                        audit.get("confidence_score"),
                    )
        except Exception as exc:
            logger.debug("[PARAM-AUDIT] cycle skipped: %s", exc)

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
            from phase6.core.runtime_knobs import create_allocator_from_config

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

            allocator = create_allocator_from_config(
                "rotation", getattr(runner, "config_dict", None)
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