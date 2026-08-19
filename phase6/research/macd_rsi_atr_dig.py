#!/usr/bin/env python3
"""
Focused dig: MACD bullish cross + RSI<K entry, 2×ATR trail (+ optional MACD-death),
no Stoch/BB, universe filters for weak/deep-bear names.

Goal: quantify whether a repeatable ~10–20% edge exists vs BH / cash on real OHLCV.
TEST-COMBINED-INDICATOR-ABLATION dig lane — not live config.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OHLCV_DIR = ROOT / "backtests/data"
REPORT_DIR = ROOT / "reports"
TRIAL_JSON = ROOT / "data/state/trials/TEST_COMBINED_MACD_RSI_ATR_DIG.json"

PAIR_FILES = {
    "btc": "backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json",
    "eth": "backtest_historical_ohlcv_eth_2025-04-20_to_2026-04-20.json",
    "sol": "backtest_historical_ohlcv_sol_2025-04-20_to_2026-04-20.json",
    "link": "backtest_historical_ohlcv_link_2025-04-20_to_2026-04-20.json",
    "avax": "backtest_historical_ohlcv_avax_2025-04-20_to_2026-04-20.json",
    "xrp": "backtest_historical_ohlcv_xrp_2025-04-20_to_2026-04-20.json",
    "doge": "backtest_historical_ohlcv_doge_2025-04-20_to_2026-04-20.json",
    "near": "backtest_historical_ohlcv_near_2025-04-20_to_2026-04-20.json",
    "arb": "backtest_historical_ohlcv_arb_2025-04-20_to_2026-04-20.json",
}

DEFAULT_CORE = ["btc", "eth", "sol", "link"]  # majors+liquid; AVAX excluded by default
DEFAULT_FULL = ["btc", "eth", "sol", "link", "avax"]


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / length, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / length, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def load_pair(pair: str) -> pd.DataFrame:
    key = pair.lower()
    path = OHLCV_DIR / PAIR_FILES[key]
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.columns = [str(c).capitalize() for c in df.columns]
    return df.dropna().copy()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["macd_line"] = _ema(out["Close"], 12) - _ema(out["Close"], 26)
    out["macd_signal"] = _ema(out["macd_line"], 9)
    out["macd_hist"] = out["macd_line"] - out["macd_signal"]
    out["rsi"] = _rsi(out["Close"], 14)
    out["atr"] = _atr(out["High"], out["Low"], out["Close"], 14)
    out["macd_cross_up"] = (out["macd_line"] > out["macd_signal"]) & (
        out["macd_line"].shift(1) <= out["macd_signal"].shift(1)
    )
    out["macd_cross_dn"] = (out["macd_line"] < out["macd_signal"]) & (
        out["macd_line"].shift(1) >= out["macd_signal"].shift(1)
    )
    out["ret_30d"] = out["Close"].pct_change(30)
    out["ret_90d"] = out["Close"].pct_change(90)
    out["dd_from_ath_90"] = out["Close"] / out["Close"].rolling(90).max() - 1.0
    # deep-bear / weak name flags at bar time (no look-ahead beyond rolling past)
    out["deep_bear"] = out["ret_30d"] < -0.40
    out["weak_name"] = (out["ret_90d"] < -0.50) | (out["dd_from_ath_90"] < -0.55)
    out["regime"] = np.where(
        out["ret_30d"] > 0.05, "bull", np.where(out["ret_30d"] < -0.05, "bear", "flat")
    )
    return out.dropna()


@dataclass
class Spec:
    arm_id: str
    description: str
    rsi_max: float  # entry RSI must be < this; 100 = no RSI filter
    atr_mult: float
    macd_death: bool  # exit on MACD cross down
    use_universe_filter: bool  # skip deep_bear/weak at entry
    require_macd_hist_pos: bool = False  # hist > 0 on entry bar
    min_rsi: float = 0.0  # optional floor (avoid dead cat if set)


SPECS: List[Spec] = [
    Spec("CASH", "Stay in cash (0%)", rsi_max=0, atr_mult=0, macd_death=False, use_universe_filter=False),
    Spec("BH", "Buy & hold pair", rsi_max=0, atr_mult=0, macd_death=False, use_universe_filter=False),
    # Core hypothesis
    Spec("F0", "MACD× + RSI<40 + 2×ATR trail (no death)", 40, 2.0, False, False),
    Spec("F1", "MACD× + RSI<40 + 2×ATR + MACD-death", 40, 2.0, True, False),
    Spec("F2", "F1 + skip deep-bear/weak entries", 40, 2.0, True, True),
    # RSI sensitivity (pre-registered)
    Spec("F3", "MACD× + RSI<35 + 2×ATR + death + filter", 35, 2.0, True, True),
    Spec("F4", "MACD× + RSI<45 + 2×ATR + death + filter", 45, 2.0, True, True),
    # ATR sensitivity
    Spec("F5", "F2 but 1.5×ATR trail", 40, 1.5, True, True),
    Spec("F6", "F2 but 3×ATR trail", 40, 3.0, True, True),
    # Controls
    Spec("F7", "MACD× only + 2×ATR + death (no RSI)", 100, 2.0, True, True),
    Spec("F8", "MACD× + RSI<40 + death only (no ATR trail)", 40, 0.0, True, True),
    Spec("F9", "F2 + require MACD hist>0", 40, 2.0, True, True, require_macd_hist_pos=True),
]


def backtest(
    df: pd.DataFrame,
    spec: Spec,
    pair: str,
    fee_bps: float = 5.0,
    initial: float = 10_000.0,
    size: float = 0.95,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    fee = fee_bps / 10_000.0
    if spec.arm_id == "CASH":
        eq = pd.DataFrame({"equity": initial}, index=df.index)
        return pd.DataFrame(), {
            "pair": pair,
            "arm": spec.arm_id,
            "description": spec.description,
            "n_trades": 0,
            "total_return": 0.0,
            "max_dd": 0.0,
            "expectancy_pct": 0.0,
            "win_rate": 0.0,
            "avg_win_pct": float("nan"),
            "avg_loss_pct": float("nan"),
            "avg_bars": 0.0,
            "sl_rate": 0.0,
            "final_equity": initial,
            "sharpe": 0.0,
            "sum_pnl_pct": 0.0,
            "edge_vs_bh_pp": None,
            "edge_vs_cash_pp": 0.0,
            "exit_mix": {},
            "regime_n": {},
        }

    cash = float(initial)
    pos = 0.0
    entry_px = 0.0
    entry_i = 0
    entry_t = None
    peak = 0.0
    entry_reg = "unk"
    trades: List[Dict[str, Any]] = []
    curve = []

    def flatten(ts, px, i, reason):
        nonlocal cash, pos, entry_px, peak
        pnl_pct = (px / entry_px - 1.0) - 2 * fee
        trades.append(
            {
                "pair": pair,
                "arm": spec.arm_id,
                "entry_time": str(entry_t),
                "exit_time": str(ts),
                "entry_price": float(entry_px),
                "exit_price": float(px),
                "pnl_pct": float(pnl_pct),
                "bars_held": int(i - entry_i),
                "exit_reason": reason,
                "entry_regime": entry_reg,
                "entry_ret_30d": float("nan"),
            }
        )
        cash = pos * px * (1 - fee)
        pos = 0.0
        peak = 0.0

    # BH special
    if spec.arm_id == "BH":
        px0 = float(df["Close"].iloc[0])
        deploy = initial * size
        pos = (deploy * (1 - fee)) / px0
        cash = initial - deploy
        entry_px = px0
        entry_t = df.index[0]
        entry_i = 0
        peak = px0
        entry_reg = str(df["regime"].iloc[0])

    for i, (ts, row) in enumerate(df.iterrows()):
        px = float(row["Close"])
        eq = cash + pos * px
        curve.append(eq)

        if spec.arm_id == "BH":
            continue

        if pos > 0:
            peak = max(peak, px)
            atr = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
            reason = None
            if spec.atr_mult > 0:
                stop = peak - spec.atr_mult * atr
                if px <= stop:
                    reason = "sl_atr_trail"
            if reason is None and spec.macd_death and bool(row["macd_cross_dn"]):
                reason = "macd_death"
            # optional TP 2R for trailing systems
            if reason is None and spec.atr_mult > 0 and px >= entry_px + 2 * spec.atr_mult * atr:
                reason = "tp_2r"
            if reason:
                flatten(ts, px, i, reason)
                # update last trade with entry ret if we stored — skip

        if pos == 0 and spec.arm_id not in ("BH", "CASH"):
            if not bool(row["macd_cross_up"]):
                continue
            rsi = float(row["rsi"])
            if rsi >= spec.rsi_max:
                continue
            if rsi < spec.min_rsi:
                continue
            if spec.require_macd_hist_pos and float(row["macd_hist"]) <= 0:
                continue
            if spec.use_universe_filter and (bool(row["deep_bear"]) or bool(row["weak_name"])):
                continue
            deploy = eq * size
            if deploy <= 0 or px <= 0:
                continue
            pos = (deploy * (1 - fee)) / px
            cash = eq - deploy
            entry_px = px
            entry_t = ts
            entry_i = i
            peak = px
            entry_reg = str(row["regime"])
            # stash 30d on trade via closure — attach now using nonlocal list later
            trades_meta_ret = float(row["ret_30d"]) if pd.notna(row["ret_30d"]) else float("nan")
            # store on a side channel by packing into entry_reg? better: hold pending
            pending_ret30 = trades_meta_ret
            # monkey: store on object
            backtest._pending = pending_ret30  # type: ignore

    if pos > 0:
        # attach pending ret to flatten — re-open last entry fields
        px = float(df["Close"].iloc[-1])
        flatten(df.index[-1], px, len(df) - 1, "eod_flatten")

    # fix entry_ret_30d: recompute from df at entry times
    tdf = pd.DataFrame(trades)
    if len(tdf):
        for idx, tr in tdf.iterrows():
            try:
                et = pd.Timestamp(tr["entry_time"])
                if et in df.index:
                    tdf.at[idx, "entry_ret_30d"] = float(df.loc[et, "ret_30d"])
                else:
                    # nearest
                    loc = df.index.get_indexer([et], method="nearest")[0]
                    tdf.at[idx, "entry_ret_30d"] = float(df.iloc[loc]["ret_30d"])
            except Exception:
                pass

    eq_s = pd.Series(curve, index=df.index[: len(curve)] if len(curve) == len(df) else df.index[: len(curve)])
    if len(curve) != len(df) and len(curve):
        eq_s = pd.Series(curve, index=list(df.index)[: len(curve)])
    final = float(curve[-1]) if curve else initial
    # for BH ensure full curve
    if spec.arm_id == "BH":
        curve = []
        cash_bh = initial - initial * size
        px0 = float(df["Close"].iloc[0])
        pos_bh = (initial * size * (1 - fee)) / px0
        for px in df["Close"].astype(float):
            curve.append(cash_bh + pos_bh * px)
        # eod sell
        curve[-1] = pos_bh * float(df["Close"].iloc[-1]) * (1 - fee)
        final = float(curve[-1])
        tdf = pd.DataFrame(
            [
                {
                    "pair": pair,
                    "arm": "BH",
                    "entry_time": str(df.index[0]),
                    "exit_time": str(df.index[-1]),
                    "entry_price": float(df["Close"].iloc[0]),
                    "exit_price": float(df["Close"].iloc[-1]),
                    "pnl_pct": (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) - 2 * fee,
                    "bars_held": len(df) - 1,
                    "exit_reason": "eod_flatten",
                    "entry_regime": str(df["regime"].iloc[0]),
                    "entry_ret_30d": float(df["ret_30d"].iloc[0]) if pd.notna(df["ret_30d"].iloc[0]) else float("nan"),
                }
            ]
        )
        eq_s = pd.Series(curve, index=df.index)

    total_return = final / initial - 1.0
    eq = pd.Series(curve, index=df.index if len(curve) == len(df) else range(len(curve)))
    peak_eq = eq.cummax()
    max_dd = float(((eq - peak_eq) / peak_eq).min()) if len(eq) else 0.0
    rets = eq.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(365)) if len(rets) and rets.std() > 0 else 0.0

    n = len(tdf)
    if n:
        wr = float((tdf["pnl_pct"] > 0).mean())
        exp = float(tdf["pnl_pct"].mean())
        aw = float(tdf.loc[tdf["pnl_pct"] > 0, "pnl_pct"].mean()) if (tdf["pnl_pct"] > 0).any() else float("nan")
        al = float(tdf.loc[tdf["pnl_pct"] <= 0, "pnl_pct"].mean()) if (tdf["pnl_pct"] <= 0).any() else float("nan")
        bars = float(tdf["bars_held"].mean())
        slr = float(tdf["exit_reason"].astype(str).str.startswith("sl_").mean())
        emix = tdf["exit_reason"].value_counts().to_dict()
        rmix = tdf["entry_regime"].value_counts().to_dict()
        sum_pnl = float(tdf["pnl_pct"].sum())
    else:
        wr = exp = bars = slr = sum_pnl = 0.0
        aw = al = float("nan")
        emix = {}
        rmix = {}

    return tdf, {
        "pair": pair,
        "arm": spec.arm_id,
        "description": spec.description,
        "n_trades": n,
        "total_return": total_return,
        "max_dd": max_dd,
        "expectancy_pct": exp,
        "win_rate": wr,
        "avg_win_pct": aw,
        "avg_loss_pct": al,
        "avg_bars": bars,
        "sl_rate": slr,
        "final_equity": final,
        "sharpe": sharpe,
        "sum_pnl_pct": sum_pnl,
        "exit_mix": {str(k): int(v) for k, v in emix.items()},
        "regime_n": {str(k): int(v) for k, v in rmix.items()},
    }


def portfolio_equal_weight(pair_returns: Dict[str, float]) -> float:
    if not pair_returns:
        return 0.0
    return float(np.mean(list(pair_returns.values())))


def run(
    pairs: List[str],
    fee_bps: float = 5.0,
) -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TRIAL_JSON.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_metrics: List[Dict[str, Any]] = []
    all_trades: List[pd.DataFrame] = []
    pair_meta = {}

    for pair in pairs:
        df0 = load_pair(pair)
        df = add_indicators(df0)
        pair_meta[pair] = {
            "bars": len(df),
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "bh_raw": float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1),
        }
        bh_ret = None
        for spec in SPECS:
            trades, m = backtest(df, spec, pair, fee_bps=fee_bps)
            if spec.arm_id == "BH":
                bh_ret = m["total_return"]
            m["bh_pair_return"] = bh_ret
            all_metrics.append(m)
            if len(trades):
                all_trades.append(trades)
        # fill edge vs bh
        for m in all_metrics:
            if m["pair"] != pair:
                continue
            bh = next(x["total_return"] for x in all_metrics if x["pair"] == pair and x["arm"] == "BH")
            m["edge_vs_bh_pp"] = m["total_return"] - bh
            m["edge_vs_cash_pp"] = m["total_return"] - 0.0

    # aggregate by arm
    arms = [s.arm_id for s in SPECS]
    agg = []
    for arm in arms:
        rows = [m for m in all_metrics if m["arm"] == arm]
        desc = rows[0]["description"]
        rets = [m["total_return"] for m in rows]
        edges_bh = [m["edge_vs_bh_pp"] for m in rows]
        nsum = sum(m["n_trades"] for m in rows)
        # trade-weighted expectancy across pairs
        tr_rows = [m for m in rows if m["n_trades"] > 0]
        tw_exp = (
            float(
                np.average(
                    [m["expectancy_pct"] for m in tr_rows],
                    weights=[m["n_trades"] for m in tr_rows],
                )
            )
            if tr_rows
            else 0.0
        )
        # count pairs with +10% and +20% absolute return
        hit10 = sum(1 for m in rows if m["total_return"] >= 0.10)
        hit20 = sum(1 for m in rows if m["total_return"] >= 0.20)
        hit10_edge_bh = sum(1 for m in rows if m["edge_vs_bh_pp"] >= 0.10)
        hit20_edge_bh = sum(1 for m in rows if m["edge_vs_bh_pp"] >= 0.20)
        agg.append(
            {
                "arm": arm,
                "description": desc,
                "n_trades_sum": nsum,
                "mean_return": float(np.mean(rets)),
                "median_return": float(np.median(rets)),
                "mean_max_dd": float(np.mean([m["max_dd"] for m in rows])),
                "mean_edge_vs_bh_pp": float(np.mean(edges_bh)),
                "mean_edge_vs_cash_pp": float(np.mean([m["edge_vs_cash_pp"] for m in rows])),
                "tw_expectancy": tw_exp,
                "mean_win_rate": float(np.mean([m["win_rate"] for m in tr_rows])) if tr_rows else 0.0,
                "pairs_abs_ret_ge_10": hit10,
                "pairs_abs_ret_ge_20": hit20,
                "pairs_edge_bh_ge_10": hit10_edge_bh,
                "pairs_edge_bh_ge_20": hit20_edge_bh,
                "pairs": len(rows),
            }
        )

    # Best arm for "pick up 10-20% edge"
    candidates = [
        a
        for a in agg
        if a["arm"] not in ("BH", "CASH") and a["n_trades_sum"] >= 5
    ]
    # Rank by: (1) pairs with >=10% abs ret, (2) mean edge vs cash, (3) mean edge vs BH, (4) less DD
    candidates.sort(
        key=lambda a: (
            a["pairs_abs_ret_ge_10"],
            a["pairs_abs_ret_ge_20"],
            a["mean_edge_vs_cash_pp"],
            a["mean_edge_vs_bh_pp"],
            a["mean_return"],
            -abs(a["mean_max_dd"]),
        ),
        reverse=True,
    )

    best = candidates[0] if candidates else None

    # Edge definition for Brad's 10-20% target:
    # A) absolute portfolio mean return in [10%, 20%+]
    # B) OR edge vs BH mean in [10%, 20%+] with non-negative abs return
    # C) OR per-pair pickups: >=2 pairs with abs >=10% and strategy mean >=0
    def classify(a: Dict[str, Any]) -> str:
        if a["mean_return"] >= 0.20:
            return "HIT_20_ABS"
        if a["mean_return"] >= 0.10:
            return "HIT_10_ABS"
        if a["mean_edge_vs_bh_pp"] >= 0.20 and a["mean_return"] >= 0:
            return "HIT_20_EDGE_BH"
        if a["mean_edge_vs_bh_pp"] >= 0.10 and a["mean_return"] >= 0:
            return "HIT_10_EDGE_BH"
        if a["pairs_abs_ret_ge_10"] >= 2 and a["mean_return"] >= 0:
            return "PARTIAL_PICKUPS_10"
        if a["pairs_edge_bh_ge_20"] >= 2:
            return "EDGE_VS_BAGS_ONLY"  # beat crashing BH but may still lose money
        return "NO_10_20_EDGE"

    for a in agg:
        a["edge_class"] = classify(a) if a["arm"] not in ("BH", "CASH") else "BENCH"

    # Recommendation
    hitters = [a for a in candidates if a["edge_class"] in ("HIT_20_ABS", "HIT_10_ABS", "HIT_20_EDGE_BH", "HIT_10_EDGE_BH", "PARTIAL_PICKUPS_10")]
    if any(a["edge_class"] in ("HIT_20_ABS", "HIT_10_ABS", "HIT_20_EDGE_BH", "HIT_10_EDGE_BH") for a in hitters):
        rec = "dig_further_promote_candidate"
        top = next(a for a in candidates if a["edge_class"] in ("HIT_20_ABS", "HIT_10_ABS", "HIT_20_EDGE_BH", "HIT_10_EDGE_BH"))
    elif hitters:
        rec = "dig_further"
        top = hitters[0]
    elif best and best["mean_edge_vs_bh_pp"] >= 0.10:
        rec = "pattern_less_loss_only"
        top = best
    else:
        rec = "no_edge_drop"
        top = best

    # Write trades
    trades_path = None
    if all_trades:
        trades_path = REPORT_DIR / f"MACD_RSI_ATR_DIG_TRADES_{stamp}.csv"
        pd.concat(all_trades, ignore_index=True).to_csv(trades_path, index=False)

    md = REPORT_DIR / f"MACD_RSI_ATR_DIG_{stamp}.md"
    lines = [
        f"# MACD× + RSI + ATR trail focused dig — {stamp}",
        "",
        "## Plain English (read first)",
        "",
        f"**Target:** find a solid 10–20% trading edge (absolute or clean vs BH with non-negative return).",
        f"**Universe:** {', '.join(p.upper() for p in pairs)} · real project daily OHLCV",
        f"**Window:** {pair_meta[pairs[0]]['start']} → {pair_meta[pairs[0]]['end']} ({pair_meta[pairs[0]]['bars']} bars)",
        f"**Recommendation:** `{rec}`",
        "",
    ]
    if top:
        lines += [
            f"### Best candidate: **{top['arm']}** — {top['description']}",
            f"- Mean return: **{top['mean_return']:.1%}** | mean maxDD: **{top['mean_max_dd']:.1%}**",
            f"- Mean edge vs BH: **{top['mean_edge_vs_bh_pp']:+.1%}** | vs cash: **{top['mean_edge_vs_cash_pp']:+.1%}**",
            f"- N trades: **{top['n_trades_sum']}** | TW expectancy/trade: **{top['tw_expectancy']:.2%}** | WR: **{top['mean_win_rate']:.0%}**",
            f"- Pairs with abs ≥10% / ≥20%: **{top['pairs_abs_ret_ge_10']}** / **{top['pairs_abs_ret_ge_20']}** of {top['pairs']}",
            f"- Edge class: `{top['edge_class']}`",
            "",
        ]

    lines += [
        "### Edge definition used",
        "- **HIT_10/20_ABS:** mean portfolio return ≥10% / ≥20%",
        "- **HIT_10/20_EDGE_BH:** mean edge vs BH ≥10%/20% **and** mean return ≥0",
        "- **PARTIAL_PICKUPS_10:** ≥2 pairs with abs return ≥10% and mean return ≥0",
        "- **EDGE_VS_BAGS_ONLY:** beats BH by ≥20pp on ≥2 pairs but may still lose money — **not** a 10–20% pickup edge",
        "",
        "## Buy-hold by pair",
        "",
        "| Pair | BH ret |",
        "|------|--------|",
    ]
    for p in pairs:
        bh = next(m["total_return"] for m in all_metrics if m["pair"] == p and m["arm"] == "BH")
        lines.append(f"| {p.upper()} | {bh:.1%} |")

    lines += [
        "",
        "## Arm leaderboard",
        "",
        "| Arm | N | mean Ret | mean DD | ΔBH | Δcash | TW exp | ≥10% pairs | class |",
        "|-----|---|----------|---------|-----|-------|--------|------------|-------|",
    ]
    for a in sorted(agg, key=lambda x: (x["mean_return"], x["mean_edge_vs_bh_pp"]), reverse=True):
        lines.append(
            f"| {a['arm']} | {a['n_trades_sum']} | {a['mean_return']:.1%} | {a['mean_max_dd']:.1%} | "
            f"{a['mean_edge_vs_bh_pp']:+.1%} | {a['mean_edge_vs_cash_pp']:+.1%} | {a['tw_expectancy']:.2%} | "
            f"{a['pairs_abs_ret_ge_10']}/{a['pairs']} | {a['edge_class']} |"
        )

    lines += ["", "## Per-pair detail (core arms)", ""]
    show = ["BH", "F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F9"]
    lines.append("| Pair | Arm | N | Ret | DD | Exp% | WR | ΔBH |")
    lines.append("|------|-----|---|-----|----|------|----|-----|")
    for p in pairs:
        for arm in show:
            m = next(x for x in all_metrics if x["pair"] == p and x["arm"] == arm)
            lines.append(
                f"| {p.upper()} | {arm} | {m['n_trades']} | {m['total_return']:.1%} | {m['max_dd']:.1%} | "
                f"{m['expectancy_pct']:.2%} | {m['win_rate']:.0%} | {m['edge_vs_bh_pp']:+.1%} |"
            )

    # Pattern section
    f2_rows = [m for m in all_metrics if m["arm"] == "F2"]
    f1_rows = [m for m in all_metrics if m["arm"] == "F1"]
    f7_rows = [m for m in all_metrics if m["arm"] == "F7"]
    lines += [
        "",
        "## Pattern assessment (standard optimization?)",
        "",
        "### Recipe under test",
        "1. **Entry:** MACD line crosses above signal (bar close), RSI(14) < threshold (base 40)",
        "2. **Exit:** trail stop at peak − k×ATR(14); optional MACD cross-down emergency; optional +2R TP",
        "3. **Filters:** no Stoch/BB; optional skip if 30d ret < −40% or 90d weak/ATH drawdown",
        "4. **Sizing:** 95% equity, 5 bps/side, long-only",
        "",
        "### What the tape says",
    ]
    # concrete bullets from F2
    for m in f2_rows:
        lines.append(
            f"- **{m['pair'].upper()} F2:** N={m['n_trades']} ret={m['total_return']:.1%} "
            f"exp={m['expectancy_pct']:.1%} ΔBH={m['edge_vs_bh_pp']:+.1%} exits={m['exit_mix']}"
        )

    lines += [
        "",
        "### Standard-opt verdict",
    ]
    if rec in ("dig_further_promote_candidate", "dig_further"):
        lines.append(
            f"- There is a **repeatable structure** ({top['arm'] if top else '?'}) worth treating as a "
            f"**candidate optimization pattern**, but sample is still thin — not live-default yet."
        )
    elif rec == "pattern_less_loss_only":
        lines.append(
            "- Pattern is real for **less-loss vs holding weak alts**, but it does **not** deliver a clean "
            "10–20% absolute edge on this window. Do not market as a +10–20% pickup system yet."
        )
    else:
        lines.append(
            "- No solid 10–20% edge pattern on this tape. Keep as research scrap; do not standardize."
        )

    lines += [
        "",
        f"**final_recommendation:** `{rec}`",
        "",
        f"Trades: `{trades_path}`" if trades_path else "",
        "",
    ]
    md.write_text("\n".join(lines) + "\n")

    payload = {
        "id": "TEST-COMBINED-MACD-RSI-ATR-DIG",
        "parent": "TEST-COMBINED-INDICATOR-ABLATION-2026-08",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs,
        "pair_meta": pair_meta,
        "fee_bps": fee_bps,
        "recipe": {
            "entry": "MACD bullish cross + RSI < K",
            "exit": "k×ATR trail from peak + optional MACD-death + optional 2R TP",
            "filters": "no Stoch/BB; optional deep_bear/weak_name skip",
        },
        "aggregate": agg,
        "per_pair": all_metrics,
        "best": top,
        "final_recommendation": rec,
        "report_md": str(md.relative_to(ROOT)),
        "trades_csv": str(trades_path.relative_to(ROOT)) if trades_path else None,
        "edge_target": "10-20% absolute or clean vs BH with non-negative return",
    }
    TRIAL_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    (REPORT_DIR / f"MACD_RSI_ATR_DIG_{stamp}.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
    print(md.read_text())
    print(f"Wrote {md}")
    print(f"Wrote {TRIAL_JSON}")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(DEFAULT_CORE))
    ap.add_argument("--fee-bps", type=float, default=5.0)
    ap.add_argument("--with-avax", action="store_true")
    args = ap.parse_args()
    pairs = [x.strip().lower() for x in args.pairs.split(",") if x.strip()]
    if args.with_avax and "avax" not in pairs:
        pairs.append("avax")
    run(pairs, fee_bps=args.fee_bps)


if __name__ == "__main__":
    main()
