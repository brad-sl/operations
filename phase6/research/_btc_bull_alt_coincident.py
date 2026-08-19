#!/usr/bin/env python3
"""BTC-bull days: do ETH/SOL/XRP/XLM move with BTC?"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LONG = ROOT / "backtests" / "data" / "long"
DATA = ROOT / "backtests" / "data"


def load_closes(symbol: str) -> dict[date, float]:
    cands = [
        LONG / f"ohlcv_daily_{symbol}.json",
        DATA / f"ohlcv_daily_{symbol}.json",
    ]
    cands += list(DATA.rglob(f"*ohlcv*{symbol}*.json"))
    cands += list(LONG.glob(f"*{symbol}*.json"))
    path = next((p for p in cands if p.exists()), None)
    if not path:
        return {}
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = raw.get("candles") or raw.get("data") or raw.get("ohlcv") or []
    out: dict[date, float] = {}
    for r in raw:
        ts = str(r.get("timestamp") or r.get("time") or "")[:10]
        try:
            out[date.fromisoformat(ts)] = float(r["close"])
        except Exception:
            continue
    return out


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    n = len(xs)
    m = sum(xs) / n
    eq = 1.0
    for x in xs:
        eq *= 1.0 + x
    pos = sum(1 for x in xs if x > 0) / n
    return {
        "n": n,
        "mean_day_pct": round(m * 100, 4),
        "compound_pct": round((eq - 1) * 100, 2),
        "pct_up_days": round(pos * 100, 1),
    }


def main() -> None:
    series = {s: load_closes(s) for s in ("btc", "eth", "sol", "xrp", "xlm", "link")}
    cover = {
        k: {
            "n": len(v),
            "start": min(v).isoformat() if v else None,
            "end": max(v).isoformat() if v else None,
        }
        for k, v in series.items()
    }
    btc = series["btc"]
    days = sorted(btc)
    lookback = 30
    bull_th, bear_th, flat_th = 15.0, -10.0, 8.0

    def classify(ret: float) -> str:
        if ret >= bull_th:
            return "bull"
        if ret <= bear_th:
            return "bear"
        if abs(ret) <= flat_th:
            return "flat"
        return "transition"

    reg: dict[date, dict] = {}
    for i, d in enumerate(days):
        if i < lookback:
            continue
        start = d - timedelta(days=lookback)
        win = [(dd, btc[dd]) for dd in days if start <= dd <= d]
        if len(win) < 5:
            continue
        p0, p1 = win[0][1], win[-1][1]
        ret = (p1 / p0 - 1) * 100 if p0 else 0.0
        prev = days[i - 1]
        day_ret = btc[d] / btc[prev] - 1 if btc.get(prev) else None
        reg[d] = {"regime": classify(ret), "btc_day": day_ret}

    out: dict = {"coverage": cover, "on_btc_bull_days": {}}
    btc_bull = [info["btc_day"] for d, info in reg.items() if info["regime"] == "bull" and info["btc_day"] is not None]
    out["on_btc_bull_days"]["btc"] = stats(btc_bull)

    for alt in ("eth", "sol", "xrp", "xlm", "link"):
        s = series[alt]
        if len(s) < 100:
            out["on_btc_bull_days"][alt] = {"missing": True, "n_closes": len(s)}
            continue
        adays = sorted(s)
        arets = []
        pb, pa = [], []
        for i, d in enumerate(adays):
            if d not in reg or reg[d]["regime"] != "bull":
                continue
            if i == 0:
                continue
            prev = adays[i - 1]
            if prev not in s or not s[prev]:
                continue
            if reg[d]["btc_day"] is None:
                continue
            # only if prev and d are consecutive in alt series near calendar
            if (d - prev).days > 3:
                continue
            ar = s[d] / s[prev] - 1
            arets.append(ar)
            pb.append(reg[d]["btc_day"])
            pa.append(ar)
        st = stats(arets)
        if len(pb) >= 20:
            mb = sum(pb) / len(pb)
            ma = sum(pa) / len(pa)
            num = sum((b - mb) * (a - ma) for b, a in zip(pb, pa))
            db = math.sqrt(sum((b - mb) ** 2 for b in pb))
            da = math.sqrt(sum((a - ma) ** 2 for a in pa))
            corr = num / (db * da) if db and da else None
            varb = sum((b - mb) ** 2 for b in pb) / len(pb)
            cov = num / len(pb)
            st["corr_vs_btc_day"] = round(corr, 3) if corr is not None else None
            st["beta_vs_btc"] = round(cov / varb, 3) if varb else None
            btc_up = sum(1 for b in pb if b > 0)
            both = sum(1 for b, a in zip(pb, pa) if b > 0 and a > 0)
            st["alt_up_given_btc_up_pct"] = round(both / btc_up * 100, 1) if btc_up else None
        # alt own 30d also bull when btc bull?
        agree = n = 0
        for d, info in reg.items():
            if info["regime"] != "bull":
                continue
            start = d - timedelta(days=30)
            win = [(dd, s[dd]) for dd in adays if start <= dd <= d and dd in s]
            if len(win) < 5:
                continue
            aret = (win[-1][1] / win[0][1] - 1) * 100
            n += 1
            if aret >= 15:
                agree += 1
        st["alt_30d_also_bull_when_btc_bull_pct"] = round(agree / n * 100, 1) if n else None
        st["alt_30d_check_n"] = n
        out["on_btc_bull_days"][alt] = st

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
