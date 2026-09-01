#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Phase 6 OrderExecutor - Robust Order Execution Wrapper
"""

import logging
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class OrderExecutor:
    """Robust order executor for Phase 6."""

    def __init__(
        self,
        exchange: Any,
        stop_loss_manager: Any,
        mode: str = "shadow",
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        trade_ledger: Any = None,
    ):
        self.exchange = exchange
        self.stop_loss_manager = stop_loss_manager
        self.mode = mode.lower().strip()
        self.shadow_mode = self.mode == "shadow"
        self.logger = logger or logging.getLogger("phase6.executor")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.trade_ledger = trade_ledger

    def _record_to_ledger(self, result: Dict[str, Any], signal_source: str = "order_executor") -> None:
        if not self.trade_ledger or not result.get("success"):
            return
        try:
            self.trade_ledger.log_execution_result(
                result,
                mode=self.mode,
                exchange=self.exchange,
                signal_source=signal_source,
                stop_loss_manager=self.stop_loss_manager,
            )
        except Exception as e:
            self.logger.warning(f"Ledger record failed: {e}")

    def _generate_client_order_id(self, prefix: str = "phase6") -> str:
        return f"{prefix}-{secrets.token_hex(16)}"

    def _retry_with_backoff(self, func, *args, **kwargs) -> Dict[str, Any]:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                time.sleep(self.base_delay * (2 ** (attempt - 1)))
        return {"success": False, "error": str(last_error)}


    def execute_buy(
        self,
        pair: str,
        usd_amount: float,
        tp_pct: float = None,
        *,
        record_ledger: bool = True,
        config_dict: Optional[Dict[str, Any]] = None,
        force_market: bool = False,
        elevated_tape: bool = False,
    ) -> Dict[str, Any]:
        """Execute BUY. Default path remains market IOC.

        Limit-first only when entry_execution.limit_first.enabled AND mode=limit_first*
        (runtime_knobs / config). Default OFF. Brad Phase B: branch exists, live flag off.
        """
        if self.shadow_mode:
            # Shadow: use snapshot price as sim entry (not live trading)
            entry_price = getattr(self.exchange, 'get_price', lambda p: 0.0)(pair) or 0.0
            size = usd_amount / entry_price if entry_price > 0 else 0.0
            # P0-02: unify - quantize computed base size from usd/price (for consistent SL/ledger)
            if size > 0 and hasattr(self.exchange, 'quantize_size'):
                try:
                    size = float(self.exchange.quantize_size(pair, size))
                except Exception:
                    size = round(size, 8)
            sl_result = False
            tp_result = False
            # ENG-S3-01: shadow must not invoke live stop_loss_manager (no exchange/SL API).
            if self.stop_loss_manager:
                self.logger.debug(
                    "[SHADOW BUY] Skipping SL/TP attach (ENG-S3-01); simulated entry only"
                )
            return {
                "success": True,
                "order_id": "shadow_buy",
                "entry_price": round(entry_price, 4),
                "size": size,
                "qty": size,
                "sl_attached": sl_result,
                "tp_attached": tp_result,
                "actual_fill_used": False,
                "execution_style": "market_ioc",
                "fill_status": "full" if size > 0 else "none",
            }

        # Resolve policy (default market). Disk hot-reload only when caller omitted config_dict.
        try:
            from phase6.core.runtime_knobs import limit_first_policy

            cfg = config_dict
            if cfg is None and self.stop_loss_manager is not None:
                cfg = getattr(self.stop_loss_manager, "config", None)
            if config_dict is None:
                # Live auto path: re-read entry_execution so kill/enable work without restart
                from phase6.core.limit_first_buy_pilot import merge_live_config

                cfg = merge_live_config(cfg if isinstance(cfg, dict) else None)
            policy = limit_first_policy(cfg if isinstance(cfg, dict) else None)
        except Exception:
            from phase6.core.limit_first_buy import LimitFirstPolicy

            policy = LimitFirstPolicy(enabled=False)

        # Auto elevated from C shadow when caller did not pass elevated_tape=True
        if not elevated_tape and bool(getattr(policy, "enabled", False)):
            try:
                from phase6.core.limit_first_buy_pilot import pair_elevated_from_c_shadow

                elevated_tape = bool(pair_elevated_from_c_shadow(pair))
            except Exception:
                pass

        use_limit = (
            (not force_market)
            and bool(policy.enabled)
            and hasattr(self.exchange, "place_limit_buy")
        )

        # Phase D pilot caps / kill → fall back to market IOC (not total buy block)
        pilot_reason = "ok"
        _record_pilot = (
            self.mode == "live"
            and not getattr(self.exchange, "shadow_mode", False)
            and (
                getattr(self.exchange, "real_client", None) is not None
                or getattr(self.exchange, "sdk_client", None) is not None
                or callable(getattr(self.exchange, "_ensure_live_client", None))
            )
            # Isolation mocks often define _ensure_live_client-less plain classes;
            # require place_limit_buy AND get_order (Coinbase client surface).
            and hasattr(self.exchange, "get_order")
        )
        if use_limit:
            try:
                from phase6.core.limit_first_buy_pilot import pilot_allows_limit, record_limit_attempt

                ok_pilot, pilot_reason = pilot_allows_limit(usd_amount, policy)
                if not ok_pilot:
                    use_limit = False
                    if _record_pilot:
                        if pilot_reason == "kill_switch":
                            record_limit_attempt(
                                pair=pair, usd_amount=usd_amount, outcome="kill_market"
                            )
                        elif pilot_reason in ("pilot_max_buys", "pilot_max_usd"):
                            record_limit_attempt(
                                pair=pair, usd_amount=usd_amount, outcome="over_cap_market"
                            )
                    self.logger.info(
                        "[EXEC BUY] limit_first deferred → market (%s) %s $%.2f",
                        pilot_reason,
                        pair,
                        usd_amount,
                    )
            except Exception as pe:
                self.logger.debug("pilot gate skipped: %s", pe)

        if use_limit and policy.elevated_tape_policy == "abort" and elevated_tape:
            self.logger.info(
                "[EXEC BUY] limit_first aborted elevated tape for %s (C align)", pair
            )
            if _record_pilot:
                try:
                    from phase6.core.limit_first_buy_pilot import record_limit_attempt

                    record_limit_attempt(
                        pair=pair, usd_amount=usd_amount, outcome="elevated_abort"
                    )
                except Exception:
                    pass
            return {
                "success": False,
                "error": "elevated_tape_abort",
                "pair": pair,
                "action": "BUY",
                "side": "BUY",
                "execution_style": "aborted_elevated",
                "fill_status": "none",
                "sl_attached": False,
                "tp_attached": False,
            }

        if use_limit:
            if _record_pilot:
                try:
                    from phase6.core.limit_first_buy_pilot import record_limit_attempt

                    record_limit_attempt(
                        pair=pair, usd_amount=usd_amount, outcome="attempted"
                    )
                except Exception:
                    pass
            result = self._execute_limit_first_buy(
                pair, usd_amount, policy=policy, tp_pct=tp_pct
            )
            if _record_pilot:
                try:
                    from phase6.core.limit_first_buy_pilot import record_limit_attempt, write_pilot_report

                    if result.get("success"):
                        filled_usd = float(result.get("entry_price") or 0) * float(
                            result.get("size") or result.get("qty") or 0
                        )
                        if filled_usd <= 0:
                            filled_usd = float(usd_amount or 0)
                        record_limit_attempt(
                            pair=pair,
                            usd_amount=usd_amount,
                            outcome="filled",
                            order_id=result.get("order_id"),
                            filled_usd=filled_usd,
                            extra={
                                "execution_style": result.get("execution_style"),
                                "fill_status": result.get("fill_status"),
                                "fee_usd": result.get("fee_usd"),
                            },
                        )
                    else:
                        err = str(result.get("error") or "")
                        outcome = "unfilled" if "unfilled" in err or "skip" in err else "error"
                        record_limit_attempt(
                            pair=pair,
                            usd_amount=usd_amount,
                            outcome=outcome,
                            order_id=result.get("order_id"),
                            extra={"error": err},
                        )
                    write_pilot_report()
                except Exception:
                    pass
        else:
            def _do_buy():
                return self.exchange.place_market_buy(pair, usd_amount)

            result = self._retry_with_backoff(_do_buy)
            if result.get("success"):
                result = self._finalize_buy_fill(
                    pair, usd_amount, result, tp_pct=tp_pct, execution_style="market_ioc"
                )
            else:
                result["sl_attached"] = False
                result["tp_attached"] = False
                result["execution_style"] = "market_ioc"
                result["fill_status"] = "none"

        result["pair"] = pair
        result["action"] = "BUY"
        result["side"] = "BUY"
        if record_ledger and result.get("success"):
            from phase6.core.ledger_sl_truth import enrich_buy_sl_truth

            enrich_buy_sl_truth(result, self.stop_loss_manager)
            self._record_to_ledger(result, signal_source="order_executor_buy")
        # Phase C shadow: CF fee log on market buys only (never places orders)
        if result.get("success") and str(result.get("execution_style") or "").startswith(
            "market"
        ):
            try:
                from phase6.core.limit_first_buy_shadow import log_market_buy_counterfactual

                bid = last = None
                if hasattr(self.exchange, "get_best_bid_ask"):
                    try:
                        refs = self.exchange.get_best_bid_ask(pair) or {}
                        bid = refs.get("bid")
                        last = refs.get("last")
                    except Exception:
                        pass
                log_market_buy_counterfactual(result, bid=bid, last=last)
            except Exception as e:
                self.logger.debug("limit_first shadow log skipped: %s", e)
        return result

    def _execute_limit_first_buy(
        self,
        pair: str,
        usd_amount: float,
        *,
        policy: Any,
        tp_pct: float = None,
    ) -> Dict[str, Any]:
        """Limit post-only rest → wait → cancel residual. No market fallback (Brad)."""
        from phase6.core.limit_first_buy import (
            base_size_from_usd,
            cancel_and_recheck,
            limit_price_from_refs,
            wait_for_limit_fill,
        )

        refs = {"bid": None, "ask": None, "last": None}
        if hasattr(self.exchange, "get_best_bid_ask"):
            try:
                refs = self.exchange.get_best_bid_ask(pair) or refs
            except Exception as e:
                self.logger.warning("[LIMIT BUY] book failed %s: %s", pair, e)
        if not refs.get("last") and hasattr(self.exchange, "get_price"):
            try:
                refs["last"] = float(self.exchange.get_price(pair) or 0) or None
            except Exception:
                pass
        limit_px = limit_price_from_refs(
            bid=refs.get("bid"),
            ask=refs.get("ask"),
            last=refs.get("last"),
            price_ref=getattr(policy, "price_ref", "bid"),
            offset_bps=float(getattr(policy, "offset_bps", 0) or 0),
        )
        if not limit_px or limit_px <= 0:
            return {
                "success": False,
                "error": "no_limit_price",
                "execution_style": "limit_post_only",
                "fill_status": "none",
                "sl_attached": False,
                "tp_attached": False,
            }
        base = base_size_from_usd(usd_amount, limit_px)
        if not base or base <= 0:
            return {
                "success": False,
                "error": "no_base_size",
                "execution_style": "limit_post_only",
                "fill_status": "none",
                "sl_attached": False,
                "tp_attached": False,
            }
        if hasattr(self.exchange, "quantize_size"):
            try:
                base = float(self.exchange.quantize_size(pair, base))
            except Exception:
                base = round(base, 8)

        post_only = bool(getattr(policy, "post_only", True))
        placed = self.exchange.place_limit_buy(
            pair, base, limit_px, post_only=post_only
        )
        if not placed.get("success"):
            return {
                "success": False,
                "error": placed.get("error") or "limit_place_failed",
                "execution_style": "limit_post_only" if post_only else "limit_gtc",
                "fill_status": "none",
                "sl_attached": False,
                "tp_attached": False,
                "raw": placed,
            }

        order_id = placed.get("order_id")
        wait = wait_for_limit_fill(
            self.exchange,
            order_id,
            fill_wait_s=float(getattr(policy, "fill_wait_s", 45) or 45),
            poll_interval_s=float(getattr(policy, "poll_interval_s", 2) or 2),
        )
        filled = float(wait.get("filled_size") or 0)
        avg = float(wait.get("average_filled_price") or 0)
        residual_cancelled = False
        if wait.get("timed_out") or (
            filled <= 0 and str(wait.get("status") or "").upper() not in {"FILLED"}
        ):
            chk = cancel_and_recheck(self.exchange, order_id)
            residual_cancelled = bool(chk.get("cancelled"))
            filled = float(chk.get("filled_size") or filled)
            avg = float(chk.get("average_filled_price") or avg)

        min_usd = float(getattr(policy, "min_fill_usd", 10) or 10)
        notional = filled * avg if filled > 0 and avg > 0 else 0.0
        if notional < min_usd or filled <= 0 or avg <= 0:
            # Brad: skip — no market fallback
            if order_id and not residual_cancelled:
                try:
                    cancel_and_recheck(self.exchange, order_id)
                except Exception:
                    pass
            return {
                "success": False,
                "error": "limit_unfilled_skip",
                "order_id": order_id,
                "limit_order_id": order_id,
                "execution_style": "limit_post_only" if post_only else "limit_gtc",
                "fill_status": "none",
                "residual_cancelled": True,
                "sl_attached": False,
                "tp_attached": False,
                "entry_price": 0.0,
                "size": 0.0,
                "qty": 0.0,
            }

        style = "limit_post_only" if post_only else "limit_gtc"
        stub = {
            "success": True,
            "order_id": order_id,
            "limit_order_id": order_id,
            "residual_cancelled": residual_cancelled,
        }
        # Seed fill hint so finalize can attach SL on verified size
        result = self._finalize_buy_fill(
            pair,
            notional,
            stub,
            tp_pct=tp_pct,
            execution_style=style,
            prefilled_entry=avg,
            prefilled_size=filled,
        )
        result["fill_status"] = "partial" if filled + 1e-12 < base else "full"
        result["liquidity"] = "M"  # post_only intent; fee audit confirms later
        return result

    def _finalize_buy_fill(
        self,
        pair: str,
        usd_amount: float,
        result: Dict[str, Any],
        *,
        tp_pct: float = None,
        execution_style: str = "market_ioc",
        prefilled_entry: float = 0.0,
        prefilled_size: float = 0.0,
    ) -> Dict[str, Any]:
        """Shared post-place fill + SL attach (ENG-S3 settlement ownership)."""
        order_id = result.get("order_id")
        from phase6.core.sl_preflight import fetch_verified_order_fill

        hint = (
            fetch_verified_order_fill(self.exchange, order_id)
            if order_id
            else {"average_filled_price": 0.0, "filled_size": 0.0, "fill_verified": False}
        )
        entry_price = float(hint.get("average_filled_price") or 0.0) or float(prefilled_entry or 0)
        size = float(hint.get("filled_size") or 0.0) or float(prefilled_size or 0)
        if size > 0 and entry_price <= 0:
            entry_price = usd_amount / size if usd_amount > 0 else 0.0
        elif size <= 0 and entry_price > 0 and usd_amount > 0:
            size = usd_amount / entry_price
        if entry_price <= 0 and size <= 0:
            self.logger.info(
                f"[EXEC BUY] Fill not yet visible for {pair} (order_id={order_id}); "
                f"delegating settlement wait to stop_loss_manager"
            )

        if size > 0 and hasattr(self.exchange, "quantize_size"):
            try:
                size = float(self.exchange.quantize_size(pair, size))
            except Exception:
                size = round(size, 8)

        sl_result = False
        tp_result = False
        if self.stop_loss_manager and (entry_price > 0 or size > 0):
            sl_result = self.stop_loss_manager.attach_stop_loss(
                pair,
                entry_price,
                size,
                anchor_entry=entry_price if entry_price > 0 else None,
                order_id=order_id if order_id else None,
                fresh_buy=True,
            )
            effective_tp = tp_pct
            if effective_tp is None:
                try:
                    from phase6.core.shadow_tp import effective_tp_pct_for_buy

                    cfg = getattr(self.stop_loss_manager, "config", None) or {}
                    if not isinstance(cfg, dict) or "take_profit" not in cfg:
                        cfg = None
                    effective_tp = effective_tp_pct_for_buy(cfg)
                except Exception:
                    effective_tp = None
            if effective_tp and effective_tp > 0:
                tp_result = self.stop_loss_manager.attach_take_profit(
                    pair, entry_price, size, effective_tp
                )
            self.logger.info(
                f"[SL/TP] Post-buy for {pair}: entry=${entry_price:.4f} size={size:.8f} "
                f"SL={sl_result} TP={tp_result} tp_pct={effective_tp} style={execution_style}"
            )

        verified = fetch_verified_order_fill(self.exchange, order_id) if order_id else hint
        if verified.get("fill_verified"):
            entry_price = float(verified["average_filled_price"])
            size = float(verified["filled_size"])
            if size > 0 and hasattr(self.exchange, "quantize_size"):
                try:
                    size = float(self.exchange.quantize_size(pair, size))
                except Exception:
                    size = round(size, 8)
        elif sl_result and order_id:
            self.logger.warning(
                f"[EXEC BUY] SL attached for {pair} but fill still unverified (order_id={order_id})"
            )

        result["entry_price"] = round(entry_price, 4) if entry_price > 0 else 0.0
        result["size"] = size
        result["qty"] = size
        result["sl_attached"] = sl_result
        result["tp_attached"] = tp_result
        result["actual_fill_used"] = bool(verified.get("fill_verified")) or (
            prefilled_size > 0 and prefilled_entry > 0
        )
        result["fill_verified"] = bool(verified.get("fill_verified"))
        result["execution_style"] = execution_style
        if "fill_status" not in result:
            result["fill_status"] = "full" if size > 0 else "none"
        return result

    def execute_sell(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        """Execute a market sell. Accepts usd_amount (like execute_buy) and computes crypto size internally.
        P0-02.6: Critical sell path audit/fix.
        - size = usd_amount / price (full get_price prec)
        - ALWAYS quantize with base_increment (via exchange.quantize_size)
        - For LIVE (P6-PE-CALLER-OE-SELL): delegates to protected_market_exit which unlocks
          any stop-held base before rebalance sells (cancel+resolve+reattach). Quantize+return shape preserved.
        - Shadow unchanged.
        - No more direct place_market_sell in this path.
        """
        if usd_amount <= 0:
            return {"success": False, "error": "zero usd amount"}
        size = 0.0
        price = 0.0
        try:
            price = getattr(self.exchange, "get_price", lambda p: 0.0)(pair) or 0.0
            if price > 0:
                size = usd_amount / price
                # P0-02.6: sell path uses unified quantize (see above)
                if size > 0 and hasattr(self.exchange, 'quantize_size'):
                    try:
                        size = float(self.exchange.quantize_size(pair, size))
                    except Exception:
                        size = round(size, 8)
        except Exception:
            pass
        if self.mode == "live":
            if size <= 0:
                return {"success": False, "error": "could not compute sell size (price=0)"}
            # P6-PE-CALLER-OE-SELL-20260826 + P0-02.6: route live sells (rebalance etc) via protected to unlock
            # stop-held base. Compute/quantize logic above is preserved exactly.
            try:
                from phase6.core.protected_market_exit import protected_market_exit
                pe = protected_market_exit(
                    self.exchange,
                    pair,
                    qty=size,
                    qty_full_hint=size,
                    mark_price=price,
                    reason="order_executor_sell",
                    signal_source="order_executor_sell",
                    ledger=True,
                    reattach_sl=True,
                )
                if not pe.get("success", False):
                    err = pe.get("error") or pe.get("cancel_error") or "protected_market_exit failed"
                    return {"success": False, "error": str(err)[:200]}
                filled = float(pe.get("filled_qty") or pe.get("qty") or size or 0)
                exit_px = float(pe.get("exit_price") or 0.0)
                out = {
                    "success": True,
                    "order_id": pe.get("order_id"),
                    "size": round(filled, 8),
                    "qty": round(filled, 8),
                    "exit_price": round(exit_px, 4) if exit_px > 0 else None,
                    "actual_fill_used": bool(exit_px > 0),
                    "pair": pair,
                    "action": "SELL",
                    "side": "SELL",
                }
                # protected did the ledger + unlock + reattach; skip _record to avoid dup
                return out
            except Exception as pe_exc:
                self.logger.error(f"[OE-SELL] protected exit exception for {pair}: {pe_exc}")
                return {"success": False, "error": f"protected: {str(pe_exc)[:120]}"}
        
        # Shadow mode
        out = {
            "success": True,
            "order_id": f"shadow_sell-{__import__('secrets').token_hex(4)}",
            "size": round(size, 8),
            "qty": round(size, 8),
            "exit_price": price,
            "pair": pair,
            "action": "SELL",
            "side": "SELL",
        }
        self._record_to_ledger(out, signal_source="order_executor_sell")
        return out

    def execute_rebalance_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full rebalance plan.
        Processes SELL moves first, and aborts if a SELL fails in live mode.
        """
        results = []
        sorted_plan = sorted(plan, key=lambda x: x.get("action", "") != "SELL")

        for move in sorted_plan:
            pair = move.get("pair")
            action = move.get("action", "").upper()
            usd_amount = float(move.get("usd_amount", 0))

            if action == "BUY":
                # Defer ledger until after attach_stop_loss inside execute_buy, then
                # finalize with exchange protective-order truth (P6-OPS #14).
                result = self.execute_buy(pair, usd_amount, record_ledger=False)
                if result.get("success"):
                    from phase6.core.ledger_sl_truth import enrich_buy_sl_truth

                    enrich_buy_sl_truth(result, self.stop_loss_manager)
                    self._record_to_ledger(result, signal_source="order_executor_rebalance")
            elif action == "SELL":
                result = self.execute_sell(pair, usd_amount)
            else:
                result = {"success": False, "error": f"unknown action: {action}"}

            result["pair"] = pair
            result["action"] = action
            # P0-02.7: preserve usd_amount from input move for logging/metadata
            if "usd_amount" not in result:
                result["usd_amount"] = usd_amount
            results.append(result)
            
            # Atomic enforcement: abort plan if SELL failed in live mode
            if self.mode == "live" and action == "SELL" and not result.get("success"):
                self.logger.error(f"[ATOMIC] SELL failed ({pair}). Aborting full plan execution.")
                break

        return results
