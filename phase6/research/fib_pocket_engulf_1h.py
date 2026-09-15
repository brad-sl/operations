#!/usr/bin/env python3
"""LAB ONLY: 1h Fib golden-pocket + engulf backtest (Honest Trader skeleton).

See docs/plans/2026-09-14-fib-pocket-engulf-1h-spec.md
No live orders / evaluate_buy_entry / basket hooks.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

ROOT = Path(__file__).resolve().parents[2]
OHLCV_DIR = ROOT / "data" / "ohlcv" / "1h"
STATE_PATH = ROOT / "data" / "state" / "fib_pocket_engulf_1h_latest.json"
REPORT_PATH = ROOT / "reports" / "FIB_POCKET_ENGULF_1H_LATEST.md"
GRID_REPORT_PATH = ROOT / "reports" / "FIB_POCKET_ENGULF_1H_GRID.md"
PUBLIC = "https://api.exchange.coinbase.com"

FEE_BPS_SIDE = 80.0  # Intro 2 taker
SLIP_BPS_SIDE = 2.0
RT_COST = 2.0 * (FEE_BPS_SIDE + SLIP_BPS_SIDE) / 10000.0  # ~0.0164
TICKET_USD = 75.0


@dataclass
class Spec:
    name: str = "v0_default"
    pivot: int = 5
    pocket: str = "gold"  # gold | wide | mid
    engulf: str = "strict"  # strict | loose
    trend: str = "ema50_200"  # ema50_200 | none
    long_only: bool = True
    min_impulse_atr: float = 1.5
    max_swing_age: int = 120
    touch_confirm_bars: int = 6
    min_stop_pct: float = 0.004
    max_stop_pct: float = 0.04
    atr_sl_buf: float = 0.15
    min_engulf_atr: float = 0.35
    time_stop_bars: int = 72
    rr: float = 2.0


POCKETS = {
    "gold": (0.618, 0.650),
    "wide": (0.618, 0.786),
    "mid": (0.500, 0.618),
}


@dataclass
class Trade:
    pair: str
    side: str
    entry_i: int
    exit_i: int
    entry_px: float
    exit_px: float
    sl: float
    tp: float
    bars_held: int
    reason: str
    r_gross: float
    r_net: float
    pnl_usd_net: float


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_candles_1h_paginated(
    pid: str,
    n_bars: int = 9000,
    sess: Optional[requests.Session] = None,
) -> List[list]:
    """Oldest→newest [time, low, high, open, close, volume]. Coinbase max ~300/req."""
    sess = sess or requests.Session()
    end = _utc_now()
    start = end - timedelta(hours=n_bars + 50)
    out: List[list] = []
    cursor_end = end
    guard = 0
    while guard < 80 and len(out) < n_bars:
        guard += 1
        cursor_start = max(start, cursor_end - timedelta(hours=300))
        params = {
            "granularity": 3600,
            "start": cursor_start.isoformat().replace("+00:00", "Z"),
            "end": cursor_end.isoformat().replace("+00:00", "Z"),
        }
        r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=30)
        if r.status_code != 200:
            break
        batch = r.json() or []
        if not batch:
            break
        batch = sorted(batch, key=lambda x: x[0])
        out = batch + out
        # dedupe by time
        seen = set()
        dedup = []
        for row in out:
            t = int(row[0])
            if t in seen:
                continue
            seen.add(t)
            dedup.append(row)
        out = sorted(dedup, key=lambda x: x[0])
        oldest = datetime.fromtimestamp(int(batch[0][0]), tz=timezone.utc)
        cursor_end = oldest - timedelta(seconds=1)
        if oldest <= start:
            break
        time.sleep(0.15)
    return out[-n_bars:] if len(out) > n_bars else out


def load_or_fetch(pid: str, n_bars: int = 9000, force: bool = False) -> List[list]:
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    path = OHLCV_DIR / f"{pid.replace('-', '_')}_1h.json"
    if path.exists() and not force:
        raw = json.loads(path.read_text())
        rows = raw.get("candles") or raw
        if isinstance(rows, list) and len(rows) >= min(2000, n_bars // 2):
            return rows[-n_bars:]
    rows = fetch_candles_1h_paginated(pid, n_bars=n_bars)
    path.write_text(json.dumps({"product": pid, "granularity": 3600, "candles": rows}, indent=0))
    return rows


def _ema(xs: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(xs)
    if len(xs) < n or n <= 0:
        return out
    k = 2.0 / (n + 1)
    s = sum(xs[:n]) / n
    out[n - 1] = s
    for i in range(n, len(xs)):
        s = xs[i] * k + s * (1 - k)
        out[i] = s
    return out


def _atr(h: Sequence[float], l: Sequence[float], c: Sequence[float], n: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(c)
    trs: List[float] = []
    for i in range(len(c)):
        if i == 0:
            trs.append(h[i] - l[i])
        else:
            trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    if len(trs) < n:
        return out
    s = sum(trs[:n]) / n
    out[n - 1] = s
    for i in range(n, len(trs)):
        s = (s * (n - 1) + trs[i]) / n
        out[i] = s
    return out


def _pivots(h: Sequence[float], l: Sequence[float], left: int) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    ph: List[Optional[float]] = [None] * len(h)
    pl: List[Optional[float]] = [None] * len(l)
    for i in range(left, len(h) - left):
        window_h = h[i - left : i + left + 1]
        window_l = l[i - left : i + left + 1]
        if h[i] >= max(window_h) and window_h.count(h[i]) == 1:
            ph[i] = h[i]
        if l[i] <= min(window_l) and window_l.count(l[i]) == 1:
            pl[i] = l[i]
    return ph, pl


def _zone(hi: float, lo: float, pocket: str, side: str) -> Tuple[float, float]:
    a, b = POCKETS[pocket]
    # a <= retrace <= b  (0=hi for long fib from lo->hi means price near hi has low retrace)
    rng = hi - lo
    if rng <= 0:
        return lo, hi
    if side == "long":
        # retrace from hi toward lo: zone between b and a retracement
        z_lo = hi - b * rng
        z_hi = hi - a * rng
        return min(z_lo, z_hi), max(z_lo, z_hi)
    z_lo = lo + a * rng
    z_hi = lo + b * rng
    return min(z_lo, z_hi), max(z_lo, z_hi)


def _is_engulf(
    o: Sequence[float],
    h: Sequence[float],
    l: Sequence[float],
    c: Sequence[float],
    i: int,
    side: str,
    mode: str,
    atr_i: Optional[float],
    min_engulf_atr: float,
) -> bool:
    if i < 1:
        return False
    body = abs(c[i] - o[i])
    if atr_i and atr_i > 0 and body < min_engulf_atr * atr_i:
        return False
    if side == "long":
        if not (c[i] > o[i]):
            return False
        if mode == "strict":
            return c[i] >= h[i - 1] and o[i] <= o[i - 1]
        return c[i] > c[i - 1]
    if not (c[i] < o[i]):
        return False
    if mode == "strict":
        return c[i] <= l[i - 1] and o[i] >= o[i - 1]
    return c[i] < c[i - 1]


def _touch_zone(h: float, l: float, z_lo: float, z_hi: float) -> bool:
    return l <= z_hi and h >= z_lo


def run_pair(pair: str, candles: List[list], spec: Spec) -> Dict[str, Any]:
    if len(candles) < 250:
        return {"pair": pair, "error": "thin_bars", "n": len(candles)}
    # Coinbase: [time, low, high, open, close, volume]
    t = [int(r[0]) for r in candles]
    l = [float(r[1]) for r in candles]
    h = [float(r[2]) for r in candles]
    o = [float(r[3]) for r in candles]
    c = [float(r[4]) for r in candles]
    atr = _atr(h, l, c, 14)
    ema50 = _ema(c, 50)
    ema200 = _ema(c, 200)
    ph, pl = _pivots(h, l, spec.pivot)

    pivot_highs: List[Tuple[int, float]] = [(i, ph[i]) for i in range(len(ph)) if ph[i] is not None]
    pivot_lows: List[Tuple[int, float]] = [(i, pl[i]) for i in range(len(pl)) if pl[i] is not None]

    trades: List[Trade] = []
    i = max(200, spec.pivot * 2 + 5)
    cooldown_until = 0

    while i < len(c) - 2:
        if i < cooldown_until:
            i += 1
            continue
        atr_i = atr[i]
        if atr_i is None or atr_i <= 0:
            i += 1
            continue

        bull = True
        bear = True
        if spec.trend == "ema50_200":
            if ema50[i] is None or ema200[i] is None:
                i += 1
                continue
            bull = ema50[i] > ema200[i]
            bear = ema50[i] < ema200[i]

        sides: List[str] = []
        if bull:
            sides.append("long")
        if bear and not spec.long_only:
            sides.append("short")
        if not sides:
            i += 1
            continue

        fired = False
        for side in sides:
            # newest valid impulse ending at or before i - pivot (confirmed)
            impulse = None
            if side == "long":
                # low then high
                lows = [p for p in pivot_lows if p[0] < i - spec.pivot]
                highs = [p for p in pivot_highs if p[0] < i - spec.pivot]
                for li, lv in reversed(lows[-40:]):
                    after = [p for p in highs if p[0] > li]
                    if not after:
                        continue
                    hi_i, hv = after[-1]
                    if hv <= lv:
                        continue
                    if (hv - lv) < spec.min_impulse_atr * atr_i:
                        continue
                    if i - hi_i > spec.max_swing_age:
                        continue
                    impulse = (li, lv, hi_i, hv)
                    break
            else:
                highs = [p for p in pivot_highs if p[0] < i - spec.pivot]
                lows = [p for p in pivot_lows if p[0] < i - spec.pivot]
                for hi_i, hv in reversed(highs[-40:]):
                    after = [p for p in lows if p[0] > hi_i]
                    if not after:
                        continue
                    li, lv = after[-1]
                    if hv <= lv:
                        continue
                    if (hv - lv) < spec.min_impulse_atr * atr_i:
                        continue
                    if i - li > spec.max_swing_age:
                        continue
                    impulse = (hi_i, hv, li, lv)
                    break
            if impulse is None:
                continue
            if side == "long":
                s_lo_i, s_lo, s_hi_i, s_hi = impulse
                z_lo, z_hi = _zone(s_hi, s_lo, spec.pocket, "long")
            else:
                s_hi_i, s_hi, s_lo_i, s_lo = impulse
                z_lo, z_hi = _zone(s_hi, s_lo, spec.pocket, "short")

            # find first touch in recent window ending at i
            touch_i = None
            start_scan = max(impulse[2] if side == "long" else impulse[2], i - spec.touch_confirm_bars - 5)
            for j in range(start_scan, i + 1):
                if _touch_zone(h[j], l[j], z_lo, z_hi):
                    touch_i = j
                    break
            if touch_i is None:
                continue
            if i - touch_i > spec.touch_confirm_bars:
                continue
            if not _is_engulf(o, h, l, c, i, side, spec.engulf, atr_i, spec.min_engulf_atr):
                continue
            # coupling: this bar or prev interacts with zone
            if not (
                _touch_zone(h[i], l[i], z_lo, z_hi)
                or (i > 0 and _touch_zone(h[i - 1], l[i - 1], z_lo, z_hi))
            ):
                continue

            entry_i = i + 1
            if entry_i >= len(c):
                continue
            entry = o[entry_i]
            if side == "long":
                sl = min(s_lo, l[i]) - spec.atr_sl_buf * atr_i
                risk = entry - sl
                if risk <= 0:
                    continue
                stop_pct = risk / entry
                if stop_pct < spec.min_stop_pct or stop_pct > spec.max_stop_pct:
                    continue
                tp = entry + spec.rr * risk
            else:
                sl = max(s_hi, h[i]) + spec.atr_sl_buf * atr_i
                risk = sl - entry
                if risk <= 0:
                    continue
                stop_pct = risk / entry
                if stop_pct < spec.min_stop_pct or stop_pct > spec.max_stop_pct:
                    continue
                tp = entry - spec.rr * risk

            # walk forward
            exit_i = entry_i
            exit_px = c[entry_i]
            reason = "time"
            last = min(len(c) - 1, entry_i + spec.time_stop_bars)
            for k in range(entry_i, last + 1):
                if side == "long":
                    # SL first if both
                    if l[k] <= sl:
                        exit_i, exit_px, reason = k, sl, "sl"
                        break
                    if h[k] >= tp:
                        exit_i, exit_px, reason = k, tp, "tp"
                        break
                else:
                    if h[k] >= sl:
                        exit_i, exit_px, reason = k, sl, "sl"
                        break
                    if l[k] <= tp:
                        exit_i, exit_px, reason = k, tp, "tp"
                        break
                exit_i, exit_px = k, c[k]
            if reason == "time":
                exit_px = c[exit_i]

            if side == "long":
                r_gross = (exit_px - entry) / risk
            else:
                r_gross = (entry - exit_px) / risk
            # fee on notional ≈ ticket; convert fee to R: cost_frac * entry / risk
            fee_r = (RT_COST * entry) / risk
            r_net = r_gross - fee_r
            pnl_usd = TICKET_USD * ((exit_px / entry - 1.0) if side == "long" else (entry / exit_px - 1.0))
            # more accurate: apply RT cost on notional
            pnl_usd_net = TICKET_USD * (
                ((exit_px * (1 - (FEE_BPS_SIDE + SLIP_BPS_SIDE) / 10000.0))
                 / (entry * (1 + (FEE_BPS_SIDE + SLIP_BPS_SIDE) / 10000.0))
                 - 1.0)
                if side == "long"
                else (
                    (entry * (1 - (FEE_BPS_SIDE + SLIP_BPS_SIDE) / 10000.0))
                    / (exit_px * (1 + (FEE_BPS_SIDE + SLIP_BPS_SIDE) / 10000.0))
                    - 1.0
                )
            )

            trades.append(
                Trade(
                    pair=pair,
                    side=side,
                    entry_i=entry_i,
                    exit_i=exit_i,
                    entry_px=entry,
                    exit_px=exit_px,
                    sl=sl,
                    tp=tp,
                    bars_held=exit_i - entry_i,
                    reason=reason,
                    r_gross=r_gross,
                    r_net=r_net,
                    pnl_usd_net=pnl_usd_net,
                )
            )
            cooldown_until = exit_i + 1
            fired = True
            break
        if fired:
            i = cooldown_until
        else:
            i += 1

    return _summarize(pair, c, trades, t)


def _summarize(pair: str, closes: Sequence[float], trades: List[Trade], times: Sequence[int]) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        bh = (closes[-1] / closes[200] - 1.0) if len(closes) > 200 else 0.0
        return {
            "pair": pair,
            "n": 0,
            "edge_class": "inconclusive_sparse_N",
            "buy_hold": bh,
            "trades": [],
        }
    wins = sum(1 for t in trades if t.r_net > 0)
    mean_r_g = sum(t.r_gross for t in trades) / n
    mean_r_n = sum(t.r_net for t in trades) / n
    sum_r_n = sum(t.r_net for t in trades)
    gp = sum(t.r_net for t in trades if t.r_net > 0)
    gl = -sum(t.r_net for t in trades if t.r_net <= 0)
    pf = (gp / gl) if gl > 1e-12 else float("inf") if gp > 0 else 0.0
    # DD in R
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        eq += t.r_net
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    bh = closes[-1] / closes[200] - 1.0 if len(closes) > 200 else 0.0
    usd = sum(t.pnl_usd_net for t in trades)
    tp_n = sum(1 for t in trades if t.reason == "tp")
    sl_n = sum(1 for t in trades if t.reason == "sl")
    # edge class
    if n < 20:
        edge = "inconclusive_sparse_N"
    elif mean_r_n > 0 and pf >= 1.2 and n >= 40:
        edge = "ATTENTION_ONLY"  # never HIT without multipair WF
    elif mean_r_n > 0:
        edge = "ATTENTION_ONLY"
    else:
        edge = "unstable_or_no_edge"

    return {
        "pair": pair,
        "n": n,
        "win_rate_net": wins / n,
        "mean_r_gross": mean_r_g,
        "mean_r_net": mean_r_n,
        "sum_r_net": sum_r_n,
        "profit_factor_net": pf if math.isfinite(pf) else None,
        "max_dd_r": max_dd,
        "median_bars": sorted(t.bars_held for t in trades)[n // 2],
        "tp_exits": tp_n,
        "sl_exits": sl_n,
        "time_exits": n - tp_n - sl_n,
        "pnl_usd_net_75": usd,
        "buy_hold_from_bar200": bh,
        "edge_class": edge,
        "rt_cost": RT_COST,
        "first_entry_ts": times[trades[0].entry_i] if trades else None,
        "last_exit_ts": times[trades[-1].exit_i] if trades else None,
        "trades": [asdict(t) for t in trades[:5]],  # sample head
        "n_trades_full": n,
    }


def run_spec(
    pairs: Sequence[str] = ("BTC-USD", "ETH-USD"),
    spec: Optional[Spec] = None,
    n_bars: int = 9000,
    force_fetch: bool = False,
) -> Dict[str, Any]:
    spec = spec or Spec()
    sess = requests.Session()
    results = []
    for p in pairs:
        candles = load_or_fetch(p, n_bars=n_bars, force=force_fetch)
        results.append(run_pair(p, candles, spec))
    payload = {
        "ts": _utc_now().isoformat(),
        "spec": asdict(spec),
        "rt_cost": RT_COST,
        "ticket_usd": TICKET_USD,
        "lab_only": True,
        "live_wire": False,
        "results": results,
        "plain_english": _plain(results, spec),
    }
    return payload


def _plain(results: List[Dict[str, Any]], spec: Spec) -> str:
    bits = [f"spec={spec.name} pivot={spec.pivot} pocket={spec.pocket} engulf={spec.engulf} trend={spec.trend}"]
    for r in results:
        if r.get("error"):
            bits.append(f"{r['pair']}: {r['error']}")
            continue
        bits.append(
            f"{r['pair']}: N={r['n']} meanR_net={r.get('mean_r_net', 0):+.3f} "
            f"WR={r.get('win_rate_net', 0):.0%} PF={r.get('profit_factor_net')} "
            f"DD_R={r.get('max_dd_r', 0):.2f} class={r.get('edge_class')} "
            f"$75_sum={r.get('pnl_usd_net_75', 0):+.2f}"
        )
    bits.append("LAB only — no live path.")
    return " · ".join(bits)


def run_grid(pair: str = "BTC-USD", n_bars: int = 9000, force_fetch: bool = False) -> Dict[str, Any]:
    candles = load_or_fetch(pair, n_bars=n_bars, force=force_fetch)
    rows = []
    for pivot in (3, 5, 8):
        for pocket in ("gold", "wide", "mid"):
            for engulf in ("strict", "loose"):
                for trend in ("ema50_200", "none"):
                    spec = Spec(
                        name=f"p{pivot}_{pocket}_{engulf}_{trend}",
                        pivot=pivot,
                        pocket=pocket,
                        engulf=engulf,
                        trend=trend,
                        long_only=True,
                    )
                    r = run_pair(pair, candles, spec)
                    rows.append(
                        {
                            "name": spec.name,
                            "pivot": pivot,
                            "pocket": pocket,
                            "engulf": engulf,
                            "trend": trend,
                            "n": r.get("n", 0),
                            "mean_r_net": r.get("mean_r_net"),
                            "win_rate_net": r.get("win_rate_net"),
                            "profit_factor_net": r.get("profit_factor_net"),
                            "max_dd_r": r.get("max_dd_r"),
                            "pnl_usd_net_75": r.get("pnl_usd_net_75"),
                            "edge_class": r.get("edge_class"),
                        }
                    )
    # rank: N>=30 by mean_r_net
    ranked = sorted(
        [x for x in rows if (x.get("n") or 0) >= 30 and x.get("mean_r_net") is not None],
        key=lambda x: x["mean_r_net"],
        reverse=True,
    )
    ranked_thin = sorted(
        [x for x in rows if x.get("mean_r_net") is not None],
        key=lambda x: (x.get("mean_r_net") or -999, x.get("n") or 0),
        reverse=True,
    )
    return {
        "ts": _utc_now().isoformat(),
        "pair": pair,
        "rt_cost": RT_COST,
        "cells": rows,
        "top_n30": ranked[:10],
        "top_any": ranked_thin[:10],
        "v0_cell": next((x for x in rows if x["name"] == "p5_gold_strict_ema50_200"), None),
    }


def write_reports(payload: Dict[str, Any], grid: Optional[Dict[str, Any]] = None) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str))
    lines = [
        "# Fib pocket + engulf 1h — LAB result",
        "",
        f"**TS:** {payload.get('ts')}",
        f"**RT cost:** {payload.get('rt_cost'):.4f} (taker+slip)",
        f"**Live wire:** {payload.get('live_wire')}",
        "",
        payload.get("plain_english", ""),
        "",
        "## Spec",
        "```json",
        json.dumps(payload.get("spec"), indent=2),
        "```",
        "",
        "## Per pair",
    ]
    for r in payload.get("results") or []:
        lines.append(f"### {r.get('pair')}")
        lines.append(f"- N={r.get('n')} edge=`{r.get('edge_class')}`")
        if r.get("n"):
            lines.append(
                f"- mean R gross/net: {r.get('mean_r_gross'):+.3f} / {r.get('mean_r_net'):+.3f}"
            )
            lines.append(
                f"- WR net={r.get('win_rate_net'):.1%} PF={r.get('profit_factor_net')} "
                f"maxDD_R={r.get('max_dd_r'):.2f}"
            )
            lines.append(
                f"- exits tp/sl/time={r.get('tp_exits')}/{r.get('sl_exits')}/{r.get('time_exits')} "
                f"med bars={r.get('median_bars')}"
            )
            lines.append(f"- sum PnL on $75 tickets (net): ${r.get('pnl_usd_net_75'):+.2f}")
            lines.append(f"- BH (from bar200): {r.get('buy_hold_from_bar200'):+.2%}")
        lines.append("")
    lines.extend(
        [
            "## Verdict",
            "- Lab measure only. No promote / no runner hook.",
            "- Prior daily fib discount family was drop (2026-08-15); this is separate 1h recipe.",
            "",
            f"Spec: `docs/plans/2026-09-14-fib-pocket-engulf-1h-spec.md`",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    if grid:
        gl = [
            "# Fib pocket engulf 1h — pre-registered grid (BTC)",
            "",
            f"**TS:** {grid.get('ts')}",
            "",
            "## v0 cell",
            f"```json\n{json.dumps(grid.get('v0_cell'), indent=2)}\n```",
            "",
            "## Top by mean R net (N≥30)",
        ]
        for x in grid.get("top_n30") or []:
            gl.append(
                f"- `{x['name']}` N={x['n']} meanR_net={x['mean_r_net']:+.3f} "
                f"WR={x.get('win_rate_net', 0):.0%} PF={x.get('profit_factor_net')} "
                f"DD={x.get('max_dd_r')} $75={x.get('pnl_usd_net_75'):+.1f} `{x.get('edge_class')}`"
            )
        if not grid.get("top_n30"):
            gl.append("_No cell with N≥30 and ranked net R._")
            gl.append("")
            gl.append("## Top any N")
            for x in grid.get("top_any") or []:
                gl.append(
                    f"- `{x['name']}` N={x['n']} meanR_net={x.get('mean_r_net'):+.3f} "
                    f"`{x.get('edge_class')}`"
                )
        gl.append("")
        gl.append("Grid was pre-registered in spec — no post-hoc fishing beyond this table.")
        GRID_REPORT_PATH.write_text("\n".join(gl) + "\n")
        (ROOT / "data" / "state" / "fib_pocket_engulf_1h_grid_latest.json").write_text(
            json.dumps(grid, indent=2, default=str)
        )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--force-fetch", action="store_true")
    ap.add_argument("--bars", type=int, default=9000)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--pairs", default="BTC-USD,ETH-USD")
    args = ap.parse_args()
    pairs = [p.strip() for p in args.pairs.split(",") if p.strip()]
    payload = run_spec(pairs=pairs, n_bars=args.bars, force_fetch=args.force_fetch)
    grid = None
    if args.grid:
        grid = run_grid(pair=pairs[0], n_bars=args.bars, force_fetch=False)
    write_reports(payload, grid)
    print(payload["plain_english"])
    if grid:
        print("grid_top", (grid.get("top_n30") or grid.get("top_any") or [])[:3])


if __name__ == "__main__":
    main()
