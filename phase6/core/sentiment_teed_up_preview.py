"""Display-only mid-cycle sentiment preview for the dashboard.

When aged X is ~0 between the 2×/day pulls, operators still need to see what
free / Adanos / raw-X are saying before the next refresh — without implying
those scores clear BUY/size floors.

SHADOW / DISPLAY ONLY — never merge into live gates from this module.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

EPS = 1e-9


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        if "T" in s:
            return datetime.fromisoformat(s)
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(s[:26])
        except ValueError:
            return None


def _parse_score_entry(entry: Any) -> Optional[float]:
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        for k in ("sentiment_score", "sentiment", "score"):
            if entry.get(k) is not None:
                try:
                    return float(entry[k])
                except (TypeError, ValueError):
                    return None
    return None


def _load_pair_score_map(path: Path, kind: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "kind": kind}
    if not path.exists():
        return {}, meta
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        meta["error"] = str(e)[:160]
        return {}, meta
    meta["timestamp"] = data.get("timestamp")
    out: Dict[str, float] = {}
    if kind in ("free", "adanos"):
        block = data.get("sentiment") or {}
        if isinstance(block, dict):
            for p, e in block.items():
                s = _parse_score_entry(e)
                if s is not None:
                    out[str(p)] = s
    else:
        for k, v in data.items():
            if not isinstance(k, str) or "USD" not in k:
                continue
            s = _parse_score_entry(v)
            if s is not None:
                out[k] = s
        if not out and isinstance(data.get("sentiment"), dict):
            for p, e in data["sentiment"].items():
                s = _parse_score_entry(e)
                if s is not None:
                    out[str(p)] = s
    meta["n"] = len(out)
    meta["n_nz"] = sum(1 for v in out.values() if abs(v) > EPS)
    return out, meta


def next_x_sentiment_refresh_meta(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Next scheduled X pull windows: 08:50 and 20:50 America/Los_Angeles."""
    try:
        from zoneinfo import ZoneInfo

        pt = ZoneInfo("America/Los_Angeles")
    except Exception:
        pt = timezone(timedelta(hours=-7))
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(pt)
    candidates: List[datetime] = []
    for day_off in (0, 1):
        base = (local + timedelta(days=day_off)).date()
        for hh, mm in ((8, 50), (20, 50)):
            dt = datetime(base.year, base.month, base.day, hh, mm, tzinfo=pt)
            if dt > local:
                candidates.append(dt)
    nxt = candidates[0] if candidates else None
    out: Dict[str, Any] = {
        "schedule_pt": ["08:50", "20:50"],
        "timezone": "America/Los_Angeles",
    }
    if nxt is not None:
        out["next_pt"] = nxt.strftime("%Y-%m-%d %H:%M %Z")
        out["next_utc"] = nxt.astimezone(timezone.utc).isoformat()
        out["hours_until"] = round((nxt - local).total_seconds() / 3600.0, 2)
    return out


def _age_hours(ts: Any) -> Optional[float]:
    if not ts:
        return None
    dt = _parse_ts(str(ts))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0


