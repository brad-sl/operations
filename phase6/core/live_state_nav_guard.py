"""Guard portfolio NAV writes/reads against cash-API-zero cliffs.

Class bug (2026-08-28): exchange get_account_balance returns 0.0 on API failure.
A refresh then wrote total_usd ≈ PAXG-only (~$84 = qty × arm_vwap) while true book
was ~$2300 cash-heavy. Dashboard header + deposit-adj 1D/7D/14D/30D all showed ~−96%.

Rules:
- Never treat a sudden total collapse as mark-to-market when cash unexplained vanished.
- Prefer prior cash/total when new cash≈0 and prior cash was material.
- Sanitize current_total for period KPIs vs last DB snapshot.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Collapse thresholds (portfolio is ~$1–5k scale; not exchange-wide)
MIN_PRIOR_TOTAL_USD = 100.0
# New total below this fraction of prior is a cliff candidate
CLIFF_FRAC = 0.50
# Unexplained cash drop vs prior total that looks like API wipe, not withdrawal
CASH_WIPE_FRAC = 0.35
# Absolute floor: if prior cash was large and new cash is near-zero
NEAR_ZERO_CASH = 1.0


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def guard_live_nav(
    *,
    new_total: float,
    new_cash: float,
    new_holdings: float,
    prior_total: Optional[float],
    prior_cash: Optional[float],
) -> Tuple[float, float, float, Dict[str, Any]]:
    """Return (total, cash, holdings, meta) safe to persist.

    If new cash collapsed while prior book was cash-heavy and holdings did not
    absorb the cash (no real redeploy), keep prior cash and recompute total.
    """
    nt = _f(new_total)
    nc = _f(new_cash)
    nh = _f(new_holdings)
    pt = _f(prior_total) if prior_total is not None else 0.0
    pc = _f(prior_cash) if prior_cash is not None else 0.0

    meta: Dict[str, Any] = {
        "guarded": False,
        "reason": None,
        "prior_total": pt or None,
        "prior_cash": pc or None,
        "raw_total": nt,
        "raw_cash": nc,
    }

    if pt < MIN_PRIOR_TOTAL_USD or pc < NEAR_ZERO_CASH:
        # No trustworthy prior — accept new (may be first write)
        return nt, nc, nh, meta

    cash_drop = pc - nc
    total_drop = pt - nt
    cliff = nt > 0 and nt < pt * CLIFF_FRAC
    cash_wiped = nc <= NEAR_ZERO_CASH and pc >= max(50.0, pt * CASH_WIPE_FRAC)
    unexplained = cash_drop >= pt * CASH_WIPE_FRAC and nh < pc * 0.5
    # Holdings did not grow by ~cash drop → not a full deploy into crypto
    holdings_absorbed = (nh - max(0.0, pt - pc)) >= cash_drop * 0.7 if cash_drop > 0 else False

    if (cliff or cash_wiped) and unexplained and not holdings_absorbed:
        safe_cash = pc
        safe_hold = nh if nh > 0 else max(0.0, pt - pc)
        safe_total = safe_cash + safe_hold
        # If still absurdly low vs prior, keep prior total
        if safe_total < pt * CLIFF_FRAC:
            safe_total = pt
            safe_cash = pc
            safe_hold = max(0.0, pt - pc)
        meta.update(
            {
                "guarded": True,
                "reason": "cash_api_zero_or_nav_cliff",
                "total_drop": round(total_drop, 2),
                "cash_drop": round(cash_drop, 2),
            }
        )
        return safe_total, safe_cash, safe_hold, meta

    return nt, nc, nh, meta


def sanitize_current_total_for_kpis(
    current_total: float,
    last_db_total: Optional[float],
    *,
    external_flow_usd: float = 0.0,
    honest_cash_plus_holdings: Optional[float] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Refuse end-NAV cliffs/spikes for period % when DB last sample disagrees.

    external_flow_usd: net deposits−withdrawals since last sample (negative = out).
    A real withdrawal can justify a lower current_total.

    honest_cash_plus_holdings: optional recomputed NAV from cash balances + non-cash
    holdings only (strips USDC-USD double-count). Preferred when present.
    """
    cur = _f(current_total)
    last = _f(last_db_total) if last_db_total is not None else 0.0
    flow = _f(external_flow_usd)
    honest = (
        _f(honest_cash_plus_holdings)
        if honest_cash_plus_holdings is not None
        else None
    )
    meta: Dict[str, Any] = {
        "sanitized": False,
        "reason": None,
        "raw_current": cur,
        "last_db_total": last or None,
        "external_flow_usd": flow,
        "honest_cash_plus_holdings": honest,
    }

    # Prefer explicit cash+non-cash holdings when it clearly undoes double-count
    if honest is not None and honest > MIN_PRIOR_TOTAL_USD:
        if cur <= 0 or abs(cur - honest) > max(25.0, honest * 0.05):
            # Spike/double-count or cliff vs honest book
            if cur > honest * 1.15 or cur < honest * 0.85 or cur <= 0:
                meta.update(
                    {
                        "sanitized": True,
                        "reason": "prefer_honest_cash_plus_holdings",
                        "drop_or_spike_usd": round(cur - honest, 2),
                    }
                )
                cur = honest

    if cur <= 0 and last > 0:
        meta.update({"sanitized": True, "reason": "nonpositive_current"})
        return last, meta
    if last < MIN_PRIOR_TOTAL_USD or cur <= 0:
        return cur, meta

    # Expected end ≈ last + flow + mtm; allow large mtm only if not cash-wipe shaped
    justified = last + flow
    # If flow explains most of the drop (withdrawal), allow current
    drop = last - cur
    if drop <= 0:
        # Spike without deposit flow (USDC double-count class: ~2× book overnight)
        spike = cur - last
        if spike >= last * 0.35 and flow <= last * 0.1:
            # Prefer honest if we have it; else last DB
            fixed = honest if (honest is not None and honest > MIN_PRIOR_TOTAL_USD) else last
            meta.update(
                {
                    "sanitized": True,
                    "reason": "nav_spike_vs_db_without_deposit",
                    "spike_usd": round(spike, 2),
                    "justified_end": round(justified, 2),
                }
            )
            return fixed, meta
        return cur, meta
    if drop < last * (1.0 - CLIFF_FRAC):
        # drop less than 50% — normal
        return cur, meta

    flow_explains = flow < 0 and abs(flow) >= drop * 0.5
    if flow_explains:
        return cur, meta

    # Cliff without withdrawal evidence → use last DB total for KPI end NAV
    meta.update(
        {
            "sanitized": True,
            "reason": "nav_cliff_vs_db_without_flow",
            "drop_usd": round(drop, 2),
            "justified_end": round(justified, 2),
        }
    )
    return last, meta


