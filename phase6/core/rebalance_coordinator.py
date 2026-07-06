"""
P4-05b: Daily rebalance orchestration (CR-03 window + ARCH-4 + legacy fallback).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from phase6.core.allocation_engine import compute_inverse_vol_allocations, rebalance_plan
from phase6.core.allocator import create_allocator
from phase6.core.evaluation import evaluate_universe
from phase6.core.sentiment_scorer import load_sentiment_scores
from phase6.scripts.deploy_capital import deploy_capital
from src.capital_allocation.withdrawal_reserve import enforce_withdrawal_reserve

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)


class RebalanceCoordinator:
    """Owns daily rebbalance body; runner keeps thin delegate + shared finalize helpers."""

    def perform_daily(self, runner: "Phase6Runner") -> None:
                logger.info("=== Daily Rebalance ===")

                # Fresh cycle: do not carry BUY order_ids from prior runs into CR-03 re-attach
                runner._recent_buy_order_ids = {}
                if getattr(runner, "stop_loss_coordinator", None):
                    runner.stop_loss_coordinator.set_buy_order_ids({})

                # Production hardening: enforce withdrawal reserve before any allocation
                try:
                    # Fable-5 / P6-143/145 G4: use config-driven reserve + pass projected targets
                    wr = runner.config_dict.get("withdrawal_reserve", {})
                    min_reserve = float(wr.get("min_reserve_usd", 200.0))
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

                # Wrap core rebalance logic (order changes) inside suspend_reattach_context
                with runner.stop_loss_coordinator.suspend_reattach_context(basket, pre_positions):
                    logger.info("[CR-03] Entered suspend_reattach_context - performing rebalance body")

                    # CR-03.3: Execute rebalance inside protected context
                    cash = runner.exchange.get_account_balance("USD")

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
                        allocator = create_allocator("rotation", min_move_usd=50.0, min_score_delta=0.05, stop_loss_pct=0.12)
                        plan = allocator.allocate(
                            proposals=proposals,
                            current_allocs=norm_allocs,
                            cash_usd=cash,
                            total_capital=total_cap
                        )

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
                    reserve_cfg = {"min_reserve_usd": 250.0}
                    min_reserve = reserve_cfg.get("min_reserve_usd", 250.0)
                    usd_balance = runner.exchange.get_account_balance("USD")
                    deployable_cash = max(0.0, usd_balance - min_reserve)

                    rebalance_cap = runner.config_dict.get("global_settings", {}).get("rebalance_cap_usd", 200.0)
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
                    cooldown_pairs = runner._get_recently_stopped_pairs(hours=24)
                    if cooldown_pairs:
                        logger.info(f"[RECOVERY] 24h cooldown active on pairs: {cooldown_pairs}")
                    runner._write_recovery_state(cooldown_pairs)
                    new_allocations = deploy_capital(
                        current_allocations=norm_positions,
                        new_capital=min(rebalance_cap, deployable_cash),
                        sentiment_scores=sentiment_scores,
                        source="reserve",
                        candidate_pairs=runner.FIXED_UNIVERSE,
                        rsi_values=runner.rsi_values,
                        min_rsi=30.0,
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

