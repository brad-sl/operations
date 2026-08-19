# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths.
"""Fast dashboard helpers: period portfolio returns and observability without v_dashboard_metrics."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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


def _nearest_ts(conn: sqlite3.Connection, cutoff: datetime) -> Optional[str]:
    cutoff_s = cutoff.isoformat()
    row = conn.execute(
        "SELECT ts FROM account_balances WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
        (cutoff_s,),
    ).fetchone()
    return row[0] if row else None


def _total_usd_at_ts(conn: sqlite3.Connection, ts: str) -> float:
    cash = 0.0
    for row in conn.execute(
        "SELECT currency, balance FROM account_balances WHERE ts = ?",
        (ts,),
    ):
        cur, bal = (row[0] or "").upper(), float(row[1] or 0)
        if cur in ("USD", "USDC"):
            cash += bal
    holdings_val = 0.0
    # One holdings fetch; batch-friendly price lookup (pair-first when idx exists).
    held = list(
        conn.execute(
            "SELECT currency, amount FROM holdings WHERE ts = ?",
            (ts,),
        )
    )
    for cur, amt in held:
        amt = float(amt or 0)
        if amt <= 0:
            continue
        c = str(cur).replace("-USD", "")
        pair = f"{c}-USD"
        # Prefer pair-leading scan; falls back if only (ts,pair) PK exists.
        px_row = conn.execute(
            "SELECT price FROM prices WHERE pair = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
            (pair, ts),
        ).fetchone()
        if not px_row:
            px_row = conn.execute(
                "SELECT price FROM prices WHERE pair = ? ORDER BY ts DESC LIMIT 1",
                (pair,),
            ).fetchone()
        px = float(px_row[0]) if px_row else 0.0
        holdings_val += amt * px
    return cash + holdings_val


def period_return_pct(current_total: float, past_total: float) -> float:
    if past_total <= 0 or current_total <= 0:
        return 0.0
    return round((current_total - past_total) / past_total * 100.0, 2)


def _linreg_slope_intercept(xs: list[float], ys: list[float]) -> Tuple[float, float]:
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = num / den
    intercept = my - slope * mx
    return slope, intercept


def _segment_adjusted_return_pct(
    conn: Any,
    prev_ts: str,
    prev_tot: float,
    ts: str,
    total: float,
    *,
    total_fn,
    cash_fn,
    adjusted_fn,
    net_flow_fn,
) -> Tuple[float, float]:
    """Deposit-adjusted return for one chart step. Never invents +50% on missed deposits.

    Returns (r_pct, flow_usd_used).
    """
    flow = float(net_flow_fn(conn, prev_ts, ts, total_fn) or 0.0)
    r_pct = float(adjusted_fn(total, prev_tot, flow))
    if abs(r_pct) <= 50.0:
        return r_pct, flow

    # Large jump: refine flow from cash path
    try:
        c0 = float(cash_fn(conn, prev_ts))
        c1 = float(cash_fn(conn, ts))
        dc = c1 - c0
        dnav = total - prev_tot
        # Cash move explains most of NAV move → external flow
        if abs(dc) >= 50.0 and abs(dnav - dc) < max(40.0, 0.15 * abs(dc)):
            flow = dc
            r_pct = float(adjusted_fn(total, prev_tot, flow))
            if abs(r_pct) <= 50.0:
                return r_pct, flow
    except Exception:
        pass

    # Still absurd: treat unexplained NAV jump as external (r≈0) instead of clamping
    # to ±50% (clamp was the bug that made Window ~−15% while 30D tile was ~−28%).
    dnav = total - prev_tot
    if prev_tot > 0 and abs(dnav) >= 0.35 * prev_tot:
        # Pure external assumption for that step
        return 0.0, dnav

    # Mild residual clamp only for noise
    return max(-50.0, min(50.0, r_pct)), flow


def _equity_health_label(
    *,
    slope_pct_per_day: float,
    window_return_pct: float,
    recent_return_pct: Optional[float],
) -> Dict[str, Any]:
    """Plain-English account health from deposit-adjusted equity curve."""
    if slope_pct_per_day > 0.08 and window_return_pct > 0:
        state = "recovering"
        blurb = "Deposit-adjusted equity is trending up over the window."
    elif slope_pct_per_day > 0.03:
        state = "stabilizing_up"
        blurb = "Slight upward trend — losses may be slowing."
    elif slope_pct_per_day < -0.15:
        state = "declining"
        blurb = "Deposit-adjusted equity is still trending down overall."
    elif slope_pct_per_day < -0.03:
        state = "soft_down"
        blurb = "Mild downtrend — still losing over the full window."
    else:
        state = "sideways"
        blurb = "No clear trend — equity is roughly sideways deposit-adjusted."

    if recent_return_pct is not None and window_return_pct is not None:
        if recent_return_pct > window_return_pct + 1.0 and recent_return_pct > -2.0:
            blurb += " Recent stretch is better than the full-window path."
        elif recent_return_pct < window_return_pct - 1.0:
            blurb += " Recent stretch is weaker than the full-window average."

    return {
        "state": state,
        "label": {
            "recovering": "Recovering",
            "stabilizing_up": "Stabilizing (up)",
            "declining": "Declining",
            "soft_down": "Soft downtrend",
            "sideways": "Sideways",
        }.get(state, state),
        "blurb": blurb,
        "slope_pct_per_day": round(slope_pct_per_day, 4),
    }


def compute_equity_trend(
    current_total_usd: float,
    db_path: Path,
    *,
    days: int = 30,
    max_points: int = 48,
    timeout: float = 1.5,
) -> Dict[str, Any]:
    """Deposit-adjusted equity index + linear trend for dashboard health chart.

    Returns series of {t, nav, index} where index starts at 100 and compounds
    adjusted period returns between samples (external deposits/withdrawals removed).
    """
    from phase6.core.portfolio_external_flows import (
        adjusted_period_return_pct,
        cash_usd_at_ts,
        net_external_flow_between,
    )

    out: Dict[str, Any] = {
        "status": "ok",
        "days": days,
        "points": [],
        "trend": None,
        "health": None,
        "window_return_pct": None,
        "recent_return_pct": None,
        "source": "account_balances_deposit_adjusted_index",
    }
    if not db_path.exists() or current_total_usd <= 0:
        out["status"] = "no_data"
        return out

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(days)))

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        # Prefer day-hour buckets so DISTINCT 60k scan stays cheap
        rows = conn.execute(
            """
            SELECT MAX(ts) AS ts
            FROM account_balances
            WHERE ts >= ?
            GROUP BY substr(ts, 1, 13)
            ORDER BY ts ASC
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        if len(rows) < 2:
            rows = conn.execute(
                """
                SELECT MAX(ts) AS ts
                FROM account_balances
                WHERE ts >= ?
                GROUP BY substr(ts, 1, 10)
                ORDER BY ts ASC
                """,
                (cutoff.strftime("%Y-%m-%d"),),
            ).fetchall()
        ts_list = [r[0] for r in rows if r and r[0]]
        if len(ts_list) < 2:
            out["status"] = "insufficient_history"
            conn.close()
            return out

        if len(ts_list) > max_points:
            n = max_points
            idxs = [round(i * (len(ts_list) - 1) / (n - 1)) for i in range(n)]
            seen = set()
            picked = []
            for i in idxs:
                if i not in seen:
                    seen.add(i)
                    picked.append(ts_list[i])
            ts_list = picked

        samples: list[Tuple[str, float]] = []  # ts, total
        for ts in ts_list:
            total = float(_total_usd_at_ts(conn, ts))
            if total > 0:
                samples.append((ts, total))

        if samples and abs(current_total_usd - samples[-1][1]) > 0.5:
            samples.append((now.isoformat().replace("+00:00", "Z"), float(current_total_usd)))

        if len(samples) < 2:
            out["status"] = "insufficient_history"
            conn.close()
            return out

        index = 100.0
        points = []
        t0 = _parse_ts(samples[0][0]) or now
        xs: list[float] = []
        ys: list[float] = []
        for i, (ts, total) in enumerate(samples):
            if i > 0:
                prev_ts, prev_tot = samples[i - 1]
                r_pct, _flow = _segment_adjusted_return_pct(
                    conn,
                    prev_ts,
                    prev_tot,
                    ts,
                    total,
                    total_fn=_total_usd_at_ts,
                    cash_fn=cash_usd_at_ts,
                    adjusted_fn=adjusted_period_return_pct,
                    net_flow_fn=net_external_flow_between,
                )
                index = index * (1.0 + r_pct / 100.0)
            dt = _parse_ts(ts) or (t0 + timedelta(hours=i))
            # tolerate naive ts
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            day = (dt - t0).total_seconds() / 86400.0
            xs.append(day)
            ys.append(index)
            points.append(
                {
                    "t": ts,
                    "nav_usd": round(total, 2),
                    "index": round(index, 3),
                    "day": round(day, 3),
                }
            )

        # Endpoint truth (same formula as 1D/7D/14D/30D tiles): single-hop deposit-adj
        # over the chart window. Path shape uses segments; Window % must match tiles.
        first_ts, first_nav = samples[0][0], float(samples[0][1])
        last_ts, last_nav = samples[-1][0], float(samples[-1][1])
        # Prefer last DB balance ts for flow end when last sample is synthetic "now"
        end_flow_ts = last_ts
        try:
            max_row = conn.execute("SELECT MAX(ts) FROM account_balances").fetchone()
            if max_row and max_row[0]:
                # If last sample is live "now", flow through latest persisted snapshot
                end_flow_ts = max_row[0]
        except Exception:
            pass
        window_flow = float(
            net_external_flow_between(conn, first_ts, end_flow_ts, _total_usd_at_ts) or 0.0
        )
        window_return_pct = adjusted_period_return_pct(last_nav, first_nav, window_flow)

        # If path drifted from endpoint truth (legacy clamp residue), re-anchor path
        # so the last index matches window_return while keeping relative segment shape.
        path_end = ys[-1]
        target_end = 100.0 * (1.0 + float(window_return_pct) / 100.0)
        if path_end > 0 and abs(path_end - target_end) > 0.15:
            # Blend: shift logs so end lands on target (multiplicative scale of excess)
            # index' = 100 * (index/100)**k chosen so end matches — simpler linear blend:
            # index' = 100 + (index-100) * (target-100)/(path_end-100) when path moved
            if abs(path_end - 100.0) > 1e-6:
                scale = (target_end - 100.0) / (path_end - 100.0)
                ys = [100.0 + (y - 100.0) * scale for y in ys]
            else:
                ys = [target_end for _ in ys]
            for i, y in enumerate(ys):
                points[i]["index"] = round(y, 3)

        conn.close()

        slope, intercept = _linreg_slope_intercept(xs, ys)
        slope_pct_per_day = slope  # index units ≈ % of start
        recent_return_pct = None
        # Match 7D tile: nearest snapshot at now-7d → same endpoint formula
        try:
            c2 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
            c2.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
            ts7 = _nearest_ts(c2, now - timedelta(days=7))
            if ts7:
                past7 = float(_total_usd_at_ts(c2, ts7))
                flow7 = float(
                    net_external_flow_between(c2, ts7, end_flow_ts, _total_usd_at_ts) or 0.0
                )
                if past7 > 0:
                    recent_return_pct = adjusted_period_return_pct(last_nav, past7, flow7)
            c2.close()
        except Exception:
            # fallback: path-index over last ~7 chart days
            if xs[-1] >= 3:
                cut = xs[-1] - min(7.0, xs[-1] * 0.35)
                j = 0
                for k, d in enumerate(xs):
                    if d >= cut:
                        j = k
                        break
                if j < len(ys) - 1 and ys[j] > 0:
                    recent_return_pct = round((ys[-1] / ys[j] - 1.0) * 100.0, 2)

        y0 = intercept + slope * xs[0]
        y1 = intercept + slope * xs[-1]
        health = _equity_health_label(
            slope_pct_per_day=slope_pct_per_day,
            window_return_pct=float(window_return_pct),
            recent_return_pct=recent_return_pct,
        )

        out["points"] = points
        out["trend"] = {
            "slope_index_per_day": round(slope, 4),
            "slope_pct_per_day": round(slope_pct_per_day, 4),
            "start_index": round(y0, 3),
            "end_index": round(y1, 3),
            "start_t": points[0]["t"],
            "end_t": points[-1]["t"],
        }
        out["health"] = health
        out["window_return_pct"] = (
            round(float(window_return_pct), 2) if window_return_pct is not None else None
        )
        out["recent_return_pct"] = (
            round(float(recent_return_pct), 2) if recent_return_pct is not None else None
        )
        out["window_matches_period_tiles"] = True
        out["window_external_flow_usd"] = round(window_flow, 2)
        out["point_count"] = len(points)
        out["span_days"] = round(xs[-1], 2) if xs else None
        return out
    except Exception as e:
        out["status"] = f"error:{type(e).__name__}"
        out["error"] = str(e)[:200]
        return out


