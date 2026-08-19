#!/usr/bin/env python3
"""
Historical bear/bull premise dig (no live writes).

Uses long BTC daily OHLCV + same detector bands as regime_cash_policy.
Answers:
  - Is 90d enough? (only if enough labeled bear/bull days inside it)
  - Bear premise: full park (USDC) vs tactical util vs full BTC on bear-labeled days
  - Bull premise: live-like high util vs tighter util vs USDC on bull-labeled days

Writes:
  reports/REGIME_BEAR_BULL_HISTORICAL_<date>.md|.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.usdc_benchmark import load_usdc_apy_pct  # noqa: E402

LONG_BTC = ROOT / "backtests" / "data" / "long" / "ohlcv_daily_btc.json"
POLICY = ROOT / "config" / "regime_cash_policy.json"
REPORTS = ROOT / "reports"
DAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Gates
MIN_REGIME_DAYS_PRIMARY = 45  # labeled days on full tape for primary call
MIN_REGIME_DAYS_90 = 20  # if 90d window has fewer → 90d inadequate
MIN_EPISODES = 3
LOOKBACK = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_closes(path: Path) -> List[Tuple[date, float]]:
    raw = json.loads(path.read_text())
    out: List[Tuple[date, float]] = []
    for r in raw:
        ts = str(r.get("timestamp") or r.get("time") or "")[:10]
        c = r.get("close")
        if not ts or c is None:
            continue
        try:
            d = date.fromisoformat(ts)
            out.append((d, float(c)))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    # de-dupe keep last
    by: Dict[date, float] = {}
    for d, c in out:
        by[d] = c
    return sorted(by.items(), key=lambda x: x[0])


def _classify(ret_pct: float, bull: float, bear: float, flat: float) -> str:
    if ret_pct >= bull:
        return "bull"
    if ret_pct <= bear:
        return "bear"
    if abs(ret_pct) <= flat:
        return "flat"
    return "transition"


def _rolling_series(
    closes: List[Tuple[date, float]],
    lookback: int,
    bull: float,
    bear: float,
    flat: float,
) -> List[Dict[str, Any]]:
    if len(closes) < lookback + 2:
        return []
    by_d = {d: c for d, c in closes}
    days = [d for d, _ in closes]
    out: List[Dict[str, Any]] = []
    for i in range(lookback, len(days)):
        end = days[i]
        start = end - timedelta(days=lookback)
        window = [(d, by_d[d]) for d in days if start <= d <= end]
        if len(window) < 5:
            continue
        p0, p1 = window[0][1], window[-1][1]
        ret_lb = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0
        day_ret = None
        if i > 0 and by_d[days[i - 1]] > 0:
            day_ret = by_d[days[i]] / by_d[days[i - 1]] - 1.0
        out.append(
            {
                "date": end.isoformat(),
                "btc_close": p1,
                "lookback_return_pct": round(ret_lb, 4),
                "regime": _classify(ret_lb, bull, bear, flat),
                "day_return": day_ret,
            }
        )
    return out


def _episodes(series: List[Dict[str, Any]], regime: str) -> List[Dict[str, Any]]:
    eps: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for row in series:
        if row["regime"] == regime:
            if cur is None:
                cur = {"start": row["date"], "end": row["date"], "days": 1, "day_returns": []}
            else:
                cur["end"] = row["date"]
                cur["days"] += 1
            if row.get("day_return") is not None:
                cur["day_returns"].append(float(row["day_return"]))
        else:
            if cur is not None:
                eps.append(_finalize_ep(cur))
                cur = None
    if cur is not None:
        eps.append(_finalize_ep(cur))
    return eps


def _finalize_ep(ep: Dict[str, Any]) -> Dict[str, Any]:
    rets = ep.get("day_returns") or []
    eq = peak = 1.0
    max_dd = 0.0
    for r in rets:
        eq *= 1.0 + float(r)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak else 0.0)
    return {
        "start": ep["start"],
        "end": ep["end"],
        "days": ep["days"],
        "btc_compound_return_pct": round((eq - 1.0) * 100.0, 4),
        "btc_max_dd_pct": round(max_dd * 100.0, 4),
        "n": len(rets),
    }


def _path(day_returns: List[float], util: float, usdc_daily: float, label: str) -> Dict[str, Any]:
    if not day_returns:
        return {
            "label": label,
            "n_days": 0,
            "util": util,
            "total_return_pct": None,
            "max_dd_pct": None,
            "insufficient": True,
        }
    eq = peak = 1.0
    max_dd = 0.0
    u = max(0.0, min(1.0, float(util)))
    for r in day_returns:
        blended = u * float(r) + (1.0 - u) * usdc_daily
        eq *= 1.0 + blended
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak else 0.0)
    return {
        "label": label,
        "n_days": len(day_returns),
        "util": u,
        "total_return_pct": round((eq - 1.0) * 100.0, 4),
        "max_dd_pct": round(max_dd * 100.0, 4),
        "end_equity_mult": round(eq, 6),
        "insufficient": False,
    }


def _day_returns(series: List[Dict[str, Any]], regime: str) -> List[float]:
    out = []
    for r in series:
        if r["regime"] == regime and r.get("day_return") is not None:
            out.append(float(r["day_return"]))
    return out


def _slice_series(series: List[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    out = []
    for r in series:
        d = date.fromisoformat(r["date"])
        if start <= d <= end:
            out.append(r)
    return out


def _judge_bear(paths: Dict[str, Dict[str, Any]], n_days: int, n_eps: int) -> Dict[str, Any]:
    """Premise: full park beats tactical on DD and not worse terminal vs tactical; USDC hurdle vs BTC."""
    park = paths["full_park_usdc"]
    tac = paths["tactical_util_0_25"]
    btc = paths["full_btc"]
    if n_days < MIN_REGIME_DAYS_PRIMARY:
        return {
            "class": "inconclusive_sparse_N",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": f"Only {n_days} bear-labeled days (<{MIN_REGIME_DAYS_PRIMARY}); cannot validate premise.",
        }
    if park.get("insufficient") or tac.get("insufficient"):
        return {
            "class": "process_incomplete",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": "Missing path metrics.",
        }
    # Park should have lower (better) max DD than tactical and full BTC
    dd_ok = float(park["max_dd_pct"]) <= float(tac["max_dd_pct"]) + 0.05  # allow tiny noise
    # Terminal: park >= tactical - 1pp (not leave huge upside while claiming park)
    # Actually bear premise is minimize loss: park terminal should beat tactical (higher = less loss)
    ret_ok = float(park["total_return_pct"]) >= float(tac["total_return_pct"]) - 0.25
    usdc_vs_btc = float(park["total_return_pct"]) >= float(btc["total_return_pct"]) - 0.01
    # Strong pass: both ret and dd vs tactical, and beats full BTC on DD materially
    strong = dd_ok and ret_ok and float(park["max_dd_pct"]) + 1.0 <= float(btc["max_dd_pct"])
    if strong and n_eps >= MIN_EPISODES:
        return {
            "class": "HIT_CRITERIA",
            "primary_pass": True,
            "enum": "propose_scoped_experiment",
            "plain": (
                f"Bear premise HOLDS on {n_days}d / {n_eps} episodes: full park "
                f"ret={park['total_return_pct']}% dd={park['max_dd_pct']}% vs tactical "
                f"ret={tac['total_return_pct']}% dd={tac['max_dd_pct']}% vs BTC "
                f"ret={btc['total_return_pct']}% dd={btc['max_dd_pct']}%."
            ),
        }
    if dd_ok and usdc_vs_btc:
        return {
            "class": "EDGE_VS_BAGS_ONLY",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": (
                f"Bear park reduces DD vs tactical/BTC but not a full dual-bar pass "
                f"(ret park={park['total_return_pct']} tac={tac['total_return_pct']}; "
                f"eps={n_eps}). Keep parked for live bear + longer tape."
            ),
        }
    return {
        "class": "unstable_or_no_edge",
        "primary_pass": False,
        "enum": "extend_trial",
        "plain": (
            f"Bear premise WEAK: park ret={park['total_return_pct']}% dd={park['max_dd_pct']}% "
            f"vs tactical ret={tac['total_return_pct']}% dd={tac['max_dd_pct']}%. "
            f"Schedule re-run when live regime=bear."
        ),
    }


def _judge_bull(paths: Dict[str, Dict[str, Any]], n_days: int, n_eps: int) -> Dict[str, Any]:
    """Premise: live-like high util beats USDC and tighter util on bull windows without DD blowup."""
    live = paths["live_util_0_85"]
    tight = paths["tight_util_0_65"]
    usdc = paths["full_park_usdc"]
    btc = paths["full_btc"]
    if n_days < MIN_REGIME_DAYS_PRIMARY:
        return {
            "class": "inconclusive_sparse_N",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": f"Only {n_days} bull-labeled days (<{MIN_REGIME_DAYS_PRIMARY}); cannot validate premise.",
        }
    if live.get("insufficient"):
        return {
            "class": "process_incomplete",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": "Missing bull path metrics.",
        }
    # Beat USDC on return
    beat_usdc = float(live["total_return_pct"]) > float(usdc["total_return_pct"]) + 0.5
    # Beat or match tight util on return
    beat_tight = float(live["total_return_pct"]) >= float(tight["total_return_pct"]) - 0.25
    # DD not much worse than tight (within 5pp)
    dd_ok = float(live["max_dd_pct"]) <= float(tight["max_dd_pct"]) + 5.0
    # Capture material vs full BTC (at least 50% of BTC return if BTC positive)
    btc_ret = float(btc["total_return_pct"] or 0)
    capture_ok = True
    if btc_ret > 5:
        capture_ok = float(live["total_return_pct"]) >= 0.45 * btc_ret
    strong = beat_usdc and beat_tight and dd_ok and capture_ok and n_eps >= MIN_EPISODES
    if strong:
        return {
            "class": "HIT_CRITERIA",
            "primary_pass": True,
            "enum": "propose_scoped_experiment",
            "plain": (
                f"Bull high-util premise HOLDS on {n_days}d / {n_eps} eps: live0.85 "
                f"ret={live['total_return_pct']}% dd={live['max_dd_pct']}% vs tight0.65 "
                f"ret={tight['total_return_pct']}% dd={tight['max_dd_pct']}% vs USDC "
                f"{usdc['total_return_pct']}% (BTC {btc['total_return_pct']}%)."
            ),
        }
    if beat_usdc and not (beat_tight and dd_ok):
        return {
            "class": "EDGE_VS_BAGS_ONLY",
            "primary_pass": False,
            "enum": "extend_trial",
            "plain": (
                f"Bull util beats USDC but dual bar vs tight/DD weak "
                f"(live ret={live['total_return_pct']} dd={live['max_dd_pct']}; "
                f"tight ret={tight['total_return_pct']} dd={tight['max_dd_pct']}). "
                f"Re-test on live bull dwell."
            ),
        }
    return {
        "class": "unstable_or_no_edge",
        "primary_pass": False,
        "enum": "extend_trial",
        "plain": (
            f"Bull premise WEAK on labeled tape: live0.85 ret={live['total_return_pct']}% "
            f"dd={live['max_dd_pct']}% vs USDC {usdc['total_return_pct']}%. "
            f"Schedule when live regime=bull."
        ),
    }


def main() -> int:
    if not LONG_BTC.exists():
        print("MISSING", LONG_BTC)
        return 2
    policy = json.loads(POLICY.read_text()) if POLICY.exists() else {}
    det = policy.get("detector") or {}
    bull_th = float(det.get("bull_return_pct", 15))
    bear_th = float(det.get("bear_return_pct", -10))
    flat_th = float(det.get("flat_abs_pct", 8))
    lookback = int(det.get("lookback_days") or LOOKBACK)

    regimes_pol = policy.get("regimes") or {}
    bear_util = float((regimes_pol.get("bear") or {}).get("target_max_util_pct", 0.25))
    bull_util = float((regimes_pol.get("bull") or {}).get("target_max_util_pct", 0.85))
    flat_util = float((regimes_pol.get("flat") or {}).get("target_max_util_pct", 0.65))

    closes = _load_closes(LONG_BTC)
    series = _rolling_series(closes, lookback, bull_th, bear_th, flat_th)
    if not series:
        print("empty series")
        return 2

    end_d = date.fromisoformat(series[-1]["date"])
    start_d = date.fromisoformat(series[0]["date"])
    d90 = end_d - timedelta(days=90)
    series_90 = _slice_series(series, d90, end_d)

    counts_full = dict(Counter(r["regime"] for r in series))
    counts_90 = dict(Counter(r["regime"] for r in series_90))

    apy = float(load_usdc_apy_pct() or 3.5)
    usdc_daily = (1.0 + apy / 100.0) ** (1.0 / 365.0) - 1.0

    # Bear / bull paths on full tape labeled days
    bear_rets = _day_returns(series, "bear")
    bull_rets = _day_returns(series, "bull")
    bear_eps = _episodes(series, "bear")
    bull_eps = _episodes(series, "bull")
    bear_90 = _day_returns(series_90, "bear")
    bull_90 = _day_returns(series_90, "bull")

    bear_paths = {
        "full_park_usdc": _path(bear_rets, 0.0, usdc_daily, "full_park_usdc"),
        "tactical_util_0_25": _path(bear_rets, bear_util, usdc_daily, f"tactical_util_{bear_util}"),
        "flat_like_util_0_65": _path(bear_rets, flat_util, usdc_daily, f"flat_like_{flat_util}"),
        "full_btc": _path(bear_rets, 1.0, usdc_daily, "full_btc"),
    }
    bull_paths = {
        "full_park_usdc": _path(bull_rets, 0.0, usdc_daily, "full_park_usdc"),
        "tight_util_0_65": _path(bull_rets, flat_util, usdc_daily, f"tight_{flat_util}"),
        "live_util_0_85": _path(bull_rets, bull_util, usdc_daily, f"live_{bull_util}"),
        "full_btc": _path(bull_rets, 1.0, usdc_daily, "full_btc"),
    }

    # 90d adequacy
    adeq_90 = {
        "bear_days": len(bear_90),
        "bull_days": len(bull_90),
        "bear_adequate": len(bear_90) >= MIN_REGIME_DAYS_90,
        "bull_adequate": len(bull_90) >= MIN_REGIME_DAYS_90,
        "note": (
            "90 calendar days is adequate for a regime premise ONLY if it contains "
            f"≥{MIN_REGIME_DAYS_90} labeled days of that regime. Otherwise use long tape "
            f"(primary needs ≥{MIN_REGIME_DAYS_PRIMARY} labeled days)."
        ),
    }

    bear_j = _judge_bear(bear_paths, len(bear_rets), len(bear_eps))
    bull_j = _judge_bull(bull_paths, len(bull_rets), len(bull_eps))

    payload = {
        "generated_at": _utc_now(),
        "data": {
            "path": str(LONG_BTC.relative_to(ROOT)),
            "n_closes": len(closes),
            "series_start": series[0]["date"],
            "series_end": series[-1]["date"],
            "span_calendar_days": (end_d - start_d).days,
            "lookback_days": lookback,
            "bands": {"bull_pct": bull_th, "bear_pct": bear_th, "flat_abs_pct": flat_th},
            "usdc_apy_pct": apy,
        },
        "regime_counts_full": counts_full,
        "regime_counts_last_90d": counts_90,
        "adequacy_90d": adeq_90,
        "bear": {
            "n_labeled_days": len(bear_rets),
            "n_episodes": len(bear_eps),
            "episodes_sample": bear_eps[:8],
            "paths": bear_paths,
            "judgment": bear_j,
            "follow_on": (
                "scoped_shadow"
                if bear_j.get("primary_pass")
                else "park_until_live_bear_or_longer_tape"
            ),
        },
        "bull": {
            "n_labeled_days": len(bull_rets),
            "n_episodes": len(bull_eps),
            "episodes_sample": bull_eps[:8],
            "paths": bull_paths,
            "judgment": bull_j,
            "follow_on": (
                "scoped_shadow"
                if bull_j.get("primary_pass")
                else "park_until_live_bull_or_longer_tape"
            ),
        },
        "live_writes": False,
        "method": (
            "BTC day returns on detector-labeled regime days; util blend with USDC daily. "
            "Proxy for park vs tactical deploy — not full multi-asset ARCH-4."
        ),
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = f"REGIME_BEAR_BULL_HISTORICAL_{DAY}"
    jpath = REPORTS / f"{stem}.json"
    mpath = REPORTS / f"{stem}.md"
    jpath.write_text(json.dumps(payload, indent=2) + "\n")

    def _path_table(paths: Dict[str, Dict[str, Any]]) -> str:
        lines = ["| Arm | n | util | ret% | maxDD% |", "|-----|---|------|------|--------|"]
        for k, p in paths.items():
            lines.append(
                f"| {p.get('label', k)} | {p.get('n_days')} | {p.get('util')} | "
                f"{p.get('total_return_pct')} | {p.get('max_dd_pct')} |"
            )
        return "\n".join(lines)

    md = f"""# Regime bear/bull historical premise dig — {DAY}

