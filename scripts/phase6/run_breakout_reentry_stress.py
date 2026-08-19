#!/usr/bin/env python3
"""Offline stress: breakout re-entry vs 30d/15 vs flat B; layered vs current policy.

Real OHLCV only. Path-B style timing on BTC; risk sleeve = equal-weight multi-pair
basket with policy cap (USD). Rest of book in USDC at configured APY.

Not a promotion gate — research artifact for Brad.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research import regime_detector as rd  # noqa: E402

OUT_JSON = ROOT / "data/state/analyst_breakout_reentry_stress_latest.json"
OUT_MD = ROOT / "reports/BREAKOUT_REENTRY_STRESS_2026-07-30.md"

PAIRS = [
    "btc",
    "eth",
    "sol",
    "avax",
    "link",
    "doge",
    "arb",
]
USDC_APY = 0.035
INITIAL = 1000.0
FLAT_B_CAP = 75.0
BULL_CAP = 200.0
FEE_BPS = 10  # 0.10% round-trip-ish on sleeve rebalance days only


def _parse_bar(row: Any) -> Optional[Tuple[date, float]]:
    if isinstance(row, dict):
        ds = row.get("date") or row.get("time") or row.get("t")
        c = row.get("close") or row.get("c") or row.get("Close")
        if ds is None or c is None:
            return None
        if isinstance(ds, str):
            d = date.fromisoformat(ds[:10])
        else:
            return None
        return d, float(c)
    return None


def load_pair_closes(pair: str) -> Dict[date, float]:
    data_dir = ROOT / "backtests/data"
    patterns = [
        f"backtest_historical_ohlcv_{pair}_*.json",
        f"backtest_historical_ohlcv_{pair.upper()}_*.json",
        f"backtest_historical_ohlcv_{pair.upper()}-USD_*.json",
    ]
    paths: List[Path] = []
    for pat in patterns:
        paths.extend(data_dir.glob(pat))
    if not paths:
        return {}
    path = sorted(paths, key=lambda p: p.stat().st_mtime)[-1]
    blob = json.loads(path.read_text())
    series = blob if isinstance(blob, list) else blob.get(f"{pair.upper()}-USD") or blob.get(pair) or []
    out: Dict[date, float] = {}
    for row in series:
        parsed = _parse_bar(row)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def load_universe() -> Tuple[List[date], Dict[str, Dict[date, float]], Dict[str, Any]]:
    books = {p: load_pair_closes(p) for p in PAIRS}
    btc_list, meta = rd._merge_live_close(rd._load_btc_closes())
    btc = {d: c for d, c in btc_list}
    books["btc"] = btc
    # common calendar: intersection where BTC exists; pairs optional forward-fill later
    days = sorted(btc.keys())
    return days, books, meta


def rsi_at(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains[i] = max(ch, 0.0)
        losses[i] = max(-ch, 0.0)
    for i in range(period, len(closes)):
        ag = sum(gains[i - period + 1 : i + 1]) / period
        al = sum(losses[i - period + 1 : i + 1]) / period
        if al <= 1e-12:
            out[i] = 100.0
        else:
            rs = ag / al
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def rolling_ret(days: List[date], px: Dict[date, float], i: int, lookback_days: int) -> Optional[float]:
    d = days[i]
    target = d - timedelta(days=lookback_days)
    j = i
    while j > 0 and days[j] > target:
        j -= 1
    p0 = px[days[j]]
    p1 = px[d]
    if p0 <= 0:
        return None
    return (p1 / p0 - 1.0) * 100.0


def at_nd_high(days: List[date], px: Dict[date, float], i: int, n: int = 30) -> bool:
    lo = max(0, i - n + 1)
    window = [px[days[k]] for k in range(lo, i + 1)]
    return px[days[i]] >= max(window) * 0.999


@dataclass
class DaySignal:
    d: str
    btc_ret_30: Optional[float]
    btc_ret_14: Optional[float]
    btc_ret_5: Optional[float]
    rsi: Optional[float]
    at_30d_high: bool
    breakout_on: bool
    regime_label: str  # bull/bear/flat/transition via 30/15/-10/8


def build_signals(days: List[date], btc: Dict[date, float]) -> List[DaySignal]:
    closes = [btc[d] for d in days]
    rsis = rsi_at(closes, 14)
    sigs: List[DaySignal] = []
    breakout_state = False
    for i, d in enumerate(days):
        r30 = rolling_ret(days, btc, i, 30) if i >= 5 else None
        r14 = rolling_ret(days, btc, i, 14) if i >= 5 else None
        r5 = rolling_ret(days, btc, i, 5) if i >= 5 else None
        rsi = rsis[i]
        hi = at_nd_high(days, btc, i, 30) if i >= 30 else False
        # breakout machine: enter new 30d high + r14>0; exit close < 20d low or r14<-5
        if i >= 30:
            w20 = [btc[days[k]] for k in range(i - 19, i + 1)]
            px = btc[d]
            new_high = px >= max(btc[days[k]] for k in range(i - 29, i))  # break prior 30d excl today
            if not breakout_state:
                if new_high and (r14 or 0) > 0:
                    breakout_state = True
            else:
                if px < min(w20) or (r14 is not None and r14 < -5):
                    breakout_state = False
        # regime label
        if r30 is None:
            lab = "unknown"
        elif r30 >= 15:
            lab = "bull"
        elif r30 <= -10:
            lab = "bear"
        elif abs(r30) <= 8:
            lab = "flat"
        else:
            lab = "transition"
        sigs.append(
            DaySignal(
                d=d.isoformat(),
                btc_ret_30=None if r30 is None else round(r30, 3),
                btc_ret_14=None if r14 is None else round(r14, 3),
                btc_ret_5=None if r5 is None else round(r5, 3),
                rsi=None if rsi is None else round(rsi, 2),
                at_30d_high=hi,
                breakout_on=breakout_state,
                regime_label=lab,
            )
        )
    return sigs


PolicyFn = Callable[[DaySignal], float]  # returns cap_usd


def policy_current_regime(s: DaySignal) -> float:
    """Live-like REGIME-CASH caps (simplified: no RSI/sent pair gates)."""
    if s.regime_label == "bull":
        return BULL_CAP
    if s.regime_label == "flat":
        return FLAT_B_CAP
    # bear, transition, unknown → park
    return 0.0


def policy_only_3015(s: DaySignal) -> float:
    return BULL_CAP if (s.btc_ret_30 is not None and s.btc_ret_30 >= 15) else 0.0


def policy_flat_b_always(s: DaySignal) -> float:
    return FLAT_B_CAP


def policy_breakout_full(s: DaySignal) -> float:
    return BULL_CAP if s.breakout_on else 0.0


def policy_breakout_flat_size(s: DaySignal) -> float:
    return FLAT_B_CAP if s.breakout_on else 0.0


def policy_layered_brk_rsi_bear_flatb(s: DaySignal) -> float:
    """breakout + RSI band + bear veto + flat-B size; bull boost if 30/15."""
    if s.regime_label == "bear" or (s.btc_ret_30 is not None and s.btc_ret_30 <= -10):
        return 0.0
    if s.btc_ret_30 is not None and s.btc_ret_30 >= 15:
        return BULL_CAP
    rsi = s.rsi
    if s.breakout_on and rsi is not None and 50.0 <= rsi <= 70.0:
        return FLAT_B_CAP
    return 0.0


def policy_layered_pure_no_bull_boost(s: DaySignal) -> float:
    """Strict user combo without 30/15 boost."""
    if s.regime_label == "bear" or (s.btc_ret_30 is not None and s.btc_ret_30 <= -10):
        return 0.0
    rsi = s.rsi
    if s.breakout_on and rsi is not None and 50.0 <= rsi <= 70.0:
        return FLAT_B_CAP
    return 0.0


def policy_breakout_rsi_band_bear_veto_bullcap(s: DaySignal) -> float:
    """Breakout re-entry at bull size, RSI band, bear veto."""
    if s.regime_label == "bear" or (s.btc_ret_30 is not None and s.btc_ret_30 <= -10):
        return 0.0
    rsi = s.rsi
    if s.breakout_on and rsi is not None and 50.0 <= rsi <= 70.0:
        return BULL_CAP
    return 0.0


def basket_return(
    days: List[date],
    books: Dict[str, Dict[date, float]],
    i: int,
) -> Optional[float]:
    """Equal-weight daily return of pairs with prices on day i-1 and i."""
    if i <= 0:
        return 0.0
    d0, d1 = days[i - 1], days[i]
    rets = []
    for p, series in books.items():
        if d0 in series and d1 in series and series[d0] > 0:
            rets.append(series[d1] / series[d0] - 1.0)
    if not rets:
        return None
    return sum(rets) / len(rets)


@dataclass
class SimResult:
    policy_id: str
    label: str
    window: str
    start: str
    end: str
    total_return_pct: float
    max_drawdown_pct: float
    time_in_market_pct: float
    mean_cap_usd: float
    median_cap_usd: float
    days: int
    deploy_days: int
    cap_changes: int
    usdc_drag_note: str = "idle cash @ USDC_APY"
    final_equity: float = 0.0


def run_sim(
    policy_id: str,
    label: str,
    days: List[date],
    books: Dict[str, Dict[date, float]],
    sigs: List[DaySignal],
    policy: PolicyFn,
    start: date,
    end: date,
    initial: float = INITIAL,
) -> SimResult:
    idx = [i for i, d in enumerate(days) if start <= d <= end]
    if len(idx) < 5:
        return SimResult(
            policy_id=policy_id,
            label=label,
            window=f"{start}..{end}",
            start=start.isoformat(),
            end=end.isoformat(),
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            time_in_market_pct=0.0,
            mean_cap_usd=0.0,
            median_cap_usd=0.0,
            days=len(idx),
            deploy_days=0,
            cap_changes=0,
            final_equity=initial,
        )

    cash = initial
    # sleeve: notional crypto marked daily; target_cap from policy
    sleeve = 0.0
    prev_cap = 0.0
    equity_curve = []
    caps = []
    deploy_days = 0
    cap_changes = 0
    daily_usdc = USDC_APY / 365.0

    for j, i in enumerate(idx):
        d = days[i]
        s = sigs[i]
        cap = float(policy(s))
        caps.append(cap)
        if cap > 1e-6:
            deploy_days += 1
        if j > 0 and abs(cap - prev_cap) > 1e-6:
            cap_changes += 1
        # grow cash (non-sleeve) at USDC
        # sleeve earns basket return
        if j > 0:
            br = basket_return(days, books, i)
            if sleeve > 0 and br is not None:
                sleeve *= 1.0 + br
            idle = max(0.0, cash)  # cash is idle USD
            cash = idle * (1.0 + daily_usdc)

        # rebalance sleeve toward cap (use total equity)
        equity = cash + sleeve
        target = min(cap, equity * 0.95)  # never deploy more than 95% book
        # If equity small, cap is absolute dollars of risk budget
        delta = target - sleeve
        if abs(delta) > 1.0:  # $1 threshold
            fee = abs(delta) * (FEE_BPS / 10000.0)
            if delta > 0:
                # buy sleeve from cash
                spend = min(delta + fee, cash)
                if spend > fee:
                    sleeve += spend - fee
                    cash -= spend
            else:
                # sell sleeve to cash
                sell = min(-delta, sleeve)
                sleeve -= sell
                cash += sell - fee
        prev_cap = cap
        equity_curve.append(cash + sleeve)

    final = equity_curve[-1] if equity_curve else initial
    # max DD
    peak = equity_curve[0]
    mdd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        dd = e / peak - 1.0
        mdd = min(mdd, dd)

    return SimResult(
        policy_id=policy_id,
        label=label,
        window=f"{start.isoformat()}..{end.isoformat()}",
        start=start.isoformat(),
        end=end.isoformat(),
        total_return_pct=round((final / initial - 1.0) * 100.0, 3),
        max_drawdown_pct=round(mdd * 100.0, 3),
        time_in_market_pct=round(100.0 * deploy_days / max(len(idx), 1), 2),
        mean_cap_usd=round(mean(caps), 2) if caps else 0.0,
        median_cap_usd=round(median(caps), 2) if caps else 0.0,
        days=len(idx),
        deploy_days=deploy_days,
        cap_changes=cap_changes,
        final_equity=round(final, 2),
    )


WINDOWS = [
    ("full_sample", date(2025, 6, 1), date(2026, 7, 30)),
    ("bull_ex", date(2025, 10, 1), date(2025, 12, 31)),
    ("bear_stress", date(2025, 8, 1), date(2025, 9, 30)),
    ("flat_chop", date(2026, 1, 1), date(2026, 3, 31)),
    ("recent", date(2026, 2, 1), date(2026, 7, 30)),
    ("live_overlap", date(2026, 4, 20), date(2026, 7, 30)),
]


PACK_A = [
    ("breakout_reentry_cap200", "Breakout ON → cap $200", policy_breakout_full),
    ("breakout_reentry_cap75", "Breakout ON → cap $75 (flat-B size)", policy_breakout_flat_size),
    ("current_30d15_only", "Only 30d≥15% → cap $200 (else park)", policy_only_3015),
    ("flat_b_always", "Always flat B cap $75", policy_flat_b_always),
]

PACK_B = [
    (
        "layered_brk_rsi_bear_flatb_bullboost",
        "Bear veto + breakout&RSI[50,70]@$75 + 30d≥15@$200",
        policy_layered_brk_rsi_bear_flatb,
    ),
    (
        "layered_pure_brk_rsi_bear_flatb",
        "Bear veto + breakout&RSI[50,70]@$75 only",
        policy_layered_pure_no_bull_boost,
    ),
    (
        "layered_brk_rsi_bear_bullcap",
        "Bear veto + breakout&RSI[50,70]@$200",
        policy_breakout_rsi_band_bear_veto_bullcap,
    ),
    ("current_policy_regime_cash", "Current REGIME-CASH caps (bull200/flat75/else0)", policy_current_regime),
]


def _rank_window(rows: List[SimResult]) -> List[Dict[str, Any]]:
    # prefer higher return, then lower |DD|
    ordered = sorted(rows, key=lambda r: (-r.total_return_pct, r.max_drawdown_pct))
    out = []
    for i, r in enumerate(ordered, 1):
        d = asdict(r)
        d["rank_return"] = i
        out.append(d)
    return out


def go_no_go(pack_a_by_win: Dict[str, List[dict]], pack_b_by_win: Dict[str, List[dict]]) -> Dict[str, Any]:
    """Plain-English gates from live_overlap + full_sample + bear."""
    def pick(win: str, pid: str, pack: Dict[str, List[dict]]) -> Optional[dict]:
        for r in pack.get(win) or []:
            if r["policy_id"] == pid:
                return r
        return None

    lo_a = {r["policy_id"]: r for r in pack_a_by_win.get("live_overlap") or []}
    lo_b = {r["policy_id"]: r for r in pack_b_by_win.get("live_overlap") or []}
    full_b = {r["policy_id"]: r for r in pack_b_by_win.get("full_sample") or []}
    bear_b = {r["policy_id"]: r for r in pack_b_by_win.get("bear_stress") or []}
    cur = lo_b.get("current_policy_regime_cash") or {}
    layer = lo_b.get("layered_brk_rsi_bear_flatb_bullboost") or {}
    pure = lo_b.get("layered_pure_brk_rsi_bear_flatb") or {}
    brk = lo_a.get("breakout_reentry_cap75") or {}
    only = lo_a.get("current_30d15_only") or {}
    flat = lo_a.get("flat_b_always") or {}

    decisions = []

    def dec(name: str, ok: bool, why: str):
        decisions.append({"name": name, "go": ok, "why": why})

    # Pack A
    if brk and only and flat:
        # breakout vs 30/15: need better ret or much better DD on live_overlap without bear blowup
        dec(
            "promote_breakout_over_30d15",
            brk["total_return_pct"] > only["total_return_pct"] + 0.5
            and brk["max_drawdown_pct"] >= only["max_drawdown_pct"] - 5,
            f"live_overlap breakout75 ret={brk['total_return_pct']} dd={brk['max_drawdown_pct']} vs 30/15 ret={only['total_return_pct']} dd={only['max_drawdown_pct']}",
        )
        dec(
            "promote_flat_b_always",
            False,  # never auto — always-on risk
            f"flat_b always is baseline sleeve not a timing edge; live_overlap ret={flat['total_return_pct']} dd={flat['max_drawdown_pct']}",
        )
    # Pack B
    if layer and cur:
        better = (
            layer["total_return_pct"] >= cur["total_return_pct"] - 0.25
            and layer["max_drawdown_pct"] >= cur["max_drawdown_pct"] - 2
        )
        # also check full sample not much worse DD
        fl = full_b.get("layered_brk_rsi_bear_flatb_bullboost")
        fc = full_b.get("current_policy_regime_cash")
        full_ok = True
        if fl and fc:
            full_ok = fl["max_drawdown_pct"] >= fc["max_drawdown_pct"] - 5
        bear_l = bear_b.get("layered_brk_rsi_bear_flatb_bullboost")
        bear_ok = True if not bear_l else bear_l["max_drawdown_pct"] >= -15
        dec(
            "shadow_layered_vs_current",
            bool(better and full_ok and bear_ok),
            f"live_overlap layer ret={layer.get('total_return_pct')} dd={layer.get('max_drawdown_pct')} vs cur ret={cur.get('total_return_pct')} dd={cur.get('max_drawdown_pct')}; full_ok={full_ok} bear_ok={bear_ok}",
        )
    if pure and cur:
        dec(
            "shadow_pure_layered_no_bullboost",
            pure.get("total_return_pct", -999) > cur.get("total_return_pct", 0) + 1
            and pure.get("max_drawdown_pct", -999) >= cur.get("max_drawdown_pct", 0) - 3,
            f"pure ret={pure.get('total_return_pct')} dd={pure.get('max_drawdown_pct')} vs cur",
        )

    return {"decisions": decisions, "live_overlap_snapshot": {"pack_a": lo_a, "pack_b": lo_b}}


def render_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Breakout re-entry stress — 2026-07-30",
        "",
        "**Status:** offline research only — not promoted to live REGIME-CASH",
        "",
        "## Method",
        "",
        "- Real multi-pair OHLCV (btc/eth/sol/avax/link/doge/arb), equal-weight sleeve",
        "- BTC drives timing (30d regime, breakout state, RSI-14)",
        "- Policy sets **USD cap** on crypto sleeve; idle cash earns USDC APY 3.5%",
        f"- Sleeve rebalance fee proxy: {FEE_BPS} bps on notion traded",
        "- **Gaps:** no per-pair RSI/sentiment gates, no SL path, no live fill slippage — Path B upper/mid bound",
        "",
        "### Breakout definition",
        "",
        "- **ON:** close makes new 30d high AND 14d return > 0",
        "- **OFF:** close < 20d low OR 14d return < −5%",
        "",
        "### RSI band",
        "",
        "- Enter-quality band: **50 ≤ RSI(14) ≤ 70** (not ‘any RSI>50’)",
        "",
        "## Pack A — breakout vs 30d/15 vs flat B",
        "",
    ]
    for win, rows in (payload.get("pack_a") or {}).items():
        lines.append(f"### Window `{win}`")
        lines.append("")
        lines.append("| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |")
        lines.append("|--------|------|--------|----------|-----------|-------------|-------------|")
        for r in rows:
            lines.append(
                f"| {r['policy_id']} | {r['total_return_pct']} | {r['max_drawdown_pct']} | "
                f"{r['time_in_market_pct']} | {r['mean_cap_usd']} | {r['deploy_days']} | {r['cap_changes']} |"
            )
        lines.append("")
    lines.append("## Pack B — layered vs current REGIME-CASH")
    lines.append("")
    for win, rows in (payload.get("pack_b") or {}).items():
        lines.append(f"### Window `{win}`")
        lines.append("")
        lines.append("| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |")
        lines.append("|--------|------|--------|----------|-----------|-------------|-------------|")
        for r in rows:
            lines.append(
                f"| {r['policy_id']} | {r['total_return_pct']} | {r['max_drawdown_pct']} | "
                f"{r['time_in_market_pct']} | {r['mean_cap_usd']} | {r['deploy_days']} | {r['cap_changes']} |"
            )
        lines.append("")

    lines.append("## Go / no-go")
    lines.append("")
    for d in (payload.get("go_no_go") or {}).get("decisions") or []:
        flag = "GO" if d.get("go") else "NO-GO"
        lines.append(f"- **{flag}** `{d['name']}` — {d['why']}")
    lines.append("")
    lines.append("## Plain-English takeaway")
    lines.append("")
    for t in payload.get("takeaways") or []:
        lines.append(f"- {t}")
    lines.append("")
    lines.append(f"_Generated {payload.get('generated_at')}_")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    days, books, meta = load_universe()
    btc = books["btc"]
    sigs = build_signals(days, btc)

    pack_a: Dict[str, List[dict]] = {}
    pack_b: Dict[str, List[dict]] = {}

    for wname, w0, w1 in WINDOWS:
        rows_a = [
            run_sim(pid, lab, days, books, sigs, fn, w0, w1)
            for pid, lab, fn in PACK_A
        ]
        rows_b = [
            run_sim(pid, lab, days, books, sigs, fn, w0, w1)
            for pid, lab, fn in PACK_B
        ]
        pack_a[wname] = _rank_window(rows_a)
        pack_b[wname] = _rank_window(rows_b)

    gng = go_no_go(pack_a, pack_b)

    # takeaways from numbers
    lo_a = {r["policy_id"]: r for r in pack_a["live_overlap"]}
    lo_b = {r["policy_id"]: r for r in pack_b["live_overlap"]}
    full_a = {r["policy_id"]: r for r in pack_a["full_sample"]}
    full_b = {r["policy_id"]: r for r in pack_b["full_sample"]}
    takeaways = []
    takeaways.append(
        f"Live overlap: 30d/15-only ret={lo_a.get('current_30d15_only',{}).get('total_return_pct')} "
        f"vs breakout@$75 ret={lo_a.get('breakout_reentry_cap75',{}).get('total_return_pct')} "
        f"vs flatB-always ret={lo_a.get('flat_b_always',{}).get('total_return_pct')}."
    )
    takeaways.append(
        f"Live overlap: current REGIME-CASH ret={lo_b.get('current_policy_regime_cash',{}).get('total_return_pct')} "
        f"dd={lo_b.get('current_policy_regime_cash',{}).get('max_drawdown_pct')} vs layered "
        f"ret={lo_b.get('layered_brk_rsi_bear_flatb_bullboost',{}).get('total_return_pct')} "
        f"dd={lo_b.get('layered_brk_rsi_bear_flatb_bullboost',{}).get('max_drawdown_pct')}."
    )
    takeaways.append(
        f"Full sample layered vs current: "
        f"{full_b.get('layered_brk_rsi_bear_flatb_bullboost',{}).get('total_return_pct')} / "
        f"dd {full_b.get('layered_brk_rsi_bear_flatb_bullboost',{}).get('max_drawdown_pct')} vs "
        f"{full_b.get('current_policy_regime_cash',{}).get('total_return_pct')} / "
        f"dd {full_b.get('current_policy_regime_cash',{}).get('max_drawdown_pct')}."
    )
    takeaways.append(
        "Caps are USD risk sleeves on an equal-weight basket — not full ARCH-4 rotation with pair RSI/sentiment; "
        "do not promote on this alone."
    )

    # signal stats
    brk_days = sum(1 for s in sigs if s.breakout_on)
    bull_days = sum(1 for s in sigs if s.regime_label == "bull")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": "breakout_reentry_stress_v1",
        "meta": {
            "pairs": PAIRS,
            "initial_usd": INITIAL,
            "flat_b_cap": FLAT_B_CAP,
            "bull_cap": BULL_CAP,
            "usdc_apy": USDC_APY,
            "fee_bps": FEE_BPS,
            "live_merge": meta,
            "bars": len(days),
            "breakout_days": brk_days,
            "bull_label_days": bull_days,
            "breakout_share_pct": round(100.0 * brk_days / max(len(sigs), 1), 2),
            "bull_share_pct": round(100.0 * bull_days / max(len(sigs), 1), 2),
        },
        "pack_a": pack_a,
        "pack_b": pack_b,
        "go_no_go": gng,
        "takeaways": takeaways,
        "gaps": [
            "No per-pair RSI/sentiment (live flat B entry gates absent)",
            "No stop-loss path / exchange gap",
            "Equal-weight sleeve ≠ ARCH-4 rotation_catch_wave",
            "Breakout params not swept",
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_md(payload))
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(json.dumps({"meta": payload["meta"], "takeaways": takeaways, "go_no_go": gng["decisions"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
