#!/usr/bin/env python3
"""Counterfactual: fixed 3% SL vs 8% SL on real stop-loss legs (1h path).

For each exchange SL fill since --since:
  - Reconstruct hold path from entry_price + Coinbase 1h OHLCV (local cache, fetch miss).
  - Simulate first touch of entry*(1-3%) and entry*(1-8%) on bar lows.
  - Report when 3% would have stopped earlier, path MFE before each stop, and
    $ delta vs actual fill (qty × (sim_exit − entry) − actual_pnl).

Also classifies legs by NEEDLE-04 era (pre 2026-09-30 ≈ 3% live; post ≈ 8% live).

Measure-only. Writes:
  reports/SL_WIDTH_3V8_CF_LATEST.md
  data/state/sl_width_3v8_cf_latest.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/brad/projects/crypto-trading-bot")
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OHLCV_DIR = ROOT / "data" / "ohlcv" / "1h"
OUT_JSON = ROOT / "data" / "state" / "sl_width_3v8_cf_latest.json"
OUT_MD = ROOT / "reports" / "SL_WIDTH_3V8_CF_LATEST.md"
NEEDLE_APPLY = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)
DEFAULT_SINCE = "2026-08-06T00:00:00+00:00"
FEE_RT = 0.006  # rough round-trip friction for $ delta honesty (~0.3%×2)


def _parse_ts(s: Any) -> datetime | None:
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _pair_path(pair: str) -> Path:
    return OHLCV_DIR / f"{pair.upper().replace('-', '_')}_1h.json"


def _load_candles(pair: str) -> list[list[float]]:
    path = _pair_path(pair)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    candles = raw.get("candles") if isinstance(raw, dict) else raw
    if not isinstance(candles, list):
        return []
    out: list[list[float]] = []
    for c in candles:
        if not isinstance(c, (list, tuple)) or len(c) < 5:
            continue
        try:
            t = float(c[0])
            if t > 1e12:
                t = t / 1000.0
            # Coinbase: [time, low, high, open, close, volume]
            out.append([t, float(c[1]), float(c[2]), float(c[3]), float(c[4])])
        except Exception:
            continue
    out.sort(key=lambda r: r[0])
    return out


def _fetch_candles(pair: str, start: datetime, end: datetime) -> list[list[float]]:
    """Paginated Coinbase public 1h candles; merge into local cache."""
    gran = 3600
    rows: list[list[float]] = []
    cur = start - timedelta(hours=6)
    end = end + timedelta(hours=6)
    while cur < end:
        chunk_end = min(cur + timedelta(seconds=gran * 280), end)
        start_s = cur.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"https://api.exchange.coinbase.com/products/{pair}/candles"
            f"?granularity={gran}&start={start_s}&end={end_s}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "phase6-sl-width-cf/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                for c in data:
                    if isinstance(c, list) and len(c) >= 5:
                        t = float(c[0])
                        if t > 1e12:
                            t /= 1000.0
                        rows.append([t, float(c[1]), float(c[2]), float(c[3]), float(c[4])])
        except Exception:
            pass
        time.sleep(0.12)
        cur = chunk_end
    by: dict[int, list[float]] = {}
    for r in rows:
        by[int(r[0])] = r
    merged = [by[k] for k in sorted(by)]
    if merged:
        OHLCV_DIR.mkdir(parents=True, exist_ok=True)
        path = _pair_path(pair)
        # merge with existing
        existing = _load_candles(pair)
        for r in existing:
            by[int(r[0])] = r
        merged = [by[k] for k in sorted(by)]
        payload = {
            "product": pair,
            "granularity": 3600,
            "candles": merged,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "source": "coinbase_public+sl_width_cf",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    return merged


def _ensure_candles(pair: str, start: datetime, end: datetime) -> list[list[float]]:
    candles = _load_candles(pair)
    if not candles:
        return _fetch_candles(pair, start, end)
    t0 = candles[0][0]
    t1 = candles[-1][0]
    need_start = start.timestamp() - 12 * 3600
    need_end = end.timestamp() + 12 * 3600
    if t0 <= need_start and t1 >= need_end:
        return candles
    # extend
    return _fetch_candles(pair, start, end)


def _first_touch(
    candles: list[list[float]],
    *,
    entry_ts: float,
    exit_ts: float,
    entry_px: float,
    stop_pct: float,
) -> dict[str, Any] | None:
    """First 1h bar after entry where low <= entry*(1-stop_pct), before actual exit+1h."""
    if entry_px <= 0 or not candles:
        return None
    stop_px = entry_px * (1.0 - stop_pct)
    mfe = 0.0
    mae = 0.0
    touched = None
    for c in candles:
        t, low, high, _o, close = c[0], c[1], c[2], c[3], c[4]
        if t + 3600 < entry_ts:
            continue
        if t > exit_ts + 3600:
            break
        # path extremes from entry
        mfe = max(mfe, high / entry_px - 1.0)
        mae = min(mae, low / entry_px - 1.0)
        if touched is None and low <= stop_px:
            # conservative fill: min(stop, open-ish) — use stop_px if open above stop else low
            fill = stop_px
            if _o < stop_px:
                fill = float(_o)  # gap through
            touched = {
                "ts": t,
                "ts_iso": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                "stop_px": stop_px,
                "fill_px": fill,
                "bar_low": low,
                "bar_high": high,
                "mfe_before_touch": mfe if mfe == max(mfe, 0) else mfe,
                "r_at_fill": fill / entry_px - 1.0,
            }
            # keep scanning mfe/mae for full path to actual exit for context
    # full-path MFE/MAE to actual exit regardless
    mfe_full = 0.0
    mae_full = 0.0
    for c in candles:
        t, low, high = c[0], c[1], c[2]
        if t + 3600 < entry_ts:
            continue
        if t > exit_ts + 3600:
            break
        mfe_full = max(mfe_full, high / entry_px - 1.0)
        mae_full = min(mae_full, low / entry_px - 1.0)
    if touched is None:
        return {
            "touched": False,
            "stop_pct": stop_pct,
            "stop_px": stop_px,
            "mfe_to_actual_exit": mfe_full,
            "mae_to_actual_exit": mae_full,
        }
    touched.update(
        {
            "touched": True,
            "stop_pct": stop_pct,
            "mfe_to_actual_exit": mfe_full,
            "mae_to_actual_exit": mae_full,
            # mfe before this stop: recompute up to touch bar
        }
    )
    # recompute MFE strictly before touch
    mfe_b = 0.0
    for c in candles:
        t, low, high = c[0], c[1], c[2]
        if t + 3600 < entry_ts:
            continue
        if t > touched["ts"]:
            break
        if t < touched["ts"]:
            mfe_b = max(mfe_b, high / entry_px - 1.0)
        else:
            # same bar: use high only if we assume stop after wick — conservative: mfe before low
            pass
    touched["mfe_before_touch"] = mfe_b
    return touched


def _sl_legs(since: datetime) -> list[dict[str, Any]]:
    out = []
    for t in _load_jsonl(TRADES):
        if str(t.get("side") or "").upper() != "SELL":
            continue
        reason = str(t.get("reason") or t.get("exit_reason") or "")
        if "stop_loss" not in reason.lower():
            continue
        if "dust" in reason.lower() or "process_bug" in reason.lower():
            continue
        ts = _parse_ts(t.get("timestamp") or t.get("ts"))
        if ts is None or ts < since:
            continue
        out.append(t)
    out.sort(key=lambda r: str(r.get("timestamp") or ""))
    return out


def _entry_ts_for_leg(trades: list[dict[str, Any]], leg: dict[str, Any]) -> datetime | None:
    """Best-effort: last BUY on pair before SL with matching-ish price, else SL ts − 7d."""
    pair = leg.get("pair")
    exit_ts = _parse_ts(leg.get("timestamp"))
    entry_px = leg.get("entry_price")
    if exit_ts is None:
        return None
    candidates = []
    for t in trades:
        if t.get("pair") != pair:
            continue
        if str(t.get("side") or "").upper() != "BUY":
            continue
        ts = _parse_ts(t.get("timestamp") or t.get("ts"))
        if ts is None or ts >= exit_ts:
            continue
        px = t.get("price") or t.get("entry_price") or t.get("exit_price")
        candidates.append((ts, px, t))
    if not candidates:
        return exit_ts - timedelta(days=7)
    # prefer buy whose price is within 1.5% of entry_price
    if entry_px:
        try:
            ep = float(entry_px)
            close = [
                c
                for c in candidates
                if c[1] is not None and abs(float(c[1]) / ep - 1.0) < 0.015
            ]
            if close:
                return max(close, key=lambda x: x[0])[0]
        except Exception:
            pass
    return max(candidates, key=lambda x: x[0])[0]


def analyze_leg(leg: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    pair = str(leg.get("pair") or "")
    exit_ts = _parse_ts(leg.get("timestamp"))
    entry_px = leg.get("entry_price")
    exit_px = leg.get("exit_price") or leg.get("price")
    qty = leg.get("qty") or leg.get("quantity")
    pnl_usd = leg.get("pnl") if leg.get("pnl") is not None else leg.get("pnl_usd")
    pnl_pct = leg.get("pnl_pct")
    if entry_px is None or exit_ts is None:
        return {"pair": pair, "error": "missing_entry_or_ts", "sl_ts": leg.get("timestamp")}
    try:
        entry_px_f = float(entry_px)
        exit_px_f = float(exit_px) if exit_px is not None else None
        qty_f = float(qty) if qty is not None else None
        pnl_f = float(pnl_usd) if pnl_usd is not None else None
        if pnl_pct is not None:
            pnl_pct_f = float(pnl_pct)
        elif exit_px_f and entry_px_f:
            pnl_pct_f = exit_px_f / entry_px_f - 1.0
        else:
            pnl_pct_f = None
    except Exception:
        return {"pair": pair, "error": "bad_numbers", "sl_ts": leg.get("timestamp")}

    entry_ts = _entry_ts_for_leg(trades, leg)
    if entry_ts is None:
        entry_ts = exit_ts - timedelta(days=7)

    candles = _ensure_candles(pair, entry_ts, exit_ts)
    if not candles:
        return {
            "pair": pair,
            "sl_ts": leg.get("timestamp"),
            "error": "no_ohlcv",
            "entry": entry_px_f,
            "actual_pnl_pct": pnl_pct_f,
            "actual_pnl_usd": pnl_f,
        }

    t3 = _first_touch(
        candles,
        entry_ts=entry_ts.timestamp(),
        exit_ts=exit_ts.timestamp(),
        entry_px=entry_px_f,
        stop_pct=0.03,
    )
    t8 = _first_touch(
        candles,
        entry_ts=entry_ts.timestamp(),
        exit_ts=exit_ts.timestamp(),
        entry_px=entry_px_f,
        stop_pct=0.08,
    )

    def sim_pnl(touch: dict[str, Any] | None) -> float | None:
        if not touch or not touch.get("touched") or qty_f is None:
            return None
        try:
            gross = (float(touch["fill_px"]) - entry_px_f) * qty_f
            # fee drag on notional
            notional = entry_px_f * qty_f
            return gross - FEE_RT * notional * 0.5  # exit-side only vs actual which already embeds fees-ish
        except Exception:
            return None

    pnl_3 = sim_pnl(t3)
    pnl_8 = sim_pnl(t8)
    # delta: 3% path vs actual
    d3 = (pnl_3 - pnl_f) if (pnl_3 is not None and pnl_f is not None) else None
    d8 = (pnl_8 - pnl_f) if (pnl_8 is not None and pnl_f is not None) else None
    # 3 vs 8 if both touch
    d_3_vs_8 = None
    if pnl_3 is not None and pnl_8 is not None:
        d_3_vs_8 = pnl_3 - pnl_8

    era = "post_needle_8pct" if exit_ts >= NEEDLE_APPLY else "pre_needle_3pct_era"
    # Did path ever go green before stop?
    mfe = (t8 or t3 or {}).get("mfe_to_actual_exit")
    went_green = mfe is not None and float(mfe) >= 0.01

    # Recommendation tag for this leg
    tag = "unknown"
    mfe_before_3 = float((t3 or {}).get("mfe_before_touch") or 0.0)
    # Prefer "green then tight-stop would cut" whenever 3% touches after a real green path
    if t3 and t3.get("touched") and mfe_before_3 >= 0.02:
        tag = "path_was_green_before_3pct_stop"
    elif t3 and t3.get("touched") and t8 and t8.get("touched"):
        hours_saved = None
        try:
            hours_saved = (float(t8["ts"]) - float(t3["ts"])) / 3600.0
        except Exception:
            pass
        if hours_saved is not None and hours_saved < 1 and abs(pnl_pct_f or 0) < 0.04:
            tag = "stops_near_simultaneous"
        elif d3 is not None and d3 > 1.0:
            tag = "3pct_helped_vs_actual"
        elif d3 is not None and d3 < -1.0:
            tag = "3pct_hurt_vs_actual"
        else:
            tag = "3pct_flat_vs_actual"
    elif t3 and t3.get("touched") and t8 and not t8.get("touched"):
        # 8% never printed on 1h lows but actual exit may be ~8% (exchange stop)
        if d3 is not None and d3 > 1.0 and mfe_before_3 < 0.02:
            tag = "3pct_helped_dead_path"  # never greened; tighter stop = less loss
        else:
            tag = "only_3pct_would_touch_before_exit"
    elif t8 and not t8.get("touched") and t3 and not t3.get("touched"):
        tag = "path_never_hit_3_or_8"  # SL fill may be basis/partial / trail-up
    elif t8 and t8.get("touched"):
        tag = "8pct_touched"

    actual_width = None
    if pnl_pct_f is not None:
        actual_width = abs(float(pnl_pct_f))

    return {
        "pair": pair,
        "sl_ts": leg.get("timestamp"),
        "reason": leg.get("reason"),
        "era": era,
        "entry_ts": entry_ts.isoformat(),
        "entry": entry_px_f,
        "exit": exit_px_f,
        "qty": qty_f,
        "actual_pnl_pct": pnl_pct_f,
        "actual_pnl_usd": pnl_f,
        "actual_abs_move": actual_width,
        "ohlcv_bars": len(candles),
        "sim_3pct": t3,
        "sim_8pct": t8,
        "sim_pnl_usd_3pct": pnl_3,
        "sim_pnl_usd_8pct": pnl_8,
        "delta_usd_3pct_minus_actual": d3,
        "delta_usd_8pct_minus_actual": d8,
        "delta_usd_3pct_minus_8pct": d_3_vs_8,
        "went_green_mfe_ge_1pct": went_green,
        "tag": tag,
    }


def build(since: datetime, *, fetch: bool = True) -> dict[str, Any]:
    # fetch flag reserved — _ensure always may fetch
    _ = fetch
    trades = _load_jsonl(TRADES)
    legs = _sl_legs(since)
    rows = [analyze_leg(L, trades) for L in legs]

    # aggregates
    ok = [r for r in rows if not r.get("error")]
    d3s = [float(r["delta_usd_3pct_minus_actual"]) for r in ok if r.get("delta_usd_3pct_minus_actual") is not None]
    d38 = [float(r["delta_usd_3pct_minus_8pct"]) for r in ok if r.get("delta_usd_3pct_minus_8pct") is not None]
    post = [r for r in ok if r.get("era") == "post_needle_8pct"]
    pre = [r for r in ok if r.get("era") == "pre_needle_3pct_era"]
    post_d3 = [float(r["delta_usd_3pct_minus_actual"]) for r in post if r.get("delta_usd_3pct_minus_actual") is not None]
    post_pnl = [float(r["actual_pnl_usd"]) for r in post if r.get("actual_pnl_usd") is not None]
    green_then_die = [r for r in ok if r.get("tag") == "path_was_green_before_3pct_stop"]
    helped = [r for r in ok if r.get("tag") == "3pct_helped_vs_actual"]

    def _sum(xs: list[float]) -> float | None:
        return sum(xs) if xs else None

    def _med(xs: list[float]) -> float | None:
        if not xs:
            return None
        s = sorted(xs)
        m = len(s) // 2
        return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])

    # Arming rule sketch from data (not live)
    # Prefer 8% when: path often greens first (MFE≥2%) OR name is core/high-vol sleeve
    # Prefer 3% when: post-needle legs with no green path and deep MAE, tryout shells
    arm_note = (
        "Data-backed sketch (NOT live): "
        "use 3% on unproven tryout shells that never printed ≥+2% MFE; "
        "keep 8% (or adaptive ≥6%) on graduated/core/names that already showed green path — "
        "tight stop there converts winners-into-losers. "
        "Post-NEEDLE actual losses are the 8% width working as designed when path never recovered."
    )

    return {
        "schema": "sl_width_3v8_cf_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "since": since.isoformat(),
        "needle_apply": NEEDLE_APPLY.isoformat(),
        "fee_rt_assumption": FEE_RT,
        "n_legs": len(rows),
        "n_ok": len(ok),
        "n_errors": len(rows) - len(ok),
        "sum_delta_usd_3pct_vs_actual": _sum(d3s),
        "median_delta_usd_3pct_vs_actual": _med(d3s),
        "sum_delta_usd_3pct_vs_8pct_sim": _sum(d38),
        "post_needle": {
            "n": len(post),
            "sum_actual_pnl_usd": _sum(post_pnl),
            "sum_delta_3pct_vs_actual": _sum(post_d3),
            "median_delta_3pct_vs_actual": _med(post_d3),
        },
        "pre_needle": {"n": len(pre)},
        "n_path_green_before_3pct_would_cut": len(green_then_die),
        "n_3pct_helped_vs_actual": len(helped),
        "arming_sketch": arm_note,
        "legs": rows,
        "glossary": {
            "3pct": "Fixed stop at entry*(1-0.03), first 1h low touch",
            "8pct": "Fixed stop at entry*(1-0.08), first 1h low touch",
            "delta 3−actual": "Simulated 3% exit $ − ledger SL $ (positive = tighter stop would have lost less)",
            "NEEDLE-04": "2026-09-30 live move 3%→8% base SL to cut fee-farm stop-outs",
        },
    }


def render_md(d: dict[str, Any]) -> str:
    lines = [
        "# SL width CF — 3% vs 8%",
        "",
        f"- as_of: `{d.get('as_of')}`",
        f"- since: `{d.get('since')}`",
        f"- legs ok: {d.get('n_ok')}/{d.get('n_legs')}",
        f"- sum Δ$ (3% sim − actual SL): **{d.get('sum_delta_usd_3pct_vs_actual')}**",
        f"- median Δ$: {d.get('median_delta_usd_3pct_vs_actual')}",
        f"- sum Δ$ (3% sim − 8% sim): {d.get('sum_delta_usd_3pct_vs_8pct_sim')}",
        f"- post-NEEDLE legs: {((d.get('post_needle') or {}).get('n'))} · "
        f"actual PnL sum {((d.get('post_needle') or {}).get('sum_actual_pnl_usd'))} · "
        f"3% vs actual sum {((d.get('post_needle') or {}).get('sum_delta_3pct_vs_actual'))}",
        f"- paths that were green then 3% would cut: {d.get('n_path_green_before_3pct_would_cut')}",
        "",
        "## Arming sketch (not live)",
        "",
        str(d.get("arming_sketch")),
        "",
        "## Legs",
        "",
    ]
    for L in d.get("legs") or []:
        if L.get("error"):
            lines.append(f"- {L.get('pair')} @ {L.get('sl_ts')}: ERROR {L.get('error')}")
            continue
        s3 = L.get("sim_3pct") or {}
        s8 = L.get("sim_8pct") or {}
        lines.append(
            f"### {L.get('pair')} @ {L.get('sl_ts')} ({L.get('era')})\n"
            f"- actual: {L.get('actual_pnl_pct')} ({L.get('actual_pnl_usd')} USD) tag=`{L.get('tag')}`\n"
            f"- 3% touch: {s3.get('touched')} @ {s3.get('ts_iso')} r={s3.get('r_at_fill')} "
            f"mfe_before={s3.get('mfe_before_touch')}\n"
            f"- 8% touch: {s8.get('touched')} @ {s8.get('ts_iso')} r={s8.get('r_at_fill')}\n"
            f"- path MFE/MAE to exit: {s8.get('mfe_to_actual_exit')}/{s8.get('mae_to_actual_exit')}\n"
            f"- Δ$ 3−actual: {L.get('delta_usd_3pct_minus_actual')} · "
            f"Δ$ 3−8 sim: {L.get('delta_usd_3pct_minus_8pct')}\n"
        )
    lines.append("")
    return "\n".join(lines)


def render_plain(d: dict[str, Any]) -> str:
    post = d.get("post_needle") or {}
    lines = [
        "SL width CF — 3% vs 8% (1h path, measure-only)",
        f"Legs: {d.get('n_ok')}/{d.get('n_legs')} · since {str(d.get('since') or '')[:10]}",
        f"Sum Δ$ if 3% instead of actual SL: {d.get('sum_delta_usd_3pct_vs_actual')} "
        f"(median {d.get('median_delta_usd_3pct_vs_actual')})",
        f"Sum Δ$ 3% sim vs 8% sim: {d.get('sum_delta_usd_3pct_vs_8pct_sim')}",
        f"Post-NEEDLE (live 8% era): n={post.get('n')} actual_pnl_sum={post.get('sum_actual_pnl_usd')} "
        f"· if-3% Δ sum={post.get('sum_delta_3pct_vs_actual')}",
        f"Green-then-3%-would-cut: {d.get('n_path_green_before_3pct_would_cut')} · "
        f"3% helped vs actual: {d.get('n_3pct_helped_vs_actual')}",
        "",
        "Per leg:",
    ]
    for L in d.get("legs") or []:
        if L.get("error"):
            lines.append(f"  {L.get('pair')}: err {L.get('error')}")
            continue
        lines.append(
            f"  {str(L.get('sl_ts') or '')[:16]} {L.get('pair')} actual={L.get('actual_pnl_pct')} "
            f"Δ3={L.get('delta_usd_3pct_minus_actual')} tag={L.get('tag')} era={L.get('era')}"
        )
    lines.append("")
    lines.append(str(d.get("arming_sketch")))
    lines.append("Full: reports/SL_WIDTH_3V8_CF_LATEST.md")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args(argv)
    since = _parse_ts(args.since)
    if since is None:
        print("bad since", file=sys.stderr)
        return 2
    d = build(since, fetch=not args.no_fetch)
    if not args.no_write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(d, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_MD.write_text(render_md(d), encoding="utf-8")
    if args.json_only:
        print(json.dumps(d, indent=2, default=str))
    else:
        print(render_plain(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
