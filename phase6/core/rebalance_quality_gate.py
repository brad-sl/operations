"""
P6-OPS / outage quality: gates before rebalance decisions execute.

- Exchange connectivity (no trades on network blackout)
- signal_freshness_enforced from config (no allocator on incomplete/stale basket)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

HARD_FAIL_MARKERS = (
    "network",
    "unreachable",
    "timeout",
    "timed out",
    "connection",
    "failed to obtain",
    "orders api",
    "name resolution",
    "errno 101",
)


@dataclass
class RebalanceGateResult:
    allowed: bool
    connectivity_ok: bool
    data_ready: bool
    reasons: List[str]
    slot_id: Optional[str] = None


def signal_freshness_enforced(runner: "Phase6Runner") -> bool:
    gs = runner.config_dict.get("global_settings", {}) or {}
    return bool(gs.get("signal_freshness_enforced", False))


def check_exchange_connectivity(exchange: Any, probe_pair: str = "BTC-USD") -> tuple[bool, str]:
    """Lightweight live probe — balance + positive spot price."""
    if exchange is None:
        return False, "no_exchange"
    if getattr(exchange, "shadow_mode", False):
        return True, "shadow_ok"
    try:
        bal = exchange.get_account_balance("USD")
        if bal is None:
            return False, "balance_none"
        price_fn = getattr(exchange, "get_price", None) or getattr(exchange, "get_market_price", None)
        if not price_fn:
            return True, "balance_ok_no_price_fn"
        px = price_fn(probe_pair)
        if px is None or float(px) <= 0:
            return False, f"price_invalid:{px}"
        return True, "ok"
    except Exception as exc:
        msg = str(exc).lower()
        if any(m in msg for m in HARD_FAIL_MARKERS):
            return False, f"network:{exc}"
        return False, f"exchange_error:{exc}"


def assess_data_readiness(runner: "Phase6Runner", coverage_report: Dict[str, Any]) -> tuple[bool, List[str]]:
    """When signal_freshness_enforced, require full non-stale basket coverage."""
    if not signal_freshness_enforced(runner):
        return True, []

    reasons: List[str] = []
    if not coverage_report.get("complete"):
        reasons.append("incomplete_coverage")
    stale_rsi = coverage_report.get("stale_rsi") or []
    stale_sent = coverage_report.get("stale_sentiment") or []
    if stale_rsi:
        reasons.append(f"stale_rsi:{','.join(stale_rsi[:5])}")
    if stale_sent:
        reasons.append(f"stale_sentiment:{','.join(stale_sent[:5])}")
    if coverage_report.get("signal_complete") is False:
        reasons.append("signal_coverage_incomplete")
    return len(reasons) == 0, reasons


def evaluate_rebalance_gate(
    runner: "Phase6Runner",
    coverage_report: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> RebalanceGateResult:
    from datetime import datetime as dt

    now = now or dt.now()
    slot_id = runner._due_rebalance_slot_id(now)
    conn_ok, conn_detail = check_exchange_connectivity(getattr(runner, "exchange", None))
    data_ok, data_reasons = assess_data_readiness(runner, coverage_report)

    reasons: List[str] = []
    if not conn_ok:
        reasons.append(f"connectivity:{conn_detail}")
    reasons.extend(data_reasons)

    allowed = conn_ok and data_ok
    if not allowed:
        logger.warning(
            "[REBALANCE GATE] blocked slot=%s conn=%s data=%s reasons=%s",
            slot_id,
            conn_ok,
            data_ok,
            reasons,
        )
    else:
        logger.info(
            "[REBALANCE GATE] allowed slot=%s (connectivity + basket signals ready)",
            slot_id,
        )

    return RebalanceGateResult(
        allowed=allowed,
        connectivity_ok=conn_ok,
        data_ready=data_ok,
        reasons=reasons,
        slot_id=slot_id,
    )


def should_mark_slot_complete(
    *,
    connectivity_ok: bool,
    data_ready: bool,
    executed: int,
    skipped: list,
    enforced: bool,
) -> bool:
    """
    Do not burn a daily slot on outage or stale-signal rebalance attempts.
    Successful trades always mark complete (user got the window action).
    """
    if executed > 0:
        return True
    if enforced and (not connectivity_ok or not data_ready):
        return False
    if not connectivity_ok:
        return False
    if skipped:
        for item in skipped:
            blob = str(item.get("reason", item.get("error", item))).lower()
            if any(m in blob for m in HARD_FAIL_MARKERS):
                return False
    # Intentional no-op (0 actions / all skipped for business rules) with good inputs
    return True


def classify_skip_hard_failure(skipped: list) -> bool:
    for item in skipped or []:
        blob = str(item.get("reason", item.get("error", item))).lower()
        if any(m in blob for m in HARD_FAIL_MARKERS):
            return True
    return False