def compute_period_performance(
    current_total_usd: float,
    db_path: Path,
    timeout: float = 0.45,
) -> Dict[str, Any]:
    """Portfolio % change vs DB snapshot before each cutoff, **deposit-adjusted**.

    If no snapshot at or before cutoff (insufficient history), returns None for that
    period key (never numeric 0.0 for missing window per KPI truth requirements).
    """
    from phase6.core.portfolio_external_flows import (
        adjusted_period_return_pct,
        net_external_flow_between,
    )

    out = {
        "today": None,
        "h24": None,
        "d7": None,
        "d14": None,
        "d30": None,
        "source": "period_snapshots_db_adjusted",
        "external_flows_usd": {},
    }
    if not db_path.exists() or current_total_usd <= 0:
        out["source"] = "no_db_or_total"
        return out

    now = datetime.now(timezone.utc)
    windows = {
        "today": now - timedelta(days=1),
        "h24": now - timedelta(hours=24),
        "d7": now - timedelta(days=7),
        "d14": now - timedelta(days=14),
        "d30": now - timedelta(days=30),
    }
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        latest_ts_row = conn.execute(
            "SELECT MAX(ts) FROM account_balances"
        ).fetchone()
        end_ts = latest_ts_row[0] if latest_ts_row else None
        for key, cutoff in windows.items():
            ts = _nearest_ts(conn, cutoff)
            if not ts:
                continue
            past = _total_usd_at_ts(conn, ts)
            net_flow = net_external_flow_between(conn, ts, end_ts, _total_usd_at_ts)
            out["external_flows_usd"][key] = net_flow
            out[key] = adjusted_period_return_pct(current_total_usd, past, net_flow)
        conn.close()
    except Exception as e:
        out["source"] = f"error:{type(e).__name__}"
    return out