**Data:** `{payload['data']['path']}` · {payload['data']['n_closes']} daily closes · \
{payload['data']['series_start']} → {payload['data']['series_end']} \
({payload['data']['span_calendar_days']}d)  
**Detector:** lookback={lookback}d · bull≥{bull_th}% · bear≤{bear_th}% · flat |r|≤{flat_th}%  
**Live writes:** none  
**Method:** util-blend proxy on labeled BTC days (not full multi-asset book)

## Plain English

### Is 90 days enough?
**Usually no — not by calendar alone.** Adequacy = enough **labeled** bear/bull days inside the window.

| Window | bear days | bull days | adequate (≥{MIN_REGIME_DAYS_90})? |
|--------|-----------|-----------|-------------------------------------|
| Last 90 calendar days | {adeq_90['bear_days']} | {adeq_90['bull_days']} | bear={adeq_90['bear_adequate']} · bull={adeq_90['bull_adequate']} |
| Full long tape (primary) | {len(bear_rets)} | {len(bull_rets)} | primary bar ≥{MIN_REGIME_DAYS_PRIMARY} labeled days |

{adeq_90['note']}

### Bear premise (full park vs tactical)
**{bear_j['plain']}**  
- class: `{bear_j['class']}` · primary_pass: **{bear_j['primary_pass']}** · enum: `{bear_j['enum']}`  
- follow_on: `{payload['bear']['follow_on']}`

