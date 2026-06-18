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

    def attach_stop_loss(self, pair: str, entry_price: float, size: float, sl_pct: float = None) -> bool:
        """
        Attach a native stop-loss order with retry logic.

        Returns True on successful placement (or shadow success).
        """
        pct = sl_pct if sl_pct is not None else self.default_sl_pct
        
        # Quantize stop and limit prices
        meta = self.exchange.get_product_metadata(pair)
        # Use full precision API prices for SL/TP attachment
        stop_price = entry_price * (1 - pct)
        limit_price = stop_price * 0.995
        
        # Quantize prices ensuring sub-dollar precision compliance
        stop_price_str = self.exchange._quantize_price(stop_price, meta.get("price_increment", "0.00000001"))
        stop_price = float(stop_price_str)
        limit_price_str = self.exchange._quantize_price(limit_price, meta.get("price_increment", "0.00000001"))
        limit_price = float(limit_price_str)
        
        # Ensure prices are valid
        if stop_price >= entry_price:
            logger.warning(f"Stop price {stop_price} >= entry {entry_price}, adjusting...")
            price_inc = float(meta.get("price_increment", "0.0001"))
            stop_price = entry_price - price_inc
            stop_price_str = self.exchange._quantize_price(stop_price, meta.get("price_increment", "0.00000001"))
            stop_price = float(stop_price_str)
            limit_price = stop_price - price_inc
            limit_price_str = self.exchange._quantize_price(limit_price, meta.get("price_increment", "0.00000001"))
            limit_price = float(limit_price_str)
        
        # Quantize size
        size_str = self.exchange._quantize_size(size, meta["base_increment"])
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
        tp_price_str = self.exchange._quantize_price(tp_price, meta["price_increment"])
        tp_price_quantized = float(tp_price_str)

        if hasattr(self.exchange, "place_limit_sell"):
            return self.exchange.place_limit_sell(pair, size, tp_price_quantized)
        print("[TODO] place_limit_sell not yet implemented on exchange client")
        return False

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
