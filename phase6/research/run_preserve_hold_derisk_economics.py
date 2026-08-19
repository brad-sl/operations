#!/usr/bin/env python3
"""
PRESERVE G2a/G2b — Hold vs DeRisk ladder economics on real PAXG paths.

Offline only. Binance Vision PAXGUSDT daily.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

FEE_RT = 0.002  # 0.20% round trip approx as 0.1% each side
INITIAL = 10_000.0
OUT_JSON = PROJECT / "data" / "state" / "preserve_hold_derisk_economics_latest.json"
OUT_MD = PROJECT / "reports" / f"PRESERVE_HOLD_DERISK_ECONOMICS_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"


def fetch_paxg() -> pd.Series:
    # prefer local cache from prior runs
    cache = PROJECT / "data" / "state" / "paxg_daily_close_cache.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        s = df.set_index("date")["close"].sort_index()
        if len(s) > 400:
            return s
    # binance vision monthly zips is heavy; use public klines paginated
    url = "https://data-api.binance.vision/api/v3/klines"
    rows = []
    end = None
    for _ in range(40):
        params = {"symbol": "PAXGUSDT", "interval": "1d", "limit": 1000}
        if end:
            params["endTime"] = end
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows = batch + rows
        end = batch[0][0] - 1
        if len(batch) < 1000:
            break
    idx = []
    closes = []
    seen = set()
    for k in rows:
        ts = pd.to_datetime(k[0], unit="ms", utc=True).tz_localize(None)
        if ts in seen:
            continue
        seen.add(ts)
        idx.append(ts)
        closes.append(float(k[4]))
    s = pd.Series(closes, index=pd.DatetimeIndex(idx), name="close").sort_index()
    cache.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": s.index, "close": s.values}).to_csv(cache, index=False)
    return s


@dataclass
class ArmResult:
    name: str
    total_return_pct: float
    max_dd_pct: float
    e1_or_stages_fired: str
    terminal_paxg_wt: float
    realized_note: str


def max_dd(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min() * 100)


def sim_usdc(n: int, apy: float = 0.0) -> ArmResult:
    eq = INITIAL * (1 + apy) ** (np.arange(n) / 365.25)
    # daily compound approx
    e = np.zeros(n)
    e[0] = INITIAL
    daily = (1 + apy) ** (1 / 365.25) - 1
    for i in range(1, n):
        e[i] = e[i - 1] * (1 + daily)
    return ArmResult("USDC_0" if apy == 0 else "USDC_4apy", (e[-1] / INITIAL - 1) * 100, max_dd(e), "n/a", 0.0, "cash")


def sim_static(px: np.ndarray, w: float = 0.20) -> ArmResult:
    # buy gold day0, hold
    g0 = px[0]
    gold_units = (INITIAL * w) * (1 - FEE_RT / 2) / g0
    cash = INITIAL * (1 - w)
    eq = cash + gold_units * px
    # fee already on entry; ignore exit fee for hold mark
    return ArmResult(
        f"static_{int(w*100)}pct",
        (eq[-1] / INITIAL - 1) * 100,
        max_dd(eq),
        "none",
        w,
        "hold mark-to-market",
    )


def sim_hold_e1(px: np.ndarray, w: float = 0.20, e1: float = -0.32) -> ArmResult:
    g0 = px[0]
    gold_units = (INITIAL * w) * (1 - FEE_RT / 2) / g0
    cash = INITIAL * (1 - w)
    eq = np.zeros(len(px))
    fired = "none"
    for i, p in enumerate(px):
        dd = p / g0 - 1.0
        if fired == "none" and dd <= e1 and gold_units > 0:
            cash += gold_units * p * (1 - FEE_RT / 2)
            gold_units = 0.0
            fired = f"E1@{i}"
        eq[i] = cash + gold_units * p
    term_w = 0.0 if eq[-1] <= 0 else (gold_units * px[-1]) / eq[-1]
    return ArmResult(
        "hold_e1_m32",
        (eq[-1] / INITIAL - 1) * 100,
        max_dd(eq),
        fired,
        term_w,
        "flatten at -32% from arm_vwap if hit",
    )


def sim_derisk(px: np.ndarray, w: float = 0.20) -> ArmResult:
    """S1 -12% 25%, S2 -18% 35%, S3 -32% 38% of original gold units."""
    g0 = px[0]
    gold0 = (INITIAL * w) * (1 - FEE_RT / 2) / g0
    gold = gold0
    cash = INITIAL * (1 - w)
    stages = [(-0.12, 0.25, "S1"), (-0.18, 0.35, "S2"), (-0.32, 0.38, "S3")]
    done = set()
    eq = np.zeros(len(px))
    fired = []
    for i, p in enumerate(px):
        dd = p / g0 - 1.0
        for thr, frac, name in stages:
            if name in done:
                continue
            if dd <= thr and gold > 0:
                sell = min(gold, gold0 * frac)
                cash += sell * p * (1 - FEE_RT / 2)
                gold -= sell
                done.add(name)
                fired.append(f"{name}@{i}")
        eq[i] = cash + gold * p
    term_w = 0.0 if eq[-1] <= 0 else (gold * px[-1]) / eq[-1]
    return ArmResult(
        "derisk_ladder",
        (eq[-1] / INITIAL - 1) * 100,
        max_dd(eq),
        ",".join(fired) if fired else "none",
        term_w,
        "staged sells from arm_vwap",
    )


def window_slice(s: pd.Series, start: str, end: Optional[str] = None) -> pd.Series:
    sub = s[s.index >= pd.Timestamp(start)]
    if end:
        sub = sub[sub.index <= pd.Timestamp(end)]
    return sub


def run_window(name: str, s: pd.Series) -> dict:
    px = s.values.astype(float)
    if len(px) < 5:
        return {"window": name, "error": "short"}
    arms = [
        sim_usdc(len(px), 0.0),
        sim_usdc(len(px), 0.04),
        sim_static(px, 0.20),
        sim_hold_e1(px, 0.20, -0.32),
        sim_derisk(px, 0.20),
        sim_static(px, 1.0),
    ]
    # path dd of gold alone
    peak = np.maximum.accumulate(px)
    gdd = float((px / peak - 1).min() * 100)
    # E1 fire check on measured worst: from window start
    e1 = sim_hold_e1(px, 0.20, -0.32)
    return {
        "window": name,
        "start": str(s.index[0].date()),
        "end": str(s.index[-1].date()),
        "n": len(px),
        "gold_path_max_dd_pct": round(gdd, 3),
        "gold_end_vs_start_pct": round((px[-1] / px[0] - 1) * 100, 3),
        "arms": [
            {
                "name": a.name,
                "total_return_pct": round(a.total_return_pct, 3),
                "max_dd_pct": round(a.max_dd_pct, 3),
                "fired": a.e1_or_stages_fired,
                "terminal_paxg_wt": round(a.terminal_paxg_wt, 4),
                "note": a.realized_note,
            }
            for a in arms
        ],
        "hold_e1_fired": e1.e1_or_stages_fired != "none",
    }


def ugly_peak_arm(s: pd.Series, peak_date: str, trough_date: str) -> dict:
    """Arm at peak, run through trough (+30d if available)."""
    peak = pd.Timestamp(peak_date)
    # series from peak
    sub = s[s.index >= peak]
    if sub.empty:
        return {"error": "no data"}
    # find local index of trough
    trough = pd.Timestamp(trough_date)
    end = trough + pd.Timedelta(days=30)
    sub = sub[sub.index <= end]
    px = sub.values.astype(float)
    hold = sim_hold_e1(px, 0.20, -0.32)
    dr = sim_derisk(px, 0.20)
    st = sim_static(px, 0.20)
    return {
        "label": f"ugly_arm_at_{peak_date}",
        "start": str(sub.index[0].date()),
        "end": str(sub.index[-1].date()),
        "gold_dd_from_arm_pct": round((px.min() / px[0] - 1) * 100, 3),
        "static20": {"ret": round(st.total_return_pct, 3), "dd": round(st.max_dd_pct, 3)},
        "hold_e1": {
            "ret": round(hold.total_return_pct, 3),
            "dd": round(hold.max_dd_pct, 3),
            "fired": hold.e1_or_stages_fired,
        },
        "derisk": {
            "ret": round(dr.total_return_pct, 3),
            "dd": round(dr.max_dd_pct, 3),
            "fired": dr.e1_or_stages_fired,
            "term_w": round(dr.terminal_paxg_wt, 4),
        },
        "verdict_fragment": (
            "DeRisk realizes sells into drawdown; Hold keeps gold unless -32% from arm."
        ),
    }


def main():
    s = fetch_paxg()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    end = s.index.max()
    windows = {
        "full": s,
        "d2022_gold_dd": window_slice(s, "2022-03-01", "2023-01-01"),
        "d2026_gold_dd": window_slice(s, "2026-01-20", "2026-08-02"),
        "last_12m": s[s.index >= end - pd.Timedelta(days=365)],
        "last_18m": s[s.index >= end - pd.Timedelta(days=548)],
    }
    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "fee_rt": FEE_RT,
        "initial": INITIAL,
        "windows": {k: run_window(k, v) for k, v in windows.items()},
        "ugly_paths": [
            ugly_peak_arm(s, "2026-01-28", "2026-07-16"),
            ugly_peak_arm(s, "2022-03-08", "2022-09-26"),
        ],
    }

    # Decisions
    ugly2026 = out["ugly_paths"][0]
    hold_f = ugly2026.get("hold_e1", {}).get("fired", "none")
    e1_ok = hold_f == "none"  # should not fire on -28% path
    derisk_ret = ugly2026.get("derisk", {}).get("ret", 0)
    hold_ret = ugly2026.get("hold_e1", {}).get("ret", 0)
    static_ret = ugly2026.get("static20", {}).get("ret", 0)

    out["decisions"] = {
        "hold_e1_does_not_fire_inside_2026_m28_path": e1_ok,
        "prefer_hold_default": True,
        "derisk_default": False,
        "derisk_optional_only_if": "ladder improves book DD enough without catastrophic underperformance vs hold on stress paths — review tables",
        "g2a_hold_economics": "PASS" if e1_ok else "REVIEW",
        "g2b_derisk": "KEEP_DISABLED_DEFAULT",
        "notes": [
            f"2026 ugly arm: static20 ret={static_ret}% hold_e1 ret={hold_ret}% fired={hold_f} derisk ret={derisk_ret}% fired={ugly2026.get('derisk',{}).get('fired')}",
            "Static backtest ≠ DeRisk; DeRisk must not inherit static +8.9% claim.",
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))

    # markdown
    lines = [
        f"# Preserve Hold vs DeRisk economics — {datetime.now(timezone.utc).date()}",
        "",
        "**Status:** OFFLINE G2a/G2b — not live",
        f"**JSON:** `{OUT_JSON}`",
        "",
        "## Decisions",
        f"- Hold E1 (−32%) non-fire on 2026 −28% arm-at-peak path: **{e1_ok}**",
        f"- **Default product: Hold**",
        f"- **DeRisk: disabled by default** (`{out['decisions']['g2b_derisk']}`)",
        "",
        "## Ugly path — arm at 2026-01-28 peak",
        "```json",
        json.dumps(ugly2026, indent=2),
        "```",
        "",
        "## Ugly path — arm at 2022-03-08 peak",
        "```json",
        json.dumps(out["ugly_paths"][1], indent=2),
        "```",
        "",
        "## Windows (summary)",
    ]
    for wn, wr in out["windows"].items():
        if wr.get("error"):
            continue
        lines.append(f"### {wn} ({wr['start']} → {wr['end']}, n={wr['n']})")
        lines.append(f"Gold path max DD: {wr['gold_path_max_dd_pct']}% | end vs start: {wr['gold_end_vs_start_pct']}%")
        lines.append("| Arm | Return% | MaxDD% | Fired | Term gold wt |")
        lines.append("|-----|--------:|-------:|-------|-------------:|")
        for a in wr["arms"]:
            if a["name"] in (
                "USDC_0",
                "USDC_4apy",
                "static_20pct",
                "hold_e1_m32",
                "derisk_ladder",
                "static_100pct",
            ):
                lines.append(
                    f"| {a['name']} | {a['total_return_pct']} | {a['max_dd_pct']} | {a['fired']} | {a['terminal_paxg_wt']} |"
                )
        lines.append("")

    lines += [
        "## Plain English",
        "- **Hold + E1−32%** matches static hold on paths that never reach −32% from entry (including the measured −28% 2026 episode if armed at that peak).",
        "- **DeRisk** sells into the hole; compare return/DD on ugly paths before ever enabling.",
        "- Behavioral value of Preserve remains: ballast while crypto parked — not gold day-trading.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(json.dumps(out["decisions"], indent=2))
    print("Wrote", OUT_JSON)
    print("Wrote", OUT_MD)


if __name__ == "__main__":
    main()
