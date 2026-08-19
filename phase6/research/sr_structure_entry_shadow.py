#!/usr/bin/env python3
"""
Market structure S/R shadow dig — bounce vs breakout/retest.

Formal family: support & resistance / market-structure price action.
Two pre-registered entry recipes (not mixed in one arm):
  1) SR_BOUNCE — fade: long on confirmed bounce from support zone
  2) SR_BREAK_RETEST — momentum: long on close through resistance, enter on retest hold

Keeps BTC-30d allow_new_buys envelope (not a regime replacement).
Optional RSI add-on arms mirror live flat/bull max_rsi gates.

Real Coinbase public daily OHLCV only. No live config writes.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
LONG_DIR = ROOT / "backtests/data/long"
REPORT_DIR = ROOT / "reports"
STATE_JSON = ROOT / "data/state/trials/TEST_SR_STRUCTURE_ENTRY_SHADOW.json"

PAIRS = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
    "link": "LINK-USD",
    "avax": "AVAX-USD",
}

FEE_BPS = 5.0
SIZE = 0.95
MAX_CANDLES = 300
GRANULARITY = 86400

FLAT_MAX_RSI = 55.0
BULL_MAX_RSI = 70.0
BULL_BTC_30D = 0.15
BEAR_BTC_30D = -0.10
FLAT_ABS = 0.08

# Structure knobs (frozen)
SWING_N = 3  # pivot: high with N lower highs each side
ZONE_ATR = 0.35  # half-width of band in ATR units
SL_PCT = 0.03  # hard floor (exchange-like)
MAX_HOLD_BARS = 30
# Bounce: must touch support then close back above zone top within confirm bars
BOUNCE_CONFIRM_BARS = 2
# Breakout: close above resistance; retest within RETEST_BARS holding above zone mid
RETEST_BARS = 5


@dataclass
class Arm:
    arm_id: str
    description: str
    recipe: str  # bh | base_rsi | bounce | break_retest
    require_rsi: bool = False
    require_regime: bool = True


ARMS: List[Arm] = [
    Arm("BH", "Buy & hold", "bh", require_rsi=False, require_regime=False),
    Arm("BASE_RSI", "Regime allow + RSI≤max (live-like baseline)", "base_rsi", require_rsi=True),
    Arm("SR_BOUNCE", "S/R bounce off support zone (no RSI)", "bounce", require_rsi=False),
    Arm("SR_BOUNCE_RSI", "S/R bounce + RSI≤max", "bounce", require_rsi=True),
    Arm("SR_BREAK_RETEST", "Break resistance + retest hold (no RSI)", "break_retest", require_rsi=False),
    Arm("SR_BREAK_RSI", "Break+retest + RSI≤max", "break_retest", require_rsi=True),
]


def fetch_daily(product_id: str, start: datetime, end: datetime) -> List[dict]:
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
    out: List[dict] = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=MAX_CANDLES - 1), end)
        params = {
            "start": chunk_start.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
            "granularity": GRANULARITY,
        }
        raw = None
        for attempt in range(5):
            resp = requests.get(url, params=params, timeout=45)
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code == 404:
                return out
            resp.raise_for_status()
            raw = resp.json()
            break
        else:
            raise RuntimeError(f"rate limited {product_id}")
        for row in reversed(raw or []):
            t = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            if t < start or t > end:
                continue
            out.append(
                {
                    "timestamp": t.strftime("%Y-%m-%dT00:00:00Z"),
                    "open": float(row[3]),
                    "high": float(row[2]),
                    "low": float(row[1]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.15)
    seen = set()
    deduped = []
    for c in sorted(out, key=lambda x: x["timestamp"]):
        if c["timestamp"] in seen:
            continue
        seen.add(c["timestamp"])
        deduped.append(c)
    return deduped


def ensure_ohlcv(pairs: Dict[str, str], start: datetime, end: datetime, force: bool = False) -> Dict[str, Path]:
    LONG_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for short, pid in pairs.items():
        path = LONG_DIR / f"ohlcv_daily_{short}.json"
        need = force or not path.exists()
        if path.exists() and not force:
            rows = json.loads(path.read_text())
            if rows:
                last = datetime.fromisoformat(rows[-1]["timestamp"].replace("Z", "+00:00"))
                first = datetime.fromisoformat(rows[0]["timestamp"].replace("Z", "+00:00"))
                if last < end - timedelta(days=3) or first > start + timedelta(days=60):
                    need = True
                else:
                    print(f"  cache hit {short}: {len(rows)} bars")
            else:
                need = True
        if need:
            print(f"  fetching {short} {start.date()}→{end.date()} ...")
            rows = fetch_daily(pid, start, end)
            if not rows:
                raise RuntimeError(f"no candles {pid}")
            path.write_text(json.dumps(rows, indent=2))
            print(f"  wrote {path.name}: {len(rows)} bars")
        paths[short] = path
    return paths


def load_df(path: Path) -> pd.DataFrame:
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.columns = [c.capitalize() for c in df.columns]
    return df


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = -d.clip(upper=0.0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1 / n, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(h, l, c, n=14) -> pd.Series:
    prev = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def add_structure(df: pd.DataFrame, btc_close: pd.Series) -> pd.DataFrame:
    o = df.copy()
    o["rsi"] = _rsi(o["Close"], 14)
    o["atr"] = _atr(o["High"], o["Low"], o["Close"], 14)
    n = SWING_N
    # Confirmed pivots only (center bar); shift so no look-ahead past confirmation
    high = o["High"]
    low = o["Low"]
    is_swing_high = pd.Series(True, index=o.index)
    is_swing_low = pd.Series(True, index=o.index)
    for k in range(1, n + 1):
        is_swing_high &= high > high.shift(k)
        is_swing_high &= high > high.shift(-k)
        is_swing_low &= low < low.shift(k)
        is_swing_low &= low < low.shift(-k)
    # Pivot value known only after N bars → shift forward by N
    sh_level = high.where(is_swing_high).shift(n)
    sl_level = low.where(is_swing_low).shift(n)
    # Carry last confirmed swing high/low
    o["last_swing_high"] = sh_level.ffill()
    o["last_swing_low"] = sl_level.ffill()
    # Prior swing high (resistance candidate before most recent) for break context
    sh_pts = high.where(is_swing_high).shift(n)
    sl_pts = low.where(is_swing_low).shift(n)
    o["resist"] = sh_pts.ffill()
    o["support"] = sl_pts.ffill()
    # Second-most-recent swing high for "prior peak" resistance when price makes new structure
    # Use expanding last-2 unique-ish via shift of ffill chain
    o["resist_prev"] = sh_pts.ffill().shift(1)
    # while same value dominates, walk back with where changes
    resist_ff = sh_pts.ffill()
    changed = resist_ff.ne(resist_ff.shift(1))
    o["resist_prev"] = resist_ff.where(changed).ffill().shift(1)

    half = ZONE_ATR * o["atr"]
    o["sup_lo"] = o["support"] - half
    o["sup_hi"] = o["support"] + half
    o["res_lo"] = o["resist"] - half
    o["res_hi"] = o["resist"] + half

    # Bounce setup flags (causal on bar i using confirmed levels)
    touch_sup = (o["Low"] <= o["sup_hi"]) & (o["Low"] >= o["sup_lo"] - half)  # touch band (slightly generous low)
    # also allow wick into band from above
    touch_sup = (o["Low"] <= o["sup_hi"]) & (o["High"] >= o["sup_lo"])
    close_above_sup = o["Close"] > o["sup_hi"]
    o["bounce_signal"] = touch_sup & close_above_sup

    # Break: close through resistance high of zone
    o["break_signal"] = o["Close"] > o["res_hi"]
    # Retest: after a break in lookback, price revisits zone and holds (close >= res_lo)
    broke_recent = o["break_signal"].rolling(RETEST_BARS, min_periods=1).max().astype(bool)
    # exclude same bar as break for retest entry — retest is touch after break
    prior_break = o["break_signal"].shift(1).rolling(RETEST_BARS, min_periods=1).max().fillna(False).astype(bool)
    retest_touch = (o["Low"] <= o["res_hi"]) & (o["Close"] >= o["res_lo"])
    o["retest_signal"] = prior_break & retest_touch & ~o["break_signal"]

    btc_aligned = btc_close.reindex(o.index).ffill()
    o["btc_ret_30d"] = btc_aligned.pct_change(30)
    br = o["btc_ret_30d"]
    o["btc_regime"] = np.where(
        br >= BULL_BTC_30D,
        "bull",
        np.where(br <= BEAR_BTC_30D, "bear", np.where(br.abs() < FLAT_ABS, "flat", "transition")),
    )
    o["allow_buys"] = o["btc_regime"].isin(["bull", "flat"])
    o["max_rsi"] = np.where(o["btc_regime"] == "bull", BULL_MAX_RSI, FLAT_MAX_RSI)
    return o


def rsi_ok(row: pd.Series, require: bool) -> bool:
    if not require:
        return True
    if pd.isna(row["rsi"]):
        return False
    return float(row["rsi"]) <= float(row["max_rsi"])


def entry_ok(row: pd.Series, arm: Arm) -> bool:
    if arm.recipe == "bh":
        return False
    if arm.require_regime and not bool(row["allow_buys"]):
        return False
    if not rsi_ok(row, arm.require_rsi):
        return False
    if arm.recipe == "base_rsi":
        return True  # regime+rsi already applied; enter when flat-ish not in position handled by loop throttle
    if arm.recipe == "bounce":
        return bool(row["bounce_signal"])
    if arm.recipe == "break_retest":
        return bool(row["retest_signal"]) or bool(row["break_signal"])
        # allow same-bar break entry OR retest (both are breakout family)
    return False


def backtest(df: pd.DataFrame, arm: Arm, pair: str, initial: float = 10_000.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    fee = FEE_BPS / 10_000.0
    cash = float(initial)
    pos = 0.0
    entry_px = 0.0
    entry_i = 0
    entry_t = None
    entry_reg = "unk"
    entry_kind = ""
    trades: List[Dict[str, Any]] = []
    curve: List[float] = []
    # BASE_RSI: enter at most on signal-like cadence — first eligible bar then after flat
    # Use: enter when rsi ok and regime; cooldown 5 bars after exit to avoid every-day churn
    cooldown = 0

    def flatten(ts, px, i, reason):
        nonlocal cash, pos, entry_px, cooldown
        pnl_pct = (px / entry_px - 1.0) - 2 * fee
        trades.append(
            {
                "pair": pair,
                "arm": arm.arm_id,
                "entry_time": str(entry_t),
                "exit_time": str(ts),
                "entry_price": float(entry_px),
                "exit_price": float(px),
                "pnl_pct": float(pnl_pct),
                "bars_held": int(i - entry_i),
                "exit_reason": reason,
                "entry_regime": entry_reg,
                "entry_kind": entry_kind,
            }
        )
        cash = pos * px * (1 - fee)
        pos = 0.0
        cooldown = 5 if arm.recipe == "base_rsi" else 1

    if arm.recipe == "bh":
        px0 = float(df["Close"].iloc[0])
        deploy = initial * SIZE
        pos = (deploy * (1 - fee)) / px0
        cash = initial - deploy
        entry_px = px0
        entry_t = df.index[0]
        entry_i = 0
        entry_reg = str(df["btc_regime"].iloc[0])
        entry_kind = "bh"
        for ts, row in df.iterrows():
            curve.append(cash + pos * float(row["Close"]))
        flatten(df.index[-1], float(df["Close"].iloc[-1]), len(df) - 1, "eod_flatten")
    else:
        for i, (ts, row) in enumerate(df.iterrows()):
            px = float(row["Close"])
            eq = cash + pos * px
            curve.append(eq)
            if cooldown > 0 and pos == 0:
                cooldown -= 1

            if pos > 0:
                reason = None
                # Structure exits
                if arm.recipe in ("bounce", "break_retest") and i > entry_i:
                    # bounce target: opposing swing resistance
                    if (
                        arm.recipe == "bounce"
                        and pd.notna(row["resist"])
                        and px >= float(row["resist"])
                    ):
                        reason = "target_resist"
                    # breakout target: ~2% beyond break level / running resist
                    elif (
                        arm.recipe == "break_retest"
                        and pd.notna(row["resist"])
                        and px >= float(row["resist"]) * 1.02
                    ):
                        reason = "target_extension"
                    # invalidate under support band
                    if reason is None and pd.notna(row["sup_lo"]) and px < float(row["sup_lo"]):
                        reason = "structure_fail"
                if reason is None and px <= entry_px * (1 - SL_PCT):
                    reason = "sl_3pct"
                if reason is None and i - entry_i >= MAX_HOLD_BARS:
                    reason = "max_hold"
                # BASE_RSI soft exit: overbought
                if reason is None and arm.recipe == "base_rsi" and float(row["rsi"]) >= 80:
                    reason = "rsi_overbought"
                if reason:
                    flatten(ts, px, i, reason)

            if pos == 0 and cooldown == 0 and entry_ok(row, arm):
                # BASE_RSI: only enter if not already "always on" — require rsi rising from below or simple: enter when rsi ok
                # Throttle BASE: enter only every time after cooldown when rsi < max (still many trades)
                # Extra: for base_rsi require Close > prior close (tiny filter) to cut pure noise
                if arm.recipe == "base_rsi" and not (px >= float(df["Close"].iloc[max(0, i - 1)])):
                    continue
                deploy = eq * SIZE
                if deploy <= 0 or px <= 0:
                    continue
                if pd.isna(row.get("support")) and arm.recipe in ("bounce", "break_retest"):
                    continue
                pos = (deploy * (1 - fee)) / px
                cash = eq - deploy
                entry_px = px
                entry_t = ts
                entry_i = i
                entry_reg = str(row["btc_regime"])
                if arm.recipe == "bounce":
                    entry_kind = "bounce"
                elif arm.recipe == "break_retest":
                    entry_kind = "retest" if bool(row["retest_signal"]) else "break"
                else:
                    entry_kind = "base_rsi"

        if pos > 0:
            flatten(df.index[-1], float(df["Close"].iloc[-1]), len(df) - 1, "eod_flatten")

    tdf = pd.DataFrame(trades)
    final = float(curve[-1]) if curve else initial
    total_return = final / initial - 1.0
    eq = pd.Series(curve)
    peak = eq.cummax()
    dd = float((eq / peak - 1.0).min()) if len(eq) else 0.0
    n = len(tdf)
    summary = {
        "pair": pair,
        "arm": arm.arm_id,
        "description": arm.description,
        "n_trades": int(n),
        "total_return": float(total_return),
        "max_dd": dd,
        "win_rate": float((tdf["pnl_pct"] > 0).mean()) if n else 0.0,
        "expectancy_pct": float(tdf["pnl_pct"].mean()) if n else 0.0,
        "avg_bars": float(tdf["bars_held"].mean()) if n else 0.0,
        "final_equity": float(final),
        "exit_mix": tdf["exit_reason"].value_counts().to_dict() if n else {},
        "entry_kind_mix": tdf["entry_kind"].value_counts().to_dict() if n else {},
        "regime_n": tdf["entry_regime"].value_counts().to_dict() if n else {},
    }
    return tdf, summary


def portfolio(pair_summaries: List[Dict[str, Any]], arm_id: str) -> Dict[str, Any]:
    rows = [s for s in pair_summaries if s["arm"] == arm_id]
    if not rows:
        return {"arm": arm_id, "n_pairs": 0}
    rets = [r["total_return"] for r in rows]
    dds = [r["max_dd"] for r in rows]
    return {
        "arm": arm_id,
        "n_pairs": len(rows),
        "mean_return": float(np.mean(rets)),
        "median_return": float(np.median(rets)),
        "mean_max_dd": float(np.mean(dds)),
        "worst_dd": float(min(dds)),
        "total_trades": int(sum(r["n_trades"] for r in rows)),
        "mean_expectancy_pct": float(np.nanmean([r["expectancy_pct"] for r in rows])),
        "mean_win_rate": float(np.nanmean([r["win_rate"] for r in rows])),
        "pairs": {r["pair"]: {"ret": r["total_return"], "dd": r["max_dd"], "n": r["n_trades"]} for r in rows},
    }


def classify(mean_ret: float, n_trades: int, delta_bh: float) -> str:
    if n_trades < 15:
        return "inconclusive_sparse_N"
    if mean_ret >= 0.10 and delta_bh >= 0:
        return "HIT_10_ABS"
    if mean_ret >= 0 and delta_bh >= 0.10:
        return "HIT_10_EDGE_BH"
    if delta_bh > 0 and mean_ret < 0:
        return "EDGE_VS_BAGS_ONLY"
    if mean_ret <= 0:
        return "unstable_or_no_edge"
    return "mild_positive_not_10pct"


def decide_arm(port: Dict[str, Any], bh_mean: float, base_mean: float, label: str) -> Dict[str, Any]:
    mean_ret = float(port.get("mean_return") or 0)
    n = int(port.get("total_trades") or 0)
    return {
        "arm": port.get("arm"),
        "mean_return": mean_ret,
        "mean_max_dd": port.get("mean_max_dd"),
        "total_trades": n,
        "delta_vs_bh_pp": (mean_ret - bh_mean) * 100,
        "delta_vs_base_pp": (mean_ret - base_mean) * 100,
        "edge_class": classify(mean_ret, n, mean_ret - bh_mean),
        "window": label,
    }


def plain_for_window(port_map: Dict[str, Dict], label: str) -> Dict[str, str]:
    bh = float(port_map.get("BH", {}).get("mean_return") or 0)
    base = float(port_map.get("BASE_RSI", {}).get("mean_return") or 0)
    bounce = port_map.get("SR_BOUNCE", {})
    bounce_r = port_map.get("SR_BOUNCE_RSI", {})
    brk = port_map.get("SR_BREAK_RETEST", {})
    brk_r = port_map.get("SR_BREAK_RSI", {})

    def line(name, p):
        if not p or not p.get("n_pairs"):
            return f"{name}: no data"
        mr = float(p.get("mean_return") or 0)
        n = int(p.get("total_trades") or 0)
        dbase = (mr - base) * 100
        cls = classify(mr, n, mr - bh)
        if n < 15:
            return f"{name}: inconclusive (N={n} trades) — not promote"
        if dbase > 0 and mr > base and float(p.get("mean_max_dd") or 0) >= float(port_map.get("BASE_RSI", {}).get("mean_max_dd") or -1):
            return f"{name}: weak/observe — beats BASE by {dbase:+.1f}pp ret (class {cls})"
        if mr > 0 and dbase > 0:
            return f"{name}: mild edge vs BASE ({dbase:+.1f}pp) class {cls} — observe only"
        return f"{name}: no_go vs BASE ({dbase:+.1f}pp, class {cls})"

    # Pick winner among structure arms for headline
    cands = []
    for aid in ("SR_BOUNCE", "SR_BOUNCE_RSI", "SR_BREAK_RETEST", "SR_BREAK_RSI"):
        p = port_map.get(aid) or {}
        if p.get("n_pairs"):
            cands.append((float(p.get("mean_return") or -9), aid, p))
    cands.sort(reverse=True)
    best = cands[0][1] if cands else "none"
    best_p = cands[0][2] if cands else {}
    best_n = int(best_p.get("total_trades") or 0)
    best_ret = float(best_p.get("mean_return") or 0)
    if best_n < 15:
        headline = f"Best structure arm `{best}` still sparse/inconclusive on {label}"
        enum = "inconclusive"
    elif best_ret > base and best_ret > 0:
        headline = f"Best structure arm `{best}` beats BASE on {label} — observe_only, no live"
        enum = "continue_observe_only"
    elif best_ret > base:
        headline = f"Best structure arm `{best}` less-loss vs BASE only on {label}"
        enum = "EDGE_VS_BAGS_ONLY"
    else:
        headline = f"No structure arm beats BASE on {label} — drop for live path"
        enum = "drop"

    return {
        "headline": headline,
        "enum_hint": enum,
        "bounce": line("SR_BOUNCE", bounce),
        "bounce_rsi": line("SR_BOUNCE_RSI", bounce_r),
        "break": line("SR_BREAK_RETEST", brk),
        "break_rsi": line("SR_BREAK_RSI", brk_r),
        "note": "S/R is entry/exit structure add-on research; not REGIME-CASH replacement. Shadow/offline only.",
    }


def run_window(label: str, paths: Dict[str, Path], start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
    btc = load_df(paths["btc"])
    pair_summaries: List[Dict[str, Any]] = []
    all_trades: List[dict] = []
    for short, path in paths.items():
        raw = load_df(path)
        full = add_structure(raw, btc_close=btc["Close"])
        sl = full
        if start:
            sl = sl[sl.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            sl = sl[sl.index <= pd.Timestamp(end, tz="UTC")]
        days = 90
        if start and end:
            days = (pd.Timestamp(end, tz="UTC") - pd.Timestamp(start, tz="UTC")).days
        min_bars = 10 if days <= 21 else 40
        if len(sl) < min_bars:
            print(f"  skip {short}: {len(sl)} bars")
            continue
        for arm in ARMS:
            tdf, summary = backtest(sl, arm, short)
            pair_summaries.append(summary)
            if len(tdf):
                all_trades.extend(tdf.to_dict(orient="records"))
            print(
                f"  {label:12s} {short:4s} {arm.arm_id:16s} "
                f"ret={summary['total_return']:+.2%} dd={summary['max_dd']:.2%} n={summary['n_trades']}"
            )

    port_map = {a.arm_id: portfolio(pair_summaries, a.arm_id) for a in ARMS}
    bh_m = float(port_map.get("BH", {}).get("mean_return") or 0)
    base_m = float(port_map.get("BASE_RSI", {}).get("mean_return") or 0)
    decisions = {
        aid: decide_arm(port_map[aid], bh_m, base_m, label)
        for aid in port_map
        if port_map[aid].get("n_pairs")
    }
    return {
        "window": label,
        "start": start,
        "end": end,
        "portfolio": port_map,
        "decisions": decisions,
        "plain_english": plain_for_window(port_map, label),
        "pair_summaries": pair_summaries,
        "n_trade_rows": len(all_trades),
        "trades_sample": all_trades[:30],
    }


def write_report(payload: Dict[str, Any], stamp: str) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = REPORT_DIR / f"SR_STRUCTURE_ENTRY_SHADOW_{stamp}.json"
    mpath = REPORT_DIR / f"SR_STRUCTURE_ENTRY_SHADOW_{stamp}.md"
    jpath.write_text(json.dumps(payload, indent=2, default=str))

    lines = [
        f"# Market structure S/R shadow — {stamp}",
        "",
        "**Family:** support & resistance / market-structure price action  ",
        "**Arms:** bounce vs break+retest (separate). Optional RSI add-on.  ",
        "**Live writes:** none",
        "",
        "## Plain English",
        "",
    ]
    for w in payload["windows"]:
        pe = w["plain_english"]
        lines.append(f"### `{w['window']}` ({w.get('start')} → {w.get('end')})")
        lines.append(f"- **Headline:** {pe['headline']}")
        lines.append(f"- {pe['bounce']}")
        lines.append(f"- {pe['bounce_rsi']}")
        lines.append(f"- {pe['break']}")
        lines.append(f"- {pe['break_rsi']}")
        lines.append("")
        lines.append("| Arm | Mean ret | Mean maxDD | Trades |")
        lines.append("|-----|----------|------------|--------|")
        for aid, p in w["portfolio"].items():
            if not p.get("n_pairs"):
                continue
            lines.append(
                f"| {aid} | {p.get('mean_return', 0):+.2%} | {p.get('mean_max_dd', 0):.2%} | {p.get('total_trades', 0)} |"
            )
        lines.append("")

    ov = payload.get("overall_recommendation") or {}
    lines += [
        "## Overall",
        "",
        f"- **Primary window:** `{ov.get('primary_window')}`",
        f"- **Call:** {ov.get('call')}",
        f"- **Enum:** `{ov.get('recommendation_enum')}`",
        f"- **14d context:** {ov.get('last_14d_context')}",
        "",
        "## Frozen knobs",
        "",
        f"- Swing pivot: **N={SWING_N}** bars each side (confirmed with lag N)",
        f"- Zone half-width: **{ZONE_ATR}×ATR**",
        f"- Bounce: touch support band + close back above band top",
        f"- Break/retest: close > resist band high; or retest hold within {RETEST_BARS}d after break",
        f"- Regime allow: BTC 30d bull/flat only; RSI caps flat≤{FLAT_MAX_RSI} bull≤{BULL_MAX_RSI}",
        f"- Exit: structure target/fail, SL {SL_PCT:.0%}, max hold {MAX_HOLD_BARS}d",
        "- Data: Coinbase daily; fee 5 bps/side; equal-weight pair mean",
        "",
        "## Go / no-go rules",
        "",
        "- Promote only if long-tape structure arm beats BASE on ret **and** DD, N≥15, then multi-week shadow — never auto-live.",
        "- Bounce and breakout stay **separate** arms forever.",
        "- Sparse short windows → inconclusive.",
        "",
        f"JSON: `{jpath.name}`",
        "",
    ]
    mpath.write_text("\n".join(lines))
    return jpath, mpath


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-fetch", action="store_true")
    ap.add_argument("--start-long", default="2021-01-01")
    args = ap.parse_args()

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_long = datetime.fromisoformat(args.start_long).replace(tzinfo=timezone.utc)
    start_14 = end - timedelta(days=14)
    start_90 = end - timedelta(days=90)
    fetch_start = start_long - timedelta(days=40)

    print("=== SR structure entry shadow (bounce | break+retest) ===")
    paths = ensure_ohlcv(PAIRS, fetch_start, end, force=args.force_fetch)

    windows = []
    for label, st in [("last_14d", start_14), ("last_90d", start_90), ("long_tape", start_long)]:
        print(f"\n--- {label} ---")
        windows.append(
            run_window(label, paths, st.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        )

    long_w = next(w for w in windows if w["window"] == "long_tape")
    w14 = next(w for w in windows if w["window"] == "last_14d")
    hint = long_w["plain_english"]["enum_hint"]
    if hint == "drop":
        enum = "drop"
    elif hint in ("continue_observe_only", "EDGE_VS_BAGS_ONLY", "inconclusive"):
        enum = "continue_observe_only" if hint != "drop" else "drop"
        if hint == "EDGE_VS_BAGS_ONLY":
            enum = "drop"  # less-loss only → do not promote path
        if hint == "inconclusive":
            enum = "continue_observe_only"
    else:
        enum = "continue_observe_only"

    # Stronger: if long tape headline says no_go/drop
    hl = long_w["plain_english"]["headline"].lower()
    if "no structure arm beats" in hl or "drop for live" in hl:
        enum = "drop"
    elif "less-loss" in hl:
        enum = "drop"
    elif "observe" in hl:
        enum = "continue_observe_only"

    overall = {
        "primary_window": "long_tape",
        "call": long_w["plain_english"]["headline"],
        "last_14d_context": w14["plain_english"]["headline"],
        "recommendation_enum": enum,
        "family": "market_structure_sr",
        "live_writes": False,
    }
    stamp = end.strftime("%Y%m%d")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "S/R bounce and break+retest as separate structure arms under REGIME-CASH allow",
        "formal_names": [
            "support_and_resistance",
            "market_structure_price_action",
            "breakout_pullback",
        ],
        "knobs": {
            "swing_n": SWING_N,
            "zone_atr": ZONE_ATR,
            "sl_pct": SL_PCT,
            "pairs": list(PAIRS.keys()),
        },
        "windows": windows,
        "overall_recommendation": overall,
    }
    jpath, mpath = write_report(payload, stamp)
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(
        json.dumps(
            {
                "trial_id": "TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815",
                "status": "REPORT_READY",
                "family": "market_structure_sr",
                "final_report": str(mpath),
                "final_recommendation": enum,
                "reports": [str(mpath), str(jpath)],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    print("\n=== OVERALL ===")
    print(json.dumps(overall, indent=2))
    print(f"report: {mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
