#!/usr/bin/env python3
"""REGIME climate vs weather — measure-only multi-horizon + dwell board.

Heinlein framing (operator law):
  Climate = what you expect  → slow REGIME-CASH weather gate (BTC ~30d bands)
  Weather = what you get     → faster structure (7d/14d + breakout/RSI layer)

Job split (do not collapse into one dial):
  A. Survival/park   — slow climate (bear ≤ −10% stays hard veto)
  B. Opportunity     — weather / layered micro timer (not green-day = flat)
  C. Size-up         — slow climate confirm (bull ≥ +15%)

This module NEVER writes regime_cash_policy, never flips allow_new_buys,
never places orders. Shadow board + crumbs only.
"""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

REPORTS_DIR = PROJECT_ROOT / "reports"
from phase6.research.regime_detector import (
    BEAR_RETURN_PCT,
    BULL_RETURN_PCT,
    FLAT_ABS_PCT,
    LOOKBACK_DAYS,
    classify_regime_layer,
    detect_regime,
    _load_btc_closes_with_meta,
    _merge_live_close,
)
from phase6.research.bull_reentry_layered import (
    LayeredSignal,
    build_signal_series,
    CAP_REENTRY,
    CAP_BULL,
    CAP_PARK,
)

SCHEMA = "regime_climate_weather_v1"
LATEST_JSON = STATE_DIR / "regime_climate_weather_latest.json"
CRUMBS = STATE_DIR / "regime_climate_weather_crumbs.jsonl"
REPORT_MD = REPORTS_DIR / "REGIME_CLIMATE_WEATHER_LATEST.md"
LONG_BTC = PROJECT_ROOT / "backtests/data/long/ohlcv_daily_btc.json"