def load_sentiment_teed_up_preview(
    basket: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build per-pair teed-up preview bundle for Signals /api/pair-signals."""
    root = Path(PROJECT_ROOT)
    free_m, free_meta = _load_pair_score_map(root / "data/state/sentiment_cache_free.json", "free")
    ad_m, ad_meta = _load_pair_score_map(root / "data/state/adanos_sentiment_cache.json", "adanos")
    x_m, x_meta = _load_pair_score_map(root / "data/state/x_sentiment_cache.json", "x")
    rss_m, rss_meta = _load_pair_score_map(root / "data/state/rss_sentiment_cache.json", "rss")
    rr_m, rr_meta = _load_pair_score_map(
        root / "data/state/sentiment_cache_reddit_reading.json", "reddit"
    )  # same {sentiment: {pair: {sentiment_score}}} shape

    live_scores: Dict[str, Any] = {}
    live_mode = "unknown"
    aging: Dict[str, Any] = {}
    non_zero_live = 0
    non_zero_raw = 0
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores_detailed

        detail = load_sentiment_scores_detailed()
        live_scores = detail.get("scores") or {}
        live_mode = str(detail.get("mode") or "unknown")
        aging = detail.get("aging") or {}
        non_zero_live = int(detail.get("non_zero") or 0)
        non_zero_raw = int(detail.get("non_zero_raw") or 0)
    except Exception:
        pass

    if basket is None:
        try:
            from phase6.core.paths import load_trading_basket

            basket = [str(p) for p in (load_trading_basket() or []) if p]
        except Exception:
            basket = sorted(set(free_m) | set(ad_m) | set(x_m) | set(live_scores.keys()))

    free_age_h = _age_hours(free_meta.get("timestamp"))
    ad_age_h = _age_hours(ad_meta.get("timestamp"))
    x_age_h = _age_hours(x_meta.get("timestamp"))
    rr_age_h = _age_hours(rr_meta.get("timestamp"))
    free_fresh = (
        free_age_h is not None
        and free_age_h <= 6.0
        and int(free_meta.get("n_nz") or 0) > 0
    )
    ad_fresh = (
        ad_age_h is not None
        and ad_age_h <= 18.0
        and int(ad_meta.get("n_nz") or 0) > 0
    )
    rr_fresh = (
        rr_age_h is not None
        and rr_age_h <= 8.0
        and int(rr_meta.get("n_nz") or 0) > 0
    )

    by_pair: Dict[str, Any] = {}
    for pair in basket:
        live_e = live_scores.get(pair) or {}
        if isinstance(live_e, dict):
            live_v = float(live_e.get("sentiment") or 0.0)
            live_raw = live_e.get("sentiment_raw")
            try:
                live_raw_f = float(live_raw) if live_raw is not None else live_v
            except (TypeError, ValueError):
                live_raw_f = live_v
            decay = live_e.get("decay_factor")
            age_min = live_e.get("age_min")
            live_src = live_e.get("source") or live_mode
        else:
            live_v = float(live_e or 0.0)
            live_raw_f = live_v
            decay = None
            age_min = None
            live_src = live_mode

        free_v = free_m.get(pair)
        ad_v = ad_m.get(pair)
        x_v = x_m.get(pair)
        rss_v = rss_m.get(pair)
        rr_v = rr_m.get(pair)

        teed_v: Optional[float] = None
        teed_src: Optional[str] = None
        if free_fresh and free_v is not None:
            teed_v = float(free_v)
            teed_src = "free"
        elif rr_fresh and rr_v is not None:
            # Hermes reddit-reading skill (Atom/OAuth) — true Reddit text shadow
            teed_v = float(rr_v)
            teed_src = "reddit"
        elif ad_fresh and ad_v is not None:
            teed_v = float(ad_v)
            teed_src = "adanos"
        elif x_v is not None:
            teed_v = float(x_v)
            teed_src = "x_raw"
        elif free_v is not None:
            teed_v = float(free_v)
            teed_src = "free_stale"
        elif rr_v is not None:
            teed_v = float(rr_v)
            teed_src = "reddit_stale"
        elif ad_v is not None:
            teed_v = float(ad_v)
            teed_src = "adanos_stale"

        live_dead = abs(live_v) < 1e-6 and (
            (decay is not None and float(decay) <= 0.05)
            or (age_min is not None and float(age_min) >= 90)
            or non_zero_live == 0
        )

        by_pair[str(pair)] = {
            "live": round(live_v, 4),
            "live_raw": round(live_raw_f, 4),
            "live_source": live_src,
            "decay_factor": decay,
            "age_min": age_min,
            "free": None if free_v is None else round(float(free_v), 4),
            "adanos": None if ad_v is None else round(float(ad_v), 4),
            "rss": None if rss_v is None else round(float(rss_v), 4),
            "reddit": None if rr_v is None else round(float(rr_v), 4),
            "x_raw": None if x_v is None else round(float(x_v), 4),
            "teed": None if teed_v is None else round(float(teed_v), 4),
            "teed_source": teed_src,
            "live_aged_out": bool(live_dead),
            "drives_gates": False,
        }

    next_x = next_x_sentiment_refresh_meta()
    if non_zero_live == 0 and (free_fresh or rr_fresh or ad_fresh or non_zero_raw > 0):
        primary = (
            "free"
            if free_fresh
            else ("reddit" if rr_fresh else ("adanos" if ad_fresh else "x_raw"))
        )
        label = f"tee:{primary} · live aged-out · next X {next_x.get('next_pt', '?')}"
    elif non_zero_live > 0:
        label = f"live {live_mode} nz={non_zero_live}"
    else:
        label = f"sent flat · next X {next_x.get('next_pt', '?')}"

    return {
        "schema": "sentiment_teed_up_preview_v1",
        "drives_gates": False,
        "live_mode": live_mode,
        "non_zero_live": non_zero_live,
        "non_zero_raw": non_zero_raw,
        "aging": aging,
        "label": label,
        "next_x_refresh": next_x,
        "sources": {
            "free": {**free_meta, "age_hours": free_age_h, "fresh": free_fresh},
            "reddit_reading": {
                **rr_meta,
                "age_hours": rr_age_h,
                "fresh": rr_fresh,
            },
            "adanos": {**ad_meta, "age_hours": ad_age_h, "fresh": ad_fresh},
            "x": {**x_meta, "age_hours": x_age_h},
            "rss": {
                **rss_meta,
                "age_hours": _age_hours(rss_meta.get("timestamp")),
            },
        },
        "by_pair": by_pair,
        "note": (
            "Teed-up scores are DISPLAY ONLY (free/reddit-reading/Adanos/raw X). "
            "Live BUY/size floors still use aged scorer output. "
            "Not a promise of the next fill."
        ),
    }
