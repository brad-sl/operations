"""
P6 decision context — tie rebalance TradePlans to param audit (rotation sells).

Logged on every daily rebalance (ARCH-4 + legacy deploy_capital path).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _proposal_summary(proposals: Sequence[Any], limit: int = 11) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in (proposals or [])[:limit]:
        if isinstance(p, dict):
            out.append(
                {
                    "pair": p.get("pair"),
                    "side": p.get("side"),
                    "score": round(float(p.get("score", 0)), 4),
                    "source": p.get("source"),
                }
            )
        else:
            out.append(
                {
                    "pair": getattr(p, "pair", None),
                    "side": getattr(p, "side", None),
                    "score": round(float(getattr(p, "score", 0)), 4),
                    "source": getattr(p, "source", None),
                }
            )
    return out


def _normalize_actions(raw: Sequence[Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for a in raw or []:
        if not isinstance(a, dict):
            continue
        pair = a.get("pair") or a.get("product_id")
        action = str(a.get("action", a.get("side", ""))).upper()
        usd = float(a.get("usd", a.get("usd_amount", 0)) or 0)
        if not pair or not action:
            continue
        actions.append(
            {
                "pair": pair,
                "product_id": pair,
                "action": action,
                "usd": usd,
                "reason": a.get("reason", ""),
            }
        )
    return actions


def build_rebalance_context(
    *,
    runner: Any,
    path: str,
    actions_taken: List[Dict[str, Any]],
    proposals: Optional[Sequence[Any]] = None,
    plan: Any = None,
    executed_count: int = 0,
    skipped: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    decision_id = f"rebalance_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    tilted_plan: Dict[str, float] = {}
    if plan is not None:
        na = getattr(plan, "new_allocations", None) or {}
        if isinstance(na, dict):
            tilted_plan = {str(k): float(v) for k, v in na.items()}

    ctx: Dict[str, Any] = {
        "timestamp": now,
        "decision_id": decision_id,
        "rebalance_path": path,
        "actions_taken": actions_taken,
        "executed_count": executed_count,
        "skipped": skipped or [],
        "tilted_plan": tilted_plan,
        "proposals_summary": _proposal_summary(proposals or []),
        "strategy_used": getattr(plan, "strategy_used", None) if plan else None,
        "expected_exposure": getattr(plan, "expected_exposure", None) if plan else None,
        "rotations": getattr(plan, "rotations", None) if plan else None,
        "account_id": getattr(runner, "account_id", None),
        "trader_id": getattr(runner, "trader_id", None),
        "slot": getattr(runner, "_last_rebalance_slot_id", None),
    }
    brief = getattr(runner, "_last_strategic_brief", None)
    if brief:
        ctx["intelligence_brief_ref"] = True
    rsi = getattr(runner, "rsi_values", None)
    if rsi:
        ctx["rsi_snapshot"] = dict(list(rsi.items())[:11])

    try:
        from phase6.core.indicator_snapshot import build_basket_indicator_snapshot

        snap = build_basket_indicator_snapshot(
            universe=getattr(runner, "FIXED_UNIVERSE", None),
            runner_rsi_values=rsi if isinstance(rsi, dict) else None,
        )
        ctx["indicator_snapshot"] = snap["indicator_snapshot"]
        ctx["indicator_meta"] = snap["indicator_meta"]
    except Exception as exc:
        logger.debug("[DECISION-CTX] indicator_snapshot skipped: %s", exc)

    # Log-only: holdings + price + Stoch/RSI rotation shadow (allocator unchanged)
    try:
        from phase6.core.rotation_shadow import (
            build_rotation_shadow,
            extract_holdings_and_cash,
            load_price_snapshot,
        )

        holdings_usd, cash_usd = extract_holdings_and_cash(runner)
        if holdings_usd:
            ctx["holdings_before"] = holdings_usd
        if cash_usd is not None:
            ctx["cash_usd"] = cash_usd
        uni = getattr(runner, "FIXED_UNIVERSE", None)
        prices = load_price_snapshot(uni)
        if prices:
            ctx["price_snapshot"] = prices
        ind_snap = ctx.get("indicator_snapshot") or {}
        ctx["rotation_shadow"] = build_rotation_shadow(
            indicator_snapshot=ind_snap,
            actions_taken=actions_taken,
            holdings_before=holdings_usd,
            cash_usd=cash_usd,
        )
        meta = ctx.get("indicator_meta")
        if isinstance(meta, dict):
            meta = dict(meta)
            meta["rotation_shadow_schema"] = ctx["rotation_shadow"].get("schema_version")
            ctx["indicator_meta"] = meta
    except Exception as exc:
        logger.debug("[DECISION-CTX] rotation_shadow skipped: %s", exc)

    cap_events = getattr(runner, "_capital_events_for_decision", None) or []
    if cap_events:
        ctx["capital_events"] = list(cap_events)
    if extra:
        ctx.update(extra)
    return ctx


def record_rebalance_decision(
    runner: Any,
    *,
    path: str,
    actions_taken: List[Dict[str, Any]],
    proposals: Optional[Sequence[Any]] = None,
    plan: Any = None,
    executed_count: int = 0,
    skipped: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Persist decision context via TradeLedger (every rebalance)."""
    ledger = getattr(runner, "trade_ledger", None)
    if ledger is None:
        logger.warning("[DECISION-CTX] no trade_ledger on runner; skip")
        return None
    actions = _normalize_actions(actions_taken)
    if plan is not None and not actions:
        actions = _normalize_actions(getattr(plan, "actions", []) or [])
    ctx = build_rebalance_context(
        runner=runner,
        path=path,
        actions_taken=actions,
        proposals=proposals,
        plan=plan,
        executed_count=executed_count,
        skipped=skipped,
        extra=extra,
    )
    try:
        ledger.log_decision_context(ctx)
        logger.info(
            "[DECISION-CTX] recorded %s actions=%s path=%s",
            ctx["decision_id"],
            len(actions),
            path,
        )
        try:
            from phase6.core.runner_capital_events import clear_capital_events_after_rebalance_log

            if ctx.get("capital_events"):
                clear_capital_events_after_rebalance_log(runner)
        except Exception:
            pass
        return ctx["decision_id"]
    except Exception as exc:
        logger.warning("[DECISION-CTX] log failed: %s", exc)
        return None