"""
ANALYST-OPT: Production (live) metrics for a date window — real ledger + state only.

Used to compare scenario backtests against what production actually did in the
same calendar overlap (not the full pack window if production started later).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, PHASE6_LIVE_STATE, REBALANCE_HISTORY, TRADING_CONFIG_PHASE6

TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
PHASE6_DB = PROJECT_ROOT / "data" / "phase6.db"
CAPITAL_EVENTS_JSONL = PROJECT_ROOT / "data/state/capital_events_runner.jsonl"

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


def _sum_runner_external_flows_since(start: date) -> float:
    """Sum deposit/withdrawal flow_usd from runner capital events (fallback if DB sparse)."""
    if not CAPITAL_EVENTS_JSONL.exists():
        return 0.0
    net = 0.0
    for line in CAPITAL_EVENTS_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(str(ev.get("ts", "")))
        if not ts or ts.date() < start:
            continue
        et = str(ev.get("event_type", "")).lower()
        if et in ("deposit", "withdrawal"):
            net += float(ev.get("flow_usd") or ev.get("amount_usd") or 0)
    return round(net, 2)


def _deposit_adjusted_go_live_return(
    prod_start: date,
    end_equity: float,
) -> Dict[str, Any]:
    """
    Return % from go-live NAV through today, excluding external cash deposits/withdrawals.
    """
    from phase6.core.dashboard_serve_helpers import _nearest_ts, _total_usd_at_ts
    from phase6.core.portfolio_external_flows import (
        adjusted_period_return_pct,
        net_external_flow_between,
    )

    start_total = configured_initial_capital()
    start_ts: Optional[str] = None
    net_flow = 0.0
    end_ts: Optional[str] = None

    if PHASE6_DB.exists() and end_equity > 0:
        try:
            conn = sqlite3.connect(f"file:{PHASE6_DB}?mode=ro", uri=True, timeout=3.0)
            row = conn.execute("SELECT MIN(ts) FROM account_balances").fetchone()
            min_ts = row[0] if row else None
            if min_ts:
                st = _total_usd_at_ts(conn, min_ts)
                if st > 0:
                    start_ts = min_ts
                    start_total = st
            if start_ts is None:
                cutoff = datetime(prod_start.year, prod_start.month, prod_start.day, tzinfo=timezone.utc)
                start_ts = _nearest_ts(conn, cutoff)
                if start_ts:
                    st = _total_usd_at_ts(conn, start_ts)
                    if st > 0:
                        start_total = st
            row = conn.execute("SELECT MAX(ts) FROM account_balances").fetchone()
            end_ts = row[0] if row and row[0] else None
            if start_ts and end_ts:
                net_flow = net_external_flow_between(conn, start_ts, end_ts, _total_usd_at_ts)
            conn.close()
        except Exception:
            pass

    unadjusted = (
        round((end_equity - start_total) / start_total * 100.0, 2)
        if start_total > 0 and end_equity > 0
        else None
    )
    adjusted = (
        adjusted_period_return_pct(end_equity, start_total, net_flow)
        if start_total > 0 and end_equity > 0
        else None
    )
    return {
        "start_equity_usd": round(start_total, 2),
        "net_external_flows_usd": round(net_flow, 2),
        "total_return_pct_unadjusted": unadjusted,
        "total_return_pct": adjusted,
        "deposit_adjusted": True,
    }


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
    deposit_meta: Dict[str, Any] = {}
    if end_equity and end_equity > 0 and o_end >= date.today():
        deposit_meta = _deposit_adjusted_go_live_return(o_start, end_equity)
        return_pct = deposit_meta.get("total_return_pct")
        result["notes"].append(
            "return_pct is deposit-adjusted: (end − start − net external flows) / start; "
            "start NAV from DB snapshot at go-live when available."
        )
        if deposit_meta.get("total_return_pct_unadjusted") is not None:
            result["notes"].append(
                f"Unadjusted NAV change since start: {deposit_meta['total_return_pct_unadjusted']}% "
                f"(inflates when you add cash)."
            )
    elif end_equity and end_equity > 0 and initial > 0 and o_end >= date.today():
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
        **deposit_meta,
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