#!/usr/bin/env python3
"""
USD hold-value contingency — offline entry/exit backtest + param sweep.

Research only. No live side effects.
Spec: docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md

Usage:
  PYTHONPATH=. .venv/bin/python phase6/research/run_usd_hold_contingency_backtest.py
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.research.bull_reentry_layered import (
    BEAR_RET_PCT,
    BULL_RET_PCT,
    build_signal_series,
    rolling_return_pct,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "data/state/usd_hold_contingency_backtest_latest.json"
OUT_MD = ROOT / "reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md"
VISION = "https://data-api.binance.vision/api/v3/klines"
FEE_RT = 0.002  # 0.1% each side round-trip proxy
INITIAL = 10_000.0
UA = {"User-Agent": "Mozilla/5.0 phase6-research", "Accept": "application/json"}


def fetch_daily(symbol: str, start_ms: int, end_ms: int) -> List[Tuple[date, float]]:
    out: List[Tuple[date, float]] = []
    cursor = start_ms
    while cursor < end_ms:
        url = (
            f"{VISION}?symbol={symbol}&interval=1d&startTime={cursor}"
            f"&endTime={end_ms}&limit=1000"
        )
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        for k in batch:
            d = datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc).date()
            out.append((d, float(k[4])))
        last = int(batch[-1][0])
        nxt = last + 86_400_000
        if nxt <= cursor:
            break
        cursor = nxt
        if len(batch) < 1000:
            break
        time.sleep(0.08)
    # dedupe by date keep last
    m: Dict[date, float] = {}
    for d, p in out:
        m[d] = p
    return sorted(m.items())


def align(series_map: Dict[str, List[Tuple[date, float]]]) -> Tuple[List[date], Dict[str, Dict[date, float]]]:
    dicts = {k: dict(v) for k, v in series_map.items()}
    common = None
    for d in dicts.values():
        s = set(d.keys())
        common = s if common is None else (common & s)
    days = sorted(common or [])
    return days, dicts


def max_dd(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for x in equity:
        peak = max(peak, x)
        if peak > 0:
            mdd = min(mdd, x / peak - 1.0)
    return mdd


def sharpe_daily(rets: Sequence[float]) -> Optional[float]:
    if len(rets) < 30:
        return None
    mu = mean(rets)
    sd = pstdev(rets)
    if sd < 1e-12:
        return 0.0 if abs(mu) < 1e-12 else 99.0
    return (mu / sd) * math.sqrt(365.0)


def metrics(equity: List[float], trades: int, days_n: int) -> Dict[str, Any]:
    if len(equity) < 2:
        return {"error": "short"}
    total = equity[-1] / equity[0] - 1.0
    rets = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            rets.append(equity[i] / equity[i - 1] - 1.0)
    ann = (1.0 + total) ** (365.0 / max(days_n, 1)) - 1.0 if days_n > 0 else None
    return {
        "final_equity": round(equity[-1], 2),
        "total_return_pct": round(total * 100.0, 3),
        "annualized_return_pct": None if ann is None else round(ann * 100.0, 3),
        "max_drawdown_pct": round(max_dd(equity) * 100.0, 3),
        "sharpe": None if sharpe_daily(rets) is None else round(float(sharpe_daily(rets)), 3),
        "trades": trades,
        "days": days_n,
        "end_vs_start_pct": round(total * 100.0, 3),
    }


def buy_hold(
    days: List[date],
    px: Dict[date, float],
    *,
    fee_rt: float = FEE_RT,
    initial: float = INITIAL,
) -> Tuple[List[float], int]:
    """Enter day0, hold to end. One round-trip fee at end (sell) + entry."""
    eq = []
    p0 = px[days[0]]
    units = (initial * (1.0 - fee_rt / 2)) / p0
    for d in days:
        eq.append(units * px[d])
    # mark final after exit fee
    eq[-1] = eq[-1] * (1.0 - fee_rt / 2)
    return eq, 1


def usdc_flat(days: List[date], apy: float = 0.0, initial: float = INITIAL) -> Tuple[List[float], int]:
    eq = []
    for i, _ in enumerate(days):
        eq.append(initial * ((1.0 + apy) ** (i / 365.0)))
    return eq, 0


@dataclass
class ContingencyParams:
    name: str
    min_bear_streak: int = 14
    btc_12m_max_pct: float = -25.0  # need 12m return <= this to arm
    paxg_weight: float = 1.0  # fraction of book into PAXG when in hedge
    exit_on_bull: bool = True
    exit_on_reentry_layer: bool = True  # breakout+rsi path / non-park layer
    exit_btc_30d_gt: Optional[float] = 10.0  # exit if 30d > this; None=off
    paxg_trail_dd: Optional[float] = None  # e.g. -0.12 soft exit from local peak while hedged
    require_12m: bool = True
    fee_rt: float = FEE_RT


def rolling_return_from_series(
    days: List[date], px: Dict[date, float], i: int, lookback: int
) -> Optional[float]:
    return rolling_return_pct(days, px, i, lookback)


def run_contingency(
    days: List[date],
    btc: Dict[date, float],
    paxg: Dict[date, float],
    params: ContingencyParams,
    initial: float = INITIAL,
) -> Tuple[List[float], int, Dict[str, Any]]:
    """
    Default USDC (0% APY). When entry rules pass, move `paxg_weight` of equity into PAXG.
    Exit back to USDC on exit rules. Partial weight allowed.
    """
    signals = build_signal_series(days, btc, flat_deploy_without_breakout=True)
    cash = initial
    units = 0.0
    hedged = False
    peak_paxg = 0.0
    trades = 0
    equity: List[float] = []
    bear_streak = 0
    entries = 0
    days_hedged = 0
    entry_dates: List[str] = []
    exit_dates: List[str] = []

    for i, d in enumerate(days):
        sig = signals[i]
        r30 = sig.btc_ret_30
        r12m = rolling_return_from_series(days, btc, i, 365)
        # streak of bear label or r30 bear
        is_bear = sig.regime_label == "bear" or (
            r30 is not None and r30 <= BEAR_RET_PCT
        )
        if is_bear:
            bear_streak += 1
        else:
            bear_streak = 0

        # mark-to-market
        if hedged and units > 0:
            px = paxg[d]
            peak_paxg = max(peak_paxg, px)
            days_hedged += 1

        # --- exits first ---
        if hedged:
            exit_reason = None
            if params.exit_on_bull and (
                sig.regime_label == "bull"
                or (r30 is not None and r30 >= BULL_RET_PCT)
            ):
                exit_reason = "bull"
            elif params.exit_on_reentry_layer and sig.layer in (
                "reentry_flat_b",
                "bull_size_up",
                "flat_b",
            ):
                # flat_b is live deploy path — treat as risk-on thaw for hedge
                exit_reason = f"layer_{sig.layer}"
            elif params.exit_btc_30d_gt is not None and r30 is not None and r30 >= params.exit_btc_30d_gt:
                exit_reason = "btc_30d_thaw"
            elif (
                params.paxg_trail_dd is not None
                and units > 0
                and peak_paxg > 0
                and paxg[d] / peak_paxg - 1.0 <= params.paxg_trail_dd
            ):
                exit_reason = "paxg_trail"

            if exit_reason:
                # sell all paxg to cash
                proceeds = units * paxg[d] * (1.0 - params.fee_rt / 2)
                cash += proceeds
                units = 0.0
                hedged = False
                peak_paxg = 0.0
                trades += 1
                exit_dates.append(f"{d.isoformat()}:{exit_reason}")

        # --- entries ---
        if not hedged:
            ok_streak = bear_streak >= params.min_bear_streak
            ok_12 = (not params.require_12m) or (
                r12m is not None and r12m <= params.btc_12m_max_pct
            )
            # only enter from park-like regimes
            parkish = sig.layer in ("bear_park", "park") or is_bear
            if ok_streak and ok_12 and parkish and params.paxg_weight > 0:
                # deploy weight of cash into paxg
                deploy = cash * min(1.0, max(0.0, params.paxg_weight))
                if deploy > 1.0:
                    px = paxg[d]
                    bought = (deploy * (1.0 - params.fee_rt / 2)) / px
                    units += bought
                    cash -= deploy
                    hedged = True
                    peak_paxg = px
                    trades += 1
                    entries += 1
                    entry_dates.append(d.isoformat())

        eq = cash + units * paxg[d]
        equity.append(eq)

    # liquidate mark (already in eq); optional final fee if still hedged for fair BH compare
    if units > 0:
        equity[-1] = cash + units * paxg[days[-1]] * (1.0 - params.fee_rt / 2)

    info = {
        "entries": entries,
        "days_hedged": days_hedged,
        "pct_days_hedged": round(100.0 * days_hedged / max(len(days), 1), 2),
        "entry_dates": entry_dates[:12],
        "exit_dates": exit_dates[:12],
        "params": asdict(params),
    }
    return equity, trades, info


def score(m: Dict[str, Any]) -> float:
    """Higher better: return, less DD, modest sharpe. North star: returns AND less loss."""
    if m.get("error"):
        return -999.0
    ret = float(m.get("total_return_pct") or 0.0)
    dd = abs(float(m.get("max_drawdown_pct") or 0.0))
    sh = float(m.get("sharpe") or 0.0)
    # prefer less loss heavily
    return ret - 1.25 * dd + 5.0 * max(min(sh, 2.0), -1.0)


def main() -> int:
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    # ~3y history for warmup + 18m eval; report both full common and last 548d
    start_ms = int((now - timedelta(days=400 + 548)).timestamp() * 1000)

    symbols = {
        "BTC": "BTCUSDT",
        "PAXG": "PAXGUSDT",
        "TRX": "TRXUSDT",
        "BNB": "BNBUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
    }
    raw: Dict[str, List[Tuple[date, float]]] = {}
    for name, sym in symbols.items():
        print(f"fetch {name}...")
        raw[name] = fetch_daily(sym, start_ms, end_ms)
        time.sleep(0.12)
        print(f"  {name}: {len(raw[name])} days")

    days, px = align(raw)
    if len(days) < 400:
        raise SystemExit(f"insufficient aligned days: {len(days)}")

    # evaluation windows
    windows = {
        "full_aligned": days,
        "last_18m": [d for d in days if d >= (days[-1] - timedelta(days=548))],
        "last_12m": [d for d in days if d >= (days[-1] - timedelta(days=365))],
    }

    all_results: Dict[str, Any] = {
        "as_of": now.isoformat(),
        "fee_rt": FEE_RT,
        "initial_usd": INITIAL,
        "aligned_start": days[0].isoformat(),
        "aligned_end": days[-1].isoformat(),
        "n_aligned_days": len(days),
        "windows": {},
        "plain_english": "",
        "recommendation": {},
    }

    best_global = None

    for wname, wdays in windows.items():
        if len(wdays) < 60:
            continue
        btc = {d: px["BTC"][d] for d in wdays}
        paxg = {d: px["PAXG"][d] for d in wdays}
        baselines = {}

        # buy & holds
        for asset in ("PAXG", "BTC", "TRX", "BNB", "ETH", "SOL"):
            eq, tr = buy_hold(wdays, {d: px[asset][d] for d in wdays})
            baselines[f"bh_{asset.lower()}"] = {
                **metrics(eq, tr, (wdays[-1] - wdays[0]).days),
                "strategy": f"buy_hold_{asset}",
            }

        eq_u, tr_u = usdc_flat(wdays, apy=0.0)
        baselines["usdc_0"] = {**metrics(eq_u, tr_u, (wdays[-1] - wdays[0]).days), "strategy": "usdc_0pct"}
        eq_u4, _ = usdc_flat(wdays, apy=0.04)
        baselines["usdc_4apy"] = {
            **metrics(eq_u4, 0, (wdays[-1] - wdays[0]).days),
            "strategy": "usdc_4pct_apy",
        }

        # static mixes
        for w_paxg in (0.25, 0.5, 0.75):
            eq_p, _ = buy_hold(wdays, paxg)
            eq_c, _ = usdc_flat(wdays, 0.0)
            # approximate mix without rebalance: start split
            p0 = paxg[wdays[0]]
            units = (INITIAL * w_paxg * (1 - FEE_RT / 2)) / p0
            cash = INITIAL * (1 - w_paxg)
            eqm = []
            for d in wdays:
                eqm.append(cash + units * paxg[d])
            eqm[-1] = cash + units * paxg[wdays[-1]] * (1 - FEE_RT / 2)
            baselines[f"static_{int(w_paxg*100)}paxg"] = {
                **metrics(eqm, 1, (wdays[-1] - wdays[0]).days),
                "strategy": f"static_{int(w_paxg*100)}pct_paxg",
            }

        # contingency sweep
        sweep_rows = []
        grid = list(
            product(
                [7, 14, 21, 30],  # min bear streak
                [-15.0, -25.0, -35.0, -999.0],  # 12m gate; -999 = off
                [0.25, 0.5, 0.75, 1.0],  # paxg weight
                [True],  # exit bull
                [True, False],  # exit on reentry/flat deploy layers
                [None, 10.0, 15.0],  # btc 30d thaw
                [None, -0.12, -0.20],  # trail
            )
        )
        # cap grid size if huge — 4*4*4*1*2*3*3 = 1152 ok
        for streak, g12, wt, ex_bull, ex_layer, thaw, trail in grid:
            require_12 = g12 > -900
            g12v = g12 if require_12 else -25.0
            pname = (
                f"c_s{streak}_12m{int(g12) if require_12 else 'off'}"
                f"_w{int(wt*100)}_thaw{thaw}_tr{trail}_L{int(ex_layer)}"
            )
            params = ContingencyParams(
                name=pname,
                min_bear_streak=streak,
                btc_12m_max_pct=g12v,
                paxg_weight=wt,
                exit_on_bull=ex_bull,
                exit_on_reentry_layer=ex_layer,
                exit_btc_30d_gt=thaw,
                paxg_trail_dd=trail,
                require_12m=require_12,
            )
            eq, tr, info = run_contingency(wdays, btc, paxg, params)
            m = metrics(eq, tr, (wdays[-1] - wdays[0]).days)
            sc = score(m)
            sweep_rows.append(
                {
                    "name": pname,
                    "score": round(sc, 4),
                    "metrics": m,
                    "info": {
                        "entries": info["entries"],
                        "pct_days_hedged": info["pct_days_hedged"],
                        "entry_dates": info["entry_dates"],
                        "exit_dates": info["exit_dates"],
                        "params": info["params"],
                    },
                }
            )

        sweep_rows.sort(key=lambda r: r["score"], reverse=True)
        # also rank by return and by calmar-like
        by_ret = sorted(sweep_rows, key=lambda r: r["metrics"]["total_return_pct"], reverse=True)
        by_dd = sorted(sweep_rows, key=lambda r: -abs(r["metrics"]["max_drawdown_pct"]))

        top = sweep_rows[:15]
        # baseline scores
        for k, v in baselines.items():
            v["score"] = round(score(v), 4)

        base_sorted = sorted(baselines.items(), key=lambda kv: kv[1]["score"], reverse=True)

        window_payload = {
            "start": wdays[0].isoformat(),
            "end": wdays[-1].isoformat(),
            "n_days": len(wdays),
            "baselines": baselines,
            "baseline_rank": [{"id": k, **v} for k, v in base_sorted],
            "sweep_n": len(sweep_rows),
            "top_by_score": top,
            "top_by_return": by_ret[:10],
            "best_low_dd_among_top50": sorted(sweep_rows[:50], key=lambda r: abs(r["metrics"]["max_drawdown_pct"]))[:5],
            "best": top[0] if top else None,
        }
        all_results["windows"][wname] = window_payload
        print(
            f"\n=== {wname} {wdays[0]}→{wdays[-1]} ===\n"
            f"best contingency score={top[0]['score']} ret={top[0]['metrics']['total_return_pct']}% "
            f"dd={top[0]['metrics']['max_drawdown_pct']}% entries={top[0]['info']['entries']}\n"
            f"best baseline={base_sorted[0][0]} score={base_sorted[0][1]['score']} "
            f"ret={base_sorted[0][1]['total_return_pct']}%"
        )

        if wname == "last_18m" and top:
            best_global = top[0]

    # recommendation from last_18m primary, confirm on last_12m
    w18 = all_results["windows"].get("last_18m") or {}
    w12 = all_results["windows"].get("last_12m") or {}
    best18 = w18.get("best")
    base18 = (w18.get("baseline_rank") or [{}])[0]
    usdc18 = (w18.get("baselines") or {}).get("usdc_0") or {}
    paxg18 = (w18.get("baselines") or {}).get("bh_paxg") or {}
    btc18 = (w18.get("baselines") or {}).get("bh_btc") or {}

    # find robust params: appear in top 20 of both 12m and 18m by score
    names18 = {r["name"] for r in (w18.get("top_by_score") or [])[:20]}
    top12 = w12.get("top_by_score") or []
    robust = [r for r in top12 if r["name"] in names18][:5]

    rec = {
        "primary_window": "last_18m",
        "best_timed_18m": best18,
        "robust_overlap_12m_18m_top20": robust,
        "baselines_18m": {
            "usdc_0": usdc18,
            "bh_paxg": paxg18,
            "bh_btc": btc18,
            "best_baseline": base18,
        },
        "viable_policy": None,
        "go_no_go": "no_go_live",
    }

    # Craft viable policy from best robust or best18
    pick = robust[0] if robust else best18
    if pick:
        p = pick["info"]["params"]
        m = pick["metrics"]
        beat_usdc = m["total_return_pct"] > (usdc18.get("total_return_pct") or 0) + 1.0
        dd_ok = abs(m["max_drawdown_pct"]) <= abs(paxg18.get("max_drawdown_pct") or 99) + 5
        # vs always paxg: timed should reduce DD or similar ret with less time in market
        viable = {
            "entry": {
                "min_bear_streak_days": p["min_bear_streak"],
                "require_btc_12m_lte_pct": p["btc_12m_max_pct"] if p["require_12m"] else None,
                "only_when_park_layer": True,
                "paxg_weight": p["paxg_weight"],
            },
            "exit": {
                "on_bull_or_30d_ge_15": p["exit_on_bull"],
                "on_reentry_or_flat_deploy_layer": p["exit_on_reentry_layer"],
                "btc_30d_thaw_pct": p["exit_btc_30d_gt"],
                "paxg_trail_dd": p["paxg_trail_dd"],
            },
            "expected_18m_if_pick": m,
            "beats_usdc_18m": beat_usdc,
            "notes": [],
        }
        if beat_usdc and m["total_return_pct"] > 0:
            rec["go_no_go"] = "shadow_candidate"
            viable["notes"].append("Beats flat USDC on 18m with positive return — shadow only.")
        elif paxg18.get("total_return_pct", 0) > (usdc18.get("total_return_pct") or 0) + 5:
            rec["go_no_go"] = "static_paxg_dominates_timed"
            viable["notes"].append(
                "Always-PAXG may beat timed rules this window; timing value is DD/time-in-market, not max return."
            )
        else:
            rec["go_no_go"] = "usdc_park_sufficient"
            viable["notes"].append("Neither timed nor complexity clearly needed vs USDC this tape.")
        rec["viable_policy"] = viable

    # plain english
    pe_lines = [
        f"Window primary: last ~18m ({w18.get('start')} → {w18.get('end')}).",
        f"USDC flat: {usdc18.get('total_return_pct')}% ret, DD {usdc18.get('max_drawdown_pct')}%.",
        f"Always PAXG: {paxg18.get('total_return_pct')}% ret, DD {paxg18.get('max_drawdown_pct')}%, Sharpe {paxg18.get('sharpe')}.",
        f"Always BTC: {btc18.get('total_return_pct')}% ret, DD {btc18.get('max_drawdown_pct')}%.",
    ]
    if pick:
        pe_lines.append(
            f"Best timed contingency: ret {pick['metrics']['total_return_pct']}% | "
            f"DD {pick['metrics']['max_drawdown_pct']}% | trades {pick['metrics']['trades']} | "
            f"hedged {pick['info']['pct_days_hedged']}% days | score {pick['score']}."
        )
        pe_lines.append(f"Params: {pick['name']}")
    pe_lines.append(f"Go/no-go: {rec['go_no_go']}")
    all_results["plain_english"] = " ".join(pe_lines)
    all_results["recommendation"] = rec

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(all_results, indent=2, default=str))
    print("WROTE", OUT_JSON)

    # markdown report
    md = []
    md.append("# USD hold contingency backtest\n")
    md.append(f"**As of:** {now.date().isoformat()}  ")
    md.append(f"**Status:** OFFLINE RESEARCH ONLY — not live  ")
    md.append(f"**Artifact:** `{OUT_JSON.relative_to(ROOT)}`  ")
    md.append(f"**Fee assumption:** {FEE_RT*100:.2f}% round-trip per entry/exit  ")
    md.append(f"**Initial:** ${INITIAL:,.0f}\n")
    md.append("## Plain English\n")
    md.append(all_results["plain_english"] + "\n")
    md.append(f"**Go/no-go:** `{rec['go_no_go']}`\n")

    for wname in ("last_18m", "last_12m", "full_aligned"):
        w = all_results["windows"].get(wname)
        if not w:
            continue
        md.append(f"## Window: {wname} ({w['start']} → {w['end']}, n={w['n_days']})\n")
        md.append("### Baselines (buy/hold or cash)\n")
        md.append("| Strategy | Return% | MaxDD% | Sharpe | Score |\n|---|---:|---:|---:|---:|")
        for row in w["baseline_rank"][:12]:
            md.append(
                f"| {row.get('strategy') or row.get('id')} | {row.get('total_return_pct')} | "
                f"{row.get('max_drawdown_pct')} | {row.get('sharpe')} | {row.get('score')} |"
            )
        md.append("\n### Top timed contingency (by score = ret − 1.25·|DD| + sharpe term)\n")
        md.append("| Rank | Return% | MaxDD% | Sharpe | Trades | %days hedged | Params |\n|---:|---:|---:|---:|---:|---:|---|")
        for i, r in enumerate(w["top_by_score"][:10], 1):
            md.append(
                f"| {i} | {r['metrics']['total_return_pct']} | {r['metrics']['max_drawdown_pct']} | "
                f"{r['metrics']['sharpe']} | {r['metrics']['trades']} | {r['info']['pct_days_hedged']} | "
                f"`{r['name']}` |"
            )
        md.append("")

    md.append("## Viable entry/exit (proposed from sweep)\n")
    vp = rec.get("viable_policy") or {}
    if vp:
        md.append("```json")
        md.append(json.dumps(vp, indent=2))
        md.append("```\n")
    md.append("### Robust overlap (top-20 score on both 12m and 18m)\n")
    if robust:
        for r in robust:
            md.append(
                f"- `{r['name']}` 12m-score-rank ret={r['metrics']['total_return_pct']}% "
                f"dd={r['metrics']['max_drawdown_pct']}%\n"
            )
    else:
        md.append("_No overlapping names in top-20 — treat best-18m as fragile._\n")

    md.append("## Interpretation rules\n")
    md.append(
        "1. **USDC** = opportunity cost floor (0% here; real Coinbase APY slightly better).\n"
        "2. **Always PAXG** = upper bound if gold kept rising — timing cannot beat perfect hindsight hold if trend is one-way up.\n"
        "3. **Timed contingency** earns its keep if it **beats USDC** and **cuts DD or time-at-risk** vs always PAXG, "
        "especially when gold later mean-reverts (not fully tested out-of-sample).\n"
        "4. **BTC/ETH/SOL BH** show why crypto beta is not the USD store this window.\n"
        "5. Do **not** promote to live without shadow + venue PAXG SL path.\n"
    )
    md.append("## Method\n")
    md.append(
        "- Daily closes via Binance Vision USDT pairs (USDT≈USD).\n"
        "- BTC regime/layers from `bull_reentry_layered.build_signal_series` (frozen knobs).\n"
        "- Contingency: default cash → enter PAXG when bear streak + optional BTC 12m gate + park layer; "
        "exit on bull / deploy layers / optional 30d thaw / optional PAXG trail.\n"
        "- Score favors less loss (north star).\n"
    )
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md))
    print("WROTE", OUT_MD)
    print("\nPLAIN:", all_results["plain_english"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
