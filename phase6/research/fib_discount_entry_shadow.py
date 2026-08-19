#!/usr/bin/env python3
"""
Fib discount-zone entry shadow dig (offline).

Hypothesis from 2026-07-28 Fib vs RSI session:
  Fib is NOT a RSI or BTC-30d regime replacement.
  Best fit = add-on gate once regime already allows buys:
    allow_new_buys (BTC 30d) + RSI ≤ max_rsi + price in Fib discount zone.

Real Coinbase public daily OHLCV only. No live config / allocator writes.
Pre-registered arms only — no combo fishing.
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
STATE_JSON = ROOT / "data/state/trials/TEST_FIB_DISCOUNT_ENTRY_SHADOW.json"

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

# Live-ish REGIME-CASH entry knobs (flat option B style; bull looser RSI)
FLAT_MAX_RSI = 55.0
BULL_MAX_RSI = 70.0
# BTC 30d regime thresholds (aligned with detector spirit)
BULL_BTC_30D = 0.15
BEAR_BTC_30D = -0.10
FLAT_ABS = 0.08

# Swing lookback for Fib anchor (bars)
SWING_L = 20
# Discount zone: retracement of last up-leg into [lo, hi]
FIB_LO = 0.50
FIB_HI = 0.786

# Exit: fixed SL + soft RSI overbought (mirrors prefer_exit spirit, not live TP)
SL_PCT = 0.03
OVERBOUGHT_RSI = 80.0
MAX_HOLD_BARS = 21


@dataclass
class Arm:
    arm_id: str
    description: str
    use_rsi: bool
    use_fib: bool
    # if use_rsi False and use_fib True → FIB_ONLY replacement check
    require_regime_allow: bool = True


ARMS: List[Arm] = [
    Arm("BH", "Buy & hold pair", use_rsi=False, use_fib=False, require_regime_allow=False),
    Arm("BASE_RSI", "Regime allow + RSI≤max (live-like entry surface)", use_rsi=True, use_fib=False),
    Arm("RSI_FIB_AND", "Regime allow + RSI≤max + Fib discount [0.5–0.786]", use_rsi=True, use_fib=True),
    Arm("FIB_ONLY", "Regime allow + Fib only (RSI replacement check)", use_rsi=False, use_fib=True),
    Arm("RSI_OR_FIB", "Regime allow + (RSI ok OR Fib discount)", use_rsi=True, use_fib=True),  # handled specially
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
            raise RuntimeError(f"rate limited fetching {product_id}")
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
        time.sleep(0.2)
    seen = set()
    deduped = []
    for c in sorted(out, key=lambda x: x["timestamp"]):
        if c["timestamp"] in seen:
            continue
        seen.add(c["timestamp"])
        deduped.append(c)
    return deduped


def ensure_ohlcv(
    pairs: Dict[str, str],
    start: datetime,
    end: datetime,
    force: bool = False,
) -> Dict[str, Path]:
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
                    print(f"  cache hit {short}: {len(rows)} bars {rows[0]['timestamp'][:10]}→{rows[-1]['timestamp'][:10]}")
            else:
                need = True
        if need:
            print(f"  fetching {short} ({pid}) {start.date()}→{end.date()} ...")
            rows = fetch_daily(pid, start, end)
            if not rows:
                raise RuntimeError(f"no candles for {pid}")
            path.write_text(json.dumps(rows, indent=2))
            print(f"  wrote {path.name}: {len(rows)} bars {rows[0]['timestamp'][:10]}→{rows[-1]['timestamp'][:10]}")
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


def add_indicators(df: pd.DataFrame, btc_close: Optional[pd.Series] = None) -> pd.DataFrame:
    """Fib from last up-leg: swing_low → swing_high over SWING_L, retracement of close."""
    o = df.copy()
    o["rsi"] = _rsi(o["Close"], 14)
    # Rolling swing anchors (no look-ahead beyond bar i: use shift(1) on extremes)
    roll_high = o["High"].rolling(SWING_L).max().shift(1)
    roll_low = o["Low"].rolling(SWING_L).min().shift(1)
    # Prefer up-leg: low then high within window — use roll_low as swing_low, roll_high as swing_high
    o["swing_high"] = roll_high
    o["swing_low"] = roll_low
    span = (o["swing_high"] - o["swing_low"]).replace(0, np.nan)
    # Retracement from high toward low: 0 at high, 1 at low
    o["fib_ret"] = (o["swing_high"] - o["Close"]) / span
    o["fib_discount"] = (o["fib_ret"] >= FIB_LO) & (o["fib_ret"] <= FIB_HI)
    # Absolute fib levels for report
    o["fib_0_5"] = o["swing_high"] - FIB_LO * span
    o["fib_0_618"] = o["swing_high"] - 0.618 * span
    o["fib_0_786"] = o["swing_high"] - FIB_HI * span
    # Pair 30d
    o["ret_30d"] = o["Close"].pct_change(30)
    # BTC regime series aligned to this index
    if btc_close is not None:
        btc_aligned = btc_close.reindex(o.index).ffill()
        o["btc_ret_30d"] = btc_aligned.pct_change(30)
    else:
        o["btc_ret_30d"] = o["ret_30d"]
    br = o["btc_ret_30d"]
    o["btc_regime"] = np.where(
        br >= BULL_BTC_30D,
        "bull",
        np.where(br <= BEAR_BTC_30D, "bear", np.where(br.abs() < FLAT_ABS, "flat", "transition")),
    )
    # allow_new_buys: bull + flat only (bear/transition park) — matches REGIME-CASH spirit
    o["allow_buys"] = o["btc_regime"].isin(["bull", "flat"])
    o["max_rsi"] = np.where(o["btc_regime"] == "bull", BULL_MAX_RSI, FLAT_MAX_RSI)
    return o


def entry_ok(row: pd.Series, arm: Arm) -> bool:
    if arm.arm_id == "BH":
        return False
    if arm.require_regime_allow and not bool(row["allow_buys"]):
        return False
    rsi = float(row["rsi"]) if pd.notna(row["rsi"]) else None
    fib = bool(row["fib_discount"]) if pd.notna(row.get("fib_ret")) else False
    max_rsi = float(row["max_rsi"])
    rsi_ok = rsi is not None and rsi <= max_rsi
    if arm.arm_id == "RSI_OR_FIB":
        return rsi_ok or fib
    if arm.use_rsi and arm.use_fib:
        return rsi_ok and fib
    if arm.use_rsi and not arm.use_fib:
        return rsi_ok
    if arm.use_fib and not arm.use_rsi:
        return fib
    return False


def backtest(
    df: pd.DataFrame,
    arm: Arm,
    pair: str,
    fee_bps: float = FEE_BPS,
    initial: float = 10_000.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    fee = fee_bps / 10_000.0
    cash = float(initial)
    pos = 0.0
    entry_px = 0.0
    entry_i = 0
    entry_t = None
    entry_reg = "unk"
    entry_fib = float("nan")
    entry_rsi = float("nan")
    trades: List[Dict[str, Any]] = []
    curve: List[float] = []

    def flatten(ts, px, i, reason):
        nonlocal cash, pos, entry_px
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
                "entry_fib_ret": entry_fib,
                "entry_rsi": entry_rsi,
            }
        )
        cash = pos * px * (1 - fee)
        pos = 0.0

    if arm.arm_id == "BH":
        px0 = float(df["Close"].iloc[0])
        deploy = initial * SIZE
        pos = (deploy * (1 - fee)) / px0
        cash = initial - deploy
        entry_px = px0
        entry_t = df.index[0]
        entry_i = 0
        entry_reg = str(df["btc_regime"].iloc[0])
        for i, (ts, row) in enumerate(df.iterrows()):
            px = float(row["Close"])
            curve.append(cash + pos * px)
        if pos > 0:
            px = float(df["Close"].iloc[-1])
            flatten(df.index[-1], px, len(df) - 1, "eod_flatten")
    else:
        for i, (ts, row) in enumerate(df.iterrows()):
            px = float(row["Close"])
            eq = cash + pos * px
            curve.append(eq)
            if pos > 0:
                reason = None
                if px <= entry_px * (1 - SL_PCT):
                    reason = "sl_3pct"
                elif float(row["rsi"]) >= OVERBOUGHT_RSI:
                    reason = "rsi_overbought"
                elif i - entry_i >= MAX_HOLD_BARS:
                    reason = "max_hold"
                if reason:
                    flatten(ts, px, i, reason)
            if pos == 0 and entry_ok(row, arm):
                deploy = eq * SIZE
                if deploy <= 0 or px <= 0:
                    continue
                pos = (deploy * (1 - fee)) / px
                cash = eq - deploy
                entry_px = px
                entry_t = ts
                entry_i = i
                entry_reg = str(row["btc_regime"])
                entry_fib = float(row["fib_ret"]) if pd.notna(row["fib_ret"]) else float("nan")
                entry_rsi = float(row["rsi"]) if pd.notna(row["rsi"]) else float("nan")
        if pos > 0:
            px = float(df["Close"].iloc[-1])
            flatten(df.index[-1], px, len(df) - 1, "eod_flatten")

    tdf = pd.DataFrame(trades)
    final = float(curve[-1]) if curve else initial
    total_return = final / initial - 1.0
    eq = pd.Series(curve, index=df.index[: len(curve)])
    peak = eq.cummax()
    dd = (eq / peak - 1.0).min() if len(eq) else 0.0
    n = len(tdf)
    wins = tdf[tdf["pnl_pct"] > 0] if n else tdf
    losses = tdf[tdf["pnl_pct"] <= 0] if n else tdf
    rets = eq.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(365)) if len(rets) > 5 and rets.std() > 0 else 0.0
    summary = {
        "pair": pair,
        "arm": arm.arm_id,
        "description": arm.description,
        "n_trades": int(n),
        "total_return": float(total_return),
        "max_dd": float(dd) if pd.notna(dd) else 0.0,
        "win_rate": float((tdf["pnl_pct"] > 0).mean()) if n else 0.0,
        "expectancy_pct": float(tdf["pnl_pct"].mean()) if n else 0.0,
        "avg_win_pct": float(wins["pnl_pct"].mean()) if len(wins) else float("nan"),
        "avg_loss_pct": float(losses["pnl_pct"].mean()) if len(losses) else float("nan"),
        "avg_bars": float(tdf["bars_held"].mean()) if n else 0.0,
        "final_equity": float(final),
        "sharpe": sharpe,
        "exit_mix": tdf["exit_reason"].value_counts().to_dict() if n else {},
        "regime_n": tdf["entry_regime"].value_counts().to_dict() if n else {},
    }
    return tdf, summary


def portfolio_equal_weight(pair_summaries: List[Dict[str, Any]], arm_id: str) -> Dict[str, Any]:
    rows = [s for s in pair_summaries if s["arm"] == arm_id]
    if not rows:
        return {"arm": arm_id, "n_pairs": 0}
    rets = [r["total_return"] for r in rows]
    dds = [r["max_dd"] for r in rows]
    n_trades = sum(r["n_trades"] for r in rows)
    return {
        "arm": arm_id,
        "n_pairs": len(rows),
        "mean_return": float(np.mean(rets)),
        "median_return": float(np.median(rets)),
        "mean_max_dd": float(np.mean(dds)),
        "worst_dd": float(np.min(dds)),
        "total_trades": int(n_trades),
        "mean_expectancy_pct": float(np.nanmean([r["expectancy_pct"] for r in rows])),
        "mean_win_rate": float(np.nanmean([r["win_rate"] for r in rows])),
        "pairs": {r["pair"]: {"ret": r["total_return"], "dd": r["max_dd"], "n": r["n_trades"]} for r in rows},
    }


def classify_edge(mean_ret: float, mean_dd: float, n_trades: int, delta_bh: float) -> str:
    if n_trades < 15:
        return "inconclusive_sparse_N"
    if mean_ret >= 0.10 and delta_bh >= 0.0:
        return "HIT_10_ABS"
    if mean_ret >= 0.0 and delta_bh >= 0.10:
        return "HIT_10_EDGE_BH"
    if delta_bh > 0 and mean_ret < 0:
        return "EDGE_VS_BAGS_ONLY"
    if mean_ret <= 0:
        return "unstable_or_no_edge"
    return "mild_positive_not_10pct"


def run_window(
    label: str,
    paths: Dict[str, Path],
    start: Optional[str],
    end: Optional[str],
) -> Dict[str, Any]:
    btc = load_df(paths["btc"])
    btc_full = add_indicators(btc, btc_close=btc["Close"])
    pair_summaries: List[Dict[str, Any]] = []
    all_trades: List[dict] = []
    for short, path in paths.items():
        raw = load_df(path)
        full = add_indicators(raw, btc_close=btc["Close"])
        # warmup then slice
        if start:
            sl = full[full.index >= pd.Timestamp(start, tz="UTC")]
        else:
            sl = full
        if end:
            sl = sl[sl.index <= pd.Timestamp(end, tz="UTC")]
        # Long/90d need warmup depth; 14d context can run thin (flagged sparse later).
        min_bars = 10 if (start and (pd.Timestamp(end, tz="UTC") - pd.Timestamp(start, tz="UTC")).days <= 21) else 40
        if len(sl) < min_bars:
            print(f"  skip {short}: only {len(sl)} bars in window (min={min_bars})")
            continue
        for arm in ARMS:
            tdf, summary = backtest(sl, arm, pair=short)
            pair_summaries.append(summary)
            if len(tdf):
                all_trades.extend(tdf.to_dict(orient="records"))
            print(
                f"  {label:12s} {short:4s} {arm.arm_id:12s} "
                f"ret={summary['total_return']:+.2%} dd={summary['max_dd']:.2%} n={summary['n_trades']}"
            )

    port = {a.arm_id: portfolio_equal_weight(pair_summaries, a.arm_id) for a in ARMS}
    bh = port.get("BH", {})
    base = port.get("BASE_RSI", {})
    fib_and = port.get("RSI_FIB_AND", {})
    fib_only = port.get("FIB_ONLY", {})
    bh_mean = float(bh.get("mean_return") or 0.0)
    base_mean = float(base.get("mean_return") or 0.0)
    fib_and_mean = float(fib_and.get("mean_return") or 0.0)
    fib_only_mean = float(fib_only.get("mean_return") or 0.0)

    decision = {
        "fib_as_add_on_vs_base": {
            "delta_ret_pp": (fib_and_mean - base_mean) * 100,
            "delta_dd_pp": (float(fib_and.get("mean_max_dd") or 0) - float(base.get("mean_max_dd") or 0)) * 100,
            "base_n": base.get("total_trades"),
            "fib_and_n": fib_and.get("total_trades"),
            "edge_class": classify_edge(
                fib_and_mean,
                float(fib_and.get("mean_max_dd") or 0),
                int(fib_and.get("total_trades") or 0),
                fib_and_mean - bh_mean,
            ),
        },
        "fib_as_rsi_replacement": {
            "delta_ret_pp_vs_base": (fib_only_mean - base_mean) * 100,
            "edge_class": classify_edge(
                fib_only_mean,
                float(fib_only.get("mean_max_dd") or 0),
                int(fib_only.get("total_trades") or 0),
                fib_only_mean - bh_mean,
            ),
        },
    }
    # Plain-English go/no-go
    add = decision["fib_as_add_on_vs_base"]
    if add["edge_class"] in ("HIT_10_ABS", "HIT_10_EDGE_BH") and add["delta_ret_pp"] > 0 and add["delta_dd_pp"] <= 1.0:
        go = "pursue_shadow_longer — Fib AND gate beat BASE on return without much worse DD"
    elif add["edge_class"] == "inconclusive_sparse_N":
        go = "inconclusive — too few trades; need longer tape or lower TF (not promote)"
    elif add["delta_ret_pp"] > 0 and float(fib_and.get("mean_max_dd") or 0) >= float(base.get("mean_max_dd") or 0):
        go = "weak_positive_add_on — slightly better ret + not worse DD; observe-only, no live"
    elif add["delta_ret_pp"] <= 0:
        go = "no_go_add_on — Fib AND does not beat RSI-only BASE on this tape"
    else:
        go = "no_go_or_hold — no clear improvement worth live path"

    rep_vs = decision["fib_as_rsi_replacement"]
    if rep_vs["delta_ret_pp_vs_base"] >= 0 and fib_only_mean > base_mean:
        replace_msg = "unexpected: FIB_ONLY ≥ BASE on this window — still not a live swap without long WF"
    else:
        replace_msg = "confirmed: FIB_ONLY is a poor RSI replacement on this tape (as hypothesized)"

    return {
        "window": label,
        "start": start,
        "end": end,
        "portfolio": port,
        "pair_summaries": pair_summaries,
        "n_trade_rows": len(all_trades),
        "decision": decision,
        "plain_english": {
            "add_on_gate": go,
            "rsi_replacement": replace_msg,
            "note": "Shadow/offline only. No regime detector swap. No live config.",
        },
        "trades_sample": all_trades[:40],
    }


def write_report(payload: Dict[str, Any], stamp: str) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jpath = REPORT_DIR / f"FIB_DISCOUNT_ENTRY_SHADOW_{stamp}.json"
    mpath = REPORT_DIR / f"FIB_DISCOUNT_ENTRY_SHADOW_{stamp}.md"
    jpath.write_text(json.dumps(payload, indent=2, default=str))

    lines = [
        f"# Fib discount-zone entry shadow — {stamp}",
        "",
        "## Plain English",
        "",
    ]
    for w in payload["windows"]:
        pe = w["plain_english"]
        lines.append(f"### Window `{w['window']}` ({w.get('start')} → {w.get('end')})")
        lines.append(f"- **Add-on (RSI+Fib AND):** {pe['add_on_gate']}")
        lines.append(f"- **Fib as RSI replacement:** {pe['rsi_replacement']}")
        lines.append("")
        lines.append("| Arm | Mean ret | Mean maxDD | Trades |")
        lines.append("|-----|----------|------------|--------|")
        for aid, p in w["portfolio"].items():
            if not p or not p.get("n_pairs"):
                continue
            lines.append(
                f"| {aid} | {p.get('mean_return', 0):+.2%} | {p.get('mean_max_dd', 0):.2%} | {p.get('total_trades', 0)} |"
            )
        lines.append("")
        d = w["decision"]["fib_as_add_on_vs_base"]
        lines.append(
            f"- vs BASE: Δret **{d['delta_ret_pp']:+.2f} pp**, ΔDD **{d['delta_dd_pp']:+.2f} pp**, "
            f"class `{d['edge_class']}`"
        )
        lines.append("")

    lines += [
        "## Design (frozen knobs)",
        "",
        f"- Swing lookback: **{SWING_L}d** prior high/low; discount fib_ret ∈ **[{FIB_LO}, {FIB_HI}]**",
        f"- Regime allow: BTC 30d bull (≥{BULL_BTC_30D:.0%}) or flat (|r|<{FLAT_ABS:.0%}); bear/transition park",
        f"- RSI caps: flat/transition path **≤{FLAT_MAX_RSI}**, bull **≤{BULL_MAX_RSI}**",
        f"- Exit: SL **{SL_PCT:.0%}**, RSI≥{OVERBOUGHT_RSI}, max hold {MAX_HOLD_BARS}d",
        "- Arms: BH · BASE_RSI · RSI_FIB_AND · FIB_ONLY · RSI_OR_FIB",
        "- Data: Coinbase public daily candles. Fee 5 bps/side. Equal-weight pair mean.",
        "",
        "## Go / no-go rules",
        "",
        "- Promote path only if long-tape add-on beats BASE on growth **and** DD, N≥15, then shadow — never auto-live.",
        "- FIB_ONLY beating BASE once does **not** authorize RSI removal.",
        "- Sparse 14d windows → inconclusive, not a winner.",
        "",
        f"JSON: `{jpath.name}`",
        "",
    ]
    mpath.write_text("\n".join(lines))
    return jpath, mpath


def main() -> int:
    ap = argparse.ArgumentParser(description="Fib discount entry shadow dig")
    ap.add_argument("--force-fetch", action="store_true")
    ap.add_argument("--start-long", default="2021-01-01")
    args = ap.parse_args()

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_long = datetime.fromisoformat(args.start_long).replace(tzinfo=timezone.utc)
    start_14 = end - timedelta(days=14)
    start_90 = end - timedelta(days=90)
    # need warmup before windows
    fetch_start = start_long - timedelta(days=40)

    print("=== Fib discount entry shadow ===")
    print(f"end={end.date()} fetch_from={fetch_start.date()}")
    paths = ensure_ohlcv(PAIRS, fetch_start, end, force=args.force_fetch)

    windows = []
    for label, st in [("last_14d", start_14), ("last_90d", start_90), ("long_tape", start_long)]:
        print(f"\n--- window {label} ---")
        windows.append(
            run_window(
                label,
                paths,
                start=st.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
        )

    stamp = end.strftime("%Y%m%d")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Fib discount as add-on to regime+RSI, not replacement",
        "knobs": {
            "swing_L": SWING_L,
            "fib_lo": FIB_LO,
            "fib_hi": FIB_HI,
            "flat_max_rsi": FLAT_MAX_RSI,
            "bull_max_rsi": BULL_MAX_RSI,
            "sl_pct": SL_PCT,
            "pairs": list(PAIRS.keys()),
        },
        "windows": windows,
        "overall_recommendation": None,
        "live_writes": False,
    }

    # Overall: long tape dominates; 14d is context only
    long_w = next(w for w in windows if w["window"] == "long_tape")
    w14 = next(w for w in windows if w["window"] == "last_14d")
    overall = {
        "primary_window": "long_tape",
        "long_tape_add_on": long_w["plain_english"]["add_on_gate"],
        "last_14d_context": w14["plain_english"]["add_on_gate"],
        "recommendation_enum": "drop"
        if "no_go" in long_w["plain_english"]["add_on_gate"]
        else (
            "continue_observe_only"
            if "inconclusive" in long_w["plain_english"]["add_on_gate"]
            or "weak_positive" in long_w["plain_english"]["add_on_gate"]
            else "propose_scoped_shadow"
            if "pursue" in long_w["plain_english"]["add_on_gate"]
            else "drop"
        ),
    }
    payload["overall_recommendation"] = overall

    jpath, mpath = write_report(payload, stamp)
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(
        json.dumps(
            {
                "trial_id": "TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815",
                "status": "REPORT_READY",
                "family": "fib_discount_entry",
                "final_report": str(mpath),
                "final_recommendation": overall["recommendation_enum"],
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
