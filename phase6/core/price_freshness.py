"""Quote freshness for dashboard PnL — detect stale runner price snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

# Beyond this age, pair PnL % is hidden on the dashboard (misleading).
DEFAULT_MAX_QUOTE_AGE_SEC = 900  # 15 minutes
# Runner writes some timestamps in host local wall time without offset (PT).
_LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def parse_iso_age_seconds(
    ts: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> Optional[float]:
    if not ts or not str(ts).strip():
        return None
    now = now or datetime.now(timezone.utc)
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # Naive: treat as America/Los_Angeles wall time (runner host), not UTC
        dt = dt.replace(tzinfo=_LOCAL_TZ)
    return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds())


def is_quote_stale(
    ts: Optional[str],
    *,
    max_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SEC,
    now: Optional[datetime] = None,
) -> bool:
    age = parse_iso_age_seconds(ts, now=now)
    if age is None:
        return True
    return age > max_age_seconds


def apply_stale_price_pnl_guard(position: Dict[str, Any]) -> Dict[str, Any]:
    """If quote is stale, suppress misleading unrealized PnL fields."""
    out = dict(position)
    if not out.get("price_stale"):
        return out
    out["pnl_unreliable"] = True
    out["unrealized_pnl_pct"] = None
    out["unrealized_pnl_usd"] = None
    return out