HORIZONS = (7, 14, 30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rolling_ret_calendar(
    days: Sequence[date], px: Dict[date, float], i: int, lookback: int
) -> Tuple[Optional[float], Dict[str, Any]]:
    """Calendar lookback (climate-style). Flags when sparse bars collapse horizons."""
    meta: Dict[str, Any] = {"mode": "calendar", "lookback_days": lookback}
    if i < 1 or i >= len(days):
        return None, {**meta, "error": "bad_index"}
    d = days[i]
    target = d - timedelta(days=lookback)
    j = i
    while j > 0 and days[j] > target:
        j -= 1
    p0, p1 = px.get(days[j]), px.get(d)
    if not p0 or not p1 or p0 <= 0:
        return None, {**meta, "error": "bad_px"}
    span = (d - days[j]).days
    bars_spanned = i - j
    meta.update(
        {
            "from": days[j].isoformat(),
            "to": d.isoformat(),
            "calendar_span_days": span,
            "bars_spanned": bars_spanned,
            "collapsed": bars_spanned <= 1 and lookback > 1,
        }
    )
    return (p1 / p0 - 1.0) * 100.0, meta


def _rolling_ret_bars(
    days: Sequence[date], px: Dict[date, float], i: int, n_bars: int
) -> Tuple[Optional[float], Dict[str, Any]]:
    """Bar-count lookback (weather when OHLCV has gaps). n_bars = trading days back."""
    meta: Dict[str, Any] = {"mode": "bars", "n_bars": n_bars}
    if i < 1 or i >= len(days) or n_bars < 1:
        return None, {**meta, "error": "bad_index"}
    j = max(0, i - n_bars)
    p0, p1 = px.get(days[j]), px.get(days[i])
    if not p0 or not p1 or p0 <= 0:
        return None, {**meta, "error": "bad_px"}
    meta.update(
        {
            "from": days[j].isoformat(),
            "to": days[i].isoformat(),
            "calendar_span_days": (days[i] - days[j]).days,
            "bars_spanned": i - j,
        }
    )
    return (p1 / p0 - 1.0) * 100.0, meta


def _rolling_ret(
    days: Sequence[date], px: Dict[date, float], i: int, lookback: int
) -> Optional[float]:
    r, _ = _rolling_ret_calendar(days, px, i, lookback)
    return r


def _parse_ohlcv_close_rows(series: Sequence[Any]) -> List[Tuple[date, float]]:
    out: List[Tuple[date, float]] = []
    for bar in series:
        if not isinstance(bar, dict):
            continue
        ts = str(bar.get("timestamp") or bar.get("time") or bar.get("date") or "")
        close = bar.get("close") or bar.get("c")
        if close is None or not ts:
            continue
        try:
            if "T" in ts:
                d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            else:
                d = date.fromisoformat(ts[:10])
            out.append((d, float(close)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def _load_marketdata_closes() -> Tuple[List[Tuple[date, float]], Dict[str, Any]]:
    """P3 primary tape: marketdata.db BTC 1d (same port as regime_detector)."""
    try:
        from phase6.core.marketdata_store import get_btc_daily_closes

        closes, md = get_btc_daily_closes()
        meta = dict(md or {})
        meta["source"] = "marketdata_db" if closes else meta.get("source") or "marketdata_db_empty"
        if closes:
            return closes, meta
    except Exception as exc:  # noqa: BLE001
        meta_err: Dict[str, Any] = {"source": "marketdata_error", "error": str(exc)}
    else:
        meta_err = {"source": "marketdata_empty"}

    closes, det_meta = _load_btc_closes_with_meta()
    meta = {**meta_err, **(det_meta or {}), "fallback": True}
    meta.setdefault("source", det_meta.get("source") if isinstance(det_meta, dict) else "detector_fallback")
    return closes, meta


def _load_long_json_closes() -> List[Tuple[date, float]]:
    """Research long tape only — never live climate SSOT by itself."""
    if not LONG_BTC.exists():
        return []
    try:
        blob = json.loads(LONG_BTC.read_text(encoding="utf-8"))
        series = blob if isinstance(blob, list) else (
            blob.get("BTC-USD") or blob.get("BTC") or blob.get("closes") or []
        )
        out = _parse_ohlcv_close_rows(series if isinstance(series, list) else [])
        return out if len(out) >= 60 else []
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def _merge_date_closes(
    *series: Sequence[Tuple[date, float]],
) -> List[Tuple[date, float]]:
    """Later series win on same date (marketdata tip overrides stale long JSON)."""
    by_d: Dict[date, float] = {}
    for seq in series:
        for d, px in seq:
            if px and px > 0:
                by_d[d] = float(px)
    return sorted(by_d.items(), key=lambda x: x[0])


def _load_long_closes() -> List[Tuple[date, float]]:
    """Dwell tape: long research history + marketdata tip (P3).

    Long JSON alone ends mid-tape and reintroduces false climate if used for
    live multi-horizon. Marketdata alone is shorter; stitch for episode stats.
    """
    long_rows = _load_long_json_closes()
    md_rows, _meta = _load_marketdata_closes()
    if long_rows and md_rows:
        return _merge_date_closes(long_rows, md_rows)
    if md_rows:
        return md_rows
    if long_rows:
        return long_rows
    return []


def _load_snapshot_closes(
    *, live_merge: bool = True
) -> Tuple[List[Tuple[date, float]], Dict[str, Any]]:
    """Multi-horizon weather tape: marketdata first; optional same-day live mark."""
    raw, load_meta = _load_marketdata_closes()
    meta: Dict[str, Any] = {
        "tape_source": load_meta.get("source"),
        "load": load_meta,
        "live_merge": {},
    }
    if live_merge and raw:
        raw, merge_meta = _merge_live_close(raw)
        meta["live_merge"] = merge_meta
    return raw, meta


def episode_stats(
    labels: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Run-length encoding → mean/median/p90 episode days per label."""
    if not labels:
        return {}
    eps: Dict[str, List[int]] = defaultdict(list)
    cur = labels[0]
    n = 1
    for lab in labels[1:]:
        if lab == cur:
            n += 1
        else:
            eps[cur].append(n)
            cur = lab
            n = 1
    eps[cur].append(n)

    out: Dict[str, Dict[str, Any]] = {}
    for reg, xs in sorted(eps.items()):
        xs_s = sorted(xs)
        p90 = xs_s[int(0.9 * (len(xs_s) - 1))] if xs_s else None
        out[reg] = {
            "n_episodes": len(xs),
            "n_days": sum(xs),
            "mean_days": round(st.mean(xs), 2) if xs else None,
            "median_days": round(st.median(xs), 2) if xs else None,
            "p90_days": p90,
            "min_days": min(xs) if xs else None,
            "max_days": max(xs) if xs else None,
        }
    return out


def build_dwell_board(
    closes: Optional[List[Tuple[date, float]]] = None,
    *,
    lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    caller_supplied = closes is not None
    closes = list(closes) if caller_supplied else _load_long_closes()
    if len(closes) < lookback_days + 5:
        return {"ok": False, "error": "insufficient_closes", "n": len(closes)}

    days = [d for d, _ in closes]
    px = {d: c for d, c in closes}
    labels_coarse: List[str] = []
    labels_layer: List[str] = []
    for i in range(len(days)):
        r = _rolling_ret(days, px, i, lookback_days)
        if r is None:
            continue
        info = classify_regime_layer(r)
        labels_coarse.append(str(info["regime"]))
        labels_layer.append(str(info["regime_layer"]))

    return {
        "ok": True,
        "n_labeled_days": len(labels_coarse),
        "lookback_days": lookback_days,
        "tape_start": days[0].isoformat() if days else None,
        "tape_end": days[-1].isoformat() if days else None,
        "tape_source": "caller" if caller_supplied else "long_json_stitched_marketdata",
        "n_bars": len(closes),
        "coarse_episodes": episode_stats(labels_coarse),
        "layer_episodes": episode_stats(labels_layer),
        "heinein": {
            "climate": "coarse regime from slow lookback (expect)",
            "weather_note": "layer labels still climate-derived; fast weather is multi-horizon block",
        },
    }


def multi_horizon_snapshot(
    closes: Optional[List[Tuple[date, float]]] = None,
    *,
    live_merge: bool = True,
) -> Dict[str, Any]:
    # P3: marketdata.db is primary weather tape (not long JSON / research freeze).
    if closes is None:
        raw, tape_meta = _load_snapshot_closes(live_merge=live_merge)
        meta = dict(tape_meta.get("live_merge") or {})
        load_meta = dict(tape_meta.get("load") or {})
        tape_source = tape_meta.get("tape_source") or load_meta.get("source") or "marketdata_db"
    else:
        raw = list(closes)
        meta = {}
        load_meta = {"source": "caller"}
        tape_source = "caller"
        if live_merge and raw:
            raw, meta = _merge_live_close(raw)
    if len(raw) < 5:
        return {"ok": False, "error": "no_btc", "tape_source": tape_source, "load": load_meta}

    days = [d for d, _ in raw]
    px = {d: c for d, c in raw}
    i = len(days) - 1
    # Data quality: live-append over a gap collapses calendar 7d/14d onto the same prior bar
    gap_days = 0
    if i >= 1:
        gap_days = max(0, (days[i] - days[i - 1]).days - 1)
    data_quality = {
        "n_bars": len(days),
        "last_bar": days[i].isoformat(),
        "prior_bar": days[i - 1].isoformat() if i >= 1 else None,
        "gap_days_before_last": gap_days,
        "sparse_tail": gap_days >= 3,
        "tape_source": tape_source,
        "note": (
            "OHLCV lag + live append: calendar short horizons may collapse onto same prior close; "
            "prefer bars_* weather until daily backfill catches up."
            if gap_days >= 3
            else "ok"
        ),
    }
    horizons: Dict[str, Any] = {}
    for h in HORIZONS:
        r_cal, m_cal = _rolling_ret_calendar(days, px, i, h)
        r_bars, m_bars = _rolling_ret_bars(days, px, i, h)
        lab_cal = classify_regime_layer(r_cal) if r_cal is not None else None
        lab_bars = classify_regime_layer(r_bars) if r_bars is not None else None
        # Prefer bar-based label for weather when calendar collapsed
        use_bars = bool(m_cal.get("collapsed")) or data_quality["sparse_tail"]
        primary_r = r_bars if use_bars else r_cal
        primary_lab = lab_bars if use_bars else lab_cal
        horizons[f"{h}d"] = {
            "btc_return_pct": round(primary_r, 3) if primary_r is not None else None,
            "regime": (primary_lab or {}).get("regime"),
            "regime_layer": (primary_lab or {}).get("regime_layer"),
            "shadow_stance": (primary_lab or {}).get("shadow_stance"),
            "primary_mode": "bars" if use_bars else "calendar",
            "calendar": {
                "btc_return_pct": round(r_cal, 3) if r_cal is not None else None,
                "regime": (lab_cal or {}).get("regime"),
                "meta": m_cal,
            },
            "bars": {
                "btc_return_pct": round(r_bars, 3) if r_bars is not None else None,
                "regime": (lab_bars or {}).get("regime"),
                "meta": m_bars,
            },
        }

    # Live climate SSOT (same as money path detector)
    try:
        climate = detect_regime(use_live_price=True)
    except TypeError:
        climate = detect_regime()
    except Exception as exc:  # noqa: BLE001
        climate = {"error": str(exc)}

    # Weather: layered breakout timer (B job)
    weather: Dict[str, Any] = {"ok": False}
    try:
        series = build_signal_series(days, px)
        last = series[-1] if series else None
        if last is not None:
            row = asdict(last) if isinstance(last, LayeredSignal) else dict(last)  # type: ignore[arg-type]
            weather = {
                "ok": True,
                "as_of": str(row.get("as_of") or days[-1]),
                "breakout_on": row.get("breakout_on"),
                "rsi": row.get("rsi"),
                "ret14": row.get("btc_ret_14"),
                "ret30": row.get("btc_ret_30"),
                "regime_label": row.get("regime_label"),
                "cap_usd": row.get("cap_usd"),
                "layer": row.get("layer"),
                "allow_new_buys": row.get("allow_new_buys"),
                "allocator_preference": row.get("allocator_preference"),
                "reasons": row.get("reasons"),
            }
    except Exception as exc:  # noqa: BLE001
        weather = {"ok": False, "error": str(exc)}

    # Disagree matrix: climate vs fast horizons vs weather sleeve
    c_reg = (climate or {}).get("regime") if isinstance(climate, dict) else None
    h7 = horizons.get("7d") or {}
    h14 = horizons.get("14d") or {}
    disagree = {
        "climate_vs_7d": c_reg != h7.get("regime"),
        "climate_vs_14d": c_reg != h14.get("regime"),
        "climate_vs_30d_layer": c_reg != (horizons.get("30d") or {}).get("regime"),
        "weather_would_micro": bool(
            weather.get("ok")
            and float(weather.get("cap_usd") or 0) >= CAP_REENTRY - 1e-9
            and float(weather.get("cap_usd") or 0) < CAP_BULL
        ),
        "weather_park": bool(weather.get("ok") and float(weather.get("cap_usd") or 0) <= CAP_PARK + 1e-9),
        "green_day_is_not_climate_flip": True,
    }

    return {
        "ok": True,
        "as_of": _now().isoformat(),
        "btc_last": days[-1].isoformat(),
        "btc_px": px.get(days[-1]),
        "tape_source": tape_source,
        "load": load_meta,
        "live_merge": meta,
        "data_quality": data_quality,
        "climate": {
            "source": "detect_regime / marketdata_db",
            "tape_source": tape_source,
            "regime": c_reg,
            "regime_layer": (climate or {}).get("regime_layer") if isinstance(climate, dict) else None,
            "btc_return_pct": (climate or {}).get("btc_return_pct") if isinstance(climate, dict) else None,
            "confidence": (climate or {}).get("confidence") if isinstance(climate, dict) else None,
            "lookback_days": LOOKBACK_DAYS,
            "thresholds": {
                "bull_return_pct": BULL_RETURN_PCT,
                "bear_return_pct": BEAR_RETURN_PCT,
                "flat_abs_pct": FLAT_ABS_PCT,
            },
            "raw": {
                k: climate.get(k)
                for k in (
                    "regime",
                    "regime_layer",
                    "btc_return_pct",
                    "confidence",
                    "window_start",
                    "window_end",
                    "as_of",
                    "source",
                    "data_source",
                )
                if isinstance(climate, dict) and k in climate
            },
        },
        "weather_horizons": horizons,
        "weather_structure": weather,
        "disagree": disagree,
        "jobs": {
            "A_survival": "climate bear veto / park",
            "B_opportunity": "weather structure micro sleeve (layered)",
            "C_size_up": "climate bull size-up only",
        },
        "quote": {
            "heinein": "Climate is what you expect; weather is what you get.",
            "product": "Regime = climate. Emergent tape = weather. Be ready for both — without letting weather rewrite climate law.",
        },
    }


def build_board(*, write: bool = True) -> Dict[str, Any]:
    snap = multi_horizon_snapshot()
    dwell = build_dwell_board()
    board = {
        "schema": SCHEMA,
        "as_of": _now().isoformat(),
        "live_writes": False,
        "measure_only": True,
        "snapshot": snap,
        "dwell": dwell,
        "plain_english": _plain(snap, dwell),
    }
    if write:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_JSON.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
        with CRUMBS.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": board["as_of"],
                        "climate": (snap.get("climate") or {}).get("regime"),
                        "r30": (snap.get("climate") or {}).get("btc_return_pct"),
                        "r7": ((snap.get("weather_horizons") or {}).get("7d") or {}).get("btc_return_pct"),
                        "r14": ((snap.get("weather_horizons") or {}).get("14d") or {}).get("btc_return_pct"),
                        "weather_cap": ((snap.get("weather_structure") or {}).get("cap_usd")),
                        "disagree_7": (snap.get("disagree") or {}).get("climate_vs_7d"),
                        "disagree_14": (snap.get("disagree") or {}).get("climate_vs_14d"),
                    },
                    default=str,
                )
                + "\n"
            )
        REPORT_MD.write_text(_md(board), encoding="utf-8")
    return board


def _plain(snap: Dict[str, Any], dwell: Dict[str, Any]) -> str:
    if not snap.get("ok"):
        return f"Board failed: {snap.get('error')}"
    c = snap.get("climate") or {}
    w = snap.get("weather_structure") or {}
    h = snap.get("weather_horizons") or {}
    d = snap.get("disagree") or {}
    dq = snap.get("data_quality") or {}
    parts = [
        f"Climate (30d SSOT): {c.get('regime')} · BTC30d={c.get('btc_return_pct')}%.",
        f"Tape: {snap.get('tape_source') or (dq.get('tape_source') or 'n/a')}.",
        f"Weather 7d/14d: {((h.get('7d') or {}).get('btc_return_pct'))}% / {((h.get('14d') or {}).get('btc_return_pct'))}% "
        f"(mode {((h.get('7d') or {}).get('primary_mode'))}).",
        f"Structure sleeve cap would be ${w.get('cap_usd')} (paper only)."
        if w.get("ok")
        else f"Structure: {w.get('error') or 'n/a'}.",
        "Green day ≠ climate flip." if d.get("green_day_is_not_climate_flip") else "",
    ]
    if dq.get("sparse_tail"):
        parts.append(
            f"DATA: OHLCV gap ~{dq.get('gap_days_before_last')}d before last bar — short calendar horizons collapsed; weather uses bar lookbacks."
        )
    if d.get("climate_vs_7d") or d.get("climate_vs_14d"):
        parts.append("Fast horizons disagree with climate — expected emergent weather; do not auto-flip money path.")
    if dwell.get("ok"):
        be = (dwell.get("coarse_episodes") or {}).get("bear") or {}
        fl = (dwell.get("coarse_episodes") or {}).get("flat") or {}
        bu = (dwell.get("coarse_episodes") or {}).get("bull") or {}
        parts.append(
            f"Dwell med days bear/flat/bull: {be.get('median_days')}/{fl.get('median_days')}/{bu.get('median_days')} "
            f"(means {be.get('mean_days')}/{fl.get('mean_days')}/{bu.get('mean_days')})."
        )
    return " ".join(p for p in parts if p)


def _md(board: Dict[str, Any]) -> str:
    snap = board.get("snapshot") or {}
    dwell = board.get("dwell") or {}
    c = snap.get("climate") or {}
    h = snap.get("weather_horizons") or {}
    w = snap.get("weather_structure") or {}
    d = snap.get("disagree") or {}
    lines = [
        "# Regime climate vs weather (measure-only)",
        "",
        f"**As of:** `{board.get('as_of')}`  ",
        f"**Live writes:** `{board.get('live_writes')}` · **schema:** `{board.get('schema')}`",
        "",
        "> Climate is what you expect; weather is what you get.  ",
        "> **Regime = climate. Emergent tape = weather.** Ready for both — weather must not silently rewrite climate law.",
        "",
        "## Plain English",
        "",
        board.get("plain_english") or "",
        "",
        "## Climate (job A/C — slow)",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| regime | `{c.get('regime')}` |",
        f"| layer | `{c.get('regime_layer')}` |",
        f"| BTC 30d % | `{c.get('btc_return_pct')}` |",
        f"| confidence | `{c.get('confidence')}` |",
        f"| lookback | `{c.get('lookback_days')}` |",
        "",
        "## Weather horizons (measure)",
        "",
        "| Horizon | BTC ret % | Would-label regime | layer |",
        "|---------|-----------|-------------------|-------|",
    ]
    for key in ("7d", "14d", "30d"):
        row = h.get(key) or {}
        lines.append(
            f"| {key} | {row.get('btc_return_pct')} | `{row.get('regime')}` | `{row.get('regime_layer')}` |"
        )
    lines += [
        "",
        "## Weather structure (job B — layered paper signal)",
        "",
        "```json",
        json.dumps(w, indent=2, default=str)[:2000],
        "```",
        "",
        "## Disagree flags",
        "",
        "```json",
        json.dumps(d, indent=2),
        "```",
        "",
        "## Dwell board (climate episodes on long tape)",
        "",
    ]
    if dwell.get("ok"):
        lines += [
            f"Tape: `{dwell.get('tape_start')}` → `{dwell.get('tape_end')}` · labeled days `{dwell.get('n_labeled_days')}`",
            "",
            "### Coarse regime episodes",
            "",
            "| Regime | days | eps | mean | median | p90 | min | max |",
            "|--------|------|-----|------|--------|-----|-----|-----|",
        ]
        for reg, row in (dwell.get("coarse_episodes") or {}).items():
            lines.append(
                f"| {reg} | {row.get('n_days')} | {row.get('n_episodes')} | {row.get('mean_days')} | "
                f"{row.get('median_days')} | {row.get('p90_days')} | {row.get('min_days')} | {row.get('max_days')} |"
            )
        lines += ["", "### Layer episodes", ""]
        lines += [
            "| Layer | days | eps | mean | median | p90 |",
            "|-------|------|-----|------|--------|-----|",
        ]
        for reg, row in (dwell.get("layer_episodes") or {}).items():
            lines.append(
                f"| {reg} | {row.get('n_days')} | {row.get('n_episodes')} | {row.get('mean_days')} | "
                f"{row.get('median_days')} | {row.get('p90_days')} |"
            )
    else:
        lines.append(f"Dwell failed: `{dwell.get('error')}`")
    lines += [
        "",
        "## Must not",
        "",
        "- Treat green day or 7d bounce as climate flip",
        "- Write `regime_cash_policy` / `allow_new_buys` from this board",
        "- Size-up off weather alone",
        "",
        f"Artifacts: `{LATEST_JSON}` · `{CRUMBS}` · layered paper: `data/state/bull_reentry_layered_paper_shadow.json`",
        "",
    ]
    return "\n".join(lines) + "\n"


def telegram_summary(board: Optional[Dict[str, Any]] = None) -> str:
    board = board or build_board(write=False)
    snap = board.get("snapshot") or {}
    c = snap.get("climate") or {}
    h = snap.get("weather_horizons") or {}
    w = snap.get("weather_structure") or {}
    return (
        "Climate/weather (measure only)\n"
        f"Climate: {c.get('regime')} · 30d {c.get('btc_return_pct')}%\n"
        f"Weather 7/14d: {(h.get('7d') or {}).get('btc_return_pct')}% / {(h.get('14d') or {}).get('btc_return_pct')}%\n"
        f"Layered paper cap: ${w.get('cap_usd')}\n"
        "No live flips. Green day ≠ regime."
    )
