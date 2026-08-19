"""
Detect deposits/withdrawals from balance snapshots so period returns exclude external cash flows.

Heuristic: large cash change with flat holdings value → external flow (not trading PnL).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLOWS_JSONL = Path("data/state/capital_external_flows.jsonl")
MIN_FLOW_USD = 50.0


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        if "T" in s:
            return datetime.fromisoformat(s)
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(s[:26])
        except ValueError:
            return None


def cash_usd_at_ts(conn: sqlite3.Connection, ts: str) -> float:
    total = 0.0
    for row in conn.execute(
        "SELECT currency, balance FROM account_balances WHERE ts = ?",
        (ts,),
    ):
        cur, bal = (row[0] or "").upper(), float(row[1] or 0)
        if cur in ("USD", "USDC"):
            total += bal
    return total


def holdings_usd_at_ts(conn: sqlite3.Connection, ts: str, total_fn) -> float:
    return float(total_fn(conn, ts)) - cash_usd_at_ts(conn, ts)


def classify_external_flow_usd(
    delta_total: float,
    delta_cash: float,
    delta_holdings: float,
    min_flow: float = MIN_FLOW_USD,
) -> float:
    """Signed USD: positive = deposit, negative = withdrawal."""
    if abs(delta_total) < min_flow and abs(delta_cash) < min_flow:
        return 0.0
    hold_flat = abs(delta_holdings) < max(25.0, 0.25 * max(abs(delta_cash), abs(delta_total)))
    if abs(delta_cash) >= min_flow and hold_flat:
        return delta_cash
    if abs(delta_total) >= min_flow and abs(delta_total - delta_cash) < 35.0 and hold_flat:
        return delta_cash if abs(delta_cash) >= min_flow else delta_total
    return 0.0


def iter_distinct_balance_timestamps(
    conn: sqlite3.Connection,
    after_ts: Optional[str] = None,
    before_ts: Optional[str] = None,
) -> List[str]:
    q = "SELECT DISTINCT ts FROM account_balances WHERE 1=1"
    params: List[Any] = []
    if after_ts:
        q += " AND ts > ?"
        params.append(after_ts)
    if before_ts:
        q += " AND ts <= ?"
        params.append(before_ts)
    q += " ORDER BY ts ASC"
    return [r[0] for r in conn.execute(q, params)]


def net_external_flow_between(
    conn: sqlite3.Connection,
    start_ts: str,
    end_ts: Optional[str],
    total_fn,
) -> float:
    """
    Sum classified external flows on snapshot boundaries with ts in (start_ts, end_ts].
    Optimized: full tick cash series, but only rebuild NAV when cash moved ≥ ~$50
    (avoids thousands of total_fn calls that timed out the dashboard).
    """
    q = """
        SELECT ts, SUM(balance) AS cash
        FROM account_balances
        WHERE currency IN ('USD', 'USDC') AND ts > ?
    """
    params: List[Any] = [start_ts]
    if end_ts:
        q += " AND ts <= ?"
        params.append(end_ts)
    q += " GROUP BY ts ORDER BY ts"
    cash_rows = conn.execute(q, params).fetchall()
    if not cash_rows:
        return 0.0

    prev_total = float(total_fn(conn, start_ts))
    prev_cash = cash_usd_at_ts(conn, start_ts)
    prev_hold = prev_total - prev_cash
    net = 0.0
    # Only NAV-rebuild when cash moved enough to be a candidate external flow.
    cash_move_floor = max(25.0, MIN_FLOW_USD * 0.5)

    for ts, cash in cash_rows:
        cash = float(cash or 0)
        dc = cash - prev_cash
        if abs(dc) < 1.0:
            continue
        if abs(dc) < cash_move_floor:
            # Noise / settlement dust — track cash only.
            prev_cash = cash
            continue
        total = float(total_fn(conn, ts))
        hold = total - cash
        flow = classify_external_flow_usd(
            total - prev_total,
            cash - prev_cash,
            hold - prev_hold,
        )
        if abs(flow) >= MIN_FLOW_USD:
            net += flow
            _append_flow_record(ts, flow, total - prev_total, cash - prev_cash, hold - prev_hold)
        prev_total, prev_cash, prev_hold = total, cash, hold
    return round(net, 2)


def _append_flow_record(ts: str, flow_usd: float, d_total: float, d_cash: float, d_hold: float) -> None:
    """Best-effort audit log (dedupe same ts+amount)."""
    try:
        FLOWS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "ts": ts,
                "flow_usd": flow_usd,
                "delta_total": round(d_total, 2),
                "delta_cash": round(d_cash, 2),
                "delta_holdings": round(d_hold, 2),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if FLOWS_JSONL.exists():
            tail = FLOWS_JSONL.read_text().strip().splitlines()[-5:]
            for t in tail:
                try:
                    o = json.loads(t)
                    if o.get("ts") == ts and abs(float(o.get("flow_usd", 0)) - flow_usd) < 0.01:
                        return
                except Exception:
                    pass
        with FLOWS_JSONL.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def adjusted_period_return_pct(
    current_total: float,
    past_total: float,
    net_external_flow: float,
) -> float:
    if past_total <= 0 or current_total <= 0:
        return 0.0
    investment_return = current_total - past_total - net_external_flow
    return round(investment_return / past_total * 100.0, 2)