def honest_nav_from_state(state: Optional[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    """Recompute NAV = cash (USD+USDC+USDT) + non-cash trading holdings only."""
    st = state or {}
    meta: Dict[str, Any] = {"cash": 0.0, "holdings": 0.0, "method": None}
    try:
        from phase6.core.cash_buckets import (
            is_cash_like_pair,
            merge_cash_rows,
            trading_holdings_usd,
        )

        cash_rows = merge_cash_rows(st.get("balances") or [], st.get("cash_positions") or [])
        # Also fold any cash-like rows that leaked into positions
        leaked = [
            p
            for p in (st.get("positions") or []) + (st.get("trading_positions") or [])
            if is_cash_like_pair((p or {}).get("pair"))
        ]
        if leaked:
            cash_rows = merge_cash_rows(st.get("balances") or [], list(cash_rows) + leaked)
        cash = sum(float(r.get("value_usd") or r.get("amount") or 0) for r in cash_rows)
        trade = [
            p
            for p in (st.get("trading_positions") or st.get("positions") or [])
            if not is_cash_like_pair((p or {}).get("pair"))
        ]
        hold = trading_holdings_usd(trade)
        meta.update({"cash": cash, "holdings": hold, "method": "cash_buckets"})
        return cash + hold, meta
    except Exception as e:
        meta["error"] = str(e)
        # Fallback: balances USD+USDC only + non USDC-USD positions
        cash = 0.0
        for b in st.get("balances") or []:
            cur = str(b.get("currency") or "").upper()
            if cur in ("USD", "USDC", "USDT"):
                cash += _f(b.get("balance") or b.get("available"))
        hold = 0.0
        for p in st.get("positions") or []:
            pair = str((p or {}).get("pair") or "").upper()
            if pair in ("USD", "USDC", "USDT", "USDC-USD", "USDT-USD"):
                continue
            if pair.endswith("-USD") and pair.split("-")[0] in ("USDC", "USDT", "DAI"):
                continue
            hold += _f((p or {}).get("value_usd"))
        meta.update({"cash": cash, "holdings": hold, "method": "fallback"})
        return cash + hold, meta
