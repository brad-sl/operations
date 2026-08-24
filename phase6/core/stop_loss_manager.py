# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

import logging
from typing import Optional, Any, List, Dict
import time

logger = logging.getLogger(__name__)

class StopLossManager:
    """
    Manage stop-loss and take-profit orders for Phase 6 using native Coinbase stop-limit orders.
    """

    def __init__(self, exchange_client: Any, config: dict, mode: str = "shadow", account_context: "AccountContext" = None):
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.account_context = account_context
        self.account_id = getattr(account_context, "account_id", "default") if account_context else "default"
        self.shadow_mode = (mode == "shadow")

        # Default risk parameters (can be overridden by config)
        self.default_sl_pct = config.get("risk_management", {}).get("stop_loss_pct", 0.03)
        self.default_tp_pct = config.get("risk_management", {}).get("take_profit_pct", 0.06)

        # Adaptive SL support (#3 risk-aware sizing)
        self.adaptive_sl_enabled = config.get("risk_management", {}).get("adaptive_sl", True)
        rm0 = config.get("risk_management") or {}
        try:
            self.sl_base_pct = float(rm0.get("sl_base_pct", self.default_sl_pct))
        except (TypeError, ValueError):
            self.sl_base_pct = float(self.default_sl_pct)
        try:
            self.sl_min_pct = float(rm0.get("sl_min_pct", 0.015))
        except (TypeError, ValueError):
            self.sl_min_pct = 0.015
        try:
            self.sl_max_pct = float(rm0.get("sl_max_pct", 0.05))
        except (TypeError, ValueError):
            self.sl_max_pct = 0.05
        self.sl_tp_symmetry = dict(rm0.get("sl_tp_symmetry") or {})

    def _live_tp_context(self) -> tuple:
        """(live_tp_active, trail_arm_pct) from exit_automation + optional symmetry override.

        Fail-open: on any load error treat as live_tp off so SL path stays safe/legacy.
        """
        live = False
        arm = None
        try:
            from phase6.core.shadow_tp import load_exit_automation, _tp_cfg

            tp = _tp_cfg(load_exit_automation())
            mode = str(tp.get("mode") or "off").strip().lower()
            live = mode == "live"
            trail = dict(tp.get("trail") or {})
            if trail.get("enabled", True):
                arm = float(trail.get("arm_pct") or 0.04)
        except Exception as e:
            logger.debug("live TP context load failed (symmetry skipped): %s", e)
            live = False
            arm = None
        # Explicit override from risk_management.sl_tp_symmetry (tests / ops)
        sym = getattr(self, "sl_tp_symmetry", None) or {}
        if sym.get("trail_arm_pct") is not None:
            try:
                arm = float(sym.get("trail_arm_pct"))
            except (TypeError, ValueError):
                pass
        if sym.get("force_live_tp_active") is not None:
            live = bool(sym.get("force_live_tp_active"))
        return live, arm

    def get_sl_pct(
        self,
        pair: str,
        regime_bias: float = 0.5,
        risk_data: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Return effective SL % for pair (#3). Uses adaptive via sl_risk_scorer + regime if enabled."""
        if not getattr(self, "adaptive_sl_enabled", True):
            return self.default_sl_pct
        try:
            from phase6.core.sl_risk_scorer import get_adaptive_sl_pct

            live_tp, trail_arm = self._live_tp_context()
            base = float(getattr(self, "sl_base_pct", self.default_sl_pct))
            return get_adaptive_sl_pct(
                pair=pair,
                base_pct=base,
                regime_bias=regime_bias,
                risk_data=risk_data,
                min_pct=float(getattr(self, "sl_min_pct", 0.015)),
                max_pct=float(getattr(self, "sl_max_pct", 0.05)),
                live_tp_active=live_tp,
                trail_arm_pct=trail_arm,
                symmetry=getattr(self, "sl_tp_symmetry", None),
            )
        except Exception as e:
            logger.debug(f"Adaptive SL fallback for {pair}: {e}")
            return self.default_sl_pct


    def attach_stop_loss(
        self,
        pair: str,
        entry_price: float,
        size: float,
        sl_pct: float = None,
        anchor_entry: float = None,
        order_id: Optional[str] = None,
        fresh_buy: bool = False,
    ) -> bool:
        """
        Attach a native stop-loss order with retry logic.
        ANALYST-20260703-051: Pre-flight settlement poll using order fill if order_id provided (tied to recent buy), else balance.
        Uses get_order_fill_details via poll_for_settlement for actual fill wait before SL attach.

        - Polls for settlement before placing to reduce PREVIEW_INSUFFICIENT_FUND.
        - Uses precise per-product tick (price_increment/base_increment) to avoid PREVIEW_INVALID_STOP_PRICE_PRECISION.
        - Risk-aware: uses sl_risk_scorer + adaptive for poll aggressiveness.
        """
        if sl_pct is not None:
            pct = sl_pct
        else:
            # #3 adaptive
            pct = self.get_sl_pct(pair) if hasattr(self, "get_sl_pct") else self.default_sl_pct

        # Pre-flight settlement poll (ANALYST-20260705-005 / 007)
        from phase6.core.sl_preflight import (
            settlement_poll_params,
            sanitize_reattach_order_id,
            resolve_sl_attach_size,
            cancel_open_stops_for_pair,
            poll_available_after_cancel,
            fetch_verified_order_fill,
            SETTLEMENT_POLL_OWNER,
        )
        from phase6.core.sl_risk_scorer import get_sl_risk

        requested_size = float(size)
        settlement_confirmed = False
        fresh_buy_order_id = order_id if fresh_buy else None
        try:
            risk = get_sl_risk(pair)
            risk_level = risk.get("level", "LOW")
            if not self.shadow_mode and not fresh_buy:
                order_id = sanitize_reattach_order_id(self.exchange, pair, order_id)
            params = settlement_poll_params(pair, order_id=order_id, risk_level=risk_level)
            skip_poll = (
                not order_id
                and risk_level == "LOW"
                and not risk.get("recent_sl_failures")
            )
            if skip_poll:
                logger.debug(
                    f"[PRE-FLIGHT] Skipping settlement poll for {pair} (LOW risk, no fresh buy order_id)"
                )
            elif not self.shadow_mode:
                if not hasattr(self.exchange, "poll_for_settlement"):
                    logger.warning(f"[PRE-FLIGHT] exchange has no poll_for_settlement for {pair}")
                else:
                    logger.debug(
                        f"[PRE-FLIGHT] Settlement poll owner={SETTLEMENT_POLL_OWNER} pair={pair} order_id={order_id}"
                    )
                    settled = self.exchange.poll_for_settlement(
                        pair,
                        timeout=params["timeout"],
                        order_id=params.get("order_id"),
                    )
                    settlement_confirmed = bool(settled)
                    if not settled:
                        if order_id:
                            logger.error(
                                f"[PRE-FLIGHT] Fill-tied settlement failed for {pair} order_id={order_id}; aborting SL attach"
                            )
                            return False
                        logger.warning(
                            f"[PRE-FLIGHT] Settlement poll failed/timeout for {pair} "
                            f"(risk={risk_level}, mode={params['mode']}); proceeding cautiously"
                        )
                    else:
                        logger.info(
                            f"[PRE-FLIGHT] Settlement confirmed for {pair} before SL "
                            f"(mode={params['mode']}, order_id={order_id or 'N/A'})"
                        )
                        if order_id:
                            verified = fetch_verified_order_fill(self.exchange, order_id)
                            if verified.get("fill_verified"):
                                entry_price = float(verified["average_filled_price"])
                                requested_size = float(verified["filled_size"])
                                anchor_entry = entry_price
                                size = requested_size
                            elif fresh_buy_order_id:
                                logger.error(
                                    f"[PRE-FLIGHT] Settlement ok but fill unverified for {pair} "
                                    f"order_id={order_id}; refusing market-price SL anchor"
                                )
                                return False
        except Exception as e:
            logger.warning(f"[PRE-FLIGHT] poll skipped or failed for {pair}: {e}")
            if order_id and not self.shadow_mode:
                return False

        if not self.shadow_mode:
            pre_size, pre_meta = resolve_sl_attach_size(self.exchange, pair, requested_size)
            if pre_size <= 0 and pre_meta.get("holds_entire_balance"):
                cancel_open_stops_for_pair(self.exchange, pair)
                poll_available_after_cancel(self.exchange, pair, timeout=4.0)

        meta = self.exchange.get_product_metadata(pair)
        price_inc = float(meta.get("price_increment", 0.0001))

        market_px = 0.0
        if not self.shadow_mode:
            try:
                market_px = float(self.exchange.get_price(pair) or 0.0)
            except Exception:
                pass

        from phase6.core.sl_preflight import (
            quantize_stop_bundle,
            resolve_stop_calc_base,
            ensure_stop_below_market,
        )

        calc_base, anchor_reason = resolve_stop_calc_base(
            pair, entry_price, anchor_entry, market_px or None
        )

        if (not calc_base or calc_base <= 0) and not self.shadow_mode:
            if fresh_buy_order_id and settlement_confirmed:
                logger.error(
                    f"[SL ANCHOR] Refusing market fallback for fresh buy {pair} "
                    f"(order_id={fresh_buy_order_id}); verified fill required"
                )
                return False
            try:
                current_px = market_px or float(self.exchange.get_price(pair) or 0.0)
                if current_px > 0:
                    logger.warning(
                        f"[SL FALLBACK] entry/anchor was 0 for {pair}; using current market ${current_px:.2f} for SL anchor (re-attach only)"
                    )
                    calc_base = current_px
                    anchor_reason = "market_fallback"
            except Exception:
                pass

        stop_price = calc_base * (1 - pct)
        limit_price = stop_price * 0.995

        stop_price, limit_price, stop_price_str, limit_price_str = quantize_stop_bundle(
            self.exchange, pair, calc_base, stop_price, limit_price
        )

        if market_px > 0:
            stop_price, limit_price = ensure_stop_below_market(
                self.exchange, pair, stop_price, limit_price, market_px, pct
            )
            stop_price_str = self.exchange.quantize_price(pair, stop_price)
            limit_price_str = self.exchange.quantize_price(pair, limit_price)

        # Floor ratchet: raise stop after large mark/entry spread (never loosen)
        try:
            from phase6.core.sl_floor_ratchet import apply_ratchet_to_stop_bundle

            rm = {}
            if isinstance(getattr(self, "config", None), dict):
                rm = self.config.get("risk_management") or {}
            elif isinstance(getattr(self, "config_dict", None), dict):
                rm = self.config_dict.get("risk_management") or {}
            # Prefer original runner entry for multiple math
            ratchet_entry = float(anchor_entry or entry_price or calc_base or 0)
            existing_stop = None
            try:
                from phase6.core.runner_capital_events import _latest_registry_stop_for_pair

                row = _latest_registry_stop_for_pair(pair)
                if isinstance(row, dict) and row.get("stop_price"):
                    existing_stop = float(row["stop_price"])
            except Exception:
                pass
            add_px = None
            if fresh_buy and entry_price and float(entry_price) > 0:
                # Fresh fill price for add-gap ratchet when topping up runners
                add_px = float(entry_price)
            pre_ratchet_stop = float(stop_price)
            stop_price, limit_price, rdec = apply_ratchet_to_stop_bundle(
                pair=pair,
                entry=ratchet_entry,
                mark=float(market_px or 0),
                proposed_stop=float(stop_price),
                proposed_limit=float(limit_price),
                existing_stop=existing_stop,
                add_price=add_px,
                risk_management=rm if isinstance(rm, dict) else {},
            )
            if rdec.applied and stop_price != pre_ratchet_stop:
                stop_price_str = self.exchange.quantize_price(pair, stop_price)
                limit_price_str = self.exchange.quantize_price(pair, limit_price)
                stop_price = float(stop_price_str)
                limit_price = float(limit_price_str)
                # Keep stop strictly below market after quantize
                if market_px > 0:
                    stop_price, limit_price = ensure_stop_below_market(
                        self.exchange, pair, stop_price, limit_price, market_px, pct
                    )
                    stop_price_str = self.exchange.quantize_price(pair, stop_price)
                    limit_price_str = self.exchange.quantize_price(pair, limit_price)
                    stop_price = float(stop_price_str)
                    limit_price = float(limit_price_str)
                anchor_reason = f"{anchor_reason}|ratchet:{','.join(rdec.reasons)}"
        except Exception as e:
            logger.warning("[SL-RATCHET] skipped for %s: %s", pair, e)

        # Ensure prices are valid vs calc base (ENG-S4-02: not stale raw entry_price)
        # After ratchet, anchor_for_stop_check must not force stop back down to genesis.
        anchor_for_stop_check = calc_base if calc_base and calc_base > 0 else entry_price
        if stop_price >= (market_px if market_px > 0 else anchor_for_stop_check):
            logger.warning(
                f"Stop price {stop_price} >= market/anchor, adjusting..."
            )
            price_inc = float(meta.get("price_increment", "0.0001"))
            ref = market_px if market_px > 0 else anchor_for_stop_check
            stop_price = ref - price_inc
            stop_price_str = self.exchange.quantize_price(pair, stop_price)
            stop_price = float(stop_price_str)
            limit_price = stop_price - price_inc
            limit_price_str = self.exchange.quantize_price(pair, limit_price)
            limit_price = float(limit_price_str)
        elif stop_price >= anchor_for_stop_check and market_px <= 0:
            # legacy path when no market
            price_inc = float(meta.get("price_increment", "0.0001"))
            stop_price = anchor_for_stop_check - price_inc
            stop_price_str = self.exchange.quantize_price(pair, stop_price)
            stop_price = float(stop_price_str)
            limit_price = stop_price - price_inc
            limit_price_str = self.exchange.quantize_price(pair, limit_price)
            limit_price = float(limit_price_str)
        
        # Quantize size to tradable balance (PREVIEW_INSUFFICIENT_FUND mitigation)
        size, size_meta = resolve_sl_attach_size(self.exchange, pair, requested_size)
        if size <= 0 and size_meta.get("holds_entire_balance"):
            cancel_open_stops_for_pair(self.exchange, pair)
            poll_available_after_cancel(self.exchange, pair, timeout=4.0)
            size, size_meta = resolve_sl_attach_size(self.exchange, pair, requested_size)
        if size <= 0:
            reason = size_meta.get("skip_reason") or size_meta.get("hint") or "zero_size"
            logger.warning("[SL-SIZE] Skipping %s attach: %s (meta=%s)", pair, reason, size_meta)
            return False

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native SL for {pair}")
            print(f"         Entry: ${entry_price:.2f} | Stop: ${stop_price:.4f} | Limit: ${limit_price:.4f} | SL%: {pct*100:.1f}% | size: {size}")
            return True

        # Live mode with retry
        max_retries = 3
        sl_order_id: Optional[str] = None
        for attempt in range(1, max_retries + 1):
            try:
                result = self.exchange.place_stop_limit_sell(
                    product_id=pair,
                    qty=size,
                    stop_price=stop_price,
                    limit_price=limit_price
                )
                success = False
                if isinstance(result, dict):
                    success = bool(result.get("success"))
                    sl_order_id = result.get("order_id")
                else:
                    success = bool(result)
                if success:
                    logger.info(f"Stop-loss successfully attached for {pair}")
                    if sl_order_id and not self.shadow_mode:
                        try:
                            from phase6.core.protective_orders_registry import register_protective_order
                            register_protective_order(
                                pair=pair,
                                sl_order_id=str(sl_order_id),
                                entry_price=float(calc_base or entry_price),
                                qty=float(size),
                                stop_price=float(stop_price),
                                limit_price=float(limit_price),
                                buy_order_id=fresh_buy_order_id,
                                mode="live",
                            )
                        except Exception as reg_exc:
                            logger.warning("[SL-REGISTRY] failed to register %s: %s", pair, reg_exc)
                    return True
                else:
                    logger.warning(f"SL attempt {attempt}/{max_retries} failed for {pair}")
            except Exception as e:
                err = str(e)
                logger.error(f"SL attempt {attempt}/{max_retries} exception for {pair}: {e}")
                if "INSUFFICIENT_FUND" in err.upper() and attempt < max_retries:
                    from phase6.core.sl_preflight import cancel_open_stops_for_pair, poll_available_after_cancel
                    cancel_open_stops_for_pair(self.exchange, pair)
                    poll_available_after_cancel(self.exchange, pair, timeout=4.0)
                    size, _ = resolve_sl_attach_size(self.exchange, pair, requested_size)

            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying SL attachment for {pair} in {sleep_time}s...")
                time.sleep(sleep_time)

        logger.error(f"Failed to attach stop-loss for {pair} after {max_retries} attempts")
        return False

    def attach_take_profit(self, pair: str, entry_price: float, size: float, tp_pct: float = None) -> bool:
        """
        Attach a native take-profit limit sell order.
        """
        pct = tp_pct if tp_pct is not None else self.default_tp_pct
        tp_price = entry_price * (1 + pct)

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native TP for {pair}")
            print(f"         Entry: ${entry_price} | TP: ${tp_price} | TP%: {pct*100:.1f}% | size: {size}")
            return True

        # Use a simple limit sell for TP (quantize price)
        meta = self.exchange.get_product_metadata(pair)
        tp_price_str = self.exchange.quantize_price(pair, tp_price)
        tp_price_quantized = float(tp_price_str)

        if hasattr(self.exchange, "place_limit_sell"):
            return self.exchange.place_limit_sell(pair, size, tp_price_quantized)
        
        # Fallback to direct client order placement
        logger.info(f"Using client.place_order for TP on {pair}")
        result = self.exchange.place_order(
            product_id=pair,
            side="SELL",
            order_type="LIMIT",
            price=str(tp_price_quantized),
            size=str(size),
            post_only=True
        )
        return bool(result)

    def detect_active_protective_orders(
        self, basket: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Detect and return active SL/TP protective orders for pairs in the basket.

        Queries via exchange_client.get_open_orders() and filters for
        stop-loss and take-profit style orders. Returns structured mapping
        per pair for use before rebalance.

        Logs detected orders.
        """
        active: Dict[str, List[Dict[str, Any]]] = {}
        try:
            open_orders = self.exchange.get_open_orders() or []
            from phase6.core.sl_preflight import order_configuration_is_stop
            for order in open_orders:
                product_id = order.get("product_id") or order.get("pair")
                if basket and product_id not in basket:
                    continue
                order_type = str(order.get("type", order.get("order_type", ""))).lower()
                side = str(order.get("side", "")).upper()
                oc = order.get("order_configuration") or {}
                has_stop = order_configuration_is_stop(oc) or bool(order.get("stop_price")) or "stop" in order_type

                protective_type = None
                if has_stop:
                    protective_type = "SL"
                elif side == "SELL" and "limit" in order_type:
                    protective_type = "TP"  # potential TP (limit sell)

                if protective_type:
                    if product_id not in active:
                        active[product_id] = []
                    order_info = dict(order)  # copy
                    order_info["protective_type"] = protective_type
                    active[product_id].append(order_info)

            if active:
                summary = {k: len(v) for k, v in active.items()}
                logger.info(f"[CR-03.1] Detected active protective orders: {summary}")
            else:
                logger.info("[CR-03.1] No active SL/TP protective orders detected for basket.")

        except Exception as e:
            logger.error(f"[CR-03.1] Error detecting active protective orders: {e}")
            active = {}

        return active

    def suspend_active_protective_orders(
        self, active_stops: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[str]]:
        """
        CR-03.2: Suspend/cancel all active SL/TP protective orders for pairs being rebalanced.

        After detection (CR-03.1), cancel the orders via exchange client.
        Records which stops were suspended with their order IDs for audit trail.

        Preserve Hold E1 (sleeve=preserve / PAXG while armed) is NEVER cancelled here.

        Returns: {pair: [order_id, ...], ...} for logging/verification.
        """
        suspended: Dict[str, List[str]] = {}
        total_suspended = 0
        preserve_skipped = 0

        for pair, orders in (active_stops or {}).items():
            suspended[pair] = []
            for order in orders:
                order_id = order.get("id") or order.get("order_id")
                ptype = order.get("protective_type", "PROTECTIVE")
                if not order_id:
                    logger.warning(f"[CR-03.2] Order without ID for {pair}: {order}")
                    continue

                # Sleeve safety: do not strip Preserve ballast stop
                try:
                    from phase6.core.preserve_hold import (
                        should_protect_preserve_sleeve,
                        load_state,
                        load_preserve_config,
                    )

                    if should_protect_preserve_sleeve(
                        pair=pair,
                        order_id=str(order_id),
                        state=load_state(),
                        cfg=load_preserve_config(
                            self.config if isinstance(self.config, dict) else {}
                        ),
                    ):
                        preserve_skipped += 1
                        logger.info(
                            "[CR-03.2] SKIP preserve sleeve order %s pair=%s",
                            order_id,
                            pair,
                        )
                        continue
                except Exception as pe:
                    logger.debug("[CR-03.2] preserve skip check failed: %s", pe)

                if self.shadow_mode:
                    print(f"[SHADOW][CR-03.2] Would cancel {ptype} order {order_id} for {pair}")
                    suspended[pair].append(order_id)
                    total_suspended += 1
                    continue

                try:
                    success = self.exchange.cancel_order(order_id)
                    if success:
                        logger.info(f"[CR-03.2] Suspended {ptype} order {order_id} for {pair}")
                        suspended[pair].append(order_id)
                        total_suspended += 1
                    else:
                        logger.warning(f"[CR-03.2] Failed to cancel {ptype} order {order_id} for {pair}")
                except Exception as e:
                    logger.error(f"[CR-03.2] Exception canceling {order_id} for {pair}: {e}")

        if preserve_skipped:
            logger.info("[CR-03.2] Preserved %s Preserve-sleeve stop(s) from suspend", preserve_skipped)
        if total_suspended > 0:
            summary = {k: v for k, v in suspended.items() if v}
            logger.info(f"[CR-03.2] Suspended {total_suspended} protective orders across {len(summary)} pairs: {summary}")
        else:
            logger.info("[CR-03.2] No active protective orders required suspension.")

        return suspended

    def verify_reconciliation(
        self,
        basket: Optional[List[str]] = None,
        suspended: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        CR-03.5: Verification method confirming end-to-end
        suspend → rebalance → re-attach sequence.
        """
        report: Dict[str, Any] = {
            "success": False,
            "timestamp": time.time(),
            "orphaned_stops": {},
            "active_protective_after": {},
            "zero_balance_with_stops": [],
            "details": "",
            "suspended_tracked": suspended or {},
        }
        try:
            holdings = self.exchange.get_holdings() or {}
            open_orders = self.exchange.get_open_orders() or []

            # Re-detect active protective orders after re-attach
            active_after: Dict[str, List[str]] = {}
            for order in open_orders:
                product_id = order.get("product_id") or order.get("pair")
                if basket and product_id not in basket:
                    continue
                order_type = str(order.get("type", "")).lower()
                side = str(order.get("side", "")).upper()
                has_stop = bool(order.get("stop_price")) or "stop" in order_type
                is_protective = has_stop or (side == "SELL" and "limit" in order_type)
                if is_protective:
                    if product_id not in active_after:
                        active_after[product_id] = []
                    oid = order.get("id") or order.get("order_id")
                    if oid:
                        active_after[product_id].append(oid)

            report["active_protective_after"] = active_after

            # Identify orphans: protective orders where current holding <= 0
            orphans: Dict[str, List[str]] = {}
            for pid, oids in active_after.items():
                asset = pid.split("-")[0] if "-" in pid else pid
                bal = holdings.get(asset, holdings.get(pid, 0))
                try:
                    bal = float(bal) if bal is not None else 0.0
                except (TypeError, ValueError):
                    bal = 0.0
                if bal <= 0:
                    orphans[pid] = oids

            report["orphaned_stops"] = orphans
            report["zero_balance_with_stops"] = list(orphans.keys())

            if orphans:
                report["details"] = (
                    f"FAILED: {len(orphans)} orphaned protective orders on zero-balance pairs"
                )
                logger.warning(
                    f"[CR-03.5] Verification FAILED - orphaned stops: {orphans}"
                )
            else:
                report["success"] = True
                report["details"] = (
                    f"SUCCESS: {len(active_after)} pairs have protective orders; "
                    f"no orphans on zero-balance holdings. "
                    f"Tracked suspended order IDs: {list((suspended or {}).values())}"
                )
                logger.info(f"[CR-03.5] Verification SUCCESS: {report['details']}")

        except Exception as e:
            logger.error(f"[CR-03.5] Verification exception: {e}")
            report["details"] = f"ERROR: {str(e)}"

        return report


    def verify_protective_stop(self, pair: str, intended_entry: float, expected_pct: float = None) -> dict:
        """
        #1: Hardened verification that SL is attached and anchored to the *original* entry.
        Returns dict with verified flag, actual stops, status.
        Call after attach/reattach.
        """
        if expected_pct is None:
            expected_pct = self.get_sl_pct(pair) if hasattr(self, "get_sl_pct") else self.default_sl_pct
        expected_stop = intended_entry * (1 - expected_pct)
        res = {
            "pair": pair,
            "intended_entry": round(intended_entry, 4),
            "expected_pct": round(expected_pct*100, 2),
            "expected_stop": round(expected_stop, 4),
            "verified": False,
            "actual": [],
            "status": "no_check"
        }
        if self.shadow_mode:
            res["status"] = "shadow_ok"
            res["verified"] = True
            return res
        try:
            stops = []
            if hasattr(self.exchange, "get_open_stop_orders"):
                stops = self.exchange.get_open_stop_orders(pair) or []
            for o in stops:
                sp = float(o.get("stop_price") or 0)
                if sp:
                    res["actual"].append(round(sp, 4))
                    if abs(sp - expected_stop) / expected_stop < 0.005:
                        res["verified"] = True
                        res["status"] = "anchored_ok"
                        break
            if not res["actual"]:
                res["status"] = "no_stop"
        except Exception as e:
            res["status"] = "error"
            res["error"] = str(e)
        logger.info(f"[SL VERIFY #1] {pair} anchored to entry ${intended_entry:.4f} -> {res['status']}")
        return res