### Bull premise (live-like util vs tight / USDC)
**{bull_j['plain']}**  
- class: `{bull_j['class']}` · primary_pass: **{bull_j['primary_pass']}** · enum: `{bull_j['enum']}`  
- follow_on: `{payload['bull']['follow_on']}`

## Regime mix

| Regime | Full tape days | Last 90d days |
|--------|----------------|---------------|
"""
    for reg in ("bull", "flat", "bear", "transition"):
        md += f"| {reg} | {counts_full.get(reg, 0)} | {counts_90.get(reg, 0)} |\n"

    md += f"""
## Bear paths (labeled bear days only)

n_days={len(bear_rets)} · episodes={len(bear_eps)} (sample first 8 in JSON)

{_path_table(bear_paths)}

## Bull paths (labeled bull days only)

n_days={len(bull_rets)} · episodes={len(bull_eps)}

{_path_table(bull_paths)}

## Decision guidance (strategy plans stay planned)

| Plan | If primary_pass | If weak / sparse |
|------|-----------------|------------------|
| PLAN-BEAR-PARK-001 | premise validated → keep parked for **live bear** shadow; no live write | stay parked; re-run at live bear or more tape |
| PLAN-BULL-KNOBS-002 | premise validated → keep parked for **live bull** shadow; no live write | stay parked; re-run at live bull |

**Pass** here means *premise supported on historical labeled days* — **not** live promote.
Live knob changes still need Brad + promotion gates.

## JSON
`{jpath.relative_to(ROOT)}`
"""
    mpath.write_text(md)
    print(json.dumps({
        "report_md": str(mpath.relative_to(ROOT)),
        "report_json": str(jpath.relative_to(ROOT)),
        "adeq_90": adeq_90,
        "bear": bear_j,
        "bull": bull_j,
        "counts_full": counts_full,
        "counts_90": counts_90,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