def win_ratio_from_positions(positions: list) -> float:
    """Open-book win ratio: share of positions with positive unrealized PnL."""
    trading = [
        p
        for p in (positions or [])
        if (p.get("pair") or "") not in ("USD", "USDC")
        and float(p.get("value_usd") or 0) >= 0.01
    ]
    if not trading:
        return 0.0
    wins = sum(1 for p in trading if float(p.get("unrealized_pnl_pct") or 0) > 0)
    return round(wins / len(trading), 3)


def fast_observability_metrics(db_path: Path, live_state: dict, timeout: float = 0.4) -> Dict[str, Any]:
    """Lightweight SQL (no v_dashboard_metrics) + live_state arch4 overlay.

    Util is primary holdings_value / total_usd from live positions (per KPI truth).
    SL OK is fraction of open trading positions with protective stop est/attach (real, not stale 0%).
    """
    arch4 = live_state.get("arch4") or {}
    perf = live_state.get("performance_metrics") or {}
    total = float(live_state.get("total_usd") or live_state.get("total_balance") or 0)
    holdings = float(live_state.get("total_holdings_value") or 0)
    active = int(
        live_state.get("active_positions")
        or len(live_state.get("trading_positions") or [])
        or 0
    )

    # Primary: holdings / total from live positions (ARCH-4 is target/secondary if differs)
    utilization = None
    if total > 0 and holdings > 0:
        utilization = round(holdings / total, 4)
    if utilization is None:
        utilization = arch4.get("last_exposure")

    # SL OK: real fraction of open trading pos with exchange protective stop
    sl_success_rate = live_state.get("sl_success_rate")
    trading_pos = live_state.get("trading_positions") or live_state.get("positions") or []
    # Enrich with recompute so raw live_state (no sl keys) gets sl_stop_price_est from entry (consistent with /positions)
    try:
        from phase6.core.position_cost_basis import recompute_trading_positions_pnl
        if trading_pos:
            trading_pos = recompute_trading_positions_pnl(trading_pos)
    except Exception:
        pass
    trading = [
        p for p in trading_pos
        if (p.get("pair") or "") not in ("USD", "USDC")
        and float(p.get("value_usd") or 0) >= 0.01
    ]
    if trading:
        protected = 0
        for p in trading:
            if (
                p.get("sl_stop_price_est") is not None
                or p.get("sl_attached") is True
                or p.get("stop_loss")
            ):
                protected += 1
        sl_success_rate = round(protected / len(trading), 4)

    metrics: Dict[str, Any] = {
        "utilization": utilization,
        "proposal_acceptance": None,
        "sl_success_rate": sl_success_rate,
        "churn": arch4.get("last_rotations"),
        "rebalance_count": None,
        "recovery_attempts": live_state.get("recovery_attempts"),
        "replay_match_rate": live_state.get("replay_match_rate"),
        "total_trades": perf.get("total_trades"),
        "win_rate": perf.get("win_rate"),
    }

    rec_path = Path("data/state/recovery_state.json")
    if rec_path.exists():
        try:
            import json as _json

            rec = _json.loads(rec_path.read_text())
            if metrics["recovery_attempts"] is None and rec.get("attempts") is not None:
                metrics["recovery_attempts"] = rec.get("attempts")
        except Exception:
            pass

    if not db_path.exists():
        try:
            from phase6.core.rebalance_logger import get_recent_rebalances

            rb = get_recent_rebalances(limit=500) or []
            executed = sum(1 for r in rb if (r.get("executed") or 0) > 0)
            if executed:
                metrics["rebalance_count"] = executed
                if active > 0:
                    metrics["churn"] = round(executed / active, 2)
        except Exception:
            pass
        return metrics

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")

        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END), 0) FROM proposals"
        ).fetchone()
        if row and row[0] and row[0] > 0:
            metrics["proposal_acceptance"] = round(float(row[1]) / float(row[0]), 4)

        row = conn.execute("SELECT COUNT(*) FROM rebalances").fetchone()
        if row:
            metrics["rebalance_count"] = int(row[0] or 0)
            if active > 0 and metrics["rebalance_count"]:
                metrics["churn"] = round(metrics["rebalance_count"] / active, 2)

        row = conn.execute(
            "SELECT success_rate FROM sl_metrics ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            db_sl = float(row[0])
            # Never overwrite live position-based SL OK with empty/zero DB metric
            if metrics.get("sl_success_rate") is None and db_sl > 0:
                metrics["sl_success_rate"] = db_sl

        row = conn.execute(
            "SELECT attempts FROM recovery_metrics ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            metrics["recovery_attempts"] = int(row[0])

        row = conn.execute(
            "SELECT match_rate FROM replay_parity ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            metrics["replay_match_rate"] = float(row[0])

        conn.close()
    except Exception:
        pass

    if metrics["rebalance_count"] is None:
        try:
            from phase6.core.rebalance_logger import get_recent_rebalances

            rb = get_recent_rebalances(limit=500) or []
            executed = sum(1 for r in rb if (r.get("executed") or 0) > 0)
            if executed:
                metrics["rebalance_count"] = executed
                if active > 0 and metrics.get("churn") is None:
                    metrics["churn"] = round(executed / active, 2)
        except Exception:
            pass

    return metrics