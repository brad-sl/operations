"""
CR-03: Atomic Stop-Loss / Take-Profit Suspend/Reattach Coordinator

Provides atomic suspend/reattach semantics for protective orders (SL/TP)
during rebalancing, Fresh Start, or position adjustments.
"""

import logging
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class StopLossCoordinator:
    """
    Atomic coordinator for CR-03 suspend/reattach of stop-loss (and future TP) orders.
    """

    def __init__(self, stop_loss_manager, exchange_client=None, config: Optional[Dict[str, Any]] = None):
        self.sl_manager = stop_loss_manager
        self.client = exchange_client or stop_loss_manager.exchange
        self.config = config or {}
        self.mode = self.config.get("mode", getattr(stop_loss_manager, 'mode', 'shadow'))
        self.require_atomic = self.config.get("require_atomic", True)

        self._suspended_orders: Dict[str, List[Dict[str, Any]]] = {}
        self._reattach_positions: Dict[str, float] = {}

    def suspend_protective_orders(self, pairs: List[str]) -> Dict[str, Any]:
        """Suspend (cancel) all active SL orders for the given pairs.
        Improved: better filtering for stop orders, uses get_open_stop_orders if available,
        detailed logging, and safe handling of different Coinbase response shapes.
        """
        canceled = []
        for pair in pairs:
            try:
                # Prefer dedicated stop fetch if present on client
                if hasattr(self.client, "get_open_stop_orders"):
                    orders = self.client.get_open_stop_orders(pair) or []
                else:
                    orders = self.client.get_open_orders(pair) or []
                
                for order in orders:
                    order_type = str(order.get("order_type", "")).lower()
                    has_stop = bool(order.get("stop_price")) or "stop" in order_type
                    oc = order.get("order_configuration", {}) or {}
                    has_stop_config = any(k in oc for k in ("stop_limit", "stop_market", "stop"))
                    
                    if has_stop or has_stop_config:
                        oid = order.get("order_id") or order.get("id") or order.get("client_order_id")
                        if oid:
                            success = self.client.cancel_order(oid)
                            canceled.append(oid)
                            logger.info(f"[SL] Cancelled stop order {oid} for {pair} (success={success})")
            except Exception as e:
                logger.warning(f"suspend error for {pair}: {e}")

        self._suspended_orders = {p: [] for p in pairs}
        return {"canceled_ids": canceled, "count": len(canceled)}

    def reattach_protective_orders(self, positions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Re-attach stop-loss orders for the given positions.
        Accepts both simple dict (amount only) and enriched dict from get_enriched_positions().

        Expected enriched position format:
            {
                "amount": float,
                "entry_price": float,      # preferred
                "current_price": float,
                "value_usd": float,
                ...
            }
        """
        results = {}

        for key, value in positions.items():
            # Normalize pair name
            if isinstance(key, str) and "-USD" in key:
                pair = key
            else:
                pair = f"{key}-USD"

            # Extract data from enriched dict or simple value
            if isinstance(value, dict):
                amount = value.get("amount", value.get("qty", 0))
                # Prefer explicit entry_price, fall back to current_price
                entry_price = value.get("entry_price") or value.get("current_price") or value.get("price", 0)
            else:
                amount = float(value) if value else 0
                entry_price = 0

            if amount <= 0 or entry_price <= 0:
                results[pair] = {"status": "skipped", "reason": "missing amount or price"}
                continue

            try:
                success = self.sl_manager.attach_stop_loss(
                    pair=pair,
                    entry_price=float(entry_price),
                    size=float(amount),
                    sl_pct=None  # use default from config
                )
                results[pair] = {
                    "status": "attached" if success else "failed",
                    "entry_price": entry_price,
                    "size": amount
                }
            except Exception as e:
                logger.error(f"Failed to re-attach SL for {pair}: {e}")
                results[pair] = {"status": "error", "error": str(e)}

        return results


    @contextmanager
    def suspend_reattach_context(self, pairs: List[str], new_positions: Dict[str, Any]):
        """
        Atomic context manager for the full CR-03 cycle.

        Usage:
            with coordinator.suspend_reattach_context(pairs, enriched_positions):
                # perform rebalance / position changes here
                pass

        new_positions should be an enriched dict from get_enriched_positions()
        (or at minimum contain 'amount' and 'entry_price'/'current_price').
        """
        suspend_summary = self.suspend_protective_orders(pairs)
        try:
            yield suspend_summary
            result = self.reattach_protective_orders(new_positions)
            attached = [p for p, r in result.items() if r.get("status") == "attached"]
            logger.info(f"[CR-03] Re-attached stops for {len(attached)} pairs: {attached}")
        except Exception as exc:
            logger.error(f"[CR-03] Exception during protected window: {exc}", exc_info=True)
            if self.require_atomic:
                logger.warning("[CR-03] Attempting restoration re-attach")
                try:
                    self.reattach_protective_orders(new_positions)
                except Exception as rollback_err:
                    logger.critical(f"[CR-03] Restoration failed: {rollback_err}")
            raise
        finally:
            self._suspended_orders.clear()

def create_cr03_coordinator(stop_loss_manager, **kwargs) -> StopLossCoordinator:
    return StopLossCoordinator(stop_loss_manager, config=kwargs)
