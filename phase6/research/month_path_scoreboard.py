#!/usr/bin/env python3
"""Month-path scoreboard — gap to ~5%/mo vs process tax + exit mix.

North-star meter for Brad's consistent ~5% monthly target on the process book.
Deposit-adjusted equity path is primary; ledger SELL PnL + TCS leak classes are
the subtract lines (house tax), not claimed alpha.

Honesty:
- No fake guarantees. Hit rate / gap language only.
- process_tax = SL (and same-day churn) dollars on leak-adjacent exits — less-loss
  path, not a printer if baseline is red.
- Sparse regime stamps = data gap.
- Never writes config / knobs / orders.

Artifacts:
  data/state/month_path_scoreboard_latest.json
  reports/MONTH_PATH_SCOREBOARD_LATEST.md
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.paths import load_project_dotenv

load_project_dotenv()

from phase6.research.trade_comparison_standard import (  # noqa: E402
    DEFAULT_ELEVATED_RSI,
    DEFAULT_LARGE_USD,
    DEFAULT_SL_COOLDOWN_H,
    DEFAULT_TP_COOLDOWN_H,
    buy_event,
    exit_class,
    is_clean_buy,
    load_ledger_rows,
    parse_ts,
    sell_event,
)

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
DB_PATH = ROOT / "data" / "phase6.db"
OUT_JSON = STATE / "month_path_scoreboard_latest.json"
OUT_MD = REPORTS / "MONTH_PATH_SCOREBOARD_LATEST.md"

TARGET_MONTHLY_PCT = 5.0
SCHEMA = "month_path_scoreboard_v1"
EDGE_CLASS = "ATTENTION_ONLY_less_loss_path"  # gap meter, not HIT_10


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def _iter_months(lo: date, hi: date) -> List[date]:
    out: List[date] = []
    cur = _month_start(lo)
    end = _month_start(hi)
    while cur <= end:
        out.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def _label_buy_leaks(
    buys: List[Dict[str, Any]],
    sells: List[Dict[str, Any]],
    *,
    sl_h: float = DEFAULT_SL_COOLDOWN_H,
    tp_h: float = DEFAULT_TP_COOLDOWN_H,
    large_usd: float = DEFAULT_LARGE_USD,
    elev_rsi: float = DEFAULT_ELEVATED_RSI,
) -> Dict[str, List[str]]:
    """Return map buy_key -> list of leak ids. Key = pair|iso_ts|order_id."""
    by_pair_buys: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_pair_sl: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_pair_tp: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for b in buys:
        if b.get("ts") and b.get("pair"):
            by_pair_buys[str(b["pair"])].append(b)
    for s in sells:
        if not s.get("ts") or not s.get("pair"):
            continue
        cls = exit_class(str(s.get("reason") or ""))
        if cls == "stop_loss":
            by_pair_sl[str(s["pair"])].append(s)
        elif cls == "take_profit":
            by_pair_tp[str(s["pair"])].append(s)

    tagged: Dict[str, List[str]] = {}
    for pair, pb in by_pair_buys.items():
        pb = sorted(pb, key=lambda x: x["ts"])
        sls = sorted(by_pair_sl.get(pair, []), key=lambda x: x["ts"])
        tps = sorted(by_pair_tp.get(pair, []), key=lambda x: x["ts"])
        for b in pb:
            leaks: List[str] = []
            ts = b["ts"]
            usd = _f(b.get("usd"))
            rsi = b.get("rsi")
            for sl in sls:
                dt_h = (ts - sl["ts"]).total_seconds() / 3600.0
                if 0 < dt_h <= sl_h:
                    leaks.append("post_sl_reentry")
                    break
            for tp in tps:
                dt_h = (ts - tp["ts"]).total_seconds() / 3600.0
                if 0 < dt_h <= tp_h:
                    leaks.append("post_tp_rebuy")
                    break
            if rsi is not None and _f(rsi) >= elev_rsi and usd >= large_usd:
                leaks.append("elevated_rsi_large")
            # same-day churn later on sell side
            key = f"{pair}|{ts.isoformat()}|{b.get('order_id') or ''}"
            if leaks:
                tagged[key] = leaks
        # pile-on window flags
        for i, b in enumerate(pb):
            window = [
                x
                for x in pb
                if x["ts"] >= b["ts"] - timedelta(days=7) and x["ts"] <= b["ts"]
            ]
            cum = sum(_f(x.get("usd")) for x in window)
            if len(window) >= 3 and cum >= 3 * large_usd:
                key = f"{pair}|{b['ts'].isoformat()}|{b.get('order_id') or ''}"
                tagged.setdefault(key, [])
                if "pile_on" not in tagged[key]:
                    tagged[key].append("pile_on")
    return tagged


def _buy_key(b: Dict[str, Any]) -> str:
    ts = b.get("ts")
    iso = ts.isoformat() if ts else ""
    return f"{b.get('pair')}|{iso}|{b.get('order_id') or ''}"


def _nav_series() -> List[Tuple[datetime, float]]:
    if not DB_PATH.exists():
        return []
    try:
        from phase6.core.dashboard_serve_helpers import _total_usd_at_ts
    except Exception:
        _total_usd_at_ts = None  # type: ignore
    out: List[Tuple[datetime, float]] = []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
        # Sample ~1 row per day (max ts each UTC day) for speed
        rows = conn.execute(
            """
            SELECT date(ts) AS d, MAX(ts) AS ts
            FROM account_balances
            GROUP BY date(ts)
            ORDER BY d
            """
        ).fetchall()
        for _d, ts in rows:
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if _total_usd_at_ts is not None:
                try:
                    nav = float(_total_usd_at_ts(conn, ts))
                except Exception:
                    nav = 0.0
            else:
                nav = 0.0
            if nav > 0:
                out.append((dt.astimezone(timezone.utc), nav))
        conn.close()
    except Exception:
        return []
    return out


def _nav_at_or_before(series: List[Tuple[datetime, float]], when: datetime) -> Optional[float]:
    best = None
    for t, nav in series:
        if t <= when:
            best = nav
        else:
            break
    return best


def _nav_at_or_after(series: List[Tuple[datetime, float]], when: datetime) -> Optional[float]:
    for t, nav in series:
        if t >= when:
            return nav
    return series[-1][1] if series else None


def _net_flow(start_ts: str, end_ts: str) -> float:
    if not DB_PATH.exists():
        return 0.0
    try:
        from phase6.core.dashboard_serve_helpers import _total_usd_at_ts
        from phase6.core.portfolio_external_flows import net_external_flow_between

        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
        flow = float(net_external_flow_between(conn, start_ts, end_ts, _total_usd_at_ts) or 0.0)
        conn.close()
        return flow
    except Exception:
        return 0.0


def _regime_for_month(ym: str) -> Dict[str, Any]:
    """Best-effort regime mix for the month from on-disk snapshots."""
    path = STATE / "regime_cash_status.json"
    hist = STATE / "regime_history.jsonl"
    counts: Counter = Counter()
    if hist.exists():
        try:
            with hist.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(row.get("ts") or row.get("as_of") or row.get("timestamp"))
                    if not ts or ts.strftime("%Y-%m") != ym:
                        continue
                    reg = str(row.get("regime") or row.get("live_regime") or "").lower()
                    if reg:
                        counts[reg] += 1
        except Exception:
            pass
    if not counts and path.exists():
        try:
            row = json.loads(path.read_text() or "{}")
            reg = str(row.get("regime") or row.get("live_regime") or "").lower()
            if reg:
                counts[reg] += 1
        except Exception:
            pass
    if not counts:
        return {"primary": None, "mix": {}, "coverage": "thin"}
    total = sum(counts.values())
    mix = {k: round(v / total, 3) for k, v in counts.most_common()}
    return {"primary": counts.most_common(1)[0][0], "mix": mix, "coverage": "ok" if total >= 3 else "thin"}


def _ticket_bucket(usd: float) -> str:
    if usd < 75:
        return "micro_<75"
    if usd < 150:
        return "tryout_75_150"
    if usd < 500:
        return "std_150_500"
    return "mega_>=500"


def build_month_path(
    *,
    target_monthly_pct: float = TARGET_MONTHLY_PCT,
    months_back: int = 6,
) -> Dict[str, Any]:
    rows = load_ledger_rows()
    buys = [buy_event(r) for r in rows if is_clean_buy(r)]
    sells = [sell_event(r) for r in rows if r.get("side") == "SELL"]
    buys = [b for b in buys if b.get("ts")]
    sells = [s for s in sells if s.get("ts")]

    tagged = _label_buy_leaks(buys, sells)
    # pair -> sorted buy keys with leaks for SL attribution
    leak_buys_by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for b in buys:
        key = _buy_key(b)
        if key in tagged:
            leak_buys_by_pair[str(b["pair"])].append(b)

    series = _nav_series()
    today = datetime.now(timezone.utc).date()
    if series:
        lo = series[0][0].date()
        hi = min(series[-1][0].date(), today)
    elif sells or buys:
        all_ts = [b["ts"].date() for b in buys] + [s["ts"].date() for s in sells]
        lo, hi = min(all_ts), max(all_ts)
    else:
        lo = hi = today

    months = _iter_months(lo, hi)
    if months_back and len(months) > months_back:
        months = months[-months_back:]

    month_rows: List[Dict[str, Any]] = []
    for m0 in months:
        m1 = _month_end(m0)
        ym = m0.strftime("%Y-%m")
        # clamp current month end to now
        end_day = min(m1, today)
        start_dt = datetime(m0.year, m0.month, m0.day, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(end_day.year, end_day.month, end_day.day, 23, 59, 59, tzinfo=timezone.utc)

        start_nav = _nav_at_or_after(series, start_dt) if series else None
        if start_nav is None and series:
            start_nav = _nav_at_or_before(series, start_dt)
        end_nav = _nav_at_or_before(series, end_dt) if series else None

        flow = 0.0
        dep_adj_pct = None
        dep_adj_usd = None
        if start_nav and end_nav and start_nav > 0:
            # flow between first and last snapshot in month
            s_ts = next((t.isoformat().replace("+00:00", "Z") for t, n in series if n == start_nav and t >= start_dt - timedelta(days=2)), None)
            e_ts = next((t.isoformat().replace("+00:00", "Z") for t, n in reversed(series) if t <= end_dt + timedelta(hours=1)), None)
            if s_ts and e_ts:
                flow = _net_flow(s_ts, e_ts)
            try:
                from phase6.core.portfolio_external_flows import adjusted_period_return_pct

                dep_adj_pct = adjusted_period_return_pct(end_nav, start_nav, flow)
            except Exception:
                dep_adj_pct = round((end_nav - start_nav - flow) / start_nav * 100.0, 2)
            dep_adj_usd = round(end_nav - start_nav - flow, 2)

        m_sells = [s for s in sells if start_dt <= s["ts"] <= end_dt]
        m_buys = [b for b in buys if start_dt <= b["ts"] <= end_dt]

        pnl_by_exit: Dict[str, Dict[str, float]] = defaultdict(lambda: {"n": 0.0, "pnl": 0.0})
        realized = 0.0
        for s in m_sells:
            cls = exit_class(str(s.get("reason") or ""))
            pnl = s.get("pnl")
            pnl_f = float(pnl) if isinstance(pnl, (int, float)) else 0.0
            pnl_by_exit[cls]["n"] += 1
            pnl_by_exit[cls]["pnl"] += pnl_f
            realized += pnl_f

        # process tax: SL pnl where a leak-tagged buy on same pair preceded within 72h
        # OR same-day buy→SL churn
        process_tax = 0.0
        process_n = 0
        process_by_leak: Counter = Counter()
        for s in m_sells:
            if exit_class(str(s.get("reason") or "")) != "stop_loss":
                continue
            pnl = s.get("pnl")
            if not isinstance(pnl, (int, float)):
                continue
            pair = str(s.get("pair") or "")
            hit = False
            leak_kinds: List[str] = []
            # same-day churn
            day_buys = [
                b
                for b in m_buys
                if str(b.get("pair")) == pair
                and b["ts"].date() == s["ts"].date()
                and b["ts"] < s["ts"]
            ]
            if day_buys:
                hit = True
                leak_kinds.append("same_day_churn")
            # prior leak buy within 72h
            for b in leak_buys_by_pair.get(pair, []):
                if b["ts"] >= s["ts"]:
                    continue
                dt_h = (s["ts"] - b["ts"]).total_seconds() / 3600.0
                if 0 < dt_h <= 72.0:
                    key = _buy_key(b)
                    kinds = tagged.get(key) or []
                    if kinds:
                        hit = True
                        leak_kinds.extend(kinds)
            if hit:
                process_tax += float(pnl)  # usually negative
                process_n += 1
                for k in set(leak_kinds):
                    process_by_leak[k] += 1

        leak_buy_n = 0
        leak_buy_usd = 0.0
        leak_counts: Counter = Counter()
        ticket_buys: Counter = Counter()
        for b in m_buys:
            usd = _f(b.get("usd"))
            ticket_buys[_ticket_bucket(usd)] += 1
            key = _buy_key(b)
            kinds = tagged.get(key) or []
            if kinds:
                leak_buy_n += 1
                leak_buy_usd += usd
                for k in kinds:
                    leak_counts[k] += 1

        # target dollars this month = target_pct * start_nav
        target_usd = round(start_nav * (target_monthly_pct / 100.0), 2) if start_nav else None
        gap_usd = None
        if target_usd is not None and dep_adj_usd is not None:
            gap_usd = round(target_usd - dep_adj_usd, 2)
        elif target_usd is not None:
            # fallback: realized ledger vs target
            gap_usd = round(target_usd - realized, 2)

        # if no process tax, still report
        process_tax_r = round(process_tax, 2)
        # dollars that would narrow the gap if process tax were zero (tax is ≤0)
        tax_vs_gap = None
        if gap_usd is not None and process_tax_r < 0:
            tax_vs_gap = round(min(-process_tax_r, max(gap_usd, 0.0)), 2)

        regime = _regime_for_month(ym)
        complete = end_day >= m1  # full calendar month closed

        month_rows.append(
            {
                "month": ym,
                "complete": complete,
                "start_nav_usd": round(start_nav, 2) if start_nav else None,
                "end_nav_usd": round(end_nav, 2) if end_nav else None,
                "net_external_flow_usd": round(flow, 2),
                "deposit_adj_return_pct": dep_adj_pct,
                "deposit_adj_pnl_usd": dep_adj_usd,
                "target_monthly_pct": target_monthly_pct,
                "target_usd": target_usd,
                "gap_to_target_usd": gap_usd,
                "hit_target": (
                    bool(dep_adj_pct is not None and dep_adj_pct >= target_monthly_pct)
                    if complete
                    else None
                ),
                "realized_sell_pnl_usd": round(realized, 2),
                "pnl_by_exit_class": {
                    k: {"n": int(v["n"]), "pnl": round(v["pnl"], 2)} for k, v in pnl_by_exit.items()
                },
                "n_buys": len(m_buys),
                "n_sells": len(m_sells),
                "buy_ticket_buckets": dict(ticket_buys),
                "leak_buy_n": leak_buy_n,
                "leak_buy_notional_usd": round(leak_buy_usd, 2),
                "leak_counts": dict(leak_counts),
                "process_tax_usd": process_tax_r,
                "process_tax_n_sl": process_n,
                "process_tax_by_leak": dict(process_by_leak),
                "process_tax_covers_gap_usd": tax_vs_gap,
                "regime": regime,
            }
        )

    closed = [m for m in month_rows if m.get("complete")]
    hits = [m for m in closed if m.get("hit_target") is True]
    miss = [m for m in closed if m.get("hit_target") is False]
    avg_pct = None
    if closed:
        vals = [m["deposit_adj_return_pct"] for m in closed if m.get("deposit_adj_return_pct") is not None]
        if vals:
            avg_pct = round(sum(vals) / len(vals), 2)

    total_tax = round(sum(m.get("process_tax_usd") or 0.0 for m in month_rows), 2)
    total_gap = round(
        sum(m["gap_to_target_usd"] for m in closed if m.get("gap_to_target_usd") is not None),
        2,
    ) if closed else None

    # current month MTD
    cur = next((m for m in reversed(month_rows) if not m.get("complete")), None) or (
        month_rows[-1] if month_rows else None
    )

    board = {
        "schema": SCHEMA,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "north_star": (
            f"Consistent ~{target_monthly_pct:.0f}% monthly deposit-adjusted return on the "
            "process book — scoreboard target, not a live SLA guarantee."
        ),
        "target_monthly_pct": target_monthly_pct,
        "edge_class": EDGE_CLASS,
        "sensor": {
            "nav_points": len(series),
            "ledger_buys": len(buys),
            "ledger_sells": len(sells),
            "ok": bool(series) or bool(sells),
        },
        "summary": {
            "n_months_closed": len(closed),
            "n_hit_target": len(hits),
            "n_miss_target": len(miss),
            "hit_rate": round(len(hits) / len(closed), 3) if closed else None,
            "avg_closed_month_return_pct": avg_pct,
            "total_process_tax_usd": total_tax,
            "sum_gap_closed_usd": total_gap,
            "current_month": cur.get("month") if cur else None,
            "current_mtd_return_pct": cur.get("deposit_adj_return_pct") if cur else None,
            "current_mtd_gap_usd": cur.get("gap_to_target_usd") if cur else None,
            "current_mtd_process_tax_usd": cur.get("process_tax_usd") if cur else None,
        },
        "months": month_rows,
        "notes": [
            "Primary path = deposit-adjusted NAV (external flows stripped).",
            "process_tax_usd = SL PnL on leak-adjacent exits (post-SL/TP reentry, elev RSI large, pile-on, same-day churn).",
            "Tax is a subtract line toward the 5% bar — not proof the gate prints money.",
            "Regime mix thin unless regime_history.jsonl is populated.",
            f"Edge class: {EDGE_CLASS}.",
        ],
    }
    return board


def format_month_path_md(board: Dict[str, Any]) -> str:
    s = board.get("summary") or {}
    lines = [
        "# Month-path scoreboard",
        f"as_of: {board.get('as_of')}",
        "",
        board.get("north_star") or "",
        "",
        f"**Edge class:** `{board.get('edge_class')}`",
        "",
        "## Summary",
        f"- Closed months: {s.get('n_months_closed')} · hit ≥{board.get('target_monthly_pct')}%: "
        f"**{s.get('n_hit_target')}** · miss **{s.get('n_miss_target')}** · hit_rate={s.get('hit_rate')}",
        f"- Avg closed-month deposit-adj return: **{s.get('avg_closed_month_return_pct')}%**",
        f"- Total process tax (leak-adjacent SL $): **${s.get('total_process_tax_usd')}**",
        f"- Sum gap on closed months: ${s.get('sum_gap_closed_usd')}",
        f"- Current {s.get('current_month')} MTD: {s.get('current_mtd_return_pct')}% · "
        f"gap ${s.get('current_mtd_gap_usd')} · process_tax ${s.get('current_mtd_process_tax_usd')}",
        "",
        "## Months (oldest → newest)",
        "",
    ]
    for m in board.get("months") or []:
        hit = m.get("hit_target")
        hit_s = "HIT" if hit is True else ("MISS" if hit is False else "MTD")
        lines.append(
            f"### {m.get('month')} [{hit_s}]"
            + ("" if m.get("complete") else " (in progress)")
        )
        lines.append(
            f"- NAV {m.get('start_nav_usd')} → {m.get('end_nav_usd')} · "
            f"flow ${m.get('net_external_flow_usd')} · "
            f"**dep-adj {m.get('deposit_adj_return_pct')}%** (${m.get('deposit_adj_pnl_usd')})"
        )
        lines.append(
            f"- Target ${m.get('target_usd')} · gap ${m.get('gap_to_target_usd')} · "
            f"realized SELL PnL ${m.get('realized_sell_pnl_usd')}"
        )
        lines.append(f"- Exit mix: {m.get('pnl_by_exit_class')}")
        lines.append(
            f"- Leaks: buys={m.get('leak_buy_n')} notional=${m.get('leak_buy_notional_usd')} "
            f"counts={m.get('leak_counts')} · process_tax **${m.get('process_tax_usd')}** "
            f"(n_sl={m.get('process_tax_n_sl')} by={m.get('process_tax_by_leak')})"
        )
        if m.get("process_tax_covers_gap_usd"):
            lines.append(
                f"- Process tax covers up to **${m.get('process_tax_covers_gap_usd')}** of this month's gap "
                "(less-loss ceiling, not alpha)."
            )
        reg = m.get("regime") or {}
        lines.append(f"- Regime primary={reg.get('primary')} mix={reg.get('mix')} ({reg.get('coverage')})")
        lines.append(f"- Ticket buckets: {m.get('buy_ticket_buckets')}")
        lines.append("")
    lines.append("## Notes")
    for n in board.get("notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def persist(board: Dict[str, Any], md: Optional[str] = None) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(board, indent=2, default=str))
    text = md if md is not None else format_month_path_md(board)
    OUT_MD.write_text(text)
    OUT_STATE_MD = STATE / "month_path_scoreboard_latest.md"
    OUT_STATE_MD.write_text(text)


def load_latest() -> Optional[Dict[str, Any]]:
    if not OUT_JSON.exists():
        return None
    try:
        return json.loads(OUT_JSON.read_text() or "null")
    except Exception:
        return None


def analyst_snippet(board: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compact block for analyst daily scoreboard / review."""
    b = board if isinstance(board, dict) else load_latest()
    if not b:
        try:
            b = build_month_path()
            persist(b)
        except Exception as e:
            return {"error": str(e), "ok": False}
    s = b.get("summary") or {}
    cur_m = None
    for m in reversed(b.get("months") or []):
        if m.get("month") == s.get("current_month"):
            cur_m = m
            break
    return {
        "ok": True,
        "schema": b.get("schema"),
        "as_of": b.get("as_of"),
        "target_monthly_pct": b.get("target_monthly_pct"),
        "north_star": b.get("north_star"),
        "edge_class": b.get("edge_class"),
        "hit_rate_closed": s.get("hit_rate"),
        "n_months_closed": s.get("n_months_closed"),
        "n_hit": s.get("n_hit_target"),
        "n_miss": s.get("n_miss_target"),
        "avg_closed_month_return_pct": s.get("avg_closed_month_return_pct"),
        "total_process_tax_usd": s.get("total_process_tax_usd"),
        "current_month": s.get("current_month"),
        "current_mtd_return_pct": s.get("current_mtd_return_pct"),
        "current_mtd_gap_usd": s.get("current_mtd_gap_usd"),
        "current_mtd_process_tax_usd": s.get("current_mtd_process_tax_usd"),
        "current_exit_mix": (cur_m or {}).get("pnl_by_exit_class"),
        "current_leak_counts": (cur_m or {}).get("leak_counts"),
        "artifacts": {
            "json": str(OUT_JSON.relative_to(ROOT)),
            "md": str(OUT_MD.relative_to(ROOT)),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=float, default=TARGET_MONTHLY_PCT)
    ap.add_argument("--months", type=int, default=6, help="How many calendar months back")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--print-json", action="store_true")
    args = ap.parse_args(argv)
    board = build_month_path(target_monthly_pct=args.target, months_back=args.months)
    md = format_month_path_md(board)
    persist(board, md)
    if args.print_json:
        print(json.dumps(board, indent=2, default=str))
    elif args.print:
        print(md, end="")
    else:
        # quiet cron-friendly one-liner to stderr? keep stdout empty for no_agent
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
