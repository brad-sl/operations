#!/usr/bin/env python3
"""PAXG vs gold-spot correlation and lag analysis (plain-English report)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def try_yfinance():
    try:
        import yfinance as yf
    except ImportError:
        return None, "yfinance not installed"
    # PAXG-USD on Yahoo; gold futures GC=F as continuous proxy for spot-ish USD gold
    # Also try GLD ETF as liquid gold proxy traded while gold futures sleep less
    tickers = {
        "PAXG": "PAXG-USD",
        "GC": "GC=F",
        "GLD": "GLD",
    }
    frames = {}
    errors = []
    for name, t in tickers.items():
        try:
            df = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty:
                errors.append(f"{t}: empty")
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            s = df["Close"].dropna().astype(float)
            s.name = name
            frames[name] = s
        except Exception as e:
            errors.append(f"{t}: {e}")
    if "PAXG" not in frames:
        return None, "PAXG download failed: " + "; ".join(errors)
    return frames, ("; ".join(errors) if errors else None)


def try_coingecko_paxg():
    """Daily-ish market_chart for PAXG only (no gold)."""
    import urllib.request

    url = "https://api.coingecko.com/api/v3/coins/pax-gold/market_chart?vs_currency=usd&days=365"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode())
        prices = data.get("prices") or []
        if len(prices) < 30:
            return None
        idx = pd.to_datetime([p[0] for p in prices], unit="ms", utc=True).tz_localize(None)
        s = pd.Series([float(p[1]) for p in prices], index=idx, name="PAXG")
        # collapse to daily last
        s = s.resample("1D").last().dropna()
        return s
    except Exception:
        return None


def try_stooq_gold():
    """Stooq daily XAUUSD if available."""
    import urllib.request

    for sym in ("xauusd", "gc.f"):
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                text = r.read().decode()
            from io import StringIO

            df = pd.read_csv(StringIO(text))
            if "Close" not in df.columns or len(df) < 30:
                continue
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            s = df["Close"].astype(float)
            s.name = "XAU"
            return s
        except Exception:
            continue
    return None


def align_daily(*series: pd.Series) -> pd.DataFrame:
    df = pd.concat(series, axis=1).sort_index()
    df = df.ffill(limit=2).dropna()
    return df


def log_returns(df: pd.DataFrame) -> pd.DataFrame:
    return np.log(df / df.shift(1)).dropna()


def corr_table(rets: pd.DataFrame) -> pd.DataFrame:
    return rets.corr()


def lag_analysis(x: pd.Series, y: pd.Series, max_lag: int = 10) -> pd.DataFrame:
    """Cross-corr: corr(x_t, y_{t+k}) for k in -max_lag..max_lag.
    Positive k means y lags x (y later).
    """
    rows = []
    for k in range(-max_lag, max_lag + 1):
        if k < 0:
            a, b = x.iloc[-k:], y.iloc[:k] if k != 0 else y
            # x leads: compare x[t] with y[t+k] k negative => y earlier
            xs = x.shift(-k)  # shift x forward in time index alignment via dropna
        # Standard: corr(x.shift(k), y) — positive k means x is delayed (x lags y)
        c = x.shift(k).corr(y)
        rows.append({"lag_days_x_vs_y": k, "corr": c, "note": _lag_note(k)})
    return pd.DataFrame(rows)


def _lag_note(k: int) -> str:
    if k == 0:
        return "same day"
    if k > 0:
        return f"PAXG delayed {k}d vs gold (gold moves first)"
    return f"PAXG leads gold by {-k}d (unusual)"


def lag_analysis_named(paxg: pd.Series, gold: pd.Series, max_lag: int = 10) -> pd.DataFrame:
    rows = []
    for k in range(-max_lag, max_lag + 1):
        # corr(PAXG_t, gold_{t-k}) via shifting gold
        # k>0: gold shifted forward => compare PAXG_t to gold_{t-k} => gold earlier => gold leads
        c = paxg.corr(gold.shift(k))
        if k == 0:
            note = "same calendar day"
        elif k > 0:
            note = f"gold leads by ~{k} trading day(s)"
        else:
            note = f"PAXG leads by ~{-k} trading day(s)"
        rows.append({"lag_days": k, "corr_paxg_vs_gold_shifted": c, "interpretation": note})
    return pd.DataFrame(rows)


def tracking_error(paxg: pd.Series, gold: pd.Series) -> dict:
    # Normalize both to 100 at start for level co-movement; premium = PAXG/gold ratio path
    g0, p0 = float(gold.iloc[0]), float(paxg.iloc[0])
    ratio = (paxg / p0) / (gold / g0)
    # Dollar-ish premium if both ~ $/oz: paxg - gold (only if same units)
    level_spread = paxg - gold
    rets_p = np.log(paxg / paxg.shift(1))
    rets_g = np.log(gold / gold.shift(1))
    te = (rets_p - rets_g).dropna()
    return {
        "n_days": int(len(paxg)),
        "start": str(paxg.index[0].date()),
        "end": str(paxg.index[-1].date()),
        "corr_levels": float(paxg.corr(gold)),
        "corr_log_returns": float(rets_p.corr(rets_g)),
        "beta_paxg_on_gold": float(np.polyfit(rets_g.dropna().align(rets_p.dropna(), join="inner")[0],
                                              rets_p.dropna().align(rets_g.dropna(), join="inner")[1], 1)[0])
        if len(te) > 10
        else None,
        "tracking_error_daily_vol": float(te.std()),
        "tracking_error_ann_vol_approx": float(te.std() * np.sqrt(252)),
        "mean_abs_daily_return_gap": float(te.abs().mean()),
        "ratio_norm_mean": float(ratio.mean()),
        "ratio_norm_std": float(ratio.std()),
        "ratio_norm_min": float(ratio.min()),
        "ratio_norm_max": float(ratio.max()),
        "level_spread_mean_usd": float(level_spread.mean()) if level_spread.notna().any() else None,
        "level_spread_std_usd": float(level_spread.std()) if level_spread.notna().any() else None,
        "level_spread_mean_pct_of_gold": float((level_spread / gold).mean() * 100),
        "level_spread_std_pct": float((level_spread / gold).std() * 100),
        "pct_days_abs_spread_under_0_5pct": float(((level_spread / gold).abs() < 0.005).mean() * 100),
        "pct_days_abs_spread_under_1pct": float(((level_spread / gold).abs() < 0.01).mean() * 100),
        "pct_days_abs_spread_under_2pct": float(((level_spread / gold).abs() < 0.02).mean() * 100),
    }


def beta_ols(y: pd.Series, x: pd.Series) -> float:
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 10:
        return float("nan")
    yy, xx = df.iloc[:, 0].values, df.iloc[:, 1].values
    b = np.polyfit(xx, yy, 1)[0]
    return float(b)


def weekend_effect(paxg: pd.Series, gold: pd.Series) -> dict:
    """Gold futures often thin/closed weekends; PAXG trades 24/7 crypto."""
    rets_p = paxg.pct_change()
    # Monday return for PAXG vs Friday-Monday gold
    # Use dayofweek Mon=0
    mon_p = rets_p[paxg.index.dayofweek == 0]
    return {
        "paxg_mean_abs_ret_mon": float(mon_p.abs().mean()) if len(mon_p) else None,
        "paxg_mean_abs_ret_all": float(rets_p.abs().mean()),
        "note": "PAXG can move on weekends when London gold is closed; Monday may catch up.",
    }


def main():
    report = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "question": "How closely does PAXG track gold spot, and what lag?",
        "method_notes": [],
        "sources": [],
        "plain_english": {},
        "stats": {},
    }

    frames, err = try_yfinance()
    if err:
        report["method_notes"].append(f"yfinance notes: {err}")

    paxg = gold = gold_name = None
    if frames and "PAXG" in frames:
        paxg = frames["PAXG"]
        report["sources"].append("Yahoo Finance PAXG-USD daily")
        if "GC" in frames:
            gold = frames["GC"]
            gold_name = "GC=F (COMEX gold futures front continuous — common USD gold proxy)"
            report["sources"].append("Yahoo Finance GC=F daily")
            report["method_notes"].append(
                "True LBMA loco London spot is not free here; GC=F is the standard liquid USD gold proxy. "
                "It is extremely tightly linked to spot but is futures, not vault gold."
            )
        elif "GLD" in frames:
            gold = frames["GLD"]
            gold_name = "GLD ETF (scaled gold exposure, not $/oz)"
            report["sources"].append("Yahoo Finance GLD daily")
            report["method_notes"].append("GLD is not $/oz; level spread $ is not meaningful — use returns/corr only.")

    if paxg is None:
        paxg = try_coingecko_paxg()
        if paxg is not None:
            report["sources"].append("CoinGecko pax-gold market_chart")
    if gold is None:
        gold = try_stooq_gold()
        if gold is not None:
            gold_name = "Stooq XAUUSD/GC"
            report["sources"].append("Stooq gold daily")

    if paxg is None or gold is None:
        report["error"] = "Could not load both series"
        report["paxg_ok"] = paxg is not None
        report["gold_ok"] = gold is not None
        out = OUT_DIR / "PAXG_GOLD_CORRELATION.md"
        out.write_text("# Failed\n" + json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2)[:2000])
        return 1

    df = align_daily(paxg.rename("PAXG"), gold.rename("GOLD"))
    # Drop weekends optional — keep all calendar days where both have values after ffill limit
    rets = log_returns(df)
    te = tracking_error(df["PAXG"], df["GOLD"])
    te["beta_paxg_on_gold"] = beta_ols(rets["PAXG"], rets["GOLD"])
    lags = lag_analysis_named(rets["PAXG"], rets["GOLD"], max_lag=10)
    best = lags.loc[lags["corr_paxg_vs_gold_shifted"].abs().idxmax()]
    best_pos = lags.iloc[(lags["lag_days"] - 0).abs().argsort()[:1]]  # lag0
    lag0 = float(lags.loc[lags["lag_days"] == 0, "corr_paxg_vs_gold_shifted"].iloc[0])
    # Best lag among reasonable
    lags_valid = lags.dropna(subset=["corr_paxg_vs_gold_shifted"])
    best_row = lags_valid.loc[lags_valid["corr_paxg_vs_gold_shifted"].idxmax()]

    we = weekend_effect(df["PAXG"], df["GOLD"])

    # Rolling 60d corr
    roll = rets["PAXG"].rolling(60).corr(rets["GOLD"]).dropna()

    report["gold_proxy"] = gold_name
    report["stats"] = {
        "tracking": te,
        "lag0_return_corr": lag0,
        "best_lag": {
            "lag_days": int(best_row["lag_days"]),
            "corr": float(best_row["corr_paxg_vs_gold_shifted"]),
            "interpretation": best_row["interpretation"],
        },
        "lag_table": lags_valid.to_dict(orient="records"),
        "rolling_60d_corr": {
            "mean": float(roll.mean()),
            "min": float(roll.min()),
            "max": float(roll.max()),
            "last": float(roll.iloc[-1]),
        },
        "weekend": we,
        "last_prices": {
            "PAXG": float(df["PAXG"].iloc[-1]),
            "GOLD_proxy": float(df["GOLD"].iloc[-1]),
            "spread_usd": float(df["PAXG"].iloc[-1] - df["GOLD"].iloc[-1]),
            "spread_pct": float((df["PAXG"].iloc[-1] / df["GOLD"].iloc[-1] - 1) * 100),
        },
    }

    # Plain English
    lc = te["corr_log_returns"]
    if lc >= 0.95:
        closeness = "very tightly"
    elif lc >= 0.85:
        closeness = "closely"
    elif lc >= 0.70:
        closeness = "moderately"
    else:
        closeness = "only loosely"

    bl = int(best_row["lag_days"])
    if bl == 0 and lag0 >= 0.9:
        lag_pe = (
            "On daily data, the best match is **same day** — there is no multi-day lag you need to worry about "
            "for Smart Park sizing. Intraday, PAXG can still slip a few minutes to hours around crypto liquidity, "
            "weekends, and exchange stress."
        )
    elif abs(bl) <= 1:
        lag_pe = (
            f"Daily lag test peaks at **{best_row['interpretation']}** "
            f"(corr {float(best_row['corr_paxg_vs_gold_shifted']):.3f}). "
            "That is still effectively **near real-time on a day timescale**, not a multi-week lag."
        )
    else:
        lag_pe = (
            f"Daily lag test peaks at **{best_row['interpretation']}** "
            f"(corr {float(best_row['corr_paxg_vs_gold_shifted']):.3f}). "
            "Worth watching — unusual for a gold-backed token; check data quality and holidays."
        )

    spread_pct = report["stats"]["last_prices"]["spread_pct"]
    report["plain_english"] = {
        "bottom_line": (
            f"PAXG moves **{closeness}** with the gold price proxy we used "
            f"(daily return correlation **{lc:.3f}**, beta **{te['beta_paxg_on_gold']:.3f}**). "
            + lag_pe
        ),
        "premium_discount": (
            f"Over the sample, the average PAXG−gold level gap was about "
            f"**{te['level_spread_mean_pct_of_gold']:.2f}%** of gold "
            f"(stdev **{te['level_spread_std_pct']:.2f}%**). "
            f"Share of days within 0.5% / 1% / 2%: "
            f"{te['pct_days_abs_spread_under_0_5pct']:.0f}% / "
            f"{te['pct_days_abs_spread_under_1pct']:.0f}% / "
            f"{te['pct_days_abs_spread_under_2pct']:.0f}%. "
            f"Latest gap: **{spread_pct:+.2f}%** (PAXG vs proxy)."
        ),
        "what_this_means_for_traders": (
            "For Smart Park, treat PAXG as **gold exposure on the exchange**, not magic crypto alpha. "
            "It should feel like gold day-to-day. Short gaps open when: gold market is closed and crypto is open, "
            "PAXG is thin on Coinbase, or people rush into on-chain gold in a crypto panic (premium) or dump it "
            "(discount). Arbitrage (mint/redeem via Paxos when available) usually pulls it back — that process "
            "is hours to days for institutions, not weeks, under normal conditions."
        ),
        "lag_summary": lag_pe,
        "closeness_word": closeness,
    }

    # Write markdown report
    md = []
    md.append("# PAXG vs gold — correlation & lag")
    md.append("")
    md.append(f"**As of:** {report['as_of']}")
    md.append(f"**Gold proxy:** {gold_name}")
    md.append(f"**Sample:** {te['start']} → {te['end']} ({te['n_days']} aligned days)")
    md.append(f"**Sources:** {', '.join(report['sources'])}")
    md.append("")
    md.append("## Plain English (go/no-go style)")
    md.append("")
    md.append(report["plain_english"]["bottom_line"])
    md.append("")
    md.append(report["plain_english"]["premium_discount"])
    md.append("")
    md.append(report["plain_english"]["what_this_means_for_traders"])
    md.append("")
    md.append("## Key numbers")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| Corr of **levels** (price series) | {te['corr_levels']:.4f} |")
    md.append(f"| Corr of **daily log returns** | {te['corr_log_returns']:.4f} |")
    md.append(f"| Beta (PAXG returns vs gold returns) | {te['beta_paxg_on_gold']:.4f} |")
    md.append(f"| Daily tracking-error vol | {te['tracking_error_daily_vol']:.5f} |")
    md.append(f"| Tracking-error vol (ann. √252) | {te['tracking_error_ann_vol_approx']:.2%} |")
    md.append(f"| Mean \|daily return gap\| | {te['mean_abs_daily_return_gap']:.5f} |")
    md.append(f"| Mean level spread % of gold | {te['level_spread_mean_pct_of_gold']:.3f}% |")
    md.append(f"| Latest PAXG | ${report['stats']['last_prices']['PAXG']:,.2f} |")
    md.append(f"| Latest gold proxy | ${report['stats']['last_prices']['GOLD_proxy']:,.2f} |")
    md.append(f"| Latest spread | {spread_pct:+.3f}% |")
    md.append(f"| Rolling 60d return corr (last / mean / min) | "
              f"{report['stats']['rolling_60d_corr']['last']:.3f} / "
              f"{report['stats']['rolling_60d_corr']['mean']:.3f} / "
              f"{report['stats']['rolling_60d_corr']['min']:.3f} |")
    md.append("")
    md.append("## Lag scan (daily returns)")
    md.append("")
    md.append("Lag > 0 means **gold moved first** (PAXG compared to gold from `lag` days earlier).")
    md.append("")
    md.append("| Lag (days) | Corr | Interpretation |")
    md.append("|------------|------|----------------|")
    for row in lags_valid.itertuples(index=False):
        md.append(
            f"| {int(row.lag_days)} | {float(row.corr_paxg_vs_gold_shifted):.4f} | {row.interpretation} |"
        )
    md.append("")
    md.append(
        f"**Peak lag:** {int(best_row['lag_days'])} day(s) — {best_row['interpretation']} "
        f"(corr {float(best_row['corr_paxg_vs_gold_shifted']):.4f}). "
        f"Same-day corr: **{lag0:.4f}**."
    )
    md.append("")
    md.append("## Method caveats")
    md.append("")
    for n in report["method_notes"]:
        md.append(f"- {n}")
    md.append(
        "- Daily bars hide **intraday** lag (minutes–hours) and **weekend** PAXG-only moves."
    )
    md.append(
        "- Coinbase PAXG-USD spread/liquidity can widen vs global PAXG or Paxos mint/redeem fair value."
    )
    md.append(
        "- Design intent (Paxos): 1 PAXG ≈ 1 fine troy oz allocated gold; arb keeps it near spot under normal access."
    )
    md.append("")
    md.append("## Design intent (context, not our calc)")
    md.append("")
    md.append(
        "PAXG is built so one token relates to one fine troy ounce of vaulted gold; "
        "public explainers describe **tight arbitrage vs XAU** and same-direction moves with spot, "
        "with temporary premiums/discounts in crypto stress or when gold markets are closed."
    )
    md.append("")
    md.append("---")
    md.append("*Generated by `scripts/analysis/paxg_gold_correlation.py`*")

    out_md = OUT_DIR / "PAXG_GOLD_CORRELATION.md"
    out_json = OUT_DIR / "PAXG_GOLD_CORRELATION.json"
    # JSON-safe lag table already
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    # slim json
    slim = {
        k: report[k]
        for k in ("as_of", "gold_proxy", "sources", "method_notes", "plain_english", "stats")
    }
    # don't dump full lag in print
    out_json.write_text(json.dumps(slim, indent=2, default=str) + "\n", encoding="utf-8")
    print(out_md.read_text()[:3500])
    print("\n... wrote", out_md, out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
