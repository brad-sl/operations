#!/usr/bin/env python3
"""
Tier-1 volatility + velocity risk scalar — SHADOW ONLY.

Doctrine
--------
Volatility clustering / GARCH-class ideas size risk, they do not pick direction.
Velocity + volume (RVOL) further dampen risk tolerance when tape participation
spikes — they do not seat, buy, or promote membership.

Never mutates config. Never places orders.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-vol-risk-scalar-shadow/1.0 (research; no orders)"}

STATE_DIR = PROJECT_ROOT / "data" / "state"
LATEST = STATE_DIR / "vol_risk_scalar_shadow_latest.json"
HISTORY = STATE_DIR / "vol_risk_scalar_shadow_history.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "VOL_RISK_SCALAR_SHADOW_LATEST.md"
VELOCITY_LATEST = STATE_DIR / "volume_velocity_shadow_latest.json"
REGIME_STATUS = STATE_DIR / "regime_cash_status.json"
ADD_RISK_STATUS = STATE_DIR / "add_risk_sizer_status.json"  # optional if present

TRADING_DAYS = 365.0  # crypto 24/7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


@dataclass
class VolRiskConfig:
    # Anchors — crypto-native, not 15% equity desk
    target_daily_vol: float = 0.028  # ~2.8% daily ≈ ~53% ann
    ewma_span_hours: int = 36
    lookback_hours: int = 24 * 45  # ~45d for long-run median
    # Asymmetric clip: cut hard, fatten little
    s_min: float = 0.35
    s_max: float = 1.15
    # Velocity dampener
    velocity_k: float = 0.55  # stress weight
    velocity_v_min: float = 0.55
    rvol_stress_soft: float = 1.8
    rvol_stress_hard: float = 3.5
    nomination_heat_cap: int = 12
    # Labels vs long-run daily σ median
    high_vol_ratio: float = 1.35
    low_vol_ratio: float = 0.75
    pairs: Tuple[str, ...] = ("BTC-USD", "ETH-USD")
    primary_pair: str = "BTC-USD"


@dataclass
class PairVol:
    pair: str
    n_returns: int
    daily_vol_ewma: Optional[float]
    ann_vol_ewma: Optional[float]
    daily_vol_median_30d: Optional[float]
    last_ret: Optional[float]
    ok: bool
    error: Optional[str] = None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_hourly_closes(
    pid: str,
    hours: int,
    sess: Optional[requests.Session] = None,
) -> Tuple[List[float], Optional[str]]:
    """Return oldest→newest close prices (hourly)."""
    sess = sess or _session()
    end = _utc_now()
    start = end - timedelta(hours=hours + 6)
    gran = 3600
    out: List[list] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(seconds=gran * 280), end)
        params = {
            "granularity": gran,
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        try:
            r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=25)
        except Exception as e:
            return [], str(e)[:160]
        if r.status_code != 200:
            return [], f"http_{r.status_code}"
        batch = r.json() or []
        if not isinstance(batch, list):
            return [], "bad_payload"
        out.extend(batch)
        cursor = chunk_end
    # candle: [time, low, high, open, close, volume]
    by_t = {}
    for c in out:
        try:
            t, _, _, _, close, _ = c[0], c[1], c[2], c[3], c[4], c[5]
            by_t[int(t)] = float(close)
        except Exception:
            continue
    closes = [by_t[k] for k in sorted(by_t.keys())]
    if len(closes) < 48:
        return closes, "short_history"
    return closes, None


def log_returns(closes: Sequence[float]) -> List[float]:
    rets: List[float] = []
    for a, b in zip(closes, closes[1:]):
        if a > 0 and b > 0:
            rets.append(math.log(b / a))
    return rets


def ewma_variance(rets: Sequence[float], span: int) -> Optional[float]:
    """RiskMetrics-style EWMA variance of hourly log returns → last variance."""
    if len(rets) < max(10, span // 2):
        return None
    alpha = 2.0 / (float(span) + 1.0)
    var = rets[0] ** 2
    for r in rets[1:]:
        var = alpha * (r ** 2) + (1.0 - alpha) * var
    return max(var, 1e-16)


def hourly_var_to_daily_vol(var_h: float) -> float:
    # √24 hours of independent hourly var (approx for 24/7)
    return math.sqrt(var_h * 24.0)


def rolling_median_daily_vol(rets: Sequence[float], window_h: int = 24) -> Optional[float]:
    """Median of non-overlapping-ish daily vols from hourly rets."""
    if len(rets) < window_h * 5:
        return None
    daily: List[float] = []
    i = 0
    while i + window_h <= len(rets):
        chunk = rets[i : i + window_h]
        v = sum(r * r for r in chunk) / max(len(chunk), 1)
        daily.append(math.sqrt(max(v * window_h, 1e-16)))  # already ~daily if window=24
        i += window_h
    if not daily:
        return None
    daily_sorted = sorted(daily)
    mid = len(daily_sorted) // 2
    if len(daily_sorted) % 2:
        return daily_sorted[mid]
    return 0.5 * (daily_sorted[mid - 1] + daily_sorted[mid])


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_pair_vol(pid: str, cfg: VolRiskConfig, sess: requests.Session) -> PairVol:
    closes, err = fetch_hourly_closes(pid, cfg.lookback_hours, sess)
    if err and len(closes) < 48:
        return PairVol(pid, 0, None, None, None, None, False, err)
    rets = log_returns(closes)
    var_h = ewma_variance(rets, cfg.ewma_span_hours)
    if var_h is None:
        return PairVol(pid, len(rets), None, None, None, None, False, "ewma_fail")
    dvol = hourly_var_to_daily_vol(var_h)
    med = rolling_median_daily_vol(rets, 24)
    last = rets[-1] if rets else None
    return PairVol(
        pair=pid,
        n_returns=len(rets),
        daily_vol_ewma=dvol,
        ann_vol_ewma=dvol * math.sqrt(TRADING_DAYS),
        daily_vol_median_30d=med,
        last_ret=last,
        ok=True,
        error=err,
    )


def velocity_stress(vel: Optional[Dict[str, Any]], cfg: VolRiskConfig) -> Dict[str, Any]:
    """
    Map volume-velocity shadow heat → [0, ~2] stress.
    0 = calm, 1 = elevated, 2 = extreme participation.
    """
    if not vel:
        return {
            "stress": 0.0,
            "source": "velocity_missing",
            "n_noms": 0,
            "max_rvol": None,
            "btc_rvol": None,
        }

    noms = vel.get("nominations") or vel.get("new_nominations") or []
    if isinstance(vel.get("nominated"), list):
        noms = vel.get("nominated") or noms
    # common shapes
    rows: List[Dict[str, Any]] = []
    if isinstance(noms, list):
        for n in noms:
            if isinstance(n, dict):
                rows.append(n)
    summary = vel.get("summary") or vel.get("stats") or {}
    n_open = int(
        _f(
            summary.get("open_tracks")
            or summary.get("n_open")
            or vel.get("n_nominations")
            or len(rows),
            0,
        )
    )

    rvols: List[float] = []
    btc_rvol = None
    for r in rows:
        rv = r.get("rvol_1h") or r.get("rvol") or r.get("rvol_burst_3h")
        if rv is not None:
            rvols.append(_f(rv))
        pid = str(r.get("pair") or r.get("product_id") or "")
        if pid.startswith("BTC"):
            btc_rvol = _f(rv) if rv is not None else btc_rvol

    # top-level scan table
    for key in ("universe", "scanned", "top", "results"):
        block = vel.get(key)
        if not isinstance(block, list):
            continue
        for r in block:
            if not isinstance(r, dict):
                continue
            rv = r.get("rvol_1h") or r.get("rvol_burst_3h") or r.get("rvol")
            if rv is not None:
                rvols.append(_f(rv))
            if str(r.get("pair") or "").startswith("BTC") and rv is not None:
                btc_rvol = _f(rv)

    max_rvol = max(rvols) if rvols else None
    # nomination heat 0..1
    heat_n = clip(n_open / float(cfg.nomination_heat_cap), 0.0, 1.0)
    # rvol heat 0..1
    if max_rvol is None:
        heat_r = 0.0
    elif max_rvol <= cfg.rvol_stress_soft:
        heat_r = 0.15 * (max_rvol / max(cfg.rvol_stress_soft, 1e-6))
    elif max_rvol >= cfg.rvol_stress_hard:
        heat_r = 1.0
    else:
        span = cfg.rvol_stress_hard - cfg.rvol_stress_soft
        heat_r = 0.15 + 0.85 * ((max_rvol - cfg.rvol_stress_soft) / max(span, 1e-6))

    stress = clip(0.45 * heat_n + 0.55 * heat_r, 0.0, 2.0)
    # BTC own velocity gets a bump
    if btc_rvol is not None and btc_rvol >= cfg.rvol_stress_soft:
        stress = clip(stress + 0.25, 0.0, 2.0)

    return {
        "stress": round(stress, 4),
        "source": "volume_velocity_shadow_latest",
        "n_noms": n_open,
        "max_rvol": None if max_rvol is None else round(max_rvol, 4),
        "btc_rvol": None if btc_rvol is None else round(btc_rvol, 4),
        "heat_n": round(heat_n, 4),
        "heat_r": round(heat_r, 4),
    }


def vol_scalar(daily_vol: float, cfg: VolRiskConfig, median_lr: Optional[float]) -> Dict[str, Any]:
    target = cfg.target_daily_vol
    # optional: blend target toward long-run median so we don't fight structural BTC vol
    if median_lr and median_lr > 0:
        target = 0.65 * cfg.target_daily_vol + 0.35 * median_lr
    raw = target / max(daily_vol, 1e-8)
    s = clip(raw, cfg.s_min, cfg.s_max)
    if median_lr and median_lr > 0:
        ratio = daily_vol / median_lr
        if ratio >= cfg.high_vol_ratio:
            label = "high"
        elif ratio <= cfg.low_vol_ratio:
            label = "low"
        else:
            label = "normal"
    else:
        label = "unknown"
    return {
        "target_daily_vol": round(target, 6),
        "sigma_hat_daily": round(daily_vol, 6),
        "raw": round(raw, 4),
        "s_vol": round(s, 4),
        "vol_regime": label,
        "vs_long_run": None if not median_lr else round(daily_vol / median_lr, 4),
    }


def velocity_scalar(stress: float, cfg: VolRiskConfig) -> float:
    # s_vel = 1/(1+k*stress), floor v_min, never > 1
    return clip(1.0 / (1.0 + cfg.velocity_k * max(stress, 0.0)), cfg.velocity_v_min, 1.0)


def base_notionals_from_state() -> Dict[str, Any]:
    """Read soft internal budgets for CF only — not trader promises."""
    rc = _load_json(REGIME_STATUS) or {}
    cap = rc.get("rebalance_cap_usd")
    if cap is None:
        cap = (rc.get("snapshot") or {}).get("rebalance_cap_usd")
    allow = rc.get("allow_new_buys")
    if allow is None:
        allow = (rc.get("snapshot") or {}).get("allow_new_buys")
    stance = rc.get("stance") or rc.get("posture") or (rc.get("snapshot") or {}).get("stance")
    add = _load_json(ADD_RISK_STATUS) or {}
    return {
        "rebalance_cap_usd_internal": cap,
        "allow_new_buys": allow,
        "stance": stance,
        "add_risk_status_present": bool(add),
        "regime_as_of": rc.get("as_of") or rc.get("ts"),
    }


def apply_shadow_sizes(s: float, bases: Dict[str, Any]) -> Dict[str, Any]:
    cap = bases.get("rebalance_cap_usd_internal")
    out: Dict[str, Any] = {
        "s_combined": round(s, 4),
        "would_reduce": s < 0.85,
        "would_fatten": s > 1.05,
    }
    if cap is not None:
        try:
            c = float(cap)
            out["internal_cap_usd"] = c
            out["would_cap_usd"] = round(c * s, 2)
            out["note"] = (
                "Internal engine budget × scalar only. Not a trader-facing cycle ceiling; "
                "ARCH-2/rotation paths can still exceed on live until separately gated."
            )
        except (TypeError, ValueError):
            pass
    return out


def write_report(payload: Dict[str, Any]) -> None:
    md = [
        "# Vol + velocity risk scalar (Tier 1 shadow)",
        f"As of `{payload.get('as_of')}`",
        "",
        "**No live size change. No orders. No config mutate.**",
        "",
        "## Plain English",
        "",
        payload.get("plain_english") or "",
        "",
        "## Scalars",
        "",
        f"- **s_vol** (BTC EWMA): `{payload.get('s_vol')}` · regime `{payload.get('vol_regime')}`",
        f"- **s_vel** (velocity dampen): `{payload.get('s_vel')}` · stress `{payload.get('velocity_stress')}`",
        f"- **s_combined**: `{payload.get('s_combined')}`",
        "",
        "## BTC / ETH vol",
        "",
    ]
    for p in payload.get("pairs") or []:
        md.append(
            f"- `{p.get('pair')}`: daily σ̂={p.get('daily_vol_ewma')} · "
            f"ann≈{None if p.get('ann_vol_ewma') is None else round(p['ann_vol_ewma']*100,1)}% · "
            f"median_lr={p.get('daily_vol_median_30d')} · ok={p.get('ok')}"
        )
    md += [
        "",
        "## Shadow size CF",
        "",
        "```json",
        json.dumps(payload.get("shadow_sizes") or {}, indent=2),
        "```",
        "",
        "## Velocity bridge",
        "",
        "```json",
        json.dumps(payload.get("velocity") or {}, indent=2),
        "```",
        "",
        "## Doctrine",
        "",
        "- Directional signals propose side; this scalar proposes relative size.",
        "- RVOL/velocity → risk tolerance dampener + scout nominator (separate jobs).",
        "- See `docs/research/VOL_CLUSTERING_RISK_SIZING_TIER1.md`.",
        "",
    ]
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MD_REPORT.write_text("\n".join(md) + "\n")


def run_vol_risk_scalar_shadow(cfg: Optional[VolRiskConfig] = None) -> Dict[str, Any]:
    cfg = cfg or VolRiskConfig()
    sess = _session()
    pairs_out: List[Dict[str, Any]] = []
    primary: Optional[PairVol] = None
    for pid in cfg.pairs:
        pv = compute_pair_vol(pid, cfg, sess)
        pairs_out.append(asdict(pv))
        if pid == cfg.primary_pair:
            primary = pv

    if primary is None or not primary.ok or primary.daily_vol_ewma is None:
        payload = {
            "schema": "vol_risk_scalar_shadow_v1",
            "as_of": _iso(),
            "ok": False,
            "error": "primary_vol_unavailable",
            "pairs": pairs_out,
            "live_promote": False,
            "mutates_config": False,
            "places_orders": False,
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(json.dumps(payload, indent=2) + "\n")
        write_report({**payload, "plain_english": "Could not compute BTC vol — shadow skipped."})
        return payload

    vpart = vol_scalar(primary.daily_vol_ewma, cfg, primary.daily_vol_median_30d)
    vel_raw = _load_json(VELOCITY_LATEST)
    vst = velocity_stress(vel_raw if isinstance(vel_raw, dict) else None, cfg)
    s_vel = velocity_scalar(_f(vst.get("stress")), cfg)
    s_vol = _f(vpart["s_vol"], 1.0)
    s = clip(s_vol * s_vel, cfg.s_min, cfg.s_max)

    bases = base_notionals_from_state()
    shadow = apply_shadow_sizes(s, bases)

    # plain english
    bits = [
        f"BTC daily vol ≈ {primary.daily_vol_ewma*100:.2f}% (EWMA {cfg.ewma_span_hours}h).",
        f"Vol regime **{vpart['vol_regime']}** → s_vol={s_vol:.2f}.",
        f"Velocity stress={vst.get('stress')} → s_vel={s_vel:.2f}.",
        f"**Combined s={s:.2f}**",
    ]
    if shadow.get("would_reduce"):
        bits.append("Shadow would **cut** size vs baseline this cycle.")
    elif shadow.get("would_fatten"):
        bits.append("Shadow would **slightly fatten** size (capped).")
    else:
        bits.append("Shadow size near baseline.")
    bits.append("Live book unchanged.")

    payload: Dict[str, Any] = {
        "schema": "vol_risk_scalar_shadow_v1",
        "as_of": _iso(),
        "ok": True,
        "live_promote": False,
        "mutates_config": False,
        "places_orders": False,
        "config": asdict(cfg),
        "pairs": pairs_out,
        "s_vol": s_vol,
        "s_vel": round(s_vel, 4),
        "s_combined": round(s, 4),
        "vol_regime": vpart["vol_regime"],
        "vol_detail": vpart,
        "velocity_stress": vst.get("stress"),
        "velocity": vst,
        "base_state": bases,
        "shadow_sizes": shadow,
        "plain_english": " ".join(bits),
        "docs": "docs/research/VOL_CLUSTERING_RISK_SIZING_TIER1.md",
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    with HISTORY.open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": payload["as_of"],
                    "s_vol": s_vol,
                    "s_vel": round(s_vel, 4),
                    "s": round(s, 4),
                    "vol_regime": vpart["vol_regime"],
                    "btc_dvol": primary.daily_vol_ewma,
                    "vel_stress": vst.get("stress"),
                }
            )
            + "\n"
        )
    write_report(payload)
    return payload


def plain_english_summary(payload: Dict[str, Any]) -> str:
    if not payload.get("ok"):
        return f"Vol-risk scalar shadow: FAIL — {payload.get('error')}"
    return (
        f"Vol-risk scalar shadow: s={payload.get('s_combined')} "
        f"(vol={payload.get('s_vol')}×vel={payload.get('s_vel')}) "
        f"regime={payload.get('vol_regime')} — LIVE unchanged"
    )


if __name__ == "__main__":
    out = run_vol_risk_scalar_shadow()
    print(plain_english_summary(out))
