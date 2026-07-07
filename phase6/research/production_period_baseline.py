"""
ANALYST-OPT: Production (live) metrics for a date window — real ledger + state only.

Used to compare scenario backtests against what production actually did in the
same calendar overlap (not the full pack window if production started later).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, PHASE6_LIVE_STATE, REBALANCE_HISTORY, TRADING_CONFIG_PHASE6

TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

IGNORE_SIGNAL_SOURCES = {"smoke_test", "test"}
IGNORE_PAIRS = {"TEST-USD"}


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = raw.replace("Z", "+00:00")
        if "+" not in s[10:]:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _parse_day(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def load_trades() -> List[dict]:
    if not TRADES_JSONL.exists():
        return []
    out = []
    with open(TRADES_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def production_data_bounds(trades: List[dict]) -> Tuple[Optional[date], Optional[date]]:
    dates: List[date] = []
    for t in trades:
        if t.get("pair") in IGNORE_PAIRS:
            continue
        if str(t.get("signal_source", "")).lower() in IGNORE_SIGNAL_SOURCES:
            continue
        qty = float(t.get("qty") or 0)
        if qty <= 0 and not t.get("usd_value"):
            continue
        ts = _parse_ts(str(t.get("timestamp", "")))
        if ts:
            dates.append(ts.date())
    if not dates:
        return None, None
    return min(dates), max(dates)


def intersect_windows(
    pack_start: date, pack_end: date, prod_start: Optional[date], prod_end: Optional[date]
) -> Optional[Tuple[date, date]]:
    if prod_start is None or prod_end is None:
        return None
    start = max(pack_start, prod_start)
    end = min(pack_end, prod_end)
    if start > end:
        return None
    return start, end


def filter_trades_in_window(trades: List[dict], start: date, end: date) -> List[dict]:
    kept = []
    for t in trades:
        if t.get("pair") in IGNORE_PAIRS:
            continue
        if str(t.get("signal_source", "")).lower() in IGNORE_SIGNAL_SOURCES:
            continue
        ts = _parse_ts(str(t.get("timestamp", "")))
        if not ts:
            continue
        d = ts.date()
        if start <= d <= end:
            kept.append(t)
    return kept


def load_rebalance_events(start: date, end: date) -> List[dict]:
    events = []
    if not REBALANCE_HISTORY.exists():
        return events
    with open(REBALANCE_HISTORY) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(str(ev.get("timestamp", "")))
            if not ts:
                continue
            if start <= ts.date() <= end:
                events.append(ev)
    return events


def configured_initial_capital() -> float:
    try:
        if TRADING_CONFIG_PHASE6.exists():
            cfg = json.loads(TRADING_CONFIG_PHASE6.read_text())
            return float(cfg.get("global_settings", {}).get("total_capital", 1000))
    except Exception:
        pass
    return 1000.0


def compute_production_metrics(
    pack_start: str,
    pack_end: str,
) -> Dict[str, Any]:
    """Metrics for production in overlap with scenario pack window."""
    ps, pe = _parse_day(pack_start), _parse_day(pack_end)
    trades = load_trades()
    prod_lo, prod_hi = production_data_bounds(trades)
    overlap = intersect_windows(ps, pe, prod_lo, prod_hi)

    result: Dict[str, Any] = {
        "source": "production_live",
        "pack_window": {"start": pack_start, "end": pack_end},
        "production_bounds": {
            "first_trade": prod_lo.isoformat() if prod_lo else None,
            "last_trade": prod_hi.isoformat() if prod_hi else None,
        },
        "overlap_window": None,
        "coverage": "none",
        "metrics": {},
        "notes": [],
    }

    if overlap is None:
        result["notes"].append(
            "No calendar overlap between scenario pack and production trade history. "
            "Use a pack window that includes live trading dates or compare on overlap-only pack."
        )
        return result

    o_start, o_end = overlap
    result["overlap_window"] = {"start": o_start.isoformat(), "end": o_end.isoformat()}
    result["coverage"] = "partial" if (o_start > ps or o_end < pe) else "full"

    window_trades = filter_trades_in_window(trades, o_start, o_end)
    rebals = load_rebalance_events(o_start, o_end)
    live_executed = sum(1 for e in rebals if e.get("mode") == "live" and int(e.get("executed", 0)) > 0)

    realized_pnl = sum(float(t.get("pnl") or 0) for t in window_trades)
    buy_usd = sum(
        float(t.get("usd_value") or 0)
        for t in window_trades
        if str(t.get("side", "")).upper() == "BUY"
    )
    sell_usd = sum(
        float(t.get("usd_value") or 0)
        for t in window_trades
        if str(t.get("side", "")).upper() == "SELL"
    )

    initial = configured_initial_capital()
    end_equity: Optional[float] = None
    if PHASE6_LIVE_STATE.exists():
        try:
            live = json.loads(PHASE6_LIVE_STATE.read_text())
            end_equity = float(live.get("total_usd") or 0)
        except Exception:
            pass

    return_pct: Optional[float] = None
    if end_equity and end_equity > 0 and initial > 0 and o_end >= date.today():
        return_pct = round((end_equity - initial) / initial * 100.0, 2)
        result["notes"].append(
            "return_pct uses configured initial capital vs current total_usd (mark-to-market); "
            "not a full audit-grade TWR for the overlap window."
        )
    elif realized_pnl and initial > 0:
        return_pct = round(realized_pnl / initial * 100.0, 2)
        result["notes"].append("return_pct approximated from summed trade pnl fields in overlap.")

    result["metrics"] = {
        "id": "production_live",
        "label": "Production (live ledger)",
        "engine": "live",
        "initial_capital": initial,
        "total_return_pct": return_pct,
        "realized_pnl_usd": round(realized_pnl, 2),
        "net_buy_usd": round(buy_usd - sell_usd, 2),
        "trade_count": len(window_trades),
        "live_rebalances_executed": live_executed,
        "end_equity_usd": round(end_equity, 2) if end_equity else None,
        "sharpe_ratio": None,
        "max_drawdown_pct": None,
    }
    return result


def compare_to_production(
    scenario_rows: List[dict],
    production: Dict[str, Any],
    primary_metric: str,
) -> List[dict]:
    """Per-scenario delta vs production on primary metric (when both defined)."""
    prod_m = (production.get("metrics") or {}).get(primary_metric)
    rows = []
    for sc in scenario_rows:
        val = (sc.get("metrics") or {}).get(primary_metric)
        delta = None
        beats = None
        if prod_m is not None and val is not None:
            try:
                delta = round(float(val) - float(prod_m), 4)
                if primary_metric == "max_drawdown_pct":
                    beats = float(val) < float(prod_m)
                else:
                    beats = float(val) > float(prod_m)
            except (TypeError, ValueError):
                pass
        rows.append(
            {
                "scenario_id": sc.get("id"),
                "scenario_value": val,
                "production_value": prod_m,
                "delta": delta,
                "beats_production": beats,
                "primary_metric": primary_metric,
            }
        )
    return rows


def compute_since_go_live() -> Dict[str, Any]:
    """Production metrics from first real trade through today."""
    trades = load_trades()
    prod_lo, prod_hi = production_data_bounds(trades)
    if prod_lo is None:
        return {
            "source": "production_live",
            "coverage": "none",
            "metrics": {},
            "notes": ["No production trades in ledger."],
        }
    end = date.today()
    return compute_production_metrics(prod_lo.isoformat(), end.isoformat())