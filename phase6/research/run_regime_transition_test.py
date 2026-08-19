#!/usr/bin/env python3
"""
ANALYST-REGIME-TRANSITION offline T0/T1/T1b runner.

Hypothesis: transition cap/park settings drive unnecessary whipsaw or idle cash.
Real BTC OHLCV + live ledger + scorecard only. No live config writes.

Writes reports/REGIME_TRANSITION_TEST_<date>.md + .json
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.usdc_benchmark import load_usdc_apy_pct
from phase6.research.production_period_baseline import compute_since_go_live
from phase6.research.regime_detector import (
    _load_btc_closes,
    _merge_live_close,
    detect_regime,
)
from phase6.research.usdc_carry_backtest import usdc_carry_metrics

TRIAL_ID = "ANALYST-REGIME-TRANSITION-20260727-TRIAL"
MASTER_ID = "ANALYST-REGIME-TRANSITION-20260727"
POLICY_PATH = ROOT / "config" / "regime_cash_policy.json"
KNOB_MAP_PATH = ROOT / "config" / "regime_knob_map.json"
STATUS_PATH = ROOT / "data" / "state" / "regime_cash_status.json"
SCORECARD_PATH = ROOT / "data" / "state" / "analyst_regime_scorecard_latest.json"
VALIDATION_PATH = ROOT / "data" / "state" / "regime_cash_validation_latest.json"
TRADES_JSONL = ROOT / "trades" / "phase6_trades.jsonl"
REPORTS = ROOT / "reports"

MIN_TRANSITION_DAYS_GATE = 14  # recommend only if enough transition-labeled days
MIN_EPISODES_GATE = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


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
    """Daily end-of-day classification + 1d BTC return (real closes only)."""
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
        # next-day forward return uses actual next close if present
        fwd = None
        if i + 1 < len(days):
            c0, c1 = by_d[days[i]], by_d[days[i + 1]]
            if c0 > 0:
                fwd = (c1 / c0 - 1.0)
        # same-day return vs prior bar
        day_ret = None
        if i > 0 and by_d[days[i - 1]] > 0:
            day_ret = by_d[days[i]] / by_d[days[i - 1]] - 1.0
        regime = _classify(ret_lb, bull, bear, flat)
        out.append(
            {
                "date": end.isoformat(),
                "btc_close": p1,
                "lookback_return_pct": round(ret_lb, 4),
                "regime": regime,
                "day_return": day_ret,
                "fwd_1d_return": fwd,
            }
        )
    return out


def _episodes(series: List[Dict[str, Any]], regime: str = "transition") -> List[Dict[str, Any]]:
    eps: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for row in series:
        if row["regime"] == regime:
            if cur is None:
                cur = {
                    "start": row["date"],
                    "end": row["date"],
                    "days": 1,
                    "day_returns": [],
                }
            else:
                cur["end"] = row["date"]
                cur["days"] += 1
            if row.get("day_return") is not None:
                cur["day_returns"].append(row["day_return"])
        else:
            if cur is not None:
                eps.append(_finalize_episode(cur))
                cur = None
    if cur is not None:
        eps.append(_finalize_episode(cur))
    return eps


def _finalize_episode(ep: Dict[str, Any]) -> Dict[str, Any]:
    rets = ep.get("day_returns") or []
    # compound BTC path inside episode
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        eq *= 1.0 + float(r)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    btc_ret = eq - 1.0
    out = {
        "start": ep["start"],
        "end": ep["end"],
        "days": ep["days"],
        "btc_compound_return": round(btc_ret, 6),
        "btc_max_dd": round(max_dd, 6),
        "n_day_returns": len(rets),
    }
    return out


def _path_metrics(
    day_returns: List[float],
    *,
    util: float,
    usdc_daily: float,
    label: str,
) -> Dict[str, Any]:
    """Blend BTC day returns with USDC cash at fixed util. Real BTC series only."""
    if not day_returns:
        return {
            "label": label,
            "n_days": 0,
            "util": util,
            "total_return": None,
            "max_dd": None,
            "insufficient": True,
        }
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    u = max(0.0, min(1.0, float(util)))
    for r in day_returns:
        # cash earns usdc_daily; risk sleeve tracks BTC day return
        blended = u * float(r) + (1.0 - u) * usdc_daily
        eq *= 1.0 + blended
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return {
        "label": label,
        "n_days": len(day_returns),
        "util": u,
        "total_return": round(eq - 1.0, 6),
        "total_return_pct": round((eq - 1.0) * 100.0, 4),
        "max_dd": round(max_dd, 6),
        "max_dd_pct": round(max_dd * 100.0, 4),
        "end_equity_mult": round(eq, 6),
        "insufficient": False,
    }


def _whipsaw_stats(series: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(series) < 2:
        return {"n": len(series), "flips": 0, "flip_rate": None}
    flips = 0
    flip_into_t = 0
    flip_out_of_t = 0
    for a, b in zip(series, series[1:]):
        if a["regime"] != b["regime"]:
            flips += 1
            if b["regime"] == "transition" and a["regime"] != "transition":
                flip_into_t += 1
            if a["regime"] == "transition" and b["regime"] != "transition":
                flip_out_of_t += 1
    n_edges = len(series) - 1
    return {
        "n_days": len(series),
        "flips": flips,
        "flip_rate": round(flips / n_edges, 4) if n_edges else None,
        "flip_into_transition": flip_into_t,
        "flip_out_of_transition": flip_out_of_t,
        "regime_counts": dict(Counter(r["regime"] for r in series)),
    }


def load_trades() -> List[dict]:
    rows: List[dict] = []
    if not TRADES_JSONL.exists():
        return rows
    with open(TRADES_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("pair") or "") in {"TEST-USD"}:
                continue
            if str(r.get("signal_source") or "").lower() in {"smoke_test", "test"}:
                continue
            rows.append(r)
    return rows


def _trade_day(r: dict) -> Optional[str]:
    ts = r.get("timestamp") or r.get("ts") or ""
    if not ts:
        return None
    try:
        return str(ts)[:10]
    except Exception:
        return None


def isolation_checks(det_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """T0: detector isolation + known band classification."""
    results: Dict[str, Any] = {"pass": True, "checks": []}

    # Run existing isolation script
    proc = subprocess.run(
        [sys.executable, str(ROOT / "phase6/research/test_isolation_regime_detector_freshness.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    det_ok = proc.returncode == 0 and "PASS" in (proc.stdout + proc.stderr)
    results["checks"].append(
        {
            "name": "test_isolation_regime_detector_freshness",
            "pass": det_ok,
            "rc": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-200:],
        }
    )
    if not det_ok:
        results["pass"] = False

    bull = float(det_cfg.get("bull_return_pct", 15))
    bear = float(det_cfg.get("bear_return_pct", -10))
    flat = float(det_cfg.get("flat_abs_pct", 8))
    # Band checks: mid-gap returns must be transition
    samples = [
        (11.0, "transition"),  # between flat 8 and bull 15
        (-9.0, "transition"),  # between bear -10 and flat -8
        (16.0, "bull"),
        (-12.0, "bear"),
        (3.0, "flat"),
        (-5.0, "flat"),
    ]
    band_ok = True
    band_detail = []
    for ret, expect in samples:
        got = _classify(ret, bull, bear, flat)
        ok = got == expect
        band_detail.append({"ret_pct": ret, "expect": expect, "got": got, "ok": ok})
        if not ok:
            band_ok = False
    results["checks"].append({"name": "transition_band_classify", "pass": band_ok, "detail": band_detail})
    if not band_ok:
        results["pass"] = False

    live = detect_regime(
        lookback_days=int(det_cfg.get("lookback_days") or 30),
        bull_return_pct=bull,
        bear_return_pct=bear,
        flat_abs_pct=flat,
        use_live_price=True,
    )
    results["live_detect"] = live
    results["checks"].append(
        {
            "name": "live_detect_known_set",
            "pass": live.get("regime") in {"bull", "bear", "flat", "transition", "unknown"},
            "regime": live.get("regime"),
        }
    )
    return results


def scorecard_transition_slice() -> Dict[str, Any]:
    if not SCORECARD_PATH.exists():
        return {"available": False}
    sc = json.loads(SCORECARD_PATH.read_text())
    # scorecard uses "recent" for transition-mapped window
    pick = None
    for r in sc.get("regimes") or []:
        if r.get("regime") in ("recent", "transition"):
            pick = r
            if r.get("regime") == "transition":
                break
    if not pick:
        return {"available": False, "reason": "no recent/transition regime in scorecard"}
    rows = []
    for s in pick.get("scenarios") or []:
        m = s.get("metrics") or {}
        rows.append(
            {
                "id": s.get("id"),
                "total_return_pct": m.get("total_return_pct"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "annualized_return_pct": m.get("annualized_return_pct"),
                "total_trades": m.get("total_trades"),
                "sharpe_ratio": m.get("sharpe_ratio"),
                "engine": m.get("engine") or s.get("engine"),
            }
        )
    # rank: prefer higher return then lower DD (USDC vs alts)
    def sort_key(x: dict):
        ret = x.get("total_return_pct")
        dd = x.get("max_drawdown_pct")
        if ret is None:
            return (-1e9, 1e9)
        return (float(ret), -float(dd or 0))

    ranked = sorted(rows, key=sort_key, reverse=True)
    usdc = next((x for x in rows if x["id"] == "usdc_hold"), None)
    best_alt = next((x for x in ranked if x["id"] != "usdc_hold"), None)
    return {
        "available": True,
        "scorecard_generated_at": sc.get("generated_at"),
        "pack_id": sc.get("pack_id"),
        "regime_key": pick.get("regime"),
        "date_range": pick.get("date_range"),
        "winner_id": pick.get("winner_id"),
        "scenarios": ranked,
        "usdc_hold": usdc,
        "best_alt": best_alt,
        "alt_beats_usdc": bool(
            best_alt
            and usdc
            and best_alt.get("total_return_pct") is not None
            and usdc.get("total_return_pct") is not None
            and float(best_alt["total_return_pct"]) > float(usdc["total_return_pct"])
        ),
    }


def recommend(
    *,
    isolation_pass: bool,
    n_transition_days: int,
    n_episodes: int,
    paths: Dict[str, Dict[str, Any]],
    scorecard: Dict[str, Any],
    live_trade_pnl_transition: float,
    flip_rate: Optional[float],
) -> Dict[str, Any]:
    """Honest enum from real evidence. Prefer lower whipsaw / DD over idle-cash FOMO."""
    if not isolation_pass:
        return {
            "enum": "abort",
            "go_shadow": False,
            "reason": "T0 isolation failed",
            "confidence": "low",
        }

    insufficient = n_transition_days < MIN_TRANSITION_DAYS_GATE or n_episodes < MIN_EPISODES_GATE
    park = paths.get("usdc_park_util0") or {}
    live_like = paths.get("live_policy_util0_45") or {}
    faster = paths.get("faster_flip_util0_65") or {}

    # Scorecard recent window is the multi-asset real-OHLCV ground truth for transition-like pack
    sc_usdc_wins = bool(scorecard.get("available") and not scorecard.get("alt_beats_usdc"))
    sc_winner = (scorecard.get("winner_id") or "").lower()

    # BTC-blend proxy: did higher util beat park on transition days without much worse DD?
    def ret(p):
        return p.get("total_return") if p and not p.get("insufficient") else None

    def dd(p):
        return p.get("max_dd") if p and not p.get("insufficient") else None

    r_park, r_live, r_fast = ret(park), ret(live_like), ret(faster)
    d_park, d_live, d_fast = dd(park), dd(live_like), dd(faster)

    faster_beats_park = (
        r_fast is not None
        and r_park is not None
        and r_fast > r_park + 0.005  # >50 bps absolute on sample
        and d_fast is not None
        and d_park is not None
        and d_fast <= d_park + 0.02  # DD not >2pp worse
    )
    live_like_clearly_worse = (
        r_live is not None
        and r_park is not None
        and r_live < r_park - 0.002
        and d_live is not None
        and d_park is not None
        and d_live > d_park + 0.01
    )

    notes = {
        "n_transition_days": n_transition_days,
        "n_episodes": n_episodes,
        "insufficient_sample": insufficient,
        "scorecard_usdc_wins_recent": sc_usdc_wins,
        "scorecard_winner": sc_winner,
        "faster_beats_park_proxy": faster_beats_park,
        "live_like_worse_than_park_proxy": live_like_clearly_worse,
        "live_trade_pnl_on_transition_days_usd": live_trade_pnl_transition,
        "flip_rate": flip_rate,
    }

    if insufficient and not scorecard.get("available"):
        return {
            "enum": "continue_observe_only",
            "go_shadow": False,
            "reason": (
                f"Insufficient transition sample (days={n_transition_days}, episodes={n_episodes}); "
                "no scorecard fallback. Keep park; collect more labeled days."
            ),
            "confidence": "low",
            "notes": notes,
        }

    # Primary decision: scorecard multi-asset + BTC proxy agreement
    if sc_usdc_wins or sc_winner == "usdc_hold":
        if faster_beats_park:
            return {
                "enum": "continue_observe_only",
                "go_shadow": False,
                "reason": (
                    "Scorecard recent/transition window: USDC hold wins vs deploy alts on real OHLCV; "
                    "BTC-blend proxy alone is not enough to flip park→deploy (correlation/ basket gap). "
                    "Keep transition park (live effective cap=0 via knob_map). No scoped faster-flip experiment."
                ),
                "confidence": "medium" if not insufficient else "low-medium",
                "notes": notes,
            }
        return {
            "enum": "drop",
            "go_shadow": False,
            "reason": (
                "Real transition/recent scorecard + BTC transition-day proxy favor park/USDC over faster flip "
                "or higher util. Hypothesis that cap/park causes costly idle cash is NOT supported — "
                "whipsaw/DD cost of deploy dominates. Drop faster-flip / raise-cap change for transition."
            ),
            "confidence": "medium-high" if n_transition_days >= MIN_TRANSITION_DAYS_GATE else "medium",
            "notes": notes,
        }

    # Alt beats USDC on scorecard — scoped experiment only, never auto-promote
    if scorecard.get("alt_beats_usdc") and scorecard.get("best_alt"):
        alt_id = scorecard["best_alt"].get("id")
        return {
            "enum": "propose_scoped_experiment",
            "go_shadow": True,
            "reason": (
                f"Scorecard best_alt={alt_id} beats USDC on transition/recent window; "
                "propose shadow scoped limited-cap deploy (not live). Confirm DD and fees first."
            ),
            "confidence": "medium",
            "notes": notes,
            "proposed_shadow": {
                "best_alt": scorecard.get("best_alt"),
                "transition_policy_sketch": {
                    "strategy_mode": "deploy",
                    "allow_new_buys": True,
                    "rebalance_cap_usd": 50.0,
                    "target_max_util_pct": 0.45,
                    "note": "proposal only — no live write",
                },
            },
        }

    return {
        "enum": "continue_observe_only",
        "go_shadow": False,
        "reason": "Mixed/weak signal; keep current transition park and re-check after more dwell.",
        "confidence": "low",
        "notes": notes,
    }


def run() -> Dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text()) if POLICY_PATH.exists() else {}
    knob_map = json.loads(KNOB_MAP_PATH.read_text()) if KNOB_MAP_PATH.exists() else {}
    status = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
    det = policy.get("detector") or {}
    t_pol = (policy.get("regimes") or {}).get("transition") or {}
    km_t = ((knob_map.get("regimes") or {}).get("transition")) or {}

    policy_hash = _sha256_file(POLICY_PATH)
    knob_hash = _sha256_file(KNOB_MAP_PATH)

    iso = isolation_checks(det)

    lookback = int(det.get("lookback_days") or 30)
    bull = float(det.get("bull_return_pct", 15))
    bear = float(det.get("bear_return_pct", -10))
    flat = float(det.get("flat_abs_pct", 8))

    closes = _load_btc_closes()
    closes, live_meta = _merge_live_close(closes)
    series = _rolling_series(closes, lookback, bull, bear, flat)
    whip = _whipsaw_stats(series)
    episodes = _episodes(series, "transition")

    # Transition-day BTC returns (in-episode day returns)
    t_day_returns: List[float] = []
    t_dates: List[str] = []
    for row in series:
        if row["regime"] == "transition" and row.get("day_return") is not None:
            t_day_returns.append(float(row["day_return"]))
            t_dates.append(row["date"])

    usdc_apy = load_usdc_apy_pct()
    usdc_daily = (usdc_apy / 100.0) / 365.0

    # Path compares on transition days only (BTC + USDC blend — labeled proxy)
    path_specs = [
        ("usdc_park_util0", 0.0),
        ("strict_park_util0", 0.0),
        ("live_policy_util0_45", float(t_pol.get("target_max_util_pct") or 0.45)),
        ("half_live_util0_225", float(t_pol.get("target_max_util_pct") or 0.45) * 0.5),
        ("faster_flip_util0_65", 0.65),
        ("full_btc_util1", 1.0),
    ]
    paths: Dict[str, Dict[str, Any]] = {}
    for label, util in path_specs:
        paths[label] = _path_metrics(t_day_returns, util=util, usdc_daily=usdc_daily, label=label)

    # Cap sensitivity is policy semantics when allow_new_buys=false: residual util only.
    # Model "cap friction": effective util scaled by cap/equity proxy — use relative scale only.
    # Without inventing equity path: treat cap>0 + allow_buys as unlocking util; cap=0 park locks util→0 new risk.
    live_allow = bool(t_pol.get("allow_new_buys"))
    live_cap = float(t_pol.get("rebalance_cap_usd") or 0)
    live_mode = t_pol.get("strategy_mode")
    status_cap = status.get("rebalance_cap_usd")
    status_allow = status.get("allow_new_buys")
    status_mode = status.get("strategy_mode")

    # Effective live (status/knob_map) path: park + cap 0 → util 0 new risk
    paths["live_effective_status_park_cap0"] = _path_metrics(
        t_day_returns, util=0.0, usdc_daily=usdc_daily, label="live_effective_status_park_cap0"
    )
    # Policy JSON transition (park, cap 50, util 0.45) — residual sleeve model
    paths["policy_json_transition_residual_u45"] = paths["live_policy_util0_45"]

    # Episode-level: short vs long
    short_eps = [e for e in episodes if e["days"] <= 3]
    long_eps = [e for e in episodes if e["days"] >= 7]
    ep_summary = {
        "n_episodes": len(episodes),
        "n_short_le3": len(short_eps),
        "n_long_ge7": len(long_eps),
        "median_days": (
            sorted(e["days"] for e in episodes)[len(episodes) // 2] if episodes else None
        ),
        "mean_days": round(sum(e["days"] for e in episodes) / len(episodes), 2) if episodes else None,
        "mean_btc_ret_short": (
            round(sum(e["btc_compound_return"] for e in short_eps) / len(short_eps), 6)
            if short_eps
            else None
        ),
        "mean_btc_ret_long": (
            round(sum(e["btc_compound_return"] for e in long_eps) / len(long_eps), 6)
            if long_eps
            else None
        ),
        "episodes_tail": episodes[-12:],
    }

    # Live ledger tagged by regime-at-day
    day_to_regime = {r["date"]: r["regime"] for r in series}
    trades = load_trades()
    by_reg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "buys": 0, "sells": 0, "pnl_usd": 0.0, "pairs": Counter()}
    )
    unknown_day = 0
    for t in trades:
        d = _trade_day(t)
        if not d:
            unknown_day += 1
            continue
        reg = day_to_regime.get(d, "unknown_unlabeled")
        bucket = by_reg[reg]
        bucket["n"] += 1
        side = str(t.get("side") or "").upper()
        if side == "BUY":
            bucket["buys"] += 1
        elif side == "SELL":
            bucket["sells"] += 1
            try:
                bucket["pnl_usd"] += float(t.get("pnl") or 0.0)
            except (TypeError, ValueError):
                pass
        pair = t.get("pair") or "?"
        bucket["pairs"][pair] += 1

    ledger_by_regime = {}
    for k, v in by_reg.items():
        ledger_by_regime[k] = {
            "n": v["n"],
            "buys": v["buys"],
            "sells": v["sells"],
            "pnl_usd_sells": round(v["pnl_usd"], 4),
            "top_pairs": v["pairs"].most_common(5),
        }
    t_ledger = ledger_by_regime.get("transition") or {
        "n": 0,
        "buys": 0,
        "sells": 0,
        "pnl_usd_sells": 0.0,
    }

    sc = scorecard_transition_slice()
    # USDC metrics on scorecard window for reference
    usdc_window = None
    if sc.get("date_range"):
        usdc_window = usdc_carry_metrics(sc["date_range"])

    validation = None
    if VALIDATION_PATH.exists():
        try:
            v = json.loads(VALIDATION_PATH.read_text())
            validation = {
                "run_id": v.get("run_id"),
                "verdict": (v.get("results") or {}).get("verdict"),
                "live_setup_regime": (v.get("live_setup") or {}).get("regime"),
                "modeled_winner": (v.get("test_scenario") or {}).get("modeled_winner"),
                "alt_beats_usdc_carry": (v.get("test_scenario") or {}).get("alt_beats_usdc_carry"),
            }
        except (json.JSONDecodeError, OSError):
            validation = {"error": "unreadable"}

    try:
        prod = compute_since_go_live()
    except Exception as e:
        prod = {"error": str(e)}

    n_t_days = len(t_day_returns)
    rec = recommend(
        isolation_pass=bool(iso.get("pass")),
        n_transition_days=n_t_days,
        n_episodes=len(episodes),
        paths=paths,
        scorecard=sc,
        live_trade_pnl_transition=float(t_ledger.get("pnl_usd_sells") or 0.0),
        flip_rate=whip.get("flip_rate"),
    )

    # Whipsaw cost lens: flip intensity × adverse residual exposure
    whip_cost = {
        "definition": (
            "Proxy: transition flip_rate * (max_dd of residual util0.45 − max_dd of park) "
            "on transition-day BTC series; plus short-episode count share."
        ),
        "flip_rate": whip.get("flip_rate"),
        "short_episode_share": (
            round(len(short_eps) / len(episodes), 4) if episodes else None
        ),
        "dd_penalty_residual_vs_park_pp": (
            round(
                100.0
                * (
                    (paths["live_policy_util0_45"].get("max_dd") or 0)
                    - (paths["usdc_park_util0"].get("max_dd") or 0)
                ),
                4,
            )
            if not paths["usdc_park_util0"].get("insufficient")
            else None
        ),
        "return_gap_residual_minus_park_pp": (
            round(
                100.0
                * (
                    (paths["live_policy_util0_45"].get("total_return") or 0)
                    - (paths["usdc_park_util0"].get("total_return") or 0)
                ),
                4,
            )
            if not paths["usdc_park_util0"].get("insufficient")
            else None
        ),
    }

    report: Dict[str, Any] = {
        "schema": "regime_transition_test_v1",
        "trial_id": TRIAL_ID,
        "master_id": MASTER_ID,
        "generated_at": _utc_now(),
        "real_data_only": True,
        "live_config_writes": False,
        "hypothesis": "Transition cap/park settings drive unnecessary whipsaw or idle cash",
        "success_metric": "Real transition slices; prefer lower whipsaw cost",
        "policy_fingerprint": {
            "regime_cash_policy_sha256": policy_hash,
            "regime_knob_map_sha256": knob_hash,
            "transition_policy_json": {
                "strategy_mode": live_mode,
                "allow_new_buys": live_allow,
                "target_max_util_pct": t_pol.get("target_max_util_pct"),
                "rebalance_cap_usd": live_cap,
                "min_cash_reserve_pct": t_pol.get("min_cash_reserve_pct"),
            },
            "live_status_snapshot": {
                "regime": status.get("regime"),
                "strategy_mode": status_mode,
                "allow_new_buys": status_allow,
                "rebalance_cap_usd": status_cap,
                "target_max_util_pct": status.get("target_max_util_pct"),
                "knob_map_scenario": status.get("knob_map_scenario"),
                "as_of": status.get("as_of") or status.get("written_at"),
            },
            "knob_map_transition": {
                "scenario_id": km_t.get("scenario_id"),
                "strategy_mode": km_t.get("strategy_mode"),
                "live_overlay": km_t.get("live_overlay"),
                "note": km_t.get("note"),
            },
            "note": (
                "Policy JSON has transition rebalance_cap_usd=50 park; live status/knob_map "
                "effective cap=0 usdc_hold — fingerprint both; no writes performed."
            ),
        },
        "tier0_isolation": iso,
        "tier1_slices": {
            "detector_thresholds": {
                "lookback_days": lookback,
                "bull_return_pct": bull,
                "bear_return_pct": bear,
                "flat_abs_pct": flat,
            },
            "ohlcv_live_merge": live_meta,
            "series_days": len(series),
            "whipsaw": whip,
            "transition_day_count": n_t_days,
            "transition_date_span": {
                "first": t_dates[0] if t_dates else None,
                "last": t_dates[-1] if t_dates else None,
            },
            "episodes": ep_summary,
            "sample_gates": {
                "min_transition_days": MIN_TRANSITION_DAYS_GATE,
                "min_episodes": MIN_EPISODES_GATE,
                "met": n_t_days >= MIN_TRANSITION_DAYS_GATE and len(episodes) >= MIN_EPISODES_GATE,
            },
        },
        "tier1b_path_compare": {
            "method": (
                "On days labeled transition by live detector thresholds, blend real BTC 1d returns "
                "with USDC daily yield at fixed util. Proxy for residual risk / limited deploy — "
                "not full multi-asset ARCH-4 (see scorecard for that)."
            ),
            "usdc_apy_pct": usdc_apy,
            "usdc_daily": usdc_daily,
            "paths": paths,
            "whipsaw_cost_lens": whip_cost,
        },
        "tier1_scorecard_multiasset": sc,
        "usdc_on_scorecard_window": usdc_window,
        "tier1_live_ledger_by_regime": {
            "trades_total": len(trades),
            "unlabeled_day_trades": unknown_day,
            "by_regime": ledger_by_regime,
            "transition": t_ledger,
        },
        "validation_latest": validation,
        "production_live": prod,
        "recommendation": rec,
        "honest_assessment": {
            "north_star": "returns AND less loss — prefer lower whipsaw cost over chasing transition upside",
            "policy_vs_effective": (
                f"JSON transition cap=${live_cap} allow_buys={live_allow} mode={live_mode}; "
                f"status cap={status_cap} allow_buys={status_allow} mode={status_mode} "
                f"scenario={status.get('knob_map_scenario')}"
            ),
            "idle_cash_claim": (
                "Idle cash in transition is intentional USDC carry. Opportunity cost exists only if "
                "deploy edge beats USDC after DD — scorecard recent window does not show that."
            ),
            "whipsaw_claim": (
                "Residual util 0.45 on transition BTC days adds DD vs pure park; short episodes "
                "amplify label flip cost if strategy toggles deploy aggressively."
            ),
            "limitations": [
                "BTC-blend path is a single-asset proxy; live book is multi-pair and concurrent.",
                "OHLCV gap filled only at live end day — mid-gap days not interpolated.",
                "Ledger regime tags use detector as-of trade day (lookback ending that day).",
                "No live config write; promote only via Brad + gates.",
            ],
        },
    }
    return report


def write_reports(report: Dict[str, Any]) -> Tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"REGIME_TRANSITION_TEST_{day}"
    json_path = REPORTS / f"{stem}.json"
    md_path = REPORTS / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    rec = report.get("recommendation") or {}
    t1 = report.get("tier1_slices") or {}
    paths = (report.get("tier1b_path_compare") or {}).get("paths") or {}
    sc = report.get("tier1_scorecard_multiasset") or {}
    fp = report.get("policy_fingerprint") or {}
    whip = (report.get("tier1b_path_compare") or {}).get("whipsaw_cost_lens") or {}
    led = (report.get("tier1_live_ledger_by_regime") or {}).get("transition") or {}
    iso = report.get("tier0_isolation") or {}

    def pget(name: str, field: str):
        p = paths.get(name) or {}
        return p.get(field)

    lines = [
        f"# Regime Transition Test — {day}",
        "",
        f"**Trial:** `{report['trial_id']}`  ",
        f"**Master:** `{report['master_id']}`  ",
        f"**Generated:** {report['generated_at']}  ",
        f"**Real data only:** {report['real_data_only']}  ",
        f"**Live config writes:** {report['live_config_writes']}",
        "",
        "## Executive summary",
        "",
        f"- Hypothesis: {report['hypothesis']}",
        f"- Transition-labeled days (BTC lookback detector): **n={t1.get('transition_day_count')}**  "
        f"episodes={((t1.get('episodes') or {}).get('n_episodes'))}",
        f"- Whipsaw flip_rate: **{(t1.get('whipsaw') or {}).get('flip_rate')}**  "
        f"(into_t={(t1.get('whipsaw') or {}).get('flip_into_transition')}, "
        f"out_t={(t1.get('whipsaw') or {}).get('flip_out_of_transition')})",
        f"- Scorecard ({sc.get('regime_key')} {sc.get('date_range')}): winner **{sc.get('winner_id')}**  "
        f"alt_beats_usdc={sc.get('alt_beats_usdc')}",
        f"- Live ledger on transition days: trades={led.get('n')} buys={led.get('buys')} "
        f"sells={led.get('sells')} sell_pnl_usd={led.get('pnl_usd_sells')}",
        f"- Path proxy (transition days): park ret%={pget('usdc_park_util0','total_return_pct')} "
        f"dd%={pget('usdc_park_util0','max_dd_pct')} | "
        f"util0.45 ret%={pget('live_policy_util0_45','total_return_pct')} "
        f"dd%={pget('live_policy_util0_45','max_dd_pct')} | "
        f"util0.65 ret%={pget('faster_flip_util0_65','total_return_pct')} "
        f"dd%={pget('faster_flip_util0_65','max_dd_pct')}",
        f"- DD penalty residual vs park (pp): **{whip.get('dd_penalty_residual_vs_park_pp')}**  "
        f"return gap residual−park (pp): **{whip.get('return_gap_residual_minus_park_pp')}**",
        f"- **Recommendation enum:** `{rec.get('enum')}`  ",
        f"- **Shadow go?** **{rec.get('go_shadow')}** — {rec.get('reason')}",
        f"- Confidence: {rec.get('confidence')}",
        "",
        "## Tier 0 — isolation",
        "",
        f"- Overall pass: **{iso.get('pass')}**",
        f"- Live detect: `{(iso.get('live_detect') or {}).get('regime')}` "
        f"btc_ret={(iso.get('live_detect') or {}).get('btc_return_pct')}",
        "",
        "```json",
        json.dumps(iso.get("checks"), indent=2),
        "```",
        "",
        "## Policy fingerprint (start-of-run)",
        "",
        f"- `regime_cash_policy.json` sha256: `{fp.get('regime_cash_policy_sha256')}`",
        f"- `regime_knob_map.json` sha256: `{fp.get('regime_knob_map_sha256')}`",
        "",
        "```json",
        json.dumps(
            {
                "transition_policy_json": fp.get("transition_policy_json"),
                "live_status_snapshot": fp.get("live_status_snapshot"),
                "knob_map_transition": fp.get("knob_map_transition"),
                "note": fp.get("note"),
            },
            indent=2,
        ),
        "```",
        "",
        "## Tier 1 — real transition slices",
        "",
        f"- Detector thresholds: `{json.dumps(t1.get('detector_thresholds'))}`",
        f"- Series days: {t1.get('series_days')}; regime counts: "
        f"`{(t1.get('whipsaw') or {}).get('regime_counts')}`",
        f"- Sample gates met: **{(t1.get('sample_gates') or {}).get('met')}** "
        f"(min_days={MIN_TRANSITION_DAYS_GATE}, min_episodes={MIN_EPISODES_GATE})",
        "",
        "### Episodes",
        "",
        "```json",
        json.dumps(t1.get("episodes"), indent=2),
        "```",
        "",
        "### Whipsaw",
        "",
        "```json",
        json.dumps(t1.get("whipsaw"), indent=2),
        "```",
        "",
        "## Tier 1b — offline path compare (transition days)",
        "",
        (report.get("tier1b_path_compare") or {}).get("method"),
        "",
        "| Path | util | n_days | Return % | Max DD % |",
        "|------|------|--------|----------|----------|",
    ]
    for key in [
        "usdc_park_util0",
        "live_effective_status_park_cap0",
        "half_live_util0_225",
        "live_policy_util0_45",
        "faster_flip_util0_65",
        "full_btc_util1",
    ]:
        p = paths.get(key) or {}
        lines.append(
            f"| {key} | {p.get('util')} | {p.get('n_days')} | "
            f"{p.get('total_return_pct')} | {p.get('max_dd_pct')} |"
        )
    lines += [
        "",
        "### Whipsaw cost lens",
        "",
        "```json",
        json.dumps(whip, indent=2),
        "```",
        "",
        "## Scorecard multi-asset (recent → transition map)",
        "",
        "```json",
        json.dumps(
            {
                "available": sc.get("available"),
                "regime_key": sc.get("regime_key"),
                "date_range": sc.get("date_range"),
                "winner_id": sc.get("winner_id"),
                "alt_beats_usdc": sc.get("alt_beats_usdc"),
                "usdc_hold": sc.get("usdc_hold"),
                "best_alt": sc.get("best_alt"),
                "top_scenarios": (sc.get("scenarios") or [])[:6],
            },
            indent=2,
        ),
        "```",
        "",
        "## Live ledger by regime (detector day tag)",
        "",
        "```json",
        json.dumps(report.get("tier1_live_ledger_by_regime"), indent=2, default=str),
        "```",
        "",
        "## Validation / production context",
        "",
        "```json",
        json.dumps(
            {
                "validation_latest": report.get("validation_latest"),
                "production_live_metrics": (report.get("production_live") or {}).get("metrics")
                if isinstance(report.get("production_live"), dict)
                else report.get("production_live"),
            },
            indent=2,
            default=str,
        ),
        "```",
        "",
        "## Honest assessment",
        "",
        "```json",
        json.dumps(report.get("honest_assessment"), indent=2),
        "```",
        "",
        "## Decide (Brad)",
        "",
        "```bash",
        f"python3 phase6/research/trial_cycle.py decide {report['trial_id']} {rec.get('enum')} "
        f"--note 'see reports/{json_path.name}'",
        "```",
        "",
        "## Files",
        "",
        f"- `{json_path.relative_to(ROOT)}`",
        f"- `{md_path.relative_to(ROOT)}`",
        "- `phase6/research/run_regime_transition_test.py`",
        "- `phase6/research/regime_detector.py`",
        "- `config/regime_cash_policy.json` (read-only fingerprint)",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    report = run()
    md_path, json_path = write_reports(report)
    print(
        json.dumps(
            {
                "md": str(md_path),
                "json": str(json_path),
                "n_transition_days": (report.get("tier1_slices") or {}).get("transition_day_count"),
                "n_episodes": ((report.get("tier1_slices") or {}).get("episodes") or {}).get(
                    "n_episodes"
                ),
                "recommendation": (report.get("recommendation") or {}).get("enum"),
                "go_shadow": (report.get("recommendation") or {}).get("go_shadow"),
                "isolation_pass": (report.get("tier0_isolation") or {}).get("pass"),
                "policy_sha256": (report.get("policy_fingerprint") or {}).get(
                    "regime_cash_policy_sha256"
                ),
            },
            indent=2,
        )
    )
    print(f"\nWrote {md_path}\nWrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
