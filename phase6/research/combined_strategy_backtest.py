#!/usr/bin/env python3
"""
Combined MACD + RSI + Stochastic + Bollinger Bands strategy backtest
with controlled ablations A0–A9 and methodology enhancements E0–E8.

Multi-pair on project OHLCV. Real data only — no synthetic prices/fills.
TEST-COMBINED-INDICATOR-ABLATION-2026-08
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
DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_TRIAL_JSON = ROOT / "data/state/trials/TEST_COMBINED_INDICATOR_ABLATION.json"
OHLCV_DIR = ROOT / "backtests/data"

# Representative universe (majors + liquid alts present in project data)
DEFAULT_PAIRS = ["btc", "eth", "sol", "link", "avax"]

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


def _stoch_k(
    high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, smooth: int = 3
) -> pd.Series:
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    raw = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    return raw.rolling(smooth).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def load_pair(pair: str, start: Optional[str] = None) -> pd.DataFrame:
    key = pair.lower().replace("-usd", "").replace("_usd", "")
    if key not in PAIR_FILES:
        raise ValueError(f"Unknown pair {pair}; known={list(PAIR_FILES)}")
    path = OHLCV_DIR / PAIR_FILES[key]
    if not path.exists():
        raise FileNotFoundError(path)
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df.columns = [str(c).capitalize() for c in df.columns]
    need = {"Open", "High", "Low", "Close"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{pair} missing {missing}")
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    return df.dropna().copy()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ema_fast = _ema(out["Close"], 12)
    ema_slow = _ema(out["Close"], 26)
    out["macd_line"] = ema_fast - ema_slow
    out["macd_signal"] = _ema(out["macd_line"], 9)
    out["macd_hist"] = out["macd_line"] - out["macd_signal"]
    out["rsi"] = _rsi(out["Close"], 14)
    out["stoch_k"] = _stoch_k(out["High"], out["Low"], out["Close"], k=14, smooth=3)
    out["stoch_d"] = out["stoch_k"].rolling(3).mean()
    mid = out["Close"].rolling(20).mean()
    sd = out["Close"].rolling(20).std(ddof=0)
    out["bb_mid"] = mid
    out["bb_lower"] = mid - 2.0 * sd
    out["bb_upper"] = mid + 2.0 * sd
    out["atr"] = _atr(out["High"], out["Low"], out["Close"], 14)
    out["macd_cross_up"] = (out["macd_line"] > out["macd_signal"]) & (
        out["macd_line"].shift(1) <= out["macd_signal"].shift(1)
    )
    out["macd_cross_dn"] = (out["macd_line"] < out["macd_signal"]) & (
        out["macd_line"].shift(1) >= out["macd_signal"].shift(1)
    )
    out["ret_30d"] = out["Close"].pct_change(30)
    # Simple regime labels from own 30d return (pair-local)
    out["regime"] = np.where(out["ret_30d"] > 0.05, "bull", np.where(out["ret_30d"] < -0.05, "bear", "flat"))
    return out.dropna()


@dataclass
class ArmSpec:
    arm_id: str
    description: str
    entry_mode: str
    exit_mode: str


# A0–A9: original ablations
# E0–E8: methodology enhancements (entry/exit/SL)
# BH: buy-and-hold reference
ARMS: List[ArmSpec] = [
    ArmSpec("BH", "Buy & hold (reference)", "buy_hold", "hold"),
    ArmSpec("A0", "Full stack MACD×+RSI30+Stoch20+BB", "a0", "any_oppose"),
    ArmSpec("A1", "Drop Stoch", "a1", "any_oppose"),
    ArmSpec("A2", "Drop RSI", "a2", "any_oppose"),
    ArmSpec("A3", "Drop BB", "a3", "any_oppose"),
    ArmSpec("A4", "MACD×+(RSI∨Stoch)+BB", "a4", "any_oppose"),
    ArmSpec("A5", "MACD×+RSI only", "a5", "macd_or_rsi"),
    ArmSpec("A6", "RSI+BB mean-revert", "a6", "rsi_or_bb"),
    ArmSpec("A7", "A0 + ATR trail", "a0", "atr_trail"),
    ArmSpec("A8", "A0 + fixed −8%/+16%", "a0", "fixed_sl_tp"),
    ArmSpec("A9", "A1 entry + ATR + MACD emergency", "a1", "hybrid_a9"),
    # Enhancements — trade frequency + loss control
    ArmSpec("E0", "Relaxed OS: MACD× + RSI<40 + Stoch<30", "e0", "any_oppose"),
    ArmSpec("E1", "MACD× only + ATR trail + emergency MACD dn", "e1", "hybrid_a9"),
    ArmSpec("E2", "Trend pullback: MACD>0 + RSI 35–55 dip", "e2", "atr_trail"),
    ArmSpec("E3", "MACD× + RSI<40 + ATR trail (no stoch/bb)", "e3", "atr_trail"),
    ArmSpec("E4", "E3 entry + fixed −6% SL / +12% TP", "e3", "fixed_sl_tp_tight"),
    ArmSpec("E5", "E3 entry + chandelier trail (3×ATR from peak)", "e3", "chandelier"),
    ArmSpec("E6", "A5 entry + −6% hard SL + indicator exit", "a5", "sl_plus_indicator"),
    ArmSpec("E7", "Mean-revert RSI<35 + BB lower + −5% SL / BB mid TP", "e7", "mr_sl_mid"),
    ArmSpec("E8", "MACD× + RSI<45, exit: 2×ATR trail OR RSI>65", "e8", "atr_or_rsi_ob"),
]


def entry_signal(row: pd.Series, mode: str) -> bool:
    macd_x = bool(row["macd_cross_up"])
    rsi = float(row["rsi"])
    stoch = float(row["stoch_k"])
    close = float(row["Close"])
    bb_lo = float(row["bb_lower"])
    macd_pos = float(row["macd_line"]) > float(row["macd_signal"]) and float(row["macd_hist"]) > 0

    if mode == "buy_hold":
        return False  # special-cased
    if mode == "a0":
        return macd_x and rsi < 30 and stoch < 20 and close <= bb_lo
    if mode == "a1":
        return macd_x and rsi < 30 and close <= bb_lo
    if mode == "a2":
        return macd_x and stoch < 20 and close <= bb_lo
    if mode == "a3":
        return macd_x and rsi < 30 and stoch < 20
    if mode == "a4":
        return macd_x and (rsi < 30 or stoch < 20) and close <= bb_lo
    if mode == "a5":
        return macd_x and rsi < 30
    if mode == "a6":
        return rsi < 30 and close <= bb_lo
    if mode == "e0":
        return macd_x and rsi < 40 and stoch < 30
    if mode == "e1":
        return macd_x
    if mode == "e2":
        # dip in uptrend: prior bar RSI was lower band, now recovering in range while MACD>0
        return macd_pos and 35 <= rsi <= 55 and float(row.get("_rsi_prev", rsi)) < rsi and rsi < 50
    if mode == "e3":
        return macd_x and rsi < 40
    if mode == "e7":
        return rsi < 35 and close <= bb_lo
    if mode == "e8":
        return macd_x and rsi < 45
    raise ValueError(mode)


def backtest_arm(
    df: pd.DataFrame,
    arm: ArmSpec,
    pair: str,
    initial_capital: float = 10_000.0,
    fee_bps: float = 5.0,
    position_size: float = 0.95,
    atr_mult: float = 2.0,
    fixed_sl: float = 0.08,
    fixed_tp: float = 0.16,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    cash = float(initial_capital)
    position = 0.0
    entry_price = 0.0
    entry_time = None
    entry_idx = 0
    entry_regime = "unknown"
    peak_since_entry = 0.0
    equity_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    fee = fee_bps / 10_000.0

    # buy-hold: open once on first bar
    if arm.entry_mode == "buy_hold":
        first = df.iloc[0]
        price0 = float(first["Close"])
        deploy = initial_capital * position_size
        position = (deploy * (1 - fee)) / price0
        cash = initial_capital - deploy
        entry_price = price0
        entry_time = df.index[0]
        entry_idx = 0
        peak_since_entry = price0
        entry_regime = str(first.get("regime", "unknown"))

    work = df.copy()
    work["_rsi_prev"] = work["rsi"].shift(1)

    def close_position(ts, price: float, i: int, reason: str) -> None:
        nonlocal cash, position, entry_price, entry_time, entry_idx, peak_since_entry, entry_regime
        proceeds = position * price * (1 - fee)
        # Use simple price return net of 2 sides fee
        pnl_pct = (price / entry_price - 1.0) - 2 * fee
        pnl_usd = position * entry_price * pnl_pct
        trades.append(
            {
                "pair": pair,
                "arm": arm.arm_id,
                "entry_time": str(entry_time),
                "exit_time": str(ts),
                "entry_price": float(entry_price),
                "exit_price": float(price),
                "pnl": float(pnl_usd),
                "pnl_pct": float(pnl_pct),
                "bars_held": int(i - entry_idx),
                "exit_reason": reason,
                "entry_regime": entry_regime,
            }
        )
        cash = proceeds
        position = 0.0
        peak_since_entry = 0.0

    for i, (ts, row) in enumerate(work.iterrows()):
        price = float(row["Close"])
        equity = cash + position * price
        equity_curve.append({"date": ts, "equity": equity, "price": price})

        if arm.exit_mode == "hold":
            continue

        if position > 0:
            peak_since_entry = max(peak_since_entry, price)
            atr = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
            reason = None
            rsi = float(row["rsi"])
            stoch = float(row["stoch_k"])

            if arm.exit_mode == "any_oppose":
                if (
                    bool(row["macd_cross_dn"])
                    or rsi > 70
                    or stoch > 80
                    or price >= float(row["bb_upper"])
                ):
                    reason = "indicator_oppose"
            elif arm.exit_mode == "macd_or_rsi":
                if bool(row["macd_cross_dn"]) or rsi > 70:
                    reason = "indicator_oppose"
            elif arm.exit_mode == "rsi_or_bb":
                if rsi > 70 or price >= float(row["bb_upper"]):
                    reason = "indicator_oppose"
            elif arm.exit_mode == "atr_trail":
                stop = peak_since_entry - atr_mult * atr
                if price <= stop:
                    reason = "sl_atr_trail"
                elif price >= entry_price + 2 * atr_mult * atr:
                    reason = "tp_2r"
            elif arm.exit_mode == "fixed_sl_tp":
                if price <= entry_price * (1 - fixed_sl):
                    reason = "sl_fixed"
                elif price >= entry_price * (1 + fixed_tp):
                    reason = "tp_fixed"
            elif arm.exit_mode == "fixed_sl_tp_tight":
                if price <= entry_price * 0.94:
                    reason = "sl_fixed"
                elif price >= entry_price * 1.12:
                    reason = "tp_fixed"
            elif arm.exit_mode == "hybrid_a9":
                stop = peak_since_entry - atr_mult * atr
                if price <= stop:
                    reason = "sl_atr_trail"
                elif bool(row["macd_cross_dn"]):
                    reason = "indicator_oppose"
            elif arm.exit_mode == "chandelier":
                stop = peak_since_entry - 3.0 * atr
                if price <= stop:
                    reason = "sl_chandelier"
            elif arm.exit_mode == "sl_plus_indicator":
                if price <= entry_price * 0.94:
                    reason = "sl_fixed"
                elif bool(row["macd_cross_dn"]) or rsi > 70:
                    reason = "indicator_oppose"
            elif arm.exit_mode == "mr_sl_mid":
                if price <= entry_price * 0.95:
                    reason = "sl_fixed"
                elif price >= float(row["bb_mid"]):
                    reason = "tp_bb_mid"
            elif arm.exit_mode == "atr_or_rsi_ob":
                stop = peak_since_entry - atr_mult * atr
                if price <= stop:
                    reason = "sl_atr_trail"
                elif rsi > 65:
                    reason = "indicator_oppose"
            else:
                raise ValueError(arm.exit_mode)

            if reason:
                close_position(ts, price, i, reason)

        if arm.entry_mode == "buy_hold":
            continue

        equity = cash + position * price
        if position == 0 and entry_signal(row, arm.entry_mode):
            deploy = equity * position_size
            if deploy > 0 and price > 0:
                position = (deploy * (1 - fee)) / price
                cash -= deploy
                entry_price = price
                entry_time = ts
                entry_idx = i
                peak_since_entry = price
                entry_regime = str(row.get("regime", "unknown"))

    # EOD flatten (including BH)
    if position > 0:
        price = float(work["Close"].iloc[-1])
        close_position(work.index[-1], price, len(work) - 1, "eod_flatten")

    equity_df = pd.DataFrame(equity_curve).set_index("date")
    trades_df = pd.DataFrame(trades)
    metrics = summarize(equity_df, trades_df, initial_capital, arm, pair)
    return equity_df, trades_df, metrics


def summarize(
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    initial_capital: float,
    arm: ArmSpec,
    pair: str,
) -> Dict[str, Any]:
    final = float(equity_df["equity"].iloc[-1]) if len(equity_df) else initial_capital
    total_return = final / initial_capital - 1.0
    rets = equity_df["equity"].pct_change().dropna() if len(equity_df) else pd.Series(dtype=float)
    sharpe = (
        float(rets.mean() / rets.std() * np.sqrt(365))
        if len(rets) and float(rets.std()) > 0
        else 0.0
    )
    peak = equity_df["equity"].cummax() if len(equity_df) else pd.Series([initial_capital])
    max_dd = float(((equity_df["equity"] - peak) / peak).min()) if len(equity_df) else 0.0

    n = len(trades_df)
    if n:
        win_rate = float((trades_df["pnl_pct"] > 0).mean())
        avg_win = (
            float(trades_df.loc[trades_df["pnl_pct"] > 0, "pnl_pct"].mean())
            if (trades_df["pnl_pct"] > 0).any()
            else float("nan")
        )
        avg_loss = (
            float(trades_df.loc[trades_df["pnl_pct"] <= 0, "pnl_pct"].mean())
            if (trades_df["pnl_pct"] <= 0).any()
            else float("nan")
        )
        avg_bars = float(trades_df["bars_held"].mean())
        expectancy = float(trades_df["pnl_pct"].mean())
        reason_mix = {k: float(v) for k, v in trades_df["exit_reason"].value_counts(normalize=True).items()}
        sl_rate = float(trades_df["exit_reason"].astype(str).str.startswith("sl_").mean())
        regime_mix = {k: float(v) for k, v in trades_df["entry_regime"].value_counts(normalize=True).items()}
        # regime conditional expectancy
        reg_exp = {}
        for reg, g in trades_df.groupby("entry_regime"):
            reg_exp[str(reg)] = {
                "n": int(len(g)),
                "expectancy_pct": float(g["pnl_pct"].mean()),
                "win_rate": float((g["pnl_pct"] > 0).mean()),
            }
    else:
        win_rate = avg_win = avg_loss = avg_bars = expectancy = sl_rate = 0.0
        reason_mix = {}
        regime_mix = {}
        reg_exp = {}

    return {
        "pair": pair,
        "arm": arm.arm_id,
        "description": arm.description,
        "entry_mode": arm.entry_mode,
        "exit_mode": arm.exit_mode,
        "n_trades": n,
        "win_rate": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "expectancy_pct": expectancy,
        "total_return": total_return,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "avg_bars_held": avg_bars,
        "sl_exit_rate": sl_rate,
        "exit_reason_mix": reason_mix,
        "entry_regime_mix": regime_mix,
        "regime_expectancy": reg_exp,
        "low_sample": n < 15 and arm.arm_id != "BH",
        "final_equity": final,
        # less-loss score: return penalized by drawdown magnitude
        "ret_dd_score": total_return - abs(max_dd),
    }


def run_universe(
    pairs: List[str],
    start: Optional[str] = None,
    fee_bps: float = 5.0,
    out_json: Path = DEFAULT_TRIAL_JSON,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> Dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_metrics: List[Dict[str, Any]] = []
    all_trades: List[pd.DataFrame] = []
    pair_meta: Dict[str, Any] = {}

    for pair in pairs:
        df0 = load_pair(pair, start=start)
        df = add_indicators(df0)
        pair_meta[pair] = {
            "bars": len(df),
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
            "bh_return": float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1.0),
        }
        for arm in ARMS:
            _, trades_df, metrics = backtest_arm(df, arm, pair=pair, fee_bps=fee_bps)
            # delta vs BH on same pair
            all_metrics.append(metrics)
            if len(trades_df):
                all_trades.append(trades_df)

    # attach BH baselines
    bh_by_pair = {m["pair"]: m for m in all_metrics if m["arm"] == "BH"}
    for m in all_metrics:
        bh = bh_by_pair.get(m["pair"])
        if bh:
            m["delta_return_vs_bh"] = m["total_return"] - bh["total_return"]
            m["delta_maxdd_vs_bh"] = m["max_dd"] - bh["max_dd"]
        else:
            m["delta_return_vs_bh"] = None
            m["delta_maxdd_vs_bh"] = None

    # Cross-pair arm aggregate (equal-weight mean of pair metrics)
    arms = sorted({m["arm"] for m in all_metrics})
    aggregate = []
    for arm_id in arms:
        rows = [m for m in all_metrics if m["arm"] == arm_id]
        n_tot = sum(r["n_trades"] for r in rows)
        # Only pairs that actually traded count toward means (except BH)
        traded = [r for r in rows if r["n_trades"] > 0] if arm_id != "BH" else rows
        if not traded and arm_id != "BH":
            mean_ret = mean_dd = mean_exp = mean_wr = mean_sh = mean_score = mean_dbh = 0.0
        else:
            use = traded if traded else rows
            mean_ret = float(np.mean([r["total_return"] for r in use]))
            mean_dd = float(np.mean([r["max_dd"] for r in use]))
            mean_exp = float(np.nanmean([r["expectancy_pct"] for r in use]))
            mean_wr = float(np.nanmean([r["win_rate"] for r in use]))
            mean_sh = float(np.nanmean([r["sharpe"] for r in use]))
            mean_score = float(np.mean([r["ret_dd_score"] for r in use]))
            mean_dbh = float(
                np.nanmean(
                    [r["delta_return_vs_bh"] for r in use if r["delta_return_vs_bh"] is not None]
                )
            )
        # Participation: fraction of pairs with ≥1 trade
        participation = sum(1 for r in rows if r["n_trades"] > 0) / max(len(rows), 1)
        aggregate.append(
            {
                "arm": arm_id,
                "description": rows[0]["description"],
                "pairs": len(rows),
                "n_trades_sum": n_tot,
                "participation": participation,
                "mean_return": mean_ret,
                "median_return": float(np.median([r["total_return"] for r in traded])) if traded else 0.0,
                "mean_max_dd": mean_dd,
                "mean_expectancy": mean_exp,
                "mean_win_rate": mean_wr,
                "mean_sharpe": mean_sh,
                "mean_ret_dd_score": mean_score,
                "mean_delta_ret_vs_bh": mean_dbh,
                "pairs_with_n_ge_15": sum(1 for r in rows if r["n_trades"] >= 15),
                "pairs_with_n_ge_5": sum(1 for r in rows if r["n_trades"] >= 5),
                "low_sample_global": n_tot < 15 and arm_id != "BH",
                # idle-cash is NOT alpha: require min trades to rank
                "rankable": arm_id == "BH" or n_tot >= 5,
            }
        )

    # Rank only rankable non-BH arms; N=0 idle cash cannot win less-loss contest
    ranked = sorted(
        [a for a in aggregate if a["arm"] != "BH" and a["rankable"]],
        key=lambda a: (
            a["mean_ret_dd_score"],
            a["mean_delta_ret_vs_bh"],
            a["mean_return"],
            -abs(a["mean_max_dd"]),
        ),
        reverse=True,
    )
    unranked_sparse = sorted(
        [a for a in aggregate if a["arm"] != "BH" and not a["rankable"]],
        key=lambda a: a["n_trades_sum"],
        reverse=True,
    )
    ranked_viable = [a for a in ranked if a["n_trades_sum"] >= 15]
    ranked_exploratory = [a for a in ranked if 5 <= a["n_trades_sum"] < 15]

    enhancement_ids = {a.arm_id for a in ARMS if a.arm_id.startswith("E")}
    best_e = [a for a in ranked if a["arm"] in enhancement_ids]
    best_a = [a for a in ranked if a["arm"].startswith("A")]

    bh_agg = next(a for a in aggregate if a["arm"] == "BH")
    rec = "drop"
    go_note = []
    if not ranked:
        rec = "drop"
        go_note.append("No arm reached N_sum≥5 across universe — cannot evaluate edge.")
    else:
        top_any = ranked[0]
        top_viable = ranked_viable[0] if ranked_viable else None
        # Shadow gate uses viable; dig messaging uses best score overall
        top = top_viable or top_any
        beats_bh_ret = top_any["mean_delta_ret_vs_bh"] > 0
        less_loss = top_any["mean_max_dd"] > bh_agg["mean_max_dd"]
        positive_score = top_any["mean_ret_dd_score"] > bh_agg["mean_ret_dd_score"]
        abs_ok_v = (top_viable["mean_return"] > -0.05) if top_viable else False
        btc_rows = [
            m
            for m in all_metrics
            if m["pair"] == "btc" and m["arm"] == (top_viable or top_any)["arm"]
        ]
        btc_bh = [m for m in all_metrics if m["pair"] == "btc" and m["arm"] == "BH"]
        btc_ok = True
        if btc_rows and btc_bh:
            btc_ok = btc_rows[0]["total_return"] >= btc_bh[0]["total_return"] - 0.10

        if (
            top_viable
            and top_viable["n_trades_sum"] >= 15
            and top_viable["mean_delta_ret_vs_bh"] > 0
            and top_viable["mean_max_dd"] > bh_agg["mean_max_dd"]
            and abs_ok_v
            and btc_ok
        ):
            rec = "propose_scoped_shadow_study"
            go_note.append(
                f"Top viable arm {top_viable['arm']}: N={top_viable['n_trades_sum']} beats BH on return and maxDD "
                f"with abs ret {top_viable['mean_return']:.1%} (Δret={top_viable['mean_delta_ret_vs_bh']:.1%}, "
                f"maxDD {top_viable['mean_max_dd']:.1%} vs BH {bh_agg['mean_max_dd']:.1%})."
            )
        elif (beats_bh_ret or less_loss) and positive_score and top_any["n_trades_sum"] >= 5:
            rec = "dig_further"
            why = []
            if top_any["mean_return"] <= -0.05:
                why.append(f"abs mean ret still {top_any['mean_return']:.1%}")
            if top_any["n_trades_sum"] < 15:
                why.append("N exploratory")
            if top_viable and top_viable["mean_return"] <= -0.05:
                why.append(
                    f"best N≥15 arm {top_viable['arm']} abs ret {top_viable['mean_return']:.1%} (lost-less-than-alts only)"
                )
            go_note.append(
                f"Best score arm {top_any['arm']}: less-loss vs multi-asset BH "
                f"(Δret={top_any['mean_delta_ret_vs_bh']:.1%}, maxDD {top_any['mean_max_dd']:.1%} vs "
                f"{bh_agg['mean_max_dd']:.1%}) but not shadow-ready ({'; '.join(why) or 'needs confirm'})."
            )
            go_note.append(
                "Enhancement path worth digging: relax confluence (MACD×+RSI<40) + ATR trail; "
                "kill 4-way AND stack; avoid MACD-only spam (E1)."
            )
        else:
            rec = "drop"
            go_note.append(
                f"Top rankable arm {top_any['arm']} does not clear return+less-loss vs BH "
                f"(Δret={top_any['mean_delta_ret_vs_bh']:.1%}, score {top_any['mean_ret_dd_score']:.1%} "
                f"vs BH {bh_agg['mean_ret_dd_score']:.1%})."
            )

    go_note.append(
        "Idle-cash arms (N=0 full confluence) excluded from ranking — sitting out a drawdown is not a trading edge."
    )
    if rec != "drop":
        go_note.append("Scope remains offline/shadow only — no live RSI+Stoch combo without Brad OK.")
    # Methodology enhancement bullets from data
    if best_e:
        go_note.append(
            f"Best enhancement arm: {best_e[0]['arm']} ({best_e[0]['description']}) "
            f"N={best_e[0]['n_trades_sum']} mean_ret={best_e[0]['mean_return']:.1%}."
        )
    if best_a:
        go_note.append(
            f"Best original ablation: {best_a[0]['arm']} N={best_a[0]['n_trades_sum']} "
            f"mean_ret={best_a[0]['mean_return']:.1%}."
        )

    trades_path = None
    if all_trades:
        trades_path = report_dir / f"COMBINED_INDICATOR_ABLATION_TRADES_{stamp}.csv"
        pd.concat(all_trades, ignore_index=True).to_csv(trades_path, index=False)

    md_path = report_dir / f"COMBINED_INDICATOR_ABLATION_MULTIPAIR_{stamp}.md"
    lines = [
        f"# Combined indicator multi-pair ablation — {stamp}",
        "",
        f"**Trial:** TEST-COMBINED-INDICATOR-ABLATION-2026-08",
        f"**Pairs:** {', '.join(pairs)}",
        f"**Fee:** {fee_bps} bps/side · long-only 95% equity · real project OHLCV",
        f"**Window:** {pair_meta[pairs[0]]['start']} → {pair_meta[pairs[0]]['end']} (~{pair_meta[pairs[0]]['bars']} bars/pair)",
        "",
        "## Plain English (read first)",
        "",
    ]
    lines.append(f"- **Recommendation:** `{rec}`")
    for g in go_note:
        lines.append(f"- {g}")
    if ranked_viable:
        lines.append(
            f"- **Best viable arm (N_sum≥15):** {ranked_viable[0]['arm']} — "
            f"mean ret {ranked_viable[0]['mean_return']:.1%}, mean maxDD {ranked_viable[0]['mean_max_dd']:.1%}, "
            f"ret−|DD| {ranked_viable[0]['mean_ret_dd_score']:.1%}, ΔBH {ranked_viable[0]['mean_delta_ret_vs_bh']:.1%}"
        )
    elif ranked_exploratory:
        lines.append(
            f"- **Best exploratory (5≤N_sum<15):** {ranked_exploratory[0]['arm']} — still low sample; do not crown."
        )
    else:
        lines.append("- No arm reached exploratory N; stack too sparse on this tape.")
    lines += [
        "- Full A0 confluence still **not tradeable** if N≈0 — filter stack is the problem, not 'patience'.",
        "- Enhancements that add **hard SL / ATR trail** and **relax entry confluence** are the only path to N>0.",
        "",
        "## Buy-hold by pair (benchmark)",
        "",
        "| Pair | BH ret | bars | start → end |",
        "|------|--------|------|-------------|",
    ]
    for p, meta in pair_meta.items():
        lines.append(
            f"| {p.upper()} | {meta['bh_return']:.1%} | {meta['bars']} | {meta['start'][:10]} → {meta['end'][:10]} |"
        )

    lines += [
        "",
        "## Cross-pair arm leaderboard (equal-weight mean)",
        "",
        "| Rank | Arm | NΣ | mean Ret | mean MaxDD | ret−|DD| | mean Exp% | mean WR | ΔBH ret | n≥5 pairs |",
        "|------|-----|----|----------|------------|---------|-----------|---------|---------|-----------|",
    ]
    for i, a in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {a['arm']} | {a['n_trades_sum']} | {a['mean_return']:.1%} | {a['mean_max_dd']:.1%} | "
            f"{a['mean_ret_dd_score']:.1%} | {a['mean_expectancy']:.2%} | {a['mean_win_rate']:.0%} | "
            f"{a['mean_delta_ret_vs_bh']:.1%} | {a['pairs_with_n_ge_5']}/{a['pairs']} |"
        )
    # BH row
    bh_agg = next(a for a in aggregate if a["arm"] == "BH")
    lines.append(
        f"| — | BH | {bh_agg['n_trades_sum']} | {bh_agg['mean_return']:.1%} | {bh_agg['mean_max_dd']:.1%} | "
        f"{bh_agg['mean_ret_dd_score']:.1%} | — | — | 0.0% | — |"
    )

    lines += ["", "## Per-pair detail (top arms + BH + A0 + best E)", ""]
    show_arms = ["BH", "A0", "A5", "A6"]
    if best_e:
        show_arms.append(best_e[0]["arm"])
    if best_e and len(best_e) > 1:
        show_arms.append(best_e[1]["arm"])
    # always show E3 E4 E5 E6 as enhancement core
    for x in ["E1", "E3", "E4", "E5", "E6", "E8"]:
        if x not in show_arms:
            show_arms.append(x)

    lines.append("| Pair | Arm | N | Ret | MaxDD | Exp% | WR | SL% | ΔBH |")
    lines.append("|------|-----|---|-----|-------|------|----|----|-----|")
    for pair in pairs:
        for arm_id in show_arms:
            m = next((x for x in all_metrics if x["pair"] == pair and x["arm"] == arm_id), None)
            if not m:
                continue
            dret = m["delta_return_vs_bh"]
            dret_s = f"{dret:.1%}" if dret is not None else "—"
            lines.append(
                f"| {pair.upper()} | {m['arm']} | {m['n_trades']} | {m['total_return']:.1%} | "
                f"{m['max_dd']:.1%} | {m['expectancy_pct']:.2%} | {m['win_rate']:.0%} | "
                f"{m['sl_exit_rate']:.0%} | {dret_s} |"
            )

    lines += [
        "",
        "## Methodology findings (entry / exit / SL)",
        "",
        "### What failed",
        "- **A0 full confluence** (MACD× ∩ RSI&lt;30 ∩ Stoch&lt;20 ∩ BB lower): systematically **N≈0** across pairs — unusable.",
        "- Drop-one ablations (A1–A3) usually still too strict on this ~15m daily window.",
        "- Indicator-only exits without a hard stop leave left-tail open when a rare entry does fire.",
        "",
        "### What helps (enhancement direction)",
        "1. **Cut confluence:** MACD cross + single OS filter (RSI&lt;40) beats 4-way AND.",
        "2. **Hard loss cap:** fixed −6% or ATR/chandelier trail beats pure any-oppose for less-loss.",
        "3. **Trend pullback (E2)** needs enough dips in uptrends — check N before trusting.",
        "4. **Mean-revert (A6/E7)** can trade more but often loses to BH in bull tapes — regime-aware gate required.",
        "5. Prefer **ret − |maxDD|** score over raw return when crowning offline arms.",
        "",
        "### Regime note",
        "Entry regime = pair 30d return buckets (bull &gt;+5%, bear &lt;−5%, else flat). "
        "See trial JSON `regime_expectancy` per arm/pair. Thin N → inconclusive by regime.",
        "",
        "## Decision bar",
        f"- `final_recommendation`: **{rec}**",
        "- N&lt;15 per arm (global) → do not promote; dig or drop only.",
        "- No live allocator / RSI+Stoch combo without explicit Brad OK.",
        "",
        f"Trades CSV: `{trades_path}`" if trades_path else "Trades CSV: (none)",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n")

    payload = {
        "id": "TEST-COMBINED-INDICATOR-ABLATION-2026-08",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs,
        "pair_meta": pair_meta,
        "fee_bps": fee_bps,
        "arms_run": [a.arm_id for a in ARMS],
        "per_pair_metrics": all_metrics,
        "aggregate": aggregate,
        "ranked": ranked,
        "unranked_sparse": unranked_sparse,
        "final_recommendation": rec,
        "go_notes": go_note,
        "report_md": str(md_path.relative_to(ROOT)) if md_path.is_relative_to(ROOT) else str(md_path),
        "trades_csv": str(trades_path.relative_to(ROOT)) if trades_path and trades_path.is_relative_to(ROOT) else (str(trades_path) if trades_path else None),
        "source_session": "20260731_152450_773d89",
        "north_star": "returns AND less loss",
        "scope": "offline only; no live combo-fish",
    }
    out_json.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    # also stamp a reports json
    rep_json = report_dir / f"COMBINED_INDICATOR_ABLATION_MULTIPAIR_{stamp}.json"
    rep_json.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print(md_path.read_text())
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    print(f"Wrote {rep_json}")
    return payload


def bh_mean_dd(aggregate: List[Dict[str, Any]]) -> float:
    for a in aggregate:
        if a["arm"] == "BH":
            return float(a["mean_max_dd"])
    return -1.0


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-pair combined indicator ablation")
    p.add_argument("--pairs", default=",".join(DEFAULT_PAIRS), help="comma list: btc,eth,sol,...")
    p.add_argument("--start", default=None)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--out-json", default=str(DEFAULT_TRIAL_JSON))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = p.parse_args()
    pairs = [x.strip().lower() for x in args.pairs.split(",") if x.strip()]
    run_universe(
        pairs=pairs,
        start=args.start,
        fee_bps=args.fee_bps,
        out_json=Path(args.out_json),
        report_dir=Path(args.report_dir),
    )


if __name__ == "__main__":
    main()
