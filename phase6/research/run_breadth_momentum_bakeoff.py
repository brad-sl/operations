#!/usr/bin/env python3
"""Breadth indicator bake-off B1–B4 on long daily OHLCV (real data only).

Paper Path A: when signal fires (and not bear), next-day equal-weight long of
liquid set (or top-k greens) vs stay-cash. No live orders.

See docs/research/MARKET_BREADTH_MOMENTUM_BREAKOUT_RESEARCH.md
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.market_breadth_breakout import (  # noqa: E402
    DEFAULT_BREADTH_UNIVERSE,
    breadth_from_returns,
)
from phase6.research.bull_reentry_layered import (  # noqa: E402
    rsi_series,
    rolling_return_pct,
    step_breakout_state,
)

LONG = ROOT / "backtests" / "data" / "long"
CACHE = ROOT / "data" / "state" / "breadth_bakeoff_ohlcv_cache"
OUT_JSON = ROOT / "data" / "state" / "breadth_momentum_bakeoff_latest.json"
OUT_MD = ROOT / "reports" / "BREADTH_MOMENTUM_BAKEOFF_LATEST.md"

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-breadth-bakeoff/1.0"}

# Map pair → local short name for long files
LOCAL_MAP = {
    "BTC-USD": "btc",
    "ETH-USD": "eth",
    "SOL-USD": "sol",
    "LINK-USD": "link",
    "AVAX-USD": "avax",
}

UNIVERSE = list(DEFAULT_BREADTH_UNIVERSE)
HORIZONS = (1, 3, 7)
BEAR_30D = -0.10
FEE_RT = 0.002  # 10 bps each way rough public taker-ish; conservative for small sleeve


@dataclass
class ArmResult:
    arm: str
    n_signals: int
    n_1d: int
    mean_1d: Optional[float]
    hit_1d: Optional[float]
    mean_3d: Optional[float]
    hit_3d: Optional[float]
    n_3d: int
    mean_7d: Optional[float]
    hit_7d: Optional[float]
    n_7d: int
    mean_1d_vs_bh: Optional[float]  # signal day EW basket hold
    false_alarm_rate_chop: Optional[float]  # signals on days where 7d forward EW < 0
    note: str = ""


def _sess() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_daily_product(pid: str, start: datetime, end: datetime) -> List[dict]:
    """Coinbase public daily candles → list of {date, open, high, low, close, volume}."""
    sess = _sess()
    gran = 86400
    out: List[list] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=280), end)
        params = {
            "granularity": gran,
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        try:
            r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=30)
        except Exception:
            break
        if r.status_code != 200:
            time.sleep(0.4)
            cursor = chunk_end
            continue
        rows = r.json() or []
        out.extend(rows)
        cursor = chunk_end
        time.sleep(0.15)
    # Coinbase: [time, low, high, open, close, volume]
    by_day: Dict[str, dict] = {}
    for row in out:
        if not row or len(row) < 6:
            continue
        ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc).date().isoformat()
        by_day[ts] = {
            "timestamp": ts + "T00:00:00Z",
            "open": float(row[3]),
            "high": float(row[2]),
            "low": float(row[1]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
    return [by_day[k] for k in sorted(by_day)]


def load_pair_daily(pid: str) -> List[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    short = LOCAL_MAP.get(pid)
    if short:
        p = LONG / f"ohlcv_daily_{short}.json"
        if p.exists():
            return json.loads(p.read_text())
    cache_p = CACHE / f"{pid.replace('-', '_').lower()}.json"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=900)
    if cache_p.exists():
        age_h = (time.time() - cache_p.stat().st_mtime) / 3600.0
        if age_h < 36:
            return json.loads(cache_p.read_text())
    rows = fetch_daily_product(pid, start, end)
    if rows:
        cache_p.write_text(json.dumps(rows))
    return rows


def to_series(rows: List[dict]) -> Tuple[List[date], Dict[date, float], Dict[date, float]]:
    days: List[date] = []
    close: Dict[date, float] = {}
    vol: Dict[date, float] = {}
    for r in rows:
        ts = str(r.get("timestamp") or "")[:10]
        try:
            d = date.fromisoformat(ts)
        except Exception:
            continue
        try:
            c = float(r["close"])
            v = float(r.get("volume") or 0.0)
        except Exception:
            continue
        if c <= 0:
            continue
        days.append(d)
        close[d] = c
        vol[d] = v
    days = sorted(set(days))
    return days, close, vol


def aligned_calendar(pair_data: Dict[str, Tuple[List[date], Dict[date, float], Dict[date, float]]]) -> List[date]:
    sets = [set(v[0]) for v in pair_data.values() if v[0]]
    if not sets:
        return []
    common = set.intersection(*sets)
    # Prefer BTC calendar as spine if available
    btc_days = pair_data.get("BTC-USD", ([], {}, {}))[0]
    if btc_days:
        return [d for d in btc_days if d in common or True]  # spine BTC; allow missing alts
    return sorted(common)


def fwd_ret(close: Dict[date, float], d: date, h: int, day_index: Dict[date, int], days: List[date]) -> Optional[float]:
    i = day_index.get(d)
    if i is None:
        return None
    j = i + h
    if j >= len(days):
        return None
    d2 = days[j]
    p0 = close.get(d)
    p1 = close.get(d2)
    if not p0 or not p1 or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def mean(xs: Sequence[Optional[float]]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None]
    return None if not vals else sum(vals) / len(vals)


def hit_rate(xs: Sequence[Optional[float]]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None]
    if not vals:
        return None
    return sum(1 for v in vals if v > 0) / len(vals)


def build_panel() -> dict:
    pair_data = {}
    for pid in UNIVERSE:
        rows = load_pair_daily(pid)
        pair_data[pid] = to_series(rows)
        print(f"  loaded {pid}: n={len(pair_data[pid][0])}", flush=True)

    btc_days, btc_c, btc_v = pair_data["BTC-USD"]
    # Use BTC spine from 2021-01-01 for stability
    start_cut = date(2021, 1, 1)
    days = [d for d in btc_days if d >= start_cut]
    day_index = {d: i for i, d in enumerate(days)}

    # Precompute daily rets and vol ratio
    ret1: Dict[str, Dict[date, float]] = {p: {} for p in UNIVERSE}
    vol_ratio: Dict[str, Dict[date, float]] = {p: {} for p in UNIVERSE}
    for pid, (p_days, p_c, p_v) in pair_data.items():
        p_idx = {d: i for i, d in enumerate(p_days)}
        for i, d in enumerate(p_days):
            if i == 0:
                continue
            prev = p_days[i - 1]
            c0, c1 = p_c.get(prev), p_c.get(d)
            if c0 and c1 and c0 > 0:
                ret1[pid][d] = c1 / c0 - 1.0
            # 7d median vol
            window = p_days[max(0, i - 7) : i]
            vols = [p_v.get(x, 0.0) for x in window if p_v.get(x, 0) > 0]
            med = sorted(vols)[len(vols) // 2] if vols else 0.0
            v = p_v.get(d, 0.0)
            vol_ratio[pid][d] = (v / med) if med > 0 else 0.0

    # BTC 30d return series + RSI + sticky breakout
    btc_day_list: List[date] = []
    btc_close_list: List[float] = []
    for d in days:
        if d in btc_c:
            btc_day_list.append(d)
            btc_close_list.append(btc_c[d])
    btc_px = {d: btc_c[d] for d in btc_day_list}
    rsi = rsi_series(btc_close_list, 14)
    rsi_by_day = {btc_day_list[i]: rsi[i] for i in range(len(btc_day_list))}

    brk_by_day: Dict[date, bool] = {}
    r30_by_day: Dict[date, Optional[float]] = {}
    brk_on = False
    for i, d in enumerate(btc_day_list):
        r30 = rolling_return_pct(btc_day_list, btc_px, i, 30)
        r14 = rolling_return_pct(btc_day_list, btc_px, i, 14)
        # rolling_return_pct returns percent points
        r30_by_day[d] = None if r30 is None else float(r30) / 100.0
        brk_on = step_breakout_state(
            prev_on=brk_on, days=btc_day_list, px=btc_px, i=i, r14=r14
        )
        brk_by_day[d] = brk_on

    return {
        "days": days,
        "day_index": day_index,
        "pair_data": pair_data,
        "ret1": ret1,
        "vol_ratio": vol_ratio,
        "rsi_by_day": rsi_by_day,
        "brk_by_day": brk_by_day,
        "r30_by_day": r30_by_day,
        "btc_c": btc_c,
    }


def ew_fwd(
    rets_today: Dict[str, float],
    panel: dict,
    d: date,
    h: int,
    names: Optional[Sequence[str]] = None,
) -> Optional[float]:
    """Equal-weight forward return of names (default all with data)."""
    days: List[date] = panel["days"]
    day_index = panel["day_index"]
    pair_data = panel["pair_data"]
    use = list(names) if names else list(UNIVERSE)
    xs = []
    for pid in use:
        close = pair_data[pid][1]
        fr = fwd_ret(close, d, h, day_index, days)
        if fr is not None:
            xs.append(fr)
    if not xs:
        return None
    return sum(xs) / len(xs)


def signal_B1(d: date, panel: dict, ret_min: float = 0.03, k: int = 4) -> Tuple[bool, List[str]]:
    rets = {p: panel["ret1"][p][d] for p in UNIVERSE if d in panel["ret1"][p]}
    b = breadth_from_returns(rets, universe=UNIVERSE, ret_min=ret_min, k=k)
    return b.breadth_on, b.green_pairs


def signal_B2(d: date, panel: dict, med_min: float = 0.025) -> Tuple[bool, List[str]]:
    rets = [panel["ret1"][p][d] for p in UNIVERSE if d in panel["ret1"][p]]
    if len(rets) < 5:
        return False, []
    med = sorted(rets)[len(rets) // 2]
    greens = [p for p in UNIVERSE if panel["ret1"][p].get(d, -1) >= 0.01]
    return med >= med_min, greens


def signal_B3(d: date, panel: dict) -> Tuple[bool, List[str]]:
    brk = panel["brk_by_day"].get(d)
    rsi = panel["rsi_by_day"].get(d)
    b1, greens = signal_B1(d, panel, ret_min=0.02, k=3)
    on = bool(brk) and rsi is not None and 50 <= rsi <= 70 and b1
    return on, greens


def signal_B4(d: date, panel: dict, k: int = 4) -> Tuple[bool, List[str]]:
    hits = []
    for p in UNIVERSE:
        r = panel["ret1"][p].get(d)
        vr = panel["vol_ratio"][p].get(d, 0.0)
        if r is not None and r > 0 and vr >= 1.5:
            hits.append(p)
    return len(hits) >= k, hits


def is_bear(d: date, panel: dict) -> bool:
    r = panel["r30_by_day"].get(d)
    if r is None:
        return False
    return r <= BEAR_30D


def eval_arm(name: str, signal_fn, panel: dict) -> ArmResult:
    days: List[date] = panel["days"]
    # leave last 7 days for forward
    eval_days = days[:-8] if len(days) > 20 else days
    r1, r3, r7 = [], [], []
    vs_bh_1 = []
    fa_flags = []  # 1 if signal and 7d EW < 0
    n_sig = 0
    for d in eval_days:
        if is_bear(d, panel):
            continue
        on, greens = signal_fn(d)
        if not on:
            continue
        n_sig += 1
        # Path A sleeve: EW of green names if any else EW universe; net of round-trip fee once
        names = greens if greens else UNIVERSE
        f1 = ew_fwd({}, panel, d, 1, names)
        f3 = ew_fwd({}, panel, d, 3, names)
        f7 = ew_fwd({}, panel, d, 7, names)
        bh1 = ew_fwd({}, panel, d, 1, UNIVERSE)
        if f1 is not None:
            r1.append(f1 - FEE_RT)
        if f3 is not None:
            r3.append(f3 - FEE_RT)
        if f7 is not None:
            r7.append(f7 - FEE_RT)
            fa_flags.append(1.0 if f7 < 0 else 0.0)
        if f1 is not None and bh1 is not None:
            vs_bh_1.append((f1 - FEE_RT) - bh1)

    return ArmResult(
        arm=name,
        n_signals=n_sig,
        n_1d=len(r1),
        mean_1d=mean(r1),
        hit_1d=hit_rate(r1),
        mean_3d=mean(r3),
        hit_3d=hit_rate(r3),
        n_3d=len(r3),
        mean_7d=mean(r7),
        hit_7d=hit_rate(r7),
        n_7d=len(r7),
        mean_1d_vs_bh=mean(vs_bh_1),
        false_alarm_rate_chop=mean(fa_flags),
        note="excess vs cash after ~20bps RT fee; bear days skipped",
    )


def always_long_control(panel: dict) -> ArmResult:
    """Every non-bear day: EW universe next 1/3/7d (no fee on hold continuous approx fee once/year ignored)."""
    days: List[date] = panel["days"]
    eval_days = days[:-8]
    r1, r3, r7 = [], [], []
    for d in eval_days:
        if is_bear(d, panel):
            continue
        f1 = ew_fwd({}, panel, d, 1, UNIVERSE)
        f3 = ew_fwd({}, panel, d, 3, UNIVERSE)
        f7 = ew_fwd({}, panel, d, 7, UNIVERSE)
        if f1 is not None:
            r1.append(f1)
        if f3 is not None:
            r3.append(f3)
        if f7 is not None:
            r7.append(f7)
    return ArmResult(
        arm="C0_always_ew_nonbear",
        n_signals=len(r1),
        n_1d=len(r1),
        mean_1d=mean(r1),
        hit_1d=hit_rate(r1),
        mean_3d=mean(r3),
        hit_3d=hit_rate(r3),
        n_3d=len(r3),
        mean_7d=mean(r7),
        hit_7d=hit_rate(r7),
        n_7d=len(r7),
        mean_1d_vs_bh=0.0,
        false_alarm_rate_chop=None,
        note="control: always long EW liquid set on non-bear days (no fee)",
    )


def pick_primary(results: List[ArmResult]) -> dict:
    """Honest pick: need N_7d>=40, mean_7d>0, hit_7d>=0.45, beat cash (already), prefer lower FA."""
    scored = []
    for r in results:
        if r.arm.startswith("C0"):
            continue
        ok_n = (r.n_7d or 0) >= 40
        ok_m = (r.mean_7d or -1) > 0
        ok_h = (r.hit_7d or 0) >= 0.45
        # vs always-long: mean_7d should not be much worse — compare later
        score = 0.0
        if r.mean_7d is not None:
            score += r.mean_7d * 100
        if r.hit_7d is not None:
            score += (r.hit_7d - 0.5) * 10
        if r.false_alarm_rate_chop is not None:
            score -= r.false_alarm_rate_chop * 5
        scored.append((score, r, ok_n and ok_m and ok_h))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return {"status": "no_arms", "primary": None, "plain": "No arms evaluated."}
    best = scored[0][1]
    gate = scored[0][2]
    if not gate:
        return {
            "status": "no_primary_gate_fail",
            "primary": best.arm,
            "candidate_only": True,
            "plain": (
                f"Best by score is {best.arm} but fails high-confidence gate "
                f"(need N7≥40, mean7>0, hit7≥45%). Stay research/shadow — do not exploit live."
            ),
        }
    return {
        "status": "primary_candidate",
        "primary": best.arm,
        "candidate_only": True,  # still not live
        "plain": (
            f"{best.arm} clears offline gate on this tape (paper only). "
            f"Still requires paper would-fire collection before live."
        ),
    }


def pct(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{x*100:+.2f}%"


def main() -> int:
    print("Building panel (local long + Coinbase fetch for missing)...", flush=True)
    panel = build_panel()
    print(f"Days on BTC spine: {len(panel['days'])} ({panel['days'][0]} → {panel['days'][-1]})", flush=True)

    arms = [
        eval_arm("B1_breadth_thrust_3pct_k4", lambda d: signal_B1(d, panel, 0.03, 4), panel),
        eval_arm("B1b_breadth_2pct_k4", lambda d: signal_B1(d, panel, 0.02, 4), panel),
        eval_arm("B2_median_basket_2_5pct", lambda d: signal_B2(d, panel, 0.025), panel),
        eval_arm("B3_btc_breakout_rsi_breadth", lambda d: signal_B3(d, panel), panel),
        eval_arm("B4_vol_expand_cluster", lambda d: signal_B4(d, panel, 4), panel),
        always_long_control(panel),
    ]

    case_flags = {}
    for d in (date(2026, 8, 15), date(2026, 8, 16), date(2026, 8, 17), date(2026, 8, 18)):
        if d not in panel["days"]:
            continue
        b1_on, greens = signal_B1(d, panel)
        case_flags[str(d)] = {
            "B1": b1_on,
            "B2": signal_B2(d, panel)[0],
            "B3": signal_B3(d, panel)[0],
            "B4": signal_B4(d, panel)[0],
            "bear": is_bear(d, panel),
            "greens_B1": greens,
        }

    decision = pick_primary(arms)
    ctrl = next(a for a in arms if a.arm.startswith("C0"))

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "universe": UNIVERSE,
        "fee_rt": FEE_RT,
        "bear_veto_btc_30d": BEAR_30D,
        "range": {"start": str(panel["days"][0]), "end": str(panel["days"][-1]), "n_days": len(panel["days"])},
        "arms": [asdict(a) for a in arms],
        "decision": decision,
        "control_mean_7d": ctrl.mean_7d,
        "case_flags_aug2026": case_flags,
        "plain_english": decision.get("plain"),
        "honesty": (
            "Returns are mean per-signal forward EW of signal names vs cash after fee. "
            "Not portfolio APY. N sparse arms are inconclusive. "
            "Always-long control shows raw beta available on non-bear days — "
            "signal must beat cash with acceptable FA; beating always-long is bonus not required for paper shadow."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))

    lines = [
        "# Breadth momentum bake-off (B1–B4)",
        f"As of `{payload['as_of']}`",
        "",
        f"Tape: **{payload['range']['start']} → {payload['range']['end']}** ({payload['range']['n_days']} BTC daily bars). "
        f"Universe: {', '.join(UNIVERSE)}. Bear veto BTC 30d ≤ −10%. Fee RT ~{FEE_RT*10000:.0f} bps on signal entries.",
        "",
        "## Plain English",
        "",
        payload["plain_english"] or "",
        "",
        payload["honesty"],
        "",
        "## Scoreboard (mean forward return after fee vs **cash**)",
        "",
        "| Arm | N sig | 1d mean / hit / N | 3d mean / hit / N | 7d mean / hit / N | FA (7d<0) |",
        "|-----|------:|-------------------|-------------------|-------------------|----------|",
    ]
    for a in arms:
        lines.append(
            f"| `{a.arm}` | {a.n_signals} | {pct(a.mean_1d)} / {pct(a.hit_1d)} / {a.n_1d} | "
            f"{pct(a.mean_3d)} / {pct(a.hit_3d)} / {a.n_3d} | "
            f"{pct(a.mean_7d)} / {pct(a.hit_7d)} / {a.n_7d} | "
            f"{pct(a.false_alarm_rate_chop) if a.false_alarm_rate_chop is not None else 'n/a'} |"
        )
    lines += [
        "",
        f"Control always-EW non-bear 7d mean: **{pct(ctrl.mean_7d)}** (this is beta, not a trade signal).",
        "",
        "## Decision",
        "",
        f"- status: **{decision.get('status')}**",
        f"- primary: `{decision.get('primary')}`",
        f"- {decision.get('plain')}",
        "",
        "## Aug 2026 case flags (calendar days on tape)",
        "",
        "```json",
        json.dumps(case_flags, indent=2),
        "```",
        "",
        f"JSON: `{OUT_JSON}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    print(OUT_MD.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
