"""
CR-03: Atomic Stop-Loss / Take-Profit Suspend/Reattach Coordinator

Provides atomic suspend/reattach semantics for protective orders (SL/TP)
during rebalancing, Fresh Start, or position adjustments.

See docs/DATA_FLOW_AND_LOCATIONS.md (and phase6/core/paths.py) for paths.
"""

from .paths import PHASE6_LIVE_STATE  # per DATA_FLOW_AND_LOCATIONS.md
import os
import json
import logging
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Callable

from phase6.core.sl_preflight import (
    sanitize_reattach_order_id,
    order_configuration_is_stop,
    cancel_open_stops_for_pair,
    poll_available_after_cancel,
)

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
        self._buy_order_ids: Dict[str, str] = {}

    def set_buy_order_ids(self, mapping: Optional[Dict[str, str]]) -> None:
        """Pairs -> recent BUY order_id for settlement poll on re-attach (ANALYST-005)."""
        self._buy_order_ids = dict(mapping or {})


    def _latest_ledger_open_buy_entry(self, pair: str) -> float:
        """Most recent BUY entry still open (after last full exit), else 0.

        Prevents stale lot prices from a prior cycle (e.g. RAVE Aug-12 entry)
        from anchoring SL on a brand-new buy at a lower print.
        """
        try:
            from phase6.core.trade_ledger import TradeLedger

            trades = TradeLedger().get_recent_trades(limit=400) or []
        except Exception as e:
            logger.debug("[SL-ANCHOR] ledger open-buy lookup failed for %s: %s", pair, e)
            return 0.0

        pair_u = str(pair).upper()
        # Newest first
        def _ts(r: Dict[str, Any]) -> str:
            return str(r.get("timestamp") or r.get("ts") or "")

        rows = [
            r
            for r in trades
            if str(r.get("pair") or "").upper() == pair_u
            and str(r.get("side") or "").upper() in ("BUY", "SELL")
        ]
        rows.sort(key=_ts, reverse=True)
        # Walk newest→oldest: if we hit SELL first, flat (no open lot from this window)
        for r in rows:
            side = str(r.get("side") or "").upper()
            if side == "SELL":
                reason = str(r.get("reason") or r.get("exit_reason") or "")
                # dust after SL still means flat for anchor purposes once primary exit hit
                return 0.0
            if side == "BUY":
                try:
                    px = float(r.get("entry_price") or r.get("price") or 0)
                except (TypeError, ValueError):
                    px = 0.0
                if px > 0:
                    return px
        return 0.0

    def _get_original_entry(self, pair: str, value: Any) -> float:
        """Lookup entry for SL anchor — never prefer a dead prior-cycle lot.

        Order:
          1) Explicit fill/entry fields on the position dict
          2) Latest ledger BUY that is still the open lot (no later SELL)
          3) live_state entry only if still plausible vs mark
          4) 0 → caller uses current price
        """
        current_p = 0.0
        if isinstance(value, dict):
            try:
                current_p = float(value.get("current_price") or value.get("price") or 0)
            except (TypeError, ValueError):
                current_p = 0.0
            for k in ("buy_fill_price", "fill_price", "entry_price", "original_entry", "entry"):
                v = value.get(k)
                try:
                    px = float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    px = 0.0
                if px > 0:
                    # Reject obviously stale high anchors (stop would sit at/above market)
                    if current_p > 0 and px * 0.97 >= current_p:
                        logger.warning(
                            "[SL-ANCHOR] %s rejecting dict %s=$%.4f (mark $%.4f — stop would be >= market)",
                            pair, k, px, current_p,
                        )
                        continue
                    return px

        ledger_px = self._latest_ledger_open_buy_entry(pair)
        if ledger_px > 0:
            if current_p <= 0 or ledger_px * 0.97 < current_p:
                logger.info("[SL-ANCHOR ledger_open_buy] %s: using $%.4f", pair, ledger_px)
                return ledger_px
            logger.warning(
                "[SL-ANCHOR] %s ledger buy $%.4f stale vs mark $%.4f — skip",
                pair, ledger_px, current_p,
            )

        # Fallback to live_state only if mark-plausible
        try:
            live_state_path = str(PHASE6_LIVE_STATE)
            if os.path.exists(live_state_path):
                with open(live_state_path) as f:
                    ls = json.load(f)
                for p in ls.get("positions", []):
                    p_pair = p.get("pair")
                    if p_pair == pair or (
                        p_pair and p_pair.replace("-USD", "") == pair.replace("-USD", "")
                    ):
                        ep = p.get("entry_price", 0)
                        try:
                            epf = float(ep) if ep else 0.0
                        except (TypeError, ValueError):
                            epf = 0.0
                        if epf <= 0:
                            continue
                        mark = current_p
                        if mark <= 0:
                            try:
                                mark = float(p.get("current_price") or 0)
                            except (TypeError, ValueError):
                                mark = 0.0
                        if mark > 0 and epf * 0.97 >= mark:
                            logger.warning(
                                "[SL-ANCHOR] %s live_state entry $%.4f stale vs mark $%.4f — skip",
                                pair, epf, mark,
                            )
                            continue
                        logger.info(
                            "[SL-ANCHOR fallback#live_state] %s: using $%.4f", pair, epf
                        )
                        return epf
        except Exception as e:
            logger.debug("[SL-ANCHOR] live_state fallback skipped for %s: %s", pair, e)
        return 0.0

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
                    oc = order.get("order_configuration", {}) or {}
                    has_stop = order_configuration_is_stop(oc) or bool(order.get("stop_price")) or "stop" in str(order.get("order_type", "")).lower()
                    
                    if has_stop:
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
                # #1 HARDEN: Use robust original entry lookup (targeted anchoring fix)
                intended_entry = self._get_original_entry(pair, value)
                current_p = value.get("current_price") or value.get("price", 0)
                try:
                    current_p = float(current_p or 0)
                except (TypeError, ValueError):
                    current_p = 0.0
                entry_for_calc = intended_entry if intended_entry > 0 else current_p
                # Hard guard: never attach SL from an entry that already implies stop >= mark
                if entry_for_calc > 0 and current_p > 0 and entry_for_calc * 0.97 >= current_p:
                    logger.warning(
                        "[SL-ANCHOR] %s entry $%.4f unusable vs mark $%.4f — anchoring to mark",
                        pair, entry_for_calc, current_p,
                    )
                    entry_for_calc = current_p
                    intended_entry = current_p
            else:
                amount = float(value) if value else 0
                entry_for_calc = 0
                intended_entry = 0
                current_p = 0.0

            # P0-02.9: ensure size passed for SL attachment is explicitly quantized
            # using canonical quantizer + real metadata (re-attach / coordinator paths)
            if amount > 0 and hasattr(self.client, "quantize_size"):
                try:
                    amount = float(self.client.quantize_size(pair, float(amount)))
                except Exception:
                    pass

            if amount <= 0 or entry_for_calc <= 0:
                results[pair] = {"status": "skipped", "reason": "missing amount or price"}
                continue

            # Release holds from existing stops before re-attach (root cause of PREVIEW_INSUFFICIENT_FUND).
            released = cancel_open_stops_for_pair(self.client, pair)
            if released:
                poll_available_after_cancel(self.client, pair, timeout=4.0)

            if intended_entry > 0 and current_p > 0 and abs(intended_entry - current_p) / max(current_p, 1e-9) > 0.005:
                logger.info(f"[SL-ANCHOR #1] {pair}: using original entry ${intended_entry:.4f} for SL (current ${current_p:.4f})")

            try:
                oid_raw = self._buy_order_ids.get(pair) or self._buy_order_ids.get(pair.replace("-USD", ""))
                oid = sanitize_reattach_order_id(self.client, pair, oid_raw)
                success = self.sl_manager.attach_stop_loss(
                    pair=pair,
                    entry_price=float(entry_for_calc),
                    size=float(amount),
                    sl_pct=None,
                    anchor_entry=float(intended_entry) if intended_entry > 0 else None,
                    order_id=oid,
                )
                results[pair] = {
                    "status": "attached" if success else "failed",
                    "entry_price": entry_for_calc,
                    "intended_entry": intended_entry,
                    "size": amount
                }
                # #1 verify after attach
                if success and intended_entry > 0:
                    try:
                        v = self.sl_manager.verify_protective_stop(pair, intended_entry)
                        results[pair]["verify"] = {"verified": v.get("verified"), "status": v.get("status")}
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to re-attach SL for {pair}: {e}")
                results[pair] = {"status": "error", "error": str(e)}

        return results

    def attach_stop_loss(
        self,
        pair: str,
        entry_price: float,
        size: float,
        *,
        order_id: Optional[str] = None,
        fresh_buy: bool = True,
    ) -> bool:
        """Post-buy SL attach for platform TradeExecutor (parity with OrderExecutor path)."""
        oid = order_id or self._buy_order_ids.get(pair)
        try:
            return bool(
                self.sl_manager.attach_stop_loss(
                    pair,
                    entry_price,
                    size,
                    anchor_entry=entry_price if entry_price > 0 else None,
                    order_id=oid,
                    fresh_buy=fresh_buy,
                )
            )
        except Exception as e:
            logger.warning("[SL-COORD] attach_stop_loss failed %s: %s", pair, e)
            return False

    @contextmanager
    def suspend_reattach_context(
        self,
        pairs: List[str],
        new_positions: Dict[str, Any],
        *,
        refresh_positions: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        """
        Atomic context manager for the full CR-03 cycle.

        Usage:
            with coordinator.suspend_reattach_context(
                pairs, enriched_positions, refresh_positions=get_fresh
            ):
                # perform rebalance / position changes here
                pass

        new_positions should be an enriched dict from get_enriched_positions()
        (or at minimum contain 'amount' and 'entry_price'/'current_price').

        refresh_positions: optional callable invoked AFTER the body succeeds (and
        on atomic rollback) so SL reattach covers post-add full bag size, not the
        pre-trade snapshot. Falls back to new_positions if refresh fails/empty.
        """
        suspend_summary = self.suspend_protective_orders(pairs)

        def _positions_for_reattach() -> Dict[str, Any]:
            if refresh_positions is None:
                return new_positions
            try:
                refreshed = refresh_positions()
                if isinstance(refreshed, dict) and refreshed:
                    logger.info(
                        "[CR-03] Using refreshed post-trade positions for SL reattach (n=%d)",
                        len(refreshed),
                    )
                    return refreshed
                logger.warning(
                    "[CR-03] position refresh returned empty; using pre-trade snapshot"
                )
            except Exception as e:
                logger.warning(
                    "[CR-03] position refresh failed; using pre-trade snapshot: %s", e
                )
            return new_positions

        try:
            yield suspend_summary
            pos = _positions_for_reattach()
            result = self.reattach_protective_orders(pos)
            attached = [p for p, r in result.items() if r.get("status") == "attached"]
            logger.info(f"[CR-03] Re-attached stops for {len(attached)} pairs: {attached}")
            # ENG-S4-01: end-to-end CR-03 verification on success path
            try:
                basket = list(pos.keys())
                recon = self.sl_manager.verify_reconciliation(
                    basket=basket,
                    suspended=suspend_summary,
                )
                logger.info(
                    "[CR-03.5] verify_reconciliation success=%s details=%s",
                    recon.get("success"),
                    recon.get("details"),
                )
            except Exception as verr:
                logger.warning("[CR-03.5] verify_reconciliation failed: %s", verr)
        except Exception as exc:
            logger.error(f"[CR-03] Exception during protected window: {exc}", exc_info=True)
            if self.require_atomic:
                logger.warning("[CR-03] Attempting restoration re-attach")
                try:
                    self.reattach_protective_orders(_positions_for_reattach())
                except Exception as rollback_err:
                    logger.critical(f"[CR-03] Restoration failed: {rollback_err}")
            raise
        finally:
            self._suspended_orders.clear()

def create_cr03_coordinator(stop_loss_manager, **kwargs) -> StopLossCoordinator:
    return StopLossCoordinator(stop_loss_manager, config=kwargs)
