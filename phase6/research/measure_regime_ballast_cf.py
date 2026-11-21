#!/usr/bin/env python3
"""Alt A — Regime-gated ballast / risk-premia measure CF (no live knobs).

Compares deposit-agnostic synthetic paths on real Coinbase daily OHLCV:
  - cash_hold
  - btc_hodl / eth_hodl / ballast_50_50
  - regime_gated_ballast (risk-on only outside bear climate; fee on switches)
  - actual_book (deposit-adjusted NAV from phase6.db daily series)

Honesty:
  - JUDGMENT/measure path — not a printer claim
  - less-loss vs bags OK; HIT_10 only if abs + ΔBH clear bars
  - No orders, no config writes

Artifacts:
  data/state/measure_regime_ballast_cf_latest.json
  reports/MEASURE_REGIME_BALLAST_CF_LATEST.md
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
CACHE = ROOT / "data" / "cache" / "measure_regime_ballast"
OUT_JSON = STATE / "measure_regime_ballast_cf_latest.json"
OUT_MD = REPORTS / "MEASURE_REGIME_BALLAST_CF_LATEST.md"
OUT_HALF_JSON = STATE / "measure_regime_ballast_cf_halfsample_latest.json"
OUT_HALF_MD = REPORTS / "MEASURE_REGIME_BALLAST_CF_HALFSAMPLE_LATEST.md"
OUT_STAMPS = STATE / "measure_regime_stamps_dense_latest.json"
SCHEMA = "measure_regime_ballast_cf_v2"
LIVE_APPLY = False

# Climate from BTC 30d return (aligned with climate crumbs language)
R30_BEAR = -10.0
R30_SOFT = -5.0
R30_BULL = 8.0
SWITCH_FEE_FRAC = 0.008  # taker-ish one-way when flipping cash↔risk
DEFAULT_DAYS = 120
# Prefer logged stamp if observed within this many days (else r30 proxy)
LOGGED_STAMP_MAX_AGE_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_day(s: str) -> date:
    return date.fromisoformat(s[:10])


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def fetch_daily_closes(pair: str, days: int = 400) -> List[Tuple[date, float]]:
    """Coinbase public daily candles → (day, close) ascending."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{pair.replace('-', '_')}_1d.json"
    url = (
        f"https://api.exchange.coinbase.com/products/{pair}/candles"
        f"?granularity=86400"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "phase6-measure-cf"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    # [time, low, high, open, close, volume]
    rows: List[Tuple[date, float]] = []
    for c in raw:
        try:
            t = int(c[0])
            close = float(c[4])
            d = datetime.fromtimestamp(t, tz=timezone.utc).date()
            rows.append((d, close))
        except Exception:
            continue
    rows = sorted({d: c for d, c in rows}.items())  # unique by day
    payload = {
        "pair": pair,
        "source": "coinbase_public_daily",
        "refreshed_at": _now().isoformat(),
        "closes": [{"d": d.isoformat(), "c": c} for d, c in rows],
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    if days and len(rows) > days:
        rows = rows[-days:]
    return rows


def load_or_fetch_closes(pair: str, days: int = 400, *, allow_network: bool = True) -> List[Tuple[date, float]]:
    cache_path = CACHE / f"{pair.replace('-', '_')}_1d.json"
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = [
                (_parse_day(x["d"]), float(x["c"]))
                for x in (payload.get("closes") or [])
            ]
            rows = sorted(rows)
            if rows:
                age_h = 999.0
                try:
                    ra = datetime.fromisoformat(
                        str(payload.get("refreshed_at", "")).replace("Z", "+00:00")
                    )
                    age_h = (_now() - ra.astimezone(timezone.utc)).total_seconds() / 3600.0
                except Exception:
                    pass
                if allow_network and age_h > 18:
                    try:
                        return fetch_daily_closes(pair, days=days)
                    except Exception:
                        pass
                if days and len(rows) > days:
                    rows = rows[-days:]
                return rows
        except Exception:
            pass
    if not allow_network:
        return []
    return fetch_daily_closes(pair, days=days)


def climate_from_r30(r30_pct: float) -> str:
    if r30_pct <= R30_BEAR:
        return "bear"
    if r30_pct <= R30_SOFT:
        return "soft_down"
    if r30_pct >= R30_BULL:
        return "bull"
    return "flat"


def _normalize_climate(label: Any, *, strategy_mode: Any = None) -> Optional[str]:
    """Map heterogeneous logged labels → climate bucket used by risk_weight."""
    sm = str(strategy_mode or "").lower()
    if sm in ("usdc_park", "usdc_hold", "park"):
        return "bear"
    s = str(label or "").strip().lower()
    if not s:
        return None
    # arm-switch sticky tape
    if s in ("btc_down", "risk_off", "down"):
        return "bear"
    if s in ("btc_up", "risk_on", "up"):
        return "bull"
    if s in ("btc_chop", "chop", "sideways"):
        return "flat"
    if "bear" in s or s in ("hard_down", "usdc_park"):
        return "bear"
    if "soft_down" in s or s in ("declining", "soft_downtrend"):
        return "soft_down"
    if "bull" in s or "soft_up" in s:
        return "bull"
    if "transition" in s:
        return "transition"
    if "flat" in s:
        return "flat"
    return None


def _parse_ts_any(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except Exception:
        return None


def _iter_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return out


def load_dense_regime_stamps() -> Dict[str, Any]:
    """Merge all on-disk regime/climate crumbs into a day→stamp map.

    Sources (priority on same day: later list order wins when ts newer):
      climate crumbs, cash learnings, validation history, boundary layer, arm-switch crumbs
    """
    events: List[Dict[str, Any]] = []
    sources_n: Dict[str, int] = {}

    def _add(src: str, ts: Optional[datetime], climate: Optional[str], extra: Optional[Dict[str, Any]] = None) -> None:
        if not ts or not climate:
            return
        row = {
            "ts": ts,
            "d": ts.date(),
            "climate": climate,
            "source": src,
        }
        if extra:
            row.update(extra)
        events.append(row)
        sources_n[src] = sources_n.get(src, 0) + 1

    for r in _iter_jsonl(STATE / "regime_climate_weather_crumbs.jsonl"):
        ts = _parse_ts_any(r.get("ts"))
        clim = _normalize_climate(r.get("climate"))
        _add(
            "climate_crumbs",
            ts,
            clim,
            {"r30": r.get("r30"), "r7": r.get("r7"), "weather_cap": r.get("weather_cap")},
        )

    for r in _iter_jsonl(STATE / "regime_cash_learnings.jsonl"):
        ts = _parse_ts_any(r.get("ts"))
        clim = _normalize_climate(r.get("regime"), strategy_mode=r.get("strategy_mode"))
        _add(
            "cash_learnings",
            ts,
            clim,
            {
                "strategy_mode": r.get("strategy_mode"),
                "allow_new_buys": r.get("allow_new_buys"),
                "btc_return_pct": r.get("btc_return_pct"),
            },
        )

    for r in _iter_jsonl(STATE / "regime_cash_validation_history.jsonl"):
        ts = _parse_ts_any(r.get("started_at") or r.get("ts"))
        clim = _normalize_climate(r.get("live_regime"), strategy_mode=r.get("live_mode"))
        _add(
            "cash_validation",
            ts,
            clim,
            {"live_mode": r.get("live_mode"), "cap": r.get("cap")},
        )

    for r in _iter_jsonl(STATE / "regime_boundary_layer_shadow.jsonl"):
        ts = _parse_ts_any(r.get("as_of") or r.get("ts"))
        clim = _normalize_climate(r.get("regime_layer") or r.get("regime"))
        _add("boundary_layer", ts, clim, {"layer_label": r.get("layer_label")})

    for r in _iter_jsonl(STATE / "regime_arm_switch_crumbs.jsonl"):
        ts = _parse_ts_any(r.get("ts"))
        # sticky_tape is denser directional signal; preferred_arm is product not climate
        clim = _normalize_climate(r.get("sticky_tape") or r.get("raw_tape"))
        if clim is None:
            arm = str(r.get("preferred_arm") or "").lower()
            if "risk_off" in arm or "defensive" in arm or "rel_btc_stable" in arm:
                clim = "bear"
            elif "risk_on" in arm:
                clim = "bull"
        _add(
            "arm_switch",
            ts,
            clim,
            {
                "sticky_tape": r.get("sticky_tape"),
                "preferred_arm": r.get("preferred_arm"),
                "btc_ret_7d_pct": r.get("btc_ret_7d_pct"),
            },
        )

    # live status snapshot as one stamp
    try:
        st = json.loads((STATE / "regime_cash_status.json").read_text(encoding="utf-8"))
        ts = _parse_ts_any(st.get("as_of") or st.get("ts")) or _now()
        clim = _normalize_climate(
            st.get("regime") or st.get("label"),
            strategy_mode=st.get("strategy_mode"),
        )
        _add(
            "live_status",
            ts,
            clim,
            {
                "strategy_mode": st.get("strategy_mode"),
                "allow_new_buys": st.get("allow_new_buys"),
                "rebalance_cap_usd": st.get("rebalance_cap_usd"),
            },
        )
    except Exception:
        pass

    events.sort(key=lambda e: e["ts"])
    # last event wins per calendar day
    by_day: Dict[str, Dict[str, Any]] = {}
    for e in events:
        dkey = e["d"].isoformat()
        by_day[dkey] = {
            "d": dkey,
            "climate": e["climate"],
            "source": e["source"],
            "ts": e["ts"].isoformat(),
            "r30": e.get("r30"),
            "strategy_mode": e.get("strategy_mode") or e.get("live_mode"),
            "sticky_tape": e.get("sticky_tape"),
        }

    return {
        "schema": "measure_regime_stamps_dense_v1",
        "as_of": _now().isoformat(),
        "n_events": len(events),
        "n_days_stamped": len(by_day),
        "sources_n": sources_n,
        "day_map": by_day,
        "first_day": min(by_day) if by_day else None,
        "last_day": max(by_day) if by_day else None,
    }


def risk_weight(climate: str) -> float:
    """Fraction of NAV in BTC/ETH ballast."""
    c = (climate or "").lower()
    if c in ("bear", "usdc_park"):
        return 0.0
    if c in ("soft_down", "transition"):
        return 0.35
    if c == "bull":
        return 0.85
    return 0.60  # flat


def build_aligned_panel(
    btc: List[Tuple[date, float]],
    eth: List[Tuple[date, float]],
    *,
    dense_day_map: Optional[Dict[str, Dict[str, Any]]] = None,
    logged_max_age_days: int = LOGGED_STAMP_MAX_AGE_DAYS,
) -> List[Dict[str, Any]]:
    bmap = {d: c for d, c in btc}
    emap = {d: c for d, c in eth}
    days = sorted(set(bmap) & set(emap))
    dense_day_map = dense_day_map or {}
    out: List[Dict[str, Any]] = []
    last_logged: Optional[Tuple[date, str, str]] = None  # d, climate, source

    for i, d in enumerate(days):
        row: Dict[str, Any] = {
            "d": d,
            "btc": bmap[d],
            "eth": emap[d],
            "btc_ret": 0.0,
            "eth_ret": 0.0,
            "r30_btc_pct": None,
            "climate_proxy": "flat",
            "climate_logged": None,
            "climate_logged_source": None,
            "climate_logged_age_days": None,
            "climate": "flat",
            "climate_source": "proxy_r30",
        }
        if i > 0:
            pb, pe = bmap[days[i - 1]], emap[days[i - 1]]
            if pb > 0:
                row["btc_ret"] = bmap[d] / pb - 1.0
            if pe > 0:
                row["eth_ret"] = emap[d] / pe - 1.0
        # 30 calendar-ish trading bars lookback
        j = max(0, i - 30)
        if i > j and bmap[days[j]] > 0:
            r30 = (bmap[d] / bmap[days[j]] - 1.0) * 100.0
            row["r30_btc_pct"] = round(r30, 3)
            row["climate_proxy"] = climate_from_r30(r30)

        # logged stamp: exact day or forward-fill within max age
        stamp = dense_day_map.get(d.isoformat())
        if stamp:
            last_logged = (d, str(stamp.get("climate") or "flat"), str(stamp.get("source") or "logged"))
        if last_logged is not None:
            age = (d - last_logged[0]).days
            if age <= logged_max_age_days:
                row["climate_logged"] = last_logged[1]
                row["climate_logged_source"] = last_logged[2]
                row["climate_logged_age_days"] = age

        # Primary climate for default gated arm: prefer fresh logged, else proxy
        if row["climate_logged"]:
            row["climate"] = row["climate_logged"]
            row["climate_source"] = f"logged:{row['climate_logged_source']}"
        else:
            row["climate"] = row["climate_proxy"]
            row["climate_source"] = "proxy_r30"
        out.append(row)
    return out


def _month_ends(days: List[date]) -> List[date]:
    by_m: Dict[str, date] = {}
    for d in days:
        by_m[d.strftime("%Y-%m")] = d
    return [by_m[k] for k in sorted(by_m)]


def sim_path(
    panel: List[Dict[str, Any]],
    *,
    mode: str,
    start_nav: float = 1000.0,
    fee_frac: float = SWITCH_FEE_FRAC,
) -> Dict[str, Any]:
    """Daily equity path for a synthetic arm."""
    if not panel:
        return {"mode": mode, "equity": [], "total_return_pct": 0.0, "max_dd_pct": 0.0, "n_switches": 0}

    nav = float(start_nav)
    peak = nav
    max_dd = 0.0
    equity: List[Dict[str, Any]] = []
    prev_w = 0.0
    prev_w_btc = 0.0
    prev_w_eth = 0.0
    n_switches = 0
    fee_paid = 0.0

    for i, row in enumerate(panel):
        climate = str(row.get("climate") or "flat")
        if mode == "cash_hold":
            w = 0.0
            w_btc, w_eth = 0.0, 0.0
        elif mode == "btc_hodl":
            w = 1.0
            w_btc, w_eth = 1.0, 0.0
        elif mode == "eth_hodl":
            w = 1.0
            w_btc, w_eth = 0.0, 1.0
        elif mode == "ballast_50_50":
            w = 1.0
            w_btc, w_eth = 0.5, 0.5
        elif mode == "regime_gated_ballast":
            w = risk_weight(climate)
            w_btc = w * 0.55
            w_eth = w * 0.45
        elif mode == "regime_gated_ballast_proxy":
            # force r30 proxy only (ignore logged)
            w = risk_weight(str(row.get("climate_proxy") or climate))
            w_btc = w * 0.55
            w_eth = w * 0.45
        elif mode == "regime_gated_ballast_logged":
            # logged when present else proxy (same as default climate field)
            clim_l = row.get("climate_logged") or row.get("climate_proxy") or climate
            w = risk_weight(str(clim_l))
            w_btc = w * 0.55
            w_eth = w * 0.45
        else:
            raise ValueError(f"unknown mode {mode}")

        # Apply prior day's allocation return (skip first bar)
        if i > 0:
            br = _f(row.get("btc_ret"))
            er = _f(row.get("eth_ret"))
            # previous weights carried through this bar's returns
            port_ret = prev_w_btc * br + prev_w_eth * er
            nav *= 1.0 + port_ret

        # Switch cost when target weight changes materially
        if i > 0 and abs(w - prev_w) >= 0.15:
            traded = abs(w - prev_w) * nav
            fee = traded * fee_frac
            nav -= fee
            fee_paid += fee
            n_switches += 1

        peak = max(peak, nav)
        if peak > 0:
            dd = nav / peak - 1.0
            max_dd = min(max_dd, dd)

        equity.append(
            {
                "d": row["d"].isoformat() if isinstance(row["d"], date) else str(row["d"]),
                "nav": round(nav, 4),
                "climate": climate,
                "w_risk": round(w, 3),
            }
        )
        prev_w = w
        prev_w_btc, prev_w_eth = w_btc, w_eth

    total_ret = (nav / start_nav - 1.0) * 100.0 if start_nav else 0.0
    # monthly buckets
    months: Dict[str, List[float]] = {}
    for e in equity:
        ym = e["d"][:7]
        months.setdefault(ym, []).append(e["nav"])
    month_rets = []
    for ym in sorted(months):
        xs = months[ym]
        if len(xs) < 2 or xs[0] <= 0:
            continue
        month_rets.append(
            {
                "month": ym,
                "return_pct": round((xs[-1] / xs[0] - 1.0) * 100.0, 3),
                "start_nav": round(xs[0], 2),
                "end_nav": round(xs[-1], 2),
            }
        )

    return {
        "mode": mode,
        "start_nav": start_nav,
        "end_nav": round(nav, 4),
        "total_return_pct": round(total_ret, 3),
        "max_dd_pct": round(max_dd * 100.0, 3),
        "n_switches": n_switches,
        "fee_paid_usd": round(fee_paid, 4),
        "month_returns": month_rets,
        "equity_tail": equity[-5:],
        "n_days": len(equity),
    }


def actual_book_path(
    start: date,
    end: date,
    *,
    start_nav_norm: float = 1000.0,
) -> Dict[str, Any]:
    """Deposit-adjusted-ish daily path from month_path _nav_series + external flows proxy.

    For day-to-day we use raw NAV ratio but strip large external jumps via
    median-smooth of daily returns when |ΔNAV| > 15% without price move context.
    """
    from phase6.research.month_path_scoreboard import _nav_series

    series = _nav_series()
    pts = [(t.date(), nav) for t, nav in series if start <= t.date() <= end and nav > 0]
    if len(pts) < 3:
        return {
            "mode": "actual_book",
            "status": "thin",
            "n_days": len(pts),
            "total_return_pct": None,
            "max_dd_pct": None,
            "month_returns": [],
            "note": "NAV series thin in window",
        }

    # Normalize to start_nav_norm; drop wild single-day jumps >25% as likely flow artifacts
    equity: List[Dict[str, Any]] = []
    nav = start_nav_norm
    peak = nav
    max_dd = 0.0
    n_jump_scrub = 0
    for i, (d, raw) in enumerate(pts):
        if i == 0:
            equity.append({"d": d.isoformat(), "nav": round(nav, 4), "raw_nav": round(raw, 2)})
            prev_raw = raw
            continue
        if prev_raw <= 0:
            prev_raw = raw
            continue
        r = raw / prev_raw - 1.0
        if abs(r) > 0.25:
            # treat as external flow — hold synthetic nav flat
            n_jump_scrub += 1
            r = 0.0
        nav *= 1.0 + r
        peak = max(peak, nav)
        if peak > 0:
            max_dd = min(max_dd, nav / peak - 1.0)
        equity.append({"d": d.isoformat(), "nav": round(nav, 4), "raw_nav": round(raw, 2)})
        prev_raw = raw

    total_ret = (nav / start_nav_norm - 1.0) * 100.0
    months: Dict[str, List[float]] = {}
    for e in equity:
        months.setdefault(e["d"][:7], []).append(e["nav"])
    month_rets = []
    for ym in sorted(months):
        xs = months[ym]
        if len(xs) < 2 or xs[0] <= 0:
            continue
        month_rets.append(
            {
                "month": ym,
                "return_pct": round((xs[-1] / xs[0] - 1.0) * 100.0, 3),
            }
        )

    # Also pull month_path closed months for honesty cross-check
    mp_path = STATE / "month_path_scoreboard_latest.json"
    mp_months = []
    if mp_path.exists():
        try:
            mp = json.loads(mp_path.read_text(encoding="utf-8"))
            for m in mp.get("months") or []:
                ym = str(m.get("month") or m.get("ym") or "")
                if not ym:
                    continue
                # window filter rough
                mp_months.append(
                    {
                        "month": ym,
                        "deposit_adj_return_pct": m.get("deposit_adj_return_pct"),
                        "hit_target": m.get("hit_target") or m.get("hit"),
                        "status": m.get("status"),
                    }
                )
        except Exception:
            pass

    return {
        "mode": "actual_book",
        "status": "ok",
        "start_nav": start_nav_norm,
        "end_nav": round(nav, 4),
        "total_return_pct": round(total_ret, 3),
        "max_dd_pct": round(max_dd * 100.0, 3),
        "n_days": len(equity),
        "n_jump_scrub": n_jump_scrub,
        "month_returns": month_rets,
        "month_path_crosscheck": mp_months[-8:],
        "equity_tail": equity[-5:],
        "note": "Jump-scrubbed daily NAV ratios (|>25%| day held flat as flow). Not pure deposit-adj SSOT — month_path is SSOT for closed months.",
    }


def edge_tag(arms: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    gated = arms.get("regime_gated_ballast") or {}
    actual = arms.get("actual_book") or {}
    cash = arms.get("cash_hold") or {}
    btc = arms.get("btc_hodl") or {}
    g_ret = gated.get("total_return_pct")
    a_ret = actual.get("total_return_pct")
    b_ret = btc.get("total_return_pct")
    c_ret = cash.get("total_return_pct") or 0.0

    tag = "ATTENTION_ONLY"
    reasons = []
    if g_ret is None:
        return {"edge_class": "inconclusive_sparse", "reasons": ["gated missing"]}
    if a_ret is not None and g_ret > a_ret + 1.0:
        reasons.append("gated_beats_actual_path")
    if b_ret is not None and g_ret > b_ret + 0.5:
        reasons.append("gated_beats_btc_hodl")
    elif b_ret is not None and g_ret < b_ret - 2.0:
        reasons.append("gated_loses_to_btc_hodl")
    if g_ret > c_ret + 0.5:
        reasons.append("gated_beats_cash")
    if g_ret >= 10.0 and (b_ret is None or g_ret >= (b_ret or 0) - 0.1):
        tag = "HIT_10_ABS_candidate_needs_WF"
        reasons.append("abs>=10_needs_long_WF")
    elif g_ret > 0 and a_ret is not None and a_ret < 0 and g_ret > a_ret:
        tag = "ATTENTION_ONLY_less_loss_path"
        reasons.append("green_or_less_red_vs_actual")
    elif g_ret <= 0 and a_ret is not None and g_ret > a_ret:
        tag = "ATTENTION_ONLY_less_loss_path"
        reasons.append("still_red_but_better_than_actual")
    elif g_ret <= 0:
        tag = "unstable_or_no_edge"
        reasons.append("gated_nonpositive")

    return {
        "edge_class": tag,
        "reasons": reasons,
        "gated_total_return_pct": g_ret,
        "actual_total_return_pct": a_ret,
        "btc_hodl_total_return_pct": b_ret,
        "cash_total_return_pct": c_ret,
    }


def _panel_slice(
    panel_full: List[Dict[str, Any]],
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
    panel = [r for r in panel_full if start <= r["d"] <= end]
    prior = [r for r in panel_full if r["d"] < start]
    if prior:
        panel = [prior[-1]] + panel
    return panel


def _run_arms_on_panel(
    panel: List[Dict[str, Any]],
    *,
    start: date,
    end: date,
) -> Dict[str, Any]:
    body = panel[1:] if len(panel) > 1 else panel
    arms: Dict[str, Any] = {}
    for mode in (
        "cash_hold",
        "btc_hodl",
        "eth_hodl",
        "ballast_50_50",
        "regime_gated_ballast",  # dense preferred (logged→proxy)
        "regime_gated_ballast_proxy",
        "regime_gated_ballast_logged",
    ):
        arms[mode] = sim_path(body, mode=mode)
    arms["actual_book"] = actual_book_path(start, end)
    tag = edge_tag(arms)

    from collections import Counter

    climates = [str(r.get("climate")) for r in body]
    proxies = [str(r.get("climate_proxy")) for r in body]
    logged = [str(r.get("climate_logged")) for r in body if r.get("climate_logged")]
    n = max(1, len(climates))
    n_logged = sum(1 for r in body if r.get("climate_logged"))
    mix_pct = {k: round(v / n, 3) for k, v in Counter(climates).items()}
    proxy_mix = {k: round(v / n, 3) for k, v in Counter(proxies).items()}
    logged_mix = (
        {k: round(v / max(1, len(logged)), 3) for k, v in Counter(logged).items()}
        if logged
        else {}
    )
    ranking = sorted(
        [
            (m, arms[m].get("total_return_pct"))
            for m in arms
            if arms[m].get("total_return_pct") is not None
        ],
        key=lambda x: float(x[1]),
        reverse=True,
    )
    gated = arms["regime_gated_ballast"]
    plain = (
        f"Alt A {start}→{end}: gated(dense) {gated.get('total_return_pct')}% · "
        f"proxy {arms['regime_gated_ballast_proxy'].get('total_return_pct')}% · "
        f"btc {arms['btc_hodl'].get('total_return_pct')}% · "
        f"actual {arms['actual_book'].get('total_return_pct')}% · "
        f"logged_cov={n_logged}/{len(body)} · edge={tag.get('edge_class')}"
    )
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "n_days": len(body)},
        "arms": arms,
        "edge": tag,
        "ranking_by_total_return": [{"mode": m, "total_return_pct": r} for m, r in ranking],
        "climate_mix_pct": mix_pct,
        "climate_proxy_mix_pct": proxy_mix,
        "climate_logged_mix_pct": logged_mix,
        "logged_coverage": {
            "n_days_with_logged": n_logged,
            "n_days": len(body),
            "pct": round(100.0 * n_logged / max(1, len(body)), 1),
        },
        "plain_english": plain,
    }


def half_sample_windows(start: date, end: date) -> Tuple[Tuple[date, date], Tuple[date, date]]:
    """First/second ~60d folds of [start, end]."""
    span = (end - start).days
    mid = start + timedelta(days=max(1, span // 2))
    # first half inclusive to day before mid; second from mid
    first_end = mid - timedelta(days=1)
    if first_end < start:
        first_end = start
    return (start, first_end), (mid, end)


def fold_consistency(h1: Dict[str, Any], h2: Dict[str, Any]) -> Dict[str, Any]:
    """Did gated stay less-loss vs actual/btc on both halves?"""
    def _g(h: Dict[str, Any]) -> Dict[str, Any]:
        arms = h.get("arms") or {}
        return {
            "gated": (arms.get("regime_gated_ballast") or {}).get("total_return_pct"),
            "proxy": (arms.get("regime_gated_ballast_proxy") or {}).get("total_return_pct"),
            "btc": (arms.get("btc_hodl") or {}).get("total_return_pct"),
            "actual": (arms.get("actual_book") or {}).get("total_return_pct"),
            "cash": (arms.get("cash_hold") or {}).get("total_return_pct"),
            "edge": ((h.get("edge") or {}).get("edge_class")),
        }

    a, b = _g(h1), _g(h2)
    checks = []
    ok = 0
    total = 0
    for label, fn in (
        ("gated_beats_btc_both", lambda x: x["gated"] is not None and x["btc"] is not None and x["gated"] > x["btc"]),
        ("gated_beats_actual_both", lambda x: x["gated"] is not None and x["actual"] is not None and x["gated"] > x["actual"]),
        ("gated_non_worse_than_cash_both", lambda x: x["gated"] is not None and x["cash"] is not None and x["gated"] >= x["cash"] - 1.0),
    ):
        total += 1
        c1, c2 = fn(a), fn(b)
        both = bool(c1 and c2)
        if both:
            ok += 1
        checks.append({"check": label, "h1": c1, "h2": c2, "both": both})

    # sign stability of gated return
    same_sign = None
    if a["gated"] is not None and b["gated"] is not None:
        same_sign = (a["gated"] >= 0 and b["gated"] >= 0) or (a["gated"] < 0 and b["gated"] < 0)

    if ok >= 2 and (a["gated"] is not None and b["gated"] is not None and a["gated"] > (a["btc"] or -999) and b["gated"] > (b["btc"] or -999)):
        verdict = "STABLE_less_loss_vs_hodl"
    elif ok >= 1:
        verdict = "MIXED_fold_dependent"
    else:
        verdict = "UNSTABLE_or_no_edge"

    return {
        "verdict": verdict,
        "checks_passed": ok,
        "checks_total": total,
        "same_sign_gated": same_sign,
        "h1": a,
        "h2": b,
        "checks": checks,
        "note": "Not a promote. STABLE_less_loss still ATTENTION_ONLY until longer WF.",
    }


def run_cf(
    *,
    days: int = DEFAULT_DAYS,
    start: Optional[date] = None,
    end: Optional[date] = None,
    allow_network: bool = True,
    write: bool = True,
    half_sample: bool = True,
) -> Dict[str, Any]:
    end = end or _now().date()
    start = start or (end - timedelta(days=days))

    dense = load_dense_regime_stamps()
    day_map = dense.get("day_map") or {}

    btc = load_or_fetch_closes("BTC-USD", days=days + 40, allow_network=allow_network)
    eth = load_or_fetch_closes("ETH-USD", days=days + 40, allow_network=allow_network)
    panel_full = build_aligned_panel(btc, eth, dense_day_map=day_map)
    panel = _panel_slice(panel_full, start, end)

    full = _run_arms_on_panel(panel, start=start, end=end)
    arms = full["arms"]
    tag = full["edge"]

    plain = (
        f"Alt A measure CF {start}→{end}: regime_gated_ballast(dense) "
        f"{arms['regime_gated_ballast'].get('total_return_pct')}% total · "
        f"proxy {arms['regime_gated_ballast_proxy'].get('total_return_pct')}% · "
        f"btc_hodl {arms['btc_hodl'].get('total_return_pct')}% · "
        f"actual_book {arms['actual_book'].get('total_return_pct')}% · "
        f"logged_cov={full['logged_coverage'].get('pct')}% · "
        f"edge={tag.get('edge_class')} · LIVE_APPLY={LIVE_APPLY} · not a GO."
    )

    half_payload = None
    if half_sample:
        (s1, e1), (s2, e2) = half_sample_windows(start, end)
        h1 = _run_arms_on_panel(_panel_slice(panel_full, s1, e1), start=s1, end=e1)
        h2 = _run_arms_on_panel(_panel_slice(panel_full, s2, e2), start=s2, end=e2)
        consistency = fold_consistency(h1, h2)
        half_payload = {
            "schema": "measure_regime_ballast_halfsample_v1",
            "as_of": _now().isoformat(),
            "live_apply": LIVE_APPLY,
            "parent_window": {"start": start.isoformat(), "end": end.isoformat()},
            "h1": h1,
            "h2": h2,
            "consistency": consistency,
            "plain_english": (
                f"Half-sample A: H1 {s1}→{e1} gated {((h1.get('arms') or {}).get('regime_gated_ballast') or {}).get('total_return_pct')}% · "
                f"H2 {s2}→{e2} gated {((h2.get('arms') or {}).get('regime_gated_ballast') or {}).get('total_return_pct')}% · "
                f"verdict={consistency.get('verdict')} · not a GO."
            ),
        }

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _now().isoformat(),
        "live_apply": LIVE_APPLY,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "fee_assumption": {
            "switch_fee_frac": SWITCH_FEE_FRAC,
            "note": "one-way taker-ish on risk-weight changes ≥15pp",
        },
        "climate_rules": {
            "r30_bear_lte": R30_BEAR,
            "r30_soft_lte": R30_SOFT,
            "r30_bull_gte": R30_BULL,
            "logged_stamp_max_age_days": LOGGED_STAMP_MAX_AGE_DAYS,
            "risk_weights": {
                "bear": 0.0,
                "soft_down": 0.35,
                "flat": 0.60,
                "bull": 0.85,
            },
        },
        "dense_stamps": {
            "n_events": dense.get("n_events"),
            "n_days_stamped": dense.get("n_days_stamped"),
            "sources_n": dense.get("sources_n"),
            "first_day": dense.get("first_day"),
            "last_day": dense.get("last_day"),
            "path": str(OUT_STAMPS.relative_to(ROOT)),
        },
        "logged_coverage": full.get("logged_coverage"),
        "climate_mix_pct": full.get("climate_mix_pct"),
        "climate_proxy_mix_pct": full.get("climate_proxy_mix_pct"),
        "climate_logged_mix_pct": full.get("climate_logged_mix_pct"),
        "arms": arms,
        "edge": tag,
        "ranking_by_total_return": full.get("ranking_by_total_return"),
        "half_sample": {
            "enabled": bool(half_sample),
            "path_json": str(OUT_HALF_JSON.relative_to(ROOT)) if half_sample else None,
            "consistency_verdict": (half_payload or {}).get("consistency", {}).get("verdict")
            if half_payload
            else None,
            "plain_english": (half_payload or {}).get("plain_english") if half_payload else None,
        },
        "plain_english": plain,
        "does_not_claim": [
            "Not a 5%/mo promise",
            "Not walk-forward standard-opt edge",
            "Not authorization to lift shell freeze or bear $0 cap",
            "Actual_book path is jump-scrubbed proxy; month_path remains closed-month SSOT",
            "Logged stamps are sparse early window — coverage % is part of the honesty bar",
            "Half-sample pass ≠ promote",
        ],
        "next_measure_step": [
            "If half-sample STABLE_less_loss: keep measure; optional denser live stamp writer",
            "If MIXED/UNSTABLE: do not staff live ballast exception from this pack",
            "Alt C remains separate exit-first track",
        ],
    }

    md = _render_md(payload, half_payload)
    half_md = _render_half_md(half_payload) if half_payload else ""

    if write:
        STATE.mkdir(parents=True, exist_ok=True)
        REPORTS.mkdir(parents=True, exist_ok=True)
        # stamps artifact (day_map can be large but fine)
        OUT_STAMPS.write_text(json.dumps(dense, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        if half_payload:
            OUT_HALF_JSON.write_text(json.dumps(half_payload, indent=2, default=str) + "\n", encoding="utf-8")
            OUT_HALF_MD.write_text(half_md, encoding="utf-8")
        payload["wrote_json"] = str(OUT_JSON)
        payload["wrote_md"] = str(OUT_MD)
        payload["wrote_stamps"] = str(OUT_STAMPS)
        if half_payload:
            payload["wrote_half_json"] = str(OUT_HALF_JSON)
            payload["wrote_half_md"] = str(OUT_HALF_MD)
    payload["md"] = md
    payload["_half"] = half_payload
    return payload


def _render_md(p: Dict[str, Any], half: Optional[Dict[str, Any]] = None) -> str:
    w = p.get("window") or {}
    lines = [
        "# Measure CF — Alt A Regime-Gated Ballast (v2 dense + half-sample)",
        "",
        f"**As of:** {p.get('as_of')}  ",
        f"**Window:** {w.get('start')} → {w.get('end')}  ",
        f"**live_apply:** `{p.get('live_apply')}` (always false)  ",
        f"**Edge class:** `{((p.get('edge') or {}).get('edge_class'))}`  ",
        f"**Logged coverage:** `{((p.get('logged_coverage') or {}).get('pct'))}%`  ",
        f"**Half-sample verdict:** `{(p.get('half_sample') or {}).get('consistency_verdict')}`  ",
        "",
        "## Plain English",
        "",
        str(p.get("plain_english") or ""),
        "",
        "## Dense regime stamps",
        "",
        "```json",
        json.dumps(p.get("dense_stamps") or {}, indent=2),
        "```",
        "",
        "## Arm scoreboard (total return %)",
        "",
        "| Arm | Total % | Max DD % | Switches | Fee $ |",
        "|-----|---------|----------|----------|-------|",
    ]
    arms = p.get("arms") or {}
    for mode in (
        "regime_gated_ballast",
        "regime_gated_ballast_logged",
        "regime_gated_ballast_proxy",
        "ballast_50_50",
        "btc_hodl",
        "eth_hodl",
        "cash_hold",
        "actual_book",
    ):
        a = arms.get(mode) or {}
        lines.append(
            f"| `{mode}` | {a.get('total_return_pct')} | {a.get('max_dd_pct')} | "
            f"{a.get('n_switches', '—')} | {a.get('fee_paid_usd', '—')} |"
        )
    lines += [
        "",
        "## Ranking",
        "",
    ]
    for row in p.get("ranking_by_total_return") or []:
        lines.append(f"- **{row.get('mode')}**: {row.get('total_return_pct')}%")
    lines += [
        "",
        "## Climate mix (dense preferred)",
        "",
        "```json",
        json.dumps(p.get("climate_mix_pct") or {}, indent=2),
        "```",
        "",
        "### Proxy-only mix",
        "",
        "```json",
        json.dumps(p.get("climate_proxy_mix_pct") or {}, indent=2),
        "```",
        "",
        "### Logged-only mix (days with stamp)",
        "",
        "```json",
        json.dumps(p.get("climate_logged_mix_pct") or {}, indent=2),
        "```",
    ]
    if half:
        lines += [
            "",
            "## Half-sample (first / second ~60d)",
            "",
            str(half.get("plain_english") or ""),
            "",
            "```json",
            json.dumps(half.get("consistency") or {}, indent=2),
            "```",
            "",
            f"Detail: `{OUT_HALF_MD.name}`",
        ]
    lines += [
        "",
        "## Does NOT claim",
        "",
    ]
    for x in p.get("does_not_claim") or []:
        lines.append(f"- {x}")
    lines += [
        "",
        "## Next measure steps",
        "",
    ]
    for x in p.get("next_measure_step") or []:
        lines.append(f"- {x}")
    lines += [
        "",
        f"JSON: `{OUT_JSON.relative_to(ROOT)}`",
        f"Stamps: `{OUT_STAMPS.relative_to(ROOT)}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def _render_half_md(half: Dict[str, Any]) -> str:
    lines = [
        "# Alt A — Half-sample folds",
        "",
        f"**As of:** {half.get('as_of')}  ",
        f"**live_apply:** false  ",
        "",
        str(half.get("plain_english") or ""),
        "",
        "## Consistency",
        "",
        "```json",
        json.dumps(half.get("consistency") or {}, indent=2),
        "```",
        "",
    ]
    for key, title in (("h1", "First half"), ("h2", "Second half")):
        h = half.get(key) or {}
        lines += [
            f"## {title}",
            "",
            f"Window: `{(h.get('window') or {}).get('start')}` → `{(h.get('window') or {}).get('end')}`  ",
            f"Logged cov: `{(h.get('logged_coverage') or {}).get('pct')}%`  ",
            f"Edge: `{(h.get('edge') or {}).get('edge_class')}`  ",
            "",
            "| Arm | Total % | Max DD % |",
            "|-----|---------|----------|",
        ]
        arms = h.get("arms") or {}
        for mode in (
            "regime_gated_ballast",
            "regime_gated_ballast_proxy",
            "btc_hodl",
            "cash_hold",
            "actual_book",
        ):
            a = arms.get(mode) or {}
            lines.append(
                f"| `{mode}` | {a.get('total_return_pct')} | {a.get('max_dd_pct')} |"
            )
        lines.append("")
    lines += [
        "## Does NOT claim",
        "",
        "- Half-sample is not walk-forward standard-opt",
        "- Not a live GO",
        "",
        f"JSON: `{OUT_HALF_JSON.relative_to(ROOT)}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Alt A regime-gated ballast measure CF")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-half-sample", action="store_true")
    ap.add_argument("--json-stdout", action="store_true")
    args = ap.parse_args(argv)
    start = _parse_day(args.start) if args.start else None
    end = _parse_day(args.end) if args.end else None
    payload = run_cf(
        days=args.days,
        start=start,
        end=end,
        allow_network=not args.no_network,
        write=not args.no_write,
        half_sample=not args.no_half_sample,
    )
    print(payload.get("plain_english"))
    hs = payload.get("half_sample") or {}
    if hs.get("plain_english"):
        print(hs["plain_english"])
    if payload.get("wrote_md"):
        print(f"Report: {payload['wrote_md']}")
    if payload.get("wrote_half_md"):
        print(f"Half-sample: {payload['wrote_half_md']}")
    if payload.get("wrote_stamps"):
        print(f"Stamps: {payload['wrote_stamps']}")
    if args.json_stdout:
        slim = {k: v for k, v in payload.items() if k not in ("md", "_half")}
        print(json.dumps(slim, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
