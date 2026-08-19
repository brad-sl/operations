#!/usr/bin/env python3
"""Squeeze→regime→confirm bake-off vs sticky breakout (real daily OHLCV).

Paper only. Spec: docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.bull_reentry_layered import (  # noqa: E402
    regime_label_from_ret30,
    rolling_return_pct,
    rsi_series,
    step_breakout_state,
)
from phase6.research.market_breadth_breakout import DEFAULT_BREADTH_UNIVERSE  # noqa: E402
from phase6.research.run_breadth_momentum_bakeoff import load_pair_daily  # noqa: E402
from phase6.research.squeeze_regime_breakout import (  # noqa: E402
    atr_series,
    bb_width_series,
    coil_then_breadth_fire,
    compression_recent,
    evaluate_bar,
)

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
FEE_RT = 0.002
HORIZONS = (1, 3, 7)


def bars_from_rows(rows: List[dict]) -> Tuple[List[date], List[float], List[float], List[float], List[float], List[float]]:
    days, o, h, l, c, v = [], [], [], [], [], []
    for r in sorted(rows, key=lambda x: str(x.get("timestamp") or x.get("date") or "")):
        ts = str(r.get("timestamp") or r.get("date") or "")[:10]
        try:
            d = date.fromisoformat(ts)
        except Exception:
            continue
        try:
            oo, hh, ll, cc = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            vv = float(r.get("volume") or 0.0)
        except Exception:
            continue
        days.append(d)
        o.append(oo)
        h.append(hh)
        l.append(ll)
        c.append(cc)
        v.append(vv)
    return days, o, h, l, c, v


def fwd_ret(closes: Sequence[float], i: int, h: int) -> Optional[float]:
    j = i + h
    if j >= len(closes) or closes[i] <= 0:
        return None
    return closes[j] / closes[i] - 1.0


def summarize(rets: List[float]) -> Dict[str, Any]:
    if not rets:
        return {"n": 0, "mean": None, "hit": None}
    return {
        "n": len(rets),
        "mean": sum(rets) / len(rets),
        "hit": sum(1 for r in rets if r > 0) / len(rets),
    }


def false_break_rate(rets_3d: List[float], side_up: bool = True) -> Optional[float]:
    """Share of signals where 3d move is against break direction."""
    if not rets_3d:
        return None
    if side_up:
        bad = sum(1 for r in rets_3d if r < 0)
    else:
        bad = sum(1 for r in rets_3d if r > 0)
    return bad / len(rets_3d)


def b4_on_day(
    day: date,
    rets: Dict[str, Dict[date, float]],
    vols: Dict[str, Dict[date, float]],
    vol_med: Dict[str, float],
    k: int = 4,
) -> bool:
    hits = 0
    for pid in DEFAULT_BREADTH_UNIVERSE:
        r = (rets.get(pid) or {}).get(day)
        v = (vols.get(pid) or {}).get(day)
        med = vol_med.get(pid) or 0.0
        if r is not None and r > 0 and v is not None and med > 0 and v >= 1.5 * med:
            hits += 1
    return hits >= k


def main() -> int:
    btc_rows = load_pair_daily("BTC-USD")
    days, o, h, l, c, vol = bars_from_rows(btc_rows)
    if len(days) < 200:
        print("insufficient BTC bars", len(days))
        return 1

    px = {days[i]: c[i] for i in range(len(days))}
    atrs = atr_series(h, l, c)
    widths = bb_width_series(c)
    rsi = rsi_series(c, 14)

    # sticky breakout path
    br_on = False
    breakout_flags = [False] * len(days)
    r14s: List[Optional[float]] = [None] * len(days)
    r30s: List[Optional[float]] = [None] * len(days)
    regimes: List[str] = ["unknown"] * len(days)
    for i in range(len(days)):
        r14s[i] = rolling_return_pct(days, px, i, 14)
        r30s[i] = rolling_return_pct(days, px, i, 30)
        regimes[i] = regime_label_from_ret30(r30s[i])
        br_on = step_breakout_state(prev_on=br_on, days=days, px=px, i=i, r14=r14s[i])
        breakout_flags[i] = br_on

    # liquid panel for B4 / EW control
    liq_close: Dict[str, Dict[date, float]] = {}
    liq_vol: Dict[str, Dict[date, float]] = {}
    for pid in DEFAULT_BREADTH_UNIVERSE:
        dd, oo, hh, ll, cc, vv = bars_from_rows(load_pair_daily(pid))
        liq_close[pid] = {dd[i]: cc[i] for i in range(len(dd))}
        liq_vol[pid] = {dd[i]: vv[i] for i in range(len(dd))}
    # daily rets + vol median
    liq_ret: Dict[str, Dict[date, float]] = {}
    vol_med: Dict[str, float] = {}
    for pid, cmap in liq_close.items():
        ds = sorted(cmap)
        rd: Dict[date, float] = {}
        for i in range(1, len(ds)):
            if cmap[ds[i - 1]] > 0:
                rd[ds[i]] = cmap[ds[i]] / cmap[ds[i - 1]] - 1.0
        liq_ret[pid] = rd
        vs = [liq_vol[pid][d] for d in ds if liq_vol[pid].get(d)]
        vs_sorted = sorted(vs)
        vol_med[pid] = vs_sorted[len(vs_sorted) // 2] if vs_sorted else 0.0

    def ew_fwd(i: int, horizon: int) -> Optional[float]:
        d0 = days[i]
        rets = []
        for pid in DEFAULT_BREADTH_UNIVERSE:
            cmap = liq_close[pid]
            # find index by scanning — map day list per pid expensive; use date+horizon calendar match on BTC days
            if d0 not in cmap:
                continue
            # forward by horizon BTC sessions
            j = i + horizon
            if j >= len(days):
                continue
            d1 = days[j]
            if d1 not in cmap or cmap[d0] <= 0:
                continue
            rets.append(cmap[d1] / cmap[d0] - 1.0)
        if not rets:
            return None
        return sum(rets) / len(rets)

    arms_signals: Dict[str, List[int]] = {
        "C0_breakout_sticky": [],
        "C0b_breakout_rsi": [],
        "S1_squeeze_break_confirm": [],
        "S2_regime": [],
        "S3_regime_eff": [],
        "S3b_regime_eff_rsi": [],
        "M2_coil_then_b4": [],
        "BH_btc_always": [],
        "BH_ew_always": [],
    }
    coil_days = 0

    for i in range(120, len(days) - max(HORIZONS) - 1):
        reg = regimes[i]
        # skip early / incomplete
        sig = evaluate_bar(
            opens=o, highs=h, lows=l, closes=c, volumes=vol, i=i, regime=reg, widths=widths, atrs=atrs
        )
        if sig.compression_on:
            coil_days += 1
        rsi_ok = rsi[i] is not None and 50.0 <= float(rsi[i] or 0) <= 70.0
        if rsi[i] is None:
            rsi_ok = False

        if breakout_flags[i] and reg != "bear":
            arms_signals["C0_breakout_sticky"].append(i)
            if rsi_ok:
                arms_signals["C0b_breakout_rsi"].append(i)
        if sig.s1_up:
            arms_signals["S1_squeeze_break_confirm"].append(i)
        if sig.s2_up:
            arms_signals["S2_regime"].append(i)
        if sig.s3_up:
            arms_signals["S3_regime_eff"].append(i)
            if rsi_ok:
                arms_signals["S3b_regime_eff_rsi"].append(i)

        b4 = b4_on_day(days[i], liq_ret, liq_vol, vol_med)
        if coil_then_breadth_fire(
            compression_recent_on=sig.compression_recent, breadth_on=b4, regime=reg
        ):
            arms_signals["M2_coil_then_b4"].append(i)

        arms_signals["BH_btc_always"].append(i)
        arms_signals["BH_ew_always"].append(i)

    # dedupe BH is every day — OK
    results = []
    for name, idxs in arms_signals.items():
        # unique preserve order
        seen = set()
        uidx = []
        for i in idxs:
            if i not in seen:
                seen.add(i)
                uidx.append(i)
        # entry: next bar open approx = use close[i] → fwd from i (signal at close)
        bucket: Dict[int, List[float]] = {h: [] for h in HORIZONS}
        fb: List[float] = []
        by_reg: Dict[str, List[float]] = {}
        for i in uidx:
            for hz in HORIZONS:
                if name.startswith("BH_ew") or name.startswith("M2"):
                    r = ew_fwd(i, hz)
                else:
                    r = fwd_ret(c, i, hz)
                if r is None:
                    continue
                r_net = r - FEE_RT
                bucket[hz].append(r_net)
                if hz == 7:
                    by_reg.setdefault(regimes[i], []).append(r_net)
                if hz == 3:
                    fb.append(r_net)
        row = {
            "arm": name,
            "n_signals": len(uidx),
            "compression_days_in_sample": coil_days,
            "false_break_3d": false_break_rate(fb, True) if not name.startswith("BH") else None,
            "by_horizon": {str(hz): summarize(bucket[hz]) for hz in HORIZONS},
            "by_regime_7d": {k: summarize(v) for k, v in sorted(by_reg.items())},
        }
        results.append(row)

    # decision
    def mean7(row):
        m = row["by_horizon"]["7"]["mean"]
        return m if m is not None else -9.0

    def n7(row):
        return row["by_horizon"]["7"]["n"]

    candidates = [r for r in results if r["arm"].startswith("S") or r["arm"].startswith("M2")]
    controls = {r["arm"]: r for r in results}
    best = max(candidates, key=mean7) if candidates else None
    c0b = controls.get("C0b_breakout_rsi")
    bh = controls.get("BH_btc_always")
    exploit = False
    primary = None
    if best and n7(best) >= 40 and mean7(best) > 0:
        if c0b and mean7(best) > mean7(c0b) and bh and mean7(best) >= mean7(bh) - 0.002:
            # modest bar: beat layered re-entry timing and not much worse than always long
            exploit = False  # still paper — never auto true without Brad
            primary = best["arm"]
        else:
            primary = best["arm"]

    plain_parts = []
    if best:
        plain_parts.append(
            f"Best squeeze-family arm on 7d: {best['arm']} mean={mean7(best)*100:+.2f}% N={n7(best)} "
            f"FB3d={best.get('false_break_3d')}"
        )
    if c0b:
        plain_parts.append(
            f"C0b breakout+RSI 7d mean={mean7(c0b)*100:+.2f}% N={n7(c0b)}"
        )
    if bh:
        plain_parts.append(f"BH BTC always 7d mean={mean7(bh)*100:+.2f}%")
    plain_parts.append(
        "Squeeze stack is setup+confirm research; exploit_ready stays false until Brad + stability checks."
    )
    decision = {
        "primary_paper": primary,
        "exploit_ready": False,
        "plain": " ".join(plain_parts),
    }

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "asset": "BTC-USD primary; EW liquid for M2/BH_ew",
        "n_bars": len(days),
        "fee_rt": FEE_RT,
        "arms": results,
        "decision": decision,
    }
    STATE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    STATE.joinpath("squeeze_regime_breakout_bakeoff_latest.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )

    lines = [
        "# Squeeze → regime → confirm bake-off",
        f"As of `{payload['as_of']}`",
        "",
        "## Plain English",
        "",
        decision["plain"],
        "",
        "## Arms (net of ~20bps RT fee)",
        "",
        "| Arm | N | 1d mean/hit | 3d mean/hit | 7d mean/hit | FB 3d |",
        "|-----|--:|------------|------------|------------|------:|",
    ]

    def cell(h):
        s = h
        if not s or s.get("n") == 0:
            return "—"
        return f"{100*s['mean']:+.2f}% / {100*s['hit']:.0f}% (n={s['n']})"

    for r in results:
        bh1, bh3, bh7 = r["by_horizon"]["1"], r["by_horizon"]["3"], r["by_horizon"]["7"]
        fb = r.get("false_break_3d")
        fbs = f"{100*fb:.0f}%" if fb is not None else "—"
        lines.append(
            f"| `{r['arm']}` | {r['n_signals']} | {cell(bh1)} | {cell(bh3)} | {cell(bh7)} | {fbs} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        f"- primary_paper: `{decision['primary_paper']}`",
        f"- exploit_ready: **{decision['exploit_ready']}**",
        "",
        "Spec: `docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md`",
        "JSON: `data/state/squeeze_regime_breakout_bakeoff_latest.json`",
        "",
    ]
    REPORTS.joinpath("SQUEEZE_REGIME_BREAKOUT_BAKEOFF_LATEST.md").write_text("\n".join(lines) + "\n")
    print(decision["plain"])
    for r in results:
        print(r["arm"], r["n_signals"], r["by_horizon"]["7"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
