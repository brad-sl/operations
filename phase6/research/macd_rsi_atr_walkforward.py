#!/usr/bin/env python3
"""
Walk-forward + longer-tape pass for champion recipe F2:
  MACD bullish cross + RSI(14)<40
  exit: 2×ATR trail from peak + MACD death cross
  no Stoch/BB; optional deep-bear/weak skip

Real Coinbase public daily candles only. Fixed params (no in-fold optim).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
LONG_DIR = ROOT / "backtests/data/long"
REPORT_DIR = ROOT / "reports"
STATE_JSON = ROOT / "data/state/trials/TEST_MACD_RSI_ATR_WALKFORWARD.json"

PAIRS = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
    "link": "LINK-USD",
}
# Optional stress
STRESS = {
    "xrp": "XRP-USD",
    "avax": "AVAX-USD",
}

FEE_BPS = 5.0
SIZE = 0.95
RSI_MAX = 40.0
ATR_MULT = 2.0
MAX_CANDLES = 300
GRANULARITY = 86400


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
        for attempt in range(5):
            resp = requests.get(url, params=params, timeout=45)
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                # some products may not exist that far back
                if resp.status_code == 404:
                    return out
                resp.raise_for_status()
            raw = resp.json()
            break
        else:
            raise RuntimeError(f"rate limited fetching {product_id}")
        for row in reversed(raw):
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


def ensure_long_ohlcv(
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
                first = datetime.fromisoformat(rows[0]["timestamp"].replace("Z", "+00:00"))
                last = datetime.fromisoformat(rows[-1]["timestamp"].replace("Z", "+00:00"))
                # refresh if missing recent week or starts after requested start+30d
                if last < end - timedelta(days=7) or first > start + timedelta(days=60):
                    need = True
                else:
                    print(f"  cache hit {short}: {len(rows)} bars {rows[0]['timestamp'][:10]}→{rows[-1]['timestamp'][:10]}")
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


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


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


def add_ind(df: pd.DataFrame) -> pd.DataFrame:
    o = df.copy()
    o["macd"] = _ema(o["Close"], 12) - _ema(o["Close"], 26)
    o["signal"] = _ema(o["macd"], 9)
    o["rsi"] = _rsi(o["Close"], 14)
    o["atr"] = _atr(o["High"], o["Low"], o["Close"], 14)
    o["cross_up"] = (o["macd"] > o["signal"]) & (o["macd"].shift(1) <= o["signal"].shift(1))
    o["cross_dn"] = (o["macd"] < o["signal"]) & (o["macd"].shift(1) >= o["signal"].shift(1))
    o["ret_30d"] = o["Close"].pct_change(30)
    o["ret_90d"] = o["Close"].pct_change(90)
    o["dd_ath_90"] = o["Close"] / o["Close"].rolling(90).max() - 1.0
    o["deep_bear"] = o["ret_30d"] < -0.40
    o["weak"] = (o["ret_90d"] < -0.50) | (o["dd_ath_90"] < -0.55)
    return o


def backtest_f2(
    df: pd.DataFrame,
    use_filter: bool = True,
    fee_bps: float = FEE_BPS,
    initial: float = 10_000.0,
) -> Tuple[List[dict], Dict[str, Any]]:
    """Fixed F2 recipe on df slice. Indicators must already be on full history;
    pass a slice that still has indicator warmup from parent or recompute on slice.
    """
    fee = fee_bps / 10_000.0
    cash = float(initial)
    pos = 0.0
    entry_px = peak = 0.0
    entry_i = 0
    entry_t = None
    trades: List[dict] = []
    curve: List[float] = []

    def flat(ts, px, i, reason):
        nonlocal cash, pos, entry_px, peak
        pnl = (px / entry_px - 1.0) - 2 * fee
        trades.append(
            {
                "entry_time": str(entry_t.date()) if entry_t is not None else None,
                "exit_time": str(ts.date()),
                "pnl_pct": float(pnl),
                "bars": int(i - entry_i),
                "reason": reason,
            }
        )
        cash = pos * px * (1 - fee)
        pos = 0.0
        peak = 0.0

    # BH
    px0 = float(df["Close"].iloc[0])
    px1 = float(df["Close"].iloc[-1])
    bh = (px1 / px0 - 1.0) - 2 * fee * 0  # raw BH no roundtrip fee for bench simplicity
    bh_fee = (px1 / px0 - 1.0) - 2 * fee

    for i, (ts, row) in enumerate(df.iterrows()):
        px = float(row["Close"])
        eq = cash + pos * px
        curve.append(eq)
        if pos > 0:
            peak = max(peak, px)
            atr = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
            reason = None
            if atr > 0 and px <= peak - ATR_MULT * atr:
                reason = "sl_atr"
            elif bool(row["cross_dn"]):
                reason = "macd_death"
            if reason:
                flat(ts, px, i, reason)
                continue
        if pos == 0:
            if not bool(row["cross_up"]):
                continue
            if float(row["rsi"]) >= RSI_MAX:
                continue
            if use_filter and (bool(row.get("deep_bear", False)) or bool(row.get("weak", False))):
                continue
            if pd.isna(row["atr"]) or pd.isna(row["rsi"]):
                continue
            deploy = eq * SIZE
            if deploy <= 0:
                continue
            pos = (deploy * (1 - fee)) / px
            cash = eq - deploy
            entry_px = px
            peak = px
            entry_i = i
            entry_t = ts

    if pos > 0:
        flat(df.index[-1], float(df["Close"].iloc[-1]), len(df) - 1, "eod")

    final = float(curve[-1]) if curve else initial
    ret = final / initial - 1.0
    eq = pd.Series(curve)
    dd = float(((eq - eq.cummax()) / eq.cummax()).min()) if len(eq) else 0.0
    n = len(trades)
    exp = float(np.mean([t["pnl_pct"] for t in trades])) if n else 0.0
    wr = float(np.mean([t["pnl_pct"] > 0 for t in trades])) if n else 0.0
    return trades, {
        "n_trades": n,
        "total_return": ret,
        "max_dd": dd,
        "expectancy": exp,
        "win_rate": wr,
        "bh_return": bh_fee,
        "edge_vs_bh": ret - bh_fee,
        "final_equity": final,
    }


def make_folds(
    index: pd.DatetimeIndex,
    test_days: int = 120,
    step_days: int = 60,
    min_bars: int = 80,
    warmup_days: int = 120,
) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """
    Returns list of (warmup_start, test_start, test_end).
    Indicators computed on [warmup_start, test_end]; metrics on test only.
    Expanding warmup from first bar.
    """
    start = index[0]
    end = index[-1]
    folds = []
    # first test starts after warmup
    t0 = start + pd.Timedelta(days=warmup_days)
    while t0 + pd.Timedelta(days=test_days) <= end:
        t1 = t0 + pd.Timedelta(days=test_days)
        folds.append((start, t0, t1))
        t0 = t0 + pd.Timedelta(days=step_days)
    # drop tiny
    return folds


def run_pair_wf(short: str, path: Path) -> Dict[str, Any]:
    raw = load_df(path)
    full = add_ind(raw).dropna()
    folds_def = make_folds(full.index)
    fold_rows = []
    all_oos_trades = []
    for fi, (w0, t0, t1) in enumerate(folds_def):
        # slice with warmup included for continuity of position? 
        # True OOS: flat at test start; indicators from full history up to each bar (no leak)
        window = full.loc[w0:t1]
        test = full.loc[t0:t1]
        if len(test) < 40:
            continue
        # Run on test segment only but indicators already from full path (good)
        # Recompute indicators only on window to avoid using future beyond t1 — window ends at t1 so OK
        w_ind = add_ind(raw.loc[w0:t1]).dropna()
        test_ind = w_ind.loc[t0:t1]
        if len(test_ind) < 40:
            continue
        trades, m = backtest_f2(test_ind, use_filter=True)
        for tr in trades:
            tr["pair"] = short
            tr["fold"] = fi
            tr["test_start"] = str(t0.date())
            tr["test_end"] = str(t1.date())
            all_oos_trades.append(tr)
        fold_rows.append(
            {
                "pair": short,
                "fold": fi,
                "test_start": str(t0.date()),
                "test_end": str(t1.date()),
                "bars": len(test_ind),
                **m,
            }
        )
    # full-period single shot
    trades_full, m_full = backtest_f2(full, use_filter=True)
    for tr in trades_full:
        tr["pair"] = short
        tr["fold"] = "FULL"
    return {
        "pair": short,
        "bars": len(full),
        "start": str(full.index[0].date()),
        "end": str(full.index[-1].date()),
        "full": m_full,
        "folds": fold_rows,
        "oos_trades": all_oos_trades,
        "full_trades": trades_full,
    }


def summarize(pair_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Equal-weight portfolio path approximation: mean of pair full returns
    full_rets = [r["full"]["total_return"] for r in pair_results]
    full_bh = [r["full"]["bh_return"] for r in pair_results]
    full_dd = [r["full"]["max_dd"] for r in pair_results]
    n_full = sum(r["full"]["n_trades"] for r in pair_results)

    # Fold-level: for each fold index, mean across pairs present
    fold_map: Dict[int, List[dict]] = {}
    for r in pair_results:
        for f in r["folds"]:
            fold_map.setdefault(f["fold"], []).append(f)

    fold_summary = []
    for fi in sorted(fold_map):
        rows = fold_map[fi]
        fold_summary.append(
            {
                "fold": fi,
                "test_start": rows[0]["test_start"],
                "test_end": rows[0]["test_end"],
                "mean_return": float(np.mean([x["total_return"] for x in rows])),
                "mean_bh": float(np.mean([x["bh_return"] for x in rows])),
                "mean_edge_bh": float(np.mean([x["edge_vs_bh"] for x in rows])),
                "mean_dd": float(np.mean([x["max_dd"] for x in rows])),
                "n_trades": int(sum(x["n_trades"] for x in rows)),
                "pairs": len(rows),
                "pct_pairs_positive": float(np.mean([x["total_return"] > 0 for x in rows])),
            }
        )

    oos_rets = [f["mean_return"] for f in fold_summary]
    hit5 = float(np.mean([r >= 0.05 for r in oos_rets])) if oos_rets else 0.0
    hit0 = float(np.mean([r >= 0.0 for r in oos_rets])) if oos_rets else 0.0
    mean_oos = float(np.mean(oos_rets)) if oos_rets else 0.0
    med_oos = float(np.median(oos_rets)) if oos_rets else 0.0

    # annualize roughly: each fold ~120d → scale mean_oos * (365/120)
    ann_factor = 365 / 120
    mean_oos_ann = mean_oos * ann_factor

    # Stability verdict
    # Brad OK with ~5% overall — map to full-period mean and OOS fold mean
    full_mean = float(np.mean(full_rets))
    if full_mean >= 0.05 and mean_oos >= 0.0 and hit0 >= 0.55:
        rec = "pattern_confirmed_modest_edge"
    elif full_mean >= 0.0 and mean_oos >= 0.0:
        rec = "pattern_stable_small_positive"
    elif mean_oos >= 0.0 and full_mean < 0:
        rec = "oos_ok_full_mixed"
    elif hit0 >= 0.5 and float(np.mean([f["mean_edge_bh"] for f in fold_summary] or [0])) > 0.05:
        rec = "less_loss_stable_not_absolute"
    else:
        rec = "unstable_or_no_edge"

    return {
        "full_period": {
            "mean_return": full_mean,
            "median_return": float(np.median(full_rets)),
            "mean_bh": float(np.mean(full_bh)),
            "mean_edge_bh": float(np.mean(full_rets) - np.mean(full_bh)),
            "mean_max_dd": float(np.mean(full_dd)),
            "n_trades_sum": n_full,
            "per_pair": {
                r["pair"]: {
                    "return": r["full"]["total_return"],
                    "bh": r["full"]["bh_return"],
                    "n": r["full"]["n_trades"],
                    "exp": r["full"]["expectancy"],
                    "wr": r["full"]["win_rate"],
                    "dd": r["full"]["max_dd"],
                    "start": r["start"],
                    "end": r["end"],
                    "bars": r["bars"],
                }
                for r in pair_results
            },
        },
        "walk_forward": {
            "n_folds": len(fold_summary),
            "test_days": 120,
            "step_days": 60,
            "mean_oos_return_per_fold": mean_oos,
            "median_oos_return_per_fold": med_oos,
            "approx_annualized_from_120d": mean_oos_ann,
            "pct_folds_ge_0": hit0,
            "pct_folds_ge_5pct": hit5,
            "mean_oos_edge_vs_bh": float(np.mean([f["mean_edge_bh"] for f in fold_summary])) if fold_summary else 0.0,
            "folds": fold_summary,
        },
        "final_recommendation": rec,
        "brad_5pct_bar": {
            "full_mean_ge_5pct": full_mean >= 0.05,
            "oos_mean_ge_0": mean_oos >= 0.0,
            "interpretation": (
                "5% overall average is a FULL-PERIOD portfolio mean bar, not per-fold 5%. "
                "OOS fold returns are ~120d slices — do not expect each fold to print +5%."
            ),
        },
    }


def write_report(payload: Dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md = REPORT_DIR / f"MACD_RSI_ATR_WALKFORWARD_{stamp}.md"
    fp = payload["full_period"]
    wf = payload["walk_forward"]
    lines = [
        f"# MACD× + RSI&lt;40 + 2×ATR walk-forward — {stamp}",
        "",
        "## Plain English",
        "",
        f"**Recipe:** fixed F2 (no fold optimization)",
        f"**Data:** Coinbase public daily · longer tape under `backtests/data/long/`",
        f"**Pairs:** {', '.join(p.upper() for p in payload['pairs'])}",
        f"**Recommendation:** `{payload['final_recommendation']}`",
        "",
        f"### Full-period (entire long tape)",
        f"- Equal-weight mean return: **{fp['mean_return']:.1%}**",
        f"- Mean BH: **{fp['mean_bh']:.1%}** · edge vs BH: **{fp['mean_edge_bh']:+.1%}**",
        f"- Mean maxDD: **{fp['mean_max_dd']:.1%}** · trades: **{fp['n_trades_sum']}**",
        f"- Brad ~5% bar (full mean ≥5%): **{'PASS' if payload['brad_5pct_bar']['full_mean_ge_5pct'] else 'FAIL'}**",
        "",
        f"### Walk-forward OOS ({wf['n_folds']} folds × ~{wf['test_days']}d, step {wf['step_days']}d)",
        f"- Mean OOS return **per fold**: **{wf['mean_oos_return_per_fold']:.1%}**",
        f"- Median OOS: **{wf['median_oos_return_per_fold']:.1%}**",
        f"- Folds ≥0%: **{wf['pct_folds_ge_0']:.0%}** · folds ≥5%: **{wf['pct_folds_ge_5pct']:.0%}**",
        f"- Mean OOS edge vs BH: **{wf['mean_oos_edge_vs_bh']:+.1%}**",
        f"- Rough annualized from 120d mean: **{wf['approx_annualized_from_120d']:.1%}** (illustrative only)",
        "",
        "### Per-pair full period",
        "",
        "| Pair | Bars | Window | F2 ret | BH | N | Exp | WR | DD |",
        "|------|------|--------|--------|-----|---|-----|----|----|",
    ]
    for p, m in fp["per_pair"].items():
        lines.append(
            f"| {p.upper()} | {m['bars']} | {m['start']}→{m['end']} | {m['return']:.1%} | {m['bh']:.1%} | "
            f"{m['n']} | {m['exp']:.1%} | {m['wr']:.0%} | {m['dd']:.1%} |"
        )
    lines += [
        "",
        "### OOS folds (equal-weight mean across pairs)",
        "",
        "| Fold | Window | mean Ret | mean BH | ΔBH | N | %pairs+ |",
        "|------|--------|----------|---------|-----|---|---------|",
    ]
    for f in wf["folds"]:
        lines.append(
            f"| {f['fold']} | {f['test_start']}→{f['test_end']} | {f['mean_return']:.1%} | "
            f"{f['mean_bh']:.1%} | {f['mean_edge_bh']:+.1%} | {f['n_trades']} | {f['pct_pairs_positive']:.0%} |"
        )
    lines += [
        "",
        "## Verdict for standard optimization",
        "",
    ]
    rec = payload["final_recommendation"]
    if rec == "pattern_confirmed_modest_edge":
        lines.append(
            "- **GO shadow / keep as standard opt candidate.** Full tape clears ~5% mean and OOS stays non-negative on average."
        )
    elif rec == "pattern_stable_small_positive":
        lines.append(
            "- **GO continue / shadow.** Positive but under 5% full mean — still a valid less-risk sleeve if DD stays controlled."
        )
    elif rec == "less_loss_stable_not_absolute":
        lines.append(
            "- **GO as risk overlay only**, not as return engine. Beats BH OOS but absolute still soft."
        )
    else:
        lines.append("- **NO-GO as standard opt** without more work — unstable or negative OOS.")
    lines += [
        "",
        "- Live promote: still **NO** without Brad OK + shadow period.",
        "- No Stoch/BB reintroduction.",
        "",
        f"**final_recommendation:** `{rec}`",
        "",
    ]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines) + "\n")
    return md


def main() -> int:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Coinbase daily history: go back as far as practical (BTC deep; alts when listed)
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    print("=== Long tape fetch (Coinbase public) ===")
    paths = ensure_long_ohlcv(PAIRS, start, end, force=False)

    print("=== Walk-forward per pair ===")
    results = []
    for short, path in paths.items():
        print(f"  WF {short}...")
        results.append(run_pair_wf(short, path))

    summary = summarize(results)
    payload = {
        "id": "TEST-MACD-RSI-ATR-WALKFORWARD",
        "parent": "TEST-COMBINED-INDICATOR-ABLATION-2026-08",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recipe": {
            "entry": "MACD cross up + RSI(14)<40",
            "exit": "2×ATR trail + MACD death",
            "filter": "skip deep_bear/weak",
            "fee_bps": FEE_BPS,
            "fixed_params": True,
        },
        "pairs": list(PAIRS.keys()),
        "data_dir": str(LONG_DIR.relative_to(ROOT)),
        "pair_results_meta": [
            {"pair": r["pair"], "bars": r["bars"], "start": r["start"], "end": r["end"]}
            for r in results
        ],
        **summary,
        "folds_detail": {r["pair"]: r["folds"] for r in results},
    }
    # trades csv
    oos = []
    for r in results:
        oos.extend(r["oos_trades"])
    trades_path = None
    if oos:
        trades_path = REPORT_DIR / f"MACD_RSI_ATR_WF_OOS_TRADES_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
        pd.DataFrame(oos).to_csv(trades_path, index=False)
        payload["oos_trades_csv"] = str(trades_path.relative_to(ROOT))

    md = write_report(payload)
    payload["report_md"] = str(md.relative_to(ROOT))
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    (REPORT_DIR / md.name.replace(".md", ".json")).write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
    print(md.read_text())
    print(f"Wrote {md}")
    print(f"Wrote {STATE_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
