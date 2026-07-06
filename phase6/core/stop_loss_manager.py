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

    def __init__(self, exchange_client: Any, config: dict, mode: str = "shadow"):
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.shadow_mode = (mode == "shadow")

        # Default risk parameters (can be overridden by config)
        self.default_sl_pct = config.get("risk_management", {}).get("stop_loss_pct", 0.03)
        self.default_tp_pct = config.get("risk_management", {}).get("take_profit_pct", 0.06)

        # Adaptive SL support (#3 risk-aware sizing)
        self.adaptive_sl_enabled = config.get("risk_management", {}).get("adaptive_sl", True)
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
            return get_adaptive_sl_pct(
                pair=pair,
                base_pct=self.default_sl_pct,
                regime_bias=regime_bias,
                risk_data=risk_data,
            )
        except Exception as e:
            logger.debug(f"Adaptive SL fallback for {pair}: {e}")
            return self.default_sl_pct


    def attach_stop_loss(self, pair: str, entry_price: float, size: float, sl_pct: float = None, anchor_entry: float = None, order_id: Optional[str] = None) -> bool:
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
        try:
            from phase6.core.sl_preflight import settlement_poll_params
            from phase6.core.sl_risk_scorer import get_sl_risk

            risk = get_sl_risk(pair)
            risk_level = risk.get("level", "LOW")
            params = settlement_poll_params(pair, order_id=order_id, risk_level=risk_level)
            if not self.shadow_mode:
                settled = self.exchange.poll_for_settlement(
                    pair,
                    timeout=params["timeout"],
                    order_id=params.get("order_id"),
                )
                if not settled:
                    logger.warning(
                        f"[PRE-FLIGHT] Settlement poll failed/timeout for {pair} "
                        f"(risk={risk_level}, mode={params['mode']}, order_id={order_id}); proceeding cautiously"
                    )
                else:
                    logger.info(
                        f"[PRE-FLIGHT] Settlement confirmed for {pair} before SL "
                        f"(mode={params['mode']}, order_id={order_id or 'N/A'})"
                    )
        except Exception as e:
            logger.debug(f"[PRE-FLIGHT] poll skipped or failed: {e}")

        meta = self.exchange.get_product_metadata(pair)
        price_inc = float(meta.get("price_increment", 0.0001))

        calc_base = anchor_entry if (anchor_entry and anchor_entry > 0) else entry_price

        if (not calc_base or calc_base <= 0) and not self.shadow_mode:
            try:
                current_px = self.exchange.get_price(pair) or 0.0
                if current_px > 0:
                    logger.warning(
                        f"[SL FALLBACK] entry/anchor was 0 for {pair}; using current market ${current_px:.2f} for SL anchor"
                    )
                    calc_base = current_px
            except Exception:
                pass

        stop_price = calc_base * (1 - pct)
        limit_price = stop_price * 0.995

        from phase6.core.sl_preflight import quantize_stop_bundle

        stop_price, limit_price, stop_price_str, limit_price_str = quantize_stop_bundle(
            self.exchange, pair, calc_base, stop_price, limit_price
        )

        # Ensure prices are valid vs entry
        if stop_price >= entry_price:
            logger.warning(f"Stop price {stop_price} >= entry {entry_price}, adjusting...")
            price_inc = float(meta.get("price_increment", "0.0001"))
            stop_price = entry_price - price_inc
            stop_price_str = self.exchange.quantize_price(pair, stop_price)
            stop_price = float(stop_price_str)
            limit_price = stop_price - price_inc
            limit_price_str = self.exchange.quantize_price(pair, limit_price)
            limit_price = float(limit_price_str)
        
        # Quantize size
        size_str = self.exchange.quantize_size(pair, size)
        size = float(size_str)

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native SL for {pair}")
            print(f"         Entry: ${entry_price:.2f} | Stop: ${stop_price:.4f} | Limit: ${limit_price:.4f} | SL%: {pct*100:.1f}% | size: {size}")
            return True

        # Live mode with retry
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                result = self.exchange.place_stop_limit_sell(
                    product_id=pair,
                    qty=size,
                    stop_price=stop_price,
                    limit_price=limit_price
                )
                if result:
                    logger.info(f"Stop-loss successfully attached for {pair}")
                    return True
                else:
                    logger.warning(f"SL attempt {attempt}/{max_retries} failed for {pair}")
            except Exception as e:
                logger.error(f"SL attempt {attempt}/{max_retries} exception for {pair}: {e}")

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
            for order in open_orders:
                product_id = order.get("product_id") or order.get("pair")
                if basket and product_id not in basket:
                    continue
                order_type = str(order.get("type", "")).lower()
                side = str(order.get("side", "")).upper()
                has_stop = bool(order.get("stop_price")) or "stop" in order_type

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

        Returns: {pair: [order_id, ...], ...} for logging/verification.
        """
        suspended: Dict[str, List[str]] = {}
        total_suspended = 0

        for pair, orders in (active_stops or {}).items():
            suspended[pair] = []
            for order in orders:
                order_id = order.get("id") or order.get("order_id")
                ptype = order.get("protective_type", "PROTECTIVE")
                if not order_id:
                    logger.warning(f"[CR-03.2] Order without ID for {pair}: {order}")
                    continue

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
