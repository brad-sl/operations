"""Resolve whether a cached position quote is too old to show PnL %."""
from __future__ import annotations

from typing import Any, Dict, Optional

from phase6.core.price_freshness import DEFAULT_MAX_QUOTE_AGE_SEC, is_quote_stale


def resolve_position_price_stale(
    position: Dict[str, Any],
    *,
    pair_quote_ts: Optional[str],
    state_as_of: Optional[str],
    max_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SEC,
) -> bool:
    """True only when we should hide misleading unrealized PnL.

    Always recompute from timestamps — do not trust baked-in price_stale=True
    from a prior enrich (that frozen flag forever after one stale cycle).
    """
    px = float(position.get("current_price") or 0)
    pos_ts = position.get("price_as_of") or pair_quote_ts

    # Fresh pair quote wins
    if pos_ts and not is_quote_stale(pos_ts, max_age_seconds=max_age_seconds):
        return False

    # Whole cache snapshot refreshed recently — trust bundled current_price
    # even if price_history last_updated lagged (RSI-cache skip bug era).
    if px > 0 and state_as_of and not is_quote_stale(state_as_of, max_age_seconds=max_age_seconds):
        return False

    if pos_ts:
        return is_quote_stale(pos_ts, max_age_seconds=max_age_seconds)
    if state_as_of:
        return is_quote_stale(state_as_of, max_age_seconds=max_age_seconds)
    return True
