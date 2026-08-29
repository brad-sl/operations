"""
P4-05b: Daily rebalance orchestration (CR-03 window + ARCH-4 + legacy fallback).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Dict, Any
try:
    from .context import AccountContext
except Exception:
    AccountContext = None

from phase6.core.allocation_engine import compute_inverse_vol_allocations, rebalance_plan
from phase6.core.evaluation import evaluate_universe
from phase6.core.sentiment_scorer import load_sentiment_scores
from phase6.scripts.deploy_capital import deploy_capital
from src.capital_allocation.withdrawal_reserve import enforce_withdrawal_reserve

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)


class RebalanceCoordinator:
    """Owns daily rebbalance body; runner keeps thin delegate + shared finalize helpers."""

    def perform_daily(self, runner: "Phase6Runner", account_context: Optional["AccountContext"] = None) -> None:
                logger.info("=== Daily Rebalance ===")

                from phase6.core.strategic_brief_loader import log_brief_for_rebalance

                runner._last_strategic_brief = log_brief_for_rebalance()

                from phase6.core.usdc_park_transitions import plan_usdc_park_for_daily_rebalance

                park_plan = plan_usdc_park_for_daily_rebalance(runner)
                if park_plan.unwind_summary and not park_plan.unwind_summary.get("skipped"):
                    from phase6.core.decision_context import record_rebalance_decision

                    record_rebalance_decision(
                        runner,
                        path="usdc_park_redeploy_unwind",
                        actions_taken=[park_plan.unwind_summary.get("sell") or {}],
                        proposals=None,
                        plan=None,
                        executed_count=1 if park_plan.unwind_summary.get("ok") else 0,
                        skipped=[],
                        extra={
                            **park_plan.unwind_summary,
                            "transition": park_plan.transition_note,
                        },
                    )

                if park_plan.run_park and park_plan.park_summary is not None:
                    from phase6.core.decision_context import record_rebalance_decision

                    record_rebalance_decision(
                        runner,
                        path="usdc_park",
                        actions_taken=park_plan.park_summary.get("sells") or [],
                        proposals=None,
                        plan=None,
                        executed_count=sum(
                            1 for s in (park_plan.park_summary.get("sells") or []) if s.get("success")
                        ),
                        skipped=[],
                        extra={
                            **park_plan.park_summary,
                            "transition": park_plan.transition_note,
                            "operational_phase": park_plan.operational_phase,
                        },
                    )
                    runner._finalize_daily_rebalance(
                        executed=sum(
                            1 for s in (park_plan.park_summary.get("sells") or []) if s.get("success")
                        ),
                        skipped=[],
                        pairs_before=0,
                        pairs_after=0,
                        capital_deployed_usd=float(park_plan.park_summary.get("convert_usd") or 0),
                    )
                    return

                # Fresh cycle: do not carry BUY order_ids from prior runs into CR-03 re-attach
                runner._recent_buy_order_ids = {}
                if getattr(runner, "stop_loss_coordinator", None):
                    runner.stop_loss_coordinator.set_buy_order_ids({})

                # Production hardening: enforce withdrawal reserve before any allocation
                try:
                    # Fable-5 / P6-143/145 G4: use config-driven reserve + pass projected targets
                    from phase6.core.runtime_knobs import min_reserve_usd as _min_reserve_usd

                    min_reserve = _min_reserve_usd(getattr(runner, "config_dict", None))
                    usd_balance = runner.exchange.get_account_balance("USD") or 0.0
                    raw_enriched = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
                    # Normalize: some paths return flat {pair: data}, others return {"positions": ..., "value_usd": ..., "verified": ...}
                    if isinstance(raw_enriched, dict) and "positions" in raw_enriched:
                        current_positions = raw_enriched.get("value_usd") or raw_enriched.get("positions") or {}
                    else:
                        current_positions = raw_enriched or {}
                    total_capital = usd_balance + sum(
                        float(p.get("usd_value", 0)) if isinstance(p, dict) else float(p or 0)
                        for p in (current_positions.values() if isinstance(current_positions, dict) else [])
                    )
                    # Projected target for enforcement (use inverse-vol placeholder; real daily rebal will have real targets)
                    from phase6.core.allocation_engine import compute_inverse_vol_allocations
                    dummy_vols = {pair: 0.65 for pair in runner.FIXED_UNIVERSE}
                    projected_targets = compute_inverse_vol_allocations(dummy_vols)
                    adjusted, info = enforce_withdrawal_reserve(
                        target_allocations_usd=projected_targets,
                        current_reserve_usd=usd_balance,
                        min_reserve_usd=min_reserve,
                        total_capital=total_capital or usd_balance
                    )
                    deployable_cash = max(0.0, usd_balance - min_reserve)
                    if info.get("enforced", False):
                        flag_msg = (info.get("flag", {}) or {}).get("message", "unknown") if isinstance(info.get("flag"), dict) else str(info.get("enforced", info))
                        logger.warning(f"[HARDENING] Withdrawal reserve active: {flag_msg}")
                    if deployable_cash < usd_balance * 0.1:
                        logger.warning(f"Reserve guard active: only ${deployable_cash:.2f} deployable after ${min_reserve} reserve")
                except Exception as e:
                    logger.error(f"[HARDENING] Withdrawal reserve check failed: {e}", exc_info=True)

                basket = getattr(runner, "FIXED_UNIVERSE", [])
                raw_pos = getattr(runner, "portfolio", None) and runner.portfolio.get_enriched_positions() or {}
                if isinstance(raw_pos, dict) and "positions" in raw_pos:
                    current_positions = raw_pos.get("positions") or raw_pos.get("value_usd") or {}
                else:
                    current_positions = raw_pos or {}

                pre_positions = current_positions

                def _refresh_positions_for_sl() -> Dict[str, Any]:
                    """Post-trade bag sizes so CR-03 SL covers full position after adds."""
                    raw = (
                        getattr(runner, "portfolio", None)
                        and runner.portfolio.get_enriched_positions()
                        or {}
                    )
                    if isinstance(raw, dict) and "positions" in raw:
                        return raw.get("positions") or {}
                    return raw or {}

                # Wrap core rebalance logic (order changes) inside suspend_reattach_context
                with runner.stop_loss_coordinator.suspend_reattach_context(
                    basket,
                    pre_positions,
                    refresh_positions=_refresh_positions_for_sl,
                ):
                    logger.info("[CR-03] Entered suspend_reattach_context - performing rebalance body")

                    # CR-03.3: Execute rebalance inside protected context
                    from phase6.core.runner_capital_events import (
                        effective_allocator_cash_usd,
                        filter_trade_plan_manual_cooldown,
                        filter_trade_plan_near_open_stop,
                        get_deployment_cooldown_pairs,
                    )
                    from phase6.core.add_risk_sizer import filter_trade_plan_add_risk

                    cash = float(runner.exchange.get_account_balance("USD") or 0)
                    alloc_cash = effective_allocator_cash_usd(runner)
                    manual_hold = float(getattr(runner, "_manual_liquidation_cash_hold_usd", 0.0) or 0.0)
                    if manual_hold > 0:
                        logger.info(
                            "[MANUAL-SELL] allocator cash reduced by hold $%.2f (raw cash $%.2f -> deploy $%.2f)",
                            manual_hold,
                            cash,
                            alloc_cash,
                        )

                    # ARCH-4: Use new unified Allocator when flag is set (paper trade / new production path)
                    if runner._use_primary_allocator_path():
                        logger.info("[ARCH-4] Using new Allocator + RotationStrategy path (replacing direct deploy_capital)")

                        # Force fresh evaluation for daily rebalance (the key decision point), regardless of cycle freshness guard.
                        # This ensures rebalance always sees the latest signals.
                        sentiment_scores = load_sentiment_scores(universe=runner.FIXED_UNIVERSE)
                        proposals = evaluate_universe(
                            basket=runner.FIXED_UNIVERSE,
                            sentiment=sentiment_scores,
                            rsi_values=getattr(runner, "rsi_values", {}),
                            mode="weighted",
                            include_scanner=True
                        )

                        # Normalize current_positions to {pair: float_usd_value} for allocator
                        # (raw from portfolio can be dicts with "value_usd" etc.)
                        norm_allocs = {}
                        for k, v in (current_positions or {}).items():
                            if isinstance(v, dict):
                                norm_allocs[k] = float(v.get("value_usd", v.get("amount", 0.0)))
                            else:
                                norm_allocs[k] = float(v) if v else 0.0

                        total_cap = cash + sum(norm_allocs.values())
                        from phase6.core.runtime_knobs import create_allocator_from_config

                        allocator = create_allocator_from_config(
                            "rotation", getattr(runner, "config_dict", None)
                        )
                        plan = allocator.allocate(
                            proposals=proposals,
                            current_allocs=norm_allocs,
                            cash_usd=alloc_cash,
                            total_capital=total_cap
                        )
                        plan = filter_trade_plan_manual_cooldown(runner, plan)
                        # Soft/hard gap gates: no light_tilt/adds into bags sitting on their stop
                        plan = filter_trade_plan_near_open_stop(runner, plan)

                        # REGIME-CASH: regime → cash park / entry gates (RSI+sentiment+lockout)
                        try:
                            from phase6.core.regime_cash_policy import apply_to_runner_plan

                            plan = apply_to_runner_plan(
                                runner,
                                plan,
                                sentiment_scores=sentiment_scores,
                                rsi_values=getattr(runner, "rsi_values", {}) or {},
                            )
                        except Exception as e:
                            logger.warning("[REGIME-CASH] filter skipped: %s", e)

                        # Factor-based clip on BUY *adds* into existing stacks (regime-aware)
                        try:
                            plan = filter_trade_plan_add_risk(runner, plan)
                        except Exception as e:
                            logger.warning("[ADD-RISK] filter skipped: %s", e)

                        # First-fill probation: no-history / ungraduated adds → tryout size + seat cap
                        try:
                            from phase6.core.first_fill_probation import (
                                filter_trade_plan_first_fill,
                            )

                            plan = filter_trade_plan_first_fill(runner, plan)
                        except Exception as e:
                            logger.warning("[FIRST-FILL] filter skipped: %s", e)

                        # RSI-primary / sentiment-reinforce: hard ticket+pair caps + sent-only haircut
                        # (binds on Emergency Recovery; does not auto-sell existing book)
                        try:
                            from phase6.core.rsi_primary_deploy import (
                                filter_trade_plan_rsi_primary_deploy,
                            )

                            plan = filter_trade_plan_rsi_primary_deploy(
                                runner,
                                plan,
                                sentiment_scores=sentiment_scores,
                                rsi_values=getattr(runner, "rsi_values", {}) or {},
                            )
                        except Exception as e:
                            logger.warning("[RSI-PRIMARY] filter skipped: %s", e)

                        # Run-phase gate: block NEW buys in extension/exhaustion/distribution
                        try:
                            from phase6.core.run_phase_deploy import (
                                filter_trade_plan_run_phase_deploy,
                            )

                            plan = filter_trade_plan_run_phase_deploy(runner, plan)
                        except Exception as e:
                            logger.warning("[RUN-PHASE] filter skipped: %s", e)

                        # P1 ignition scout: shadow board always; propose mode may append early BUY hints
                        try:
                            from phase6.core.run_lifecycle import (
                                apply_ignition_proposals_to_plan,
                                run_ignition_scout,
                            )

                            # Refresh scout board each rebalance (shadow)
                            try:
                                pool = list(
                                    (runner.config_dict.get("phase_6_specific") or {}).get(
                                        "opportunity_pool"
                                    )
                                    or (runner.config_dict.get("global_settings") or {}).get(
                                        "pairs"
                                    )
                                    or []
                                )
                                if pool:
                                    run_ignition_scout(
                                        pool,
                                        config_dict=runner.config_dict,
                                        sentiment_by_pair=sentiment_scores or {},
                                        write_board=True,
                                    )
                            except Exception as _sc_e:
                                logger.debug("[IGNITION-SCOUT] board refresh: %s", _sc_e)

                            plan = apply_ignition_proposals_to_plan(
                                runner, plan, config_dict=runner.config_dict
                            )
                            # Re-apply hard gates if proposals added
                            if any(
                                a.get("ignition_scout")
                                for a in (plan.actions or [])
                                if isinstance(a, dict)
                            ):
                                from phase6.core.rsi_primary_deploy import (
                                    filter_trade_plan_rsi_primary_deploy,
                                )
                                from phase6.core.run_phase_deploy import (
                                    filter_trade_plan_run_phase_deploy,
                                )

                                plan = filter_trade_plan_rsi_primary_deploy(
                                    runner,
                                    plan,
                                    sentiment_scores=sentiment_scores,
                                    rsi_values=getattr(runner, "rsi_values", {}) or {},
                                )
                                plan = filter_trade_plan_run_phase_deploy(runner, plan)
                        except Exception as e:
                            logger.warning("[IGNITION-SCOUT] skipped: %s", e)

                        # Respect trade buffer: do not churn on pairs traded in the recent window.
                        # Prevents immediate rotation of newly entered positions on the daily rebalance.
                        buffer_hours = runner.config_dict.get("global_settings", {}).get("trade_buffer_hours", 24)
                        recent_pairs = set()
                        if hasattr(self, "trade_ledger"):
                            try:
                                recent_trades = runner.trade_ledger.get_recent_trades(hours=buffer_hours)
                                recent_pairs = {t.get("pair") for t in recent_trades if t.get("pair")}
                            except Exception:
                                pass
                        if recent_pairs:
                            original_len = len(plan.actions)
                            plan.actions = [a for a in plan.actions if a.get("pair") not in recent_pairs]
                            suppressed = original_len - len(plan.actions)
                            if suppressed > 0:
                                logger.info(f"[TRADE BUFFER] Suppressed {suppressed} actions on pairs traded in last {buffer_hours}h to avoid churn: {recent_pairs}")

                        runner._last_plan = plan  # for dashboard and logs
                        executed, skipped = runner._execute_trade_plan(plan)
                        from phase6.core.decision_context import record_rebalance_decision

                        record_rebalance_decision(
                            runner,
                            path="arch4_rotation",
                            actions_taken=plan.actions,
                            proposals=proposals,
                            plan=plan,
                            executed_count=executed,
                            skipped=skipped,
                        )
                        logger.info(
                            f"[ARCH-4] Rebalance complete via new stack. Strategy={plan.strategy_used}, "
                            f"actions={len(plan.actions)}, exposure={plan.expected_exposure:.1%}"
                        )
                        pairs_before = len(norm_allocs)
                        runner._finalize_daily_rebalance(
                            executed,
                            skipped,
                            pairs_before=pairs_before,
                            pairs_after=pairs_before,
                            capital_deployed_usd=float(sum(a.get("usd", a.get("usd_amount", 0)) for a in plan.actions)),
                        )
                        return

                    if not runner.use_new_allocator:
                        logger.warning("[LEGACY FALLBACK] use_new_allocator=False — deploy_capital path")
                    # This is the logic that demonstrated +6-24pp edge vs hold in full 365d diagnostics (tuned smaller cap, permissive min_sent -0.30)
                    logger.info("[OLD-STYLE WIRED] Using permissive_deploy via deploy_capital (rebalance_style=permissive_deploy from config, rebalance_cap_usd tuned to 150). Dashboard will be fed by this path.")
                    # Compute target weights using inverse volatility + sentiment
                    sentiment_scores = load_sentiment_scores(universe=runner.FIXED_UNIVERSE)

                    # Use deploy_capital to handle both capital deployment rules and static allocation
                    # For daily rebalance, all cash is potentially available
                    # Rebalance cap now comes from config (no more hard-coded $50)
                    # Current scope (narrow): only limits new capital deployed from USD wallet.
                    # Internal rotations (sell weak pair → buy strong pair) are NOT capped by this value.
                    # See MASTER_TASK_TRACKING.md → "Future Backtest Item: Rebalance Cap Scope"

                    # Ensure deployable_cash is defined (rebalance might skip daily reserve check if already handled)
                    from phase6.core.runtime_knobs import min_reserve_usd as _min_reserve_usd

                    min_reserve = _min_reserve_usd(getattr(runner, "config_dict", None))
                    deployable_cash = max(0.0, alloc_cash)

                    from phase6.core.runtime_knobs import rebalance_cap_usd as _rebalance_cap_usd

                    rebalance_cap = _rebalance_cap_usd(getattr(runner, "config_dict", None))
                    # Normalize positions (P6-001 fix)
                    # After boundary fix in get_enriched_positions, keys are now consistent -USD pairs
                    # and we must use "value_usd" (never "amount").
                    # Assertions enforce the contract required by Fable 5 review + standing sticky-rebalancing rules.
                    norm_positions = {}
                    for k, v in current_positions.items():
                        if isinstance(v, dict):
                            norm_positions[k] = float(v.get("value_usd", v.get("amount", 0.0)))
                        else:
                            norm_positions[k] = float(v) if v else 0.0

                    # Contract assertions (fail fast if the P6-001 bug regresses)
                    if norm_positions:
                        bad_keys = [k for k in norm_positions if not k.endswith("-USD")]
                        if bad_keys:
                            raise ValueError(f"P6-001 regression: bare currency keys in norm_positions: {bad_keys}")
                        total_val_check = sum(norm_positions.values())
                        if total_val_check < 0 or total_val_check > 1e7:  # sanity upper bound for this system
                            logger.warning(f"P6-001 warning: suspicious total norm value ${total_val_check}")
                    total_cash = cash + sum(norm_positions.values())

                    # Apply deployment rules (pass normalized floats)
                    # Use config block hours (default 72) — do not hardcode 24
                    cooldown_pairs = get_deployment_cooldown_pairs(runner)
                    if cooldown_pairs:
                        try:
                            from phase6.core.runner_capital_events import _runner_capital_settings

                            _bh = int(
                                float(
                                    _runner_capital_settings(runner).get(
                                        "stop_loss_exchange_block_rebuy_hours", 72
                                    )
                                )
                            )
                        except Exception:
                            _bh = 72
                        logger.info(
                            f"[RECOVERY] {_bh}h cooldown active on pairs: {cooldown_pairs}"
                        )
                    runner._write_recovery_state(cooldown_pairs)
                    from phase6.core.runtime_knobs import deploy_min_rsi as _deploy_min_rsi

                    new_allocations = deploy_capital(
                        current_allocations=norm_positions,
                        new_capital=min(rebalance_cap, deployable_cash),
                        sentiment_scores=sentiment_scores,
                        source="reserve",
                        candidate_pairs=runner.FIXED_UNIVERSE,
                        rsi_values=runner.rsi_values,
                        min_rsi=_deploy_min_rsi(getattr(runner, "config_dict", None)),
                        cooldown_pairs=cooldown_pairs
                    )

                    # Generate rebalance plan based on new allocations
                    target_weights_pct = {k: round(v / total_cash * 100, 4) for k, v in new_allocations.items()}
                    plan = rebalance_plan(norm_positions, target_weights_pct, total_capital=total_cash)

                    logger.info(f"Daily Rebalance: cash=${cash:.2f} | target_weights={new_allocations}")

                    executed = 0
                    skipped = []

                    for move in plan:
                        pair = move.get("pair")
                        action = move.get("action", "").upper()
                        usd_amount = float(move.get("usd_amount", 0))


                # === LIVE TEST OVERRIDE: Force small safe order size ===
                        if runner.shadow_mode:
                            logger.info(f"[SHADOW] {action} ${usd_amount:.2f} {pair}")
                            executed += 1
                            continue

                        try:
                            if action == "BUY":
                                result = runner.order_executor.execute_buy(pair, usd_amount)
                                if result.get('success'):
                                    executed += 1
                                    if result.get('sl_attached'):
                                        logger.info(f"[REBALANCE BUY] {pair}: ${usd_amount:.2f} | SL attached | order_id={result.get('order_id')}")
                                    else:
                                        logger.warning(f"[REBALANCE BUY] {pair}: ${usd_amount:.2f} | SL failed")
                                else:
                                    skipped.append({"pair": pair, "reason": f"buy failed: {result.get('error')}"})

                            elif action == "SELL":
                                result = runner.order_executor.execute_sell(pair, usd_amount)
                                if result.get("success"):
                                    executed += 1
                                    logger.info(f"[REBALANCE SELL] {pair}: executed via executor")
                                else:
                                    skipped.append({"pair": pair, "reason": "sell failed: " + str(result.get("error", "unknown"))})

                        except Exception as e:
                            logger.exception(f"[REBALANCE ERROR] {pair}: {e}")
                            skipped.append({"pair": pair, "reason": str(e)})

                    logger.info(f"[CR-03] Rebalance body completed inside context. Executed={executed}, Skipped={len(skipped)}")

                    from phase6.core.decision_context import record_rebalance_decision

                    record_rebalance_decision(
                        runner,
                        path="legacy_deploy_capital",
                        actions_taken=[
                            {
                                "pair": m.get("pair"),
                                "action": str(m.get("action", "")).upper(),
                                "usd": float(m.get("usd_amount", 0)),
                                "reason": "rebalance_plan",
                            }
                            for m in (plan if isinstance(plan, list) else [])
                        ],
                        proposals=None,
                        plan=None,
                        executed_count=executed,
                        skipped=skipped,
                        extra={"target_weights": target_weights_pct if "target_weights_pct" in locals() else {}},
                    )

                    # Refresh positions after trades so re-attach uses new holdings
                    runner.portfolio.refresh()
                    new_positions = runner.portfolio.get_enriched_positions() or {}

                # Post-context: state update (legacy path)
                new_positions = runner.portfolio.get_enriched_positions() or {}
                runner._finalize_daily_rebalance(
                    executed,
                    skipped,
                    pairs_before=len(norm_positions) if "norm_positions" in locals() else 0,
                    pairs_after=len(new_positions) if new_positions else 0,
                    capital_deployed_usd=float(min(rebalance_cap, cash))
                    if "rebalance_cap" in locals() and "cash" in locals()
                    else 0.0,
                )

