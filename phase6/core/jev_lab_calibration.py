"""Jev lab L4 calibration rollup — measure-only.

Joins judgment crumbs to forward returns (OHLCV) and optional knife shadow.
Never places orders. Honest N: insufficient sample → no edge claim.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CRUMBS = ROOT / "data" / "state" / "jev_lab_crumbs.jsonl"
DEFAULT_LATEST = ROOT / "data" / "state" / "jev_lab_calibration_latest.json"
DEFAULT_MD = ROOT / "reports" / "JEV_LAB_CALIBRATION_LATEST.md"
DEFAULT_OHLCV_DIR = ROOT / "data" / "ohlcv" / "1h"
KNIFE_LATEST = ROOT / "data" / "state" / "knife_filter_shadow_latest.json"
KNIFE_CRUMBS = ROOT / "data" / "state" / "knife_filter_shadow_crumbs.jsonl"
COINBASE_PUBLIC = "https://api.exchange.coinbase.com"

# horizons in hours (1h bars)
HORIZONS_H = (1, 4, 24)
MIN_N_CLAIM = 20  # below this → N_INSUFFICIENT, no edge claim
OHLCV_STALE_SEC = 3 * 3600  # refresh if last bar older than this vs wall clock



def _parse_ts(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        # ms vs s
        if v > 1e12:
            return v / 1000.0
        if v > 1e10:
            return v / 1000.0
        return v
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _pair_ohlcv_path(pair: str, ohlcv_dir: Path) -> Path:
    # BTC-USD → BTC_USD_1h.json
    base = pair.upper().replace("-", "_")
    return ohlcv_dir / f"{base}_1h.json"


def _candles_from_raw(raw: Any) -> List[Any]:
    candles = raw.get("candles") if isinstance(raw, dict) else raw
    if not isinstance(candles, list):
        return []
    return [c for c in candles if isinstance(c, (list, tuple)) and len(c) >= 5]


def load_ohlcv_candles(pair: str, ohlcv_dir: Path = DEFAULT_OHLCV_DIR) -> List[Tuple[float, float]]:
    """Return sorted list of (ts_sec, close). Coinbase-ish [t, low, high, open, close, vol]."""
    path = _pair_ohlcv_path(pair, ohlcv_dir)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: List[Tuple[float, float]] = []
    for c in _candles_from_raw(raw):
        try:
            t = float(c[0])
            close = float(c[4])
        except (TypeError, ValueError, IndexError):
            continue
        if t > 1e12:
            t = t / 1000.0
        out.append((t, close))
    out.sort(key=lambda x: x[0])
    return out


def refresh_ohlcv_1h(
    pairs: Sequence[str],
    ohlcv_dir: Path = DEFAULT_OHLCV_DIR,
    *,
    n_bars: int = 500,
    force: bool = False,
) -> Dict[str, Any]:
    """Best-effort Coinbase public 1h refresh for lab pairs. Measure-only helper."""
    import urllib.error
    import urllib.request
    from datetime import timedelta

    ohlcv_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    report: Dict[str, Any] = {"refreshed": [], "skipped": [], "errors": []}

    for pair in pairs:
        pid = str(pair).upper()
        path = _pair_ohlcv_path(pid, ohlcv_dir)
        existing = load_ohlcv_candles(pid, ohlcv_dir)
        last_t = existing[-1][0] if existing else 0.0
        age = now.timestamp() - last_t if last_t else 1e18
        if not force and existing and age < OHLCV_STALE_SEC:
            report["skipped"].append({"pair": pid, "age_h": round(age / 3600.0, 2)})
            continue
        start_dt = now - timedelta(hours=n_bars + 5)
        # Coinbase rejects sub-second / odd ISO; use Z seconds only
        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"{COINBASE_PUBLIC}/products/{pid}/candles"
            f"?granularity=3600&start={start}&end={end}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "phase6-jev-lab/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            # fallback: no start/end (exchange returns recent window)
            try:
                url2 = f"{COINBASE_PUBLIC}/products/{pid}/candles?granularity=3600"
                req2 = urllib.request.Request(url2, headers={"User-Agent": "phase6-jev-lab/1.0"})
                with urllib.request.urlopen(req2, timeout=25) as resp2:
                    rows = json.loads(resp2.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e2:
                report["errors"].append({"pair": pid, "error": f"{e} | fallback: {e2}"[:200]})
                continue
        if not isinstance(rows, list) or not rows:
            report["errors"].append({"pair": pid, "error": "empty_candles"})
            continue
        rows = sorted(rows, key=lambda x: x[0])
        if len(rows) > n_bars:
            rows = rows[-n_bars:]
        payload = {
            "product": pid,
            "granularity": 3600,
            "candles": rows,
            "refreshed_at": now.isoformat(),
            "source": "coinbase_public",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        report["refreshed"].append({"pair": pid, "n": len(rows), "last_t": rows[-1][0]})
    return report



def forward_return(
    candles: Sequence[Tuple[float, float]],
    ts: float,
    hours: int,
) -> Optional[float]:
    """Close-to-close return from first bar at/after ts to bar ~hours later."""
    if not candles or ts is None:
        return None
    # entry: first bar with t >= ts, else last bar with t <= ts
    entry_i: Optional[int] = None
    for i, (t, _c) in enumerate(candles):
        if t >= ts:
            entry_i = i
            break
    if entry_i is None:
        # all bars before ts — use last
        entry_i = len(candles) - 1
    # if bar is far after ts (>2h), still ok for sparse lab ticks
    entry_t, entry_px = candles[entry_i]
    if entry_px <= 0:
        return None
    target_t = entry_t + hours * 3600.0
    exit_i = entry_i
    for j in range(entry_i, len(candles)):
        if candles[j][0] >= target_t:
            exit_i = j
            break
    else:
        # not enough forward data
        if entry_i >= len(candles) - 1:
            return None
        exit_i = len(candles) - 1
        # require at least ~50% of horizon elapsed
        elapsed_h = (candles[exit_i][0] - entry_t) / 3600.0
        if elapsed_h < hours * 0.5:
            return None
    exit_px = candles[exit_i][1]
    if exit_px <= 0:
        return None
    return (exit_px / entry_px) - 1.0


def load_crumbs(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _answer_field(answers: Dict[str, Any], key: str, field: str) -> Any:
    a = answers.get(key) or {}
    if isinstance(a, dict):
        return a.get(field)
    return None


def _mean(xs: Sequence[float]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _pct(xs: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(float(x) for x in xs if x is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = int(round(q * (len(vals) - 1)))
    idx = max(0, min(len(vals) - 1, idx))
    return vals[idx]


@dataclass
class CalibrationConfig:
    crumbs_path: Path = field(default_factory=lambda: DEFAULT_CRUMBS)
    ohlcv_dir: Path = field(default_factory=lambda: DEFAULT_OHLCV_DIR)
    latest_path: Path = field(default_factory=lambda: DEFAULT_LATEST)
    md_path: Path = field(default_factory=lambda: DEFAULT_MD)
    lookback_days: float = 7.0
    min_n_claim: int = MIN_N_CLAIM
    write: bool = True
    refresh_ohlcv: bool = True
    force_ohlcv_refresh: bool = False



def _enrich_row(
    row: Dict[str, Any],
    candle_cache: Dict[str, List[Tuple[float, float]]],
    ohlcv_dir: Path,
) -> Dict[str, Any]:
    pair = str(row.get("pair") or "").upper()
    ts = _parse_ts(row.get("ts"))
    answers = row.get("answers") or {}
    paper = row.get("paper") or {}
    out = {
        "pair": pair,
        "ts": row.get("ts"),
        "ts_epoch": ts,
        "ok": bool(row.get("ok")),
        "model": row.get("model"),
        "latency_ms": row.get("latency_ms"),
        "action": _answer_field(answers, "action", "choice"),
        "action_conf": _answer_field(answers, "action", "confidence"),
        "regime": _answer_field(answers, "regime", "choice"),
        "setup_quality": _answer_field(answers, "setup_quality", "score"),
        "fakeout_noul": _answer_field(answers, "is_fakeout_or_stop_run", "noul"),
        "should_trade_noul": _answer_field(answers, "should_trade_name_now", "noul"),
        "confidence_route": paper.get("confidence_route"),
        "paper_would_buy_tag": bool(paper.get("paper_would_buy_tag")),
        "would_order": False,  # hard
        "fwd": {},
        "fwd_ready": False,
    }
    if not out["ok"] or ts is None or not pair:
        return out
    if pair not in candle_cache:
        candle_cache[pair] = load_ohlcv_candles(pair, ohlcv_dir)
    candles = candle_cache[pair]
    fwd: Dict[str, Optional[float]] = {}
    ready = True
    for h in HORIZONS_H:
        r = forward_return(candles, ts, h) if candles else None
        fwd[f"{h}h"] = r
        if r is None:
            ready = False
    out["fwd"] = fwd
    # mark ready if at least 1h available (partial ok for young crumbs)
    out["fwd_ready"] = fwd.get("1h") is not None
    out["fwd_partial"] = not all(fwd.get(f"{h}h") is not None for h in HORIZONS_H)
    return out


def _bucket_stats(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        k = r.get(key)
        label = str(k) if k is not None else "null"
        buckets[label].append(r)

    def pack(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        r1 = [x["fwd"]["1h"] for x in items if x.get("fwd", {}).get("1h") is not None]
        r4 = [x["fwd"]["4h"] for x in items if x.get("fwd", {}).get("4h") is not None]
        r24 = [x["fwd"]["24h"] for x in items if x.get("fwd", {}).get("24h") is not None]
        return {
            "n": len(items),
            "n_fwd_1h": len(r1),
            "mean_r_1h": _round(_mean(r1)),
            "mean_r_4h": _round(_mean(r4)),
            "mean_r_24h": _round(_mean(r24)),
            "n_paper_buy": sum(1 for x in items if x.get("paper_would_buy_tag")),
        }

    return {k: pack(v) for k, v in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))}


def _round(x: Optional[float], nd: int = 6) -> Optional[float]:
    if x is None:
        return None
    return round(float(x), nd)


def knife_agreement_snapshot(knife_path: Path = KNIFE_LATEST) -> Dict[str, Any]:
    """Lightweight knife board snapshot for side-by-side (not causal join at low N)."""
    if not knife_path.is_file():
        return {"available": False, "reason": "knife_latest_missing"}
    try:
        d = json.loads(knife_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "reason": "knife_latest_unreadable"}
    rows = d.get("rows") or []
    return {
        "available": True,
        "ts": d.get("ts"),
        "n_pairs": d.get("n_pairs") or len(rows),
        "claim_class": d.get("claim_class"),
        "plain_english": d.get("plain_english"),
        "arm_table": d.get("arm_table"),
        "note": "Side-board only until pair-level crumb join has N; not a causal claim.",
    }


def run_calibration(cfg: Optional[CalibrationConfig] = None) -> Dict[str, Any]:
    cfg = cfg or CalibrationConfig()
    crumbs = load_crumbs(cfg.crumbs_path)
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - float(cfg.lookback_days) * 86400.0

    windowed = []
    for c in crumbs:
        ts = _parse_ts(c.get("ts"))
        if ts is None or ts < cutoff:
            continue
        windowed.append(c)

    pairs_hint = sorted(
        {
            str(c.get("pair")).upper()
            for c in windowed
            if c.get("pair")
        }
        or {"BTC-USD", "ETH-USD"}
    )
    ohlcv_refresh: Dict[str, Any] = {"skipped_all": True}
    if cfg.refresh_ohlcv:
        ohlcv_refresh = refresh_ohlcv_1h(
            pairs_hint,
            cfg.ohlcv_dir,
            force=cfg.force_ohlcv_refresh,
        )

    candle_cache: Dict[str, List[Tuple[float, float]]] = {}
    enriched = [_enrich_row(c, candle_cache, cfg.ohlcv_dir) for c in windowed]
    ok_rows = [r for r in enriched if r.get("ok")]
    fwd_rows = [r for r in ok_rows if r.get("fwd_ready")]

    latencies = [float(r["latency_ms"]) for r in ok_rows if r.get("latency_ms") is not None]
    costs = []
    for c in windowed:
        u = c.get("usage") or {}
        # OpenRouter may put cost in usage
        for k in ("cost", "total_cost", "native_tokens_prompt"):
            if k == "cost" or k == "total_cost":
                try:
                    if u.get(k) is not None:
                        costs.append(float(u[k]))
                except (TypeError, ValueError):
                    pass

    n_ok = len(ok_rows)
    n_fwd = len(fwd_rows)
    claim = (
        "N_INSUFFICIENT_no_edge_claim"
        if n_ok < int(cfg.min_n_claim)
        else "MEASURE_ONLY_calibration_board"
    )
    if n_ok >= int(cfg.min_n_claim) and n_fwd < max(5, int(cfg.min_n_claim) // 2):
        claim = "N_PARTIAL_fwd_thin_no_edge_claim"

    by_route = _bucket_stats(ok_rows, "confidence_route")
    by_action = _bucket_stats(ok_rows, "action")
    by_paper = _bucket_stats(ok_rows, "paper_would_buy_tag")

    # fakeout high vs low vs subsequent 1h return (sign check)
    hi_fk = [r for r in fwd_rows if (r.get("fakeout_noul") or 0) >= 0.55]
    lo_fk = [r for r in fwd_rows if r.get("fakeout_noul") is not None and r.get("fakeout_noul") < 0.35]
    fakeout_check = {
        "hi_fakeout_n": len(hi_fk),
        "lo_fakeout_n": len(lo_fk),
        "hi_mean_r_1h": _round(_mean([r["fwd"]["1h"] for r in hi_fk if r["fwd"].get("1h") is not None])),
        "lo_mean_r_1h": _round(_mean([r["fwd"]["1h"] for r in lo_fk if r["fwd"].get("1h") is not None])),
        "note": "Expect hi_fakeout mean_r not strongly positive if calibrated; N-tag always.",
    }

    # should_trade high vs buy-tag rate (internal consistency, not PnL)
    st_hi = [r for r in ok_rows if (r.get("should_trade_noul") or 0) >= 0.65]
    consistency = {
        "should_trade_ge_0.65_n": len(st_hi),
        "paper_buy_among_st_hi": sum(1 for r in st_hi if r.get("paper_would_buy_tag")),
        "paper_buy_total": sum(1 for r in ok_rows if r.get("paper_would_buy_tag")),
    }

    knife = knife_agreement_snapshot()

    pairs_seen = sorted({str(r.get("pair")) for r in ok_rows if r.get("pair")})
    models = sorted({str(r.get("model")) for r in ok_rows if r.get("model")})

    plain = _plain_english(
        n_ok=n_ok,
        n_fwd=n_fwd,
        claim=claim,
        min_n=int(cfg.min_n_claim),
        by_route=by_route,
        lat_p50=_pct(latencies, 0.50),
        lat_p95=_pct(latencies, 0.95),
        pairs=pairs_seen,
    )

    summary: Dict[str, Any] = {
        "kind": "jev_lab_calibration_l4",
        "ts": datetime.now(timezone.utc).isoformat(),
        "measure_only": True,
        "would_order_always_false": True,
        "lookback_days": cfg.lookback_days,
        "min_n_claim": cfg.min_n_claim,
        "claim_class": claim,
        "n_crumbs_window": len(windowed),
        "n_ok": n_ok,
        "n_fwd_ready": n_fwd,
        "pairs": pairs_seen,
        "models": models,
        "latency_ms": {
            "n": len(latencies),
            "p50": _round(_pct(latencies, 0.50), 1),
            "p95": _round(_pct(latencies, 0.95), 1),
            "mean": _round(_mean(latencies), 1),
        },
        "cost_sum_if_present": _round(sum(costs), 8) if costs else None,
        "by_confidence_route": by_route,
        "by_action": by_action,
        "by_paper_would_buy_tag": by_paper,
        "fakeout_vs_fwd": fakeout_check,
        "internal_consistency": consistency,
        "knife_sideboard": knife,
        "ohlcv_refresh": ohlcv_refresh,
        "platform_proof": {
            "packet_ok_path": n_ok > 0 or len(windowed) == 0,
            "paper_gate_never_orders": True,
            "fwd_join_wired": True,
            "honest_n_gate": n_ok < int(cfg.min_n_claim),
            "fwd_needs_age": (
                "Fresh crumbs need ≥1h of post-tick bars before fwd_1h is defined; "
                "n_fwd=0 on brand-new ticks is expected, not a join bug."
            ),
            "note": (
                "Proof of harness functionality against current execution/state; "
                "not proof of alpha."
            ),
        },
        "plain_english": plain,
        "must_not": [
            "no_orders",
            "no_live_buy_block",
            "no_tryout_knob",
            "no_promote",
            "no_edge_claim_below_min_n",
        ],
        "rows_sample": ok_rows[:20],  # small sample for debug
    }

    if cfg.write:
        cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.latest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        _write_md(summary, cfg.md_path)

    return summary


def _plain_english(
    *,
    n_ok: int,
    n_fwd: int,
    claim: str,
    min_n: int,
    by_route: Dict[str, Any],
    lat_p50: Optional[float],
    lat_p95: Optional[float],
    pairs: Sequence[str],
) -> str:
    bits = [
        f"Jev L4 calibration · claim={claim}",
        f"n_ok={n_ok} n_fwd={n_fwd} min_n={min_n}",
        f"pairs={','.join(pairs) or 'none'}",
    ]
    if lat_p50 is not None:
        if lat_p95 is not None:
            bits.append(f"lat_p50={lat_p50:.0f}ms p95={lat_p95:.0f}ms")
        else:
            bits.append(f"lat_p50={lat_p50:.0f}ms")
    for route, st in list(by_route.items())[:4]:
        bits.append(f"{route}:n={st.get('n')} mean_r_1h={st.get('mean_r_1h')}")
    if n_ok < min_n:
        bits.append("No edge claim — keep collecting crumbs.")
    bits.append("would_order=false always.")
    return " | ".join(bits)


def _write_md(summary: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Jev Lab Calibration (L4) — LATEST",
        "",
        f"- **ts:** {summary.get('ts')}",
        f"- **claim:** `{summary.get('claim_class')}`",
        f"- **lookback_days:** {summary.get('lookback_days')}",
        f"- **n_ok / n_fwd:** {summary.get('n_ok')} / {summary.get('n_fwd_ready')}",
        f"- **pairs:** {', '.join(summary.get('pairs') or []) or '—'}",
        f"- **models:** {', '.join(summary.get('models') or []) or '—'}",
        "",
        "## Plain English",
        "",
        str(summary.get("plain_english") or ""),
        "",
        "## Latency",
        "",
        f"- p50: {(summary.get('latency_ms') or {}).get('p50')} ms",
        f"- p95: {(summary.get('latency_ms') or {}).get('p95')} ms",
        "",
        "## By confidence route",
        "",
        "| Route | n | n_fwd_1h | mean_r_1h | mean_r_4h | mean_r_24h | paper_buy |",
        "|-------|---|----------|-----------|-----------|------------|-----------|",
    ]
    for route, st in (summary.get("by_confidence_route") or {}).items():
        lines.append(
            f"| {route} | {st.get('n')} | {st.get('n_fwd_1h')} | {st.get('mean_r_1h')} | "
            f"{st.get('mean_r_4h')} | {st.get('mean_r_24h')} | {st.get('n_paper_buy')} |"
        )
    lines.extend(
        [
            "",
            "## Fakeout vs forward (N-tagged)",
            "",
            "```json",
            json.dumps(summary.get("fakeout_vs_fwd"), indent=2),
            "```",
            "",
            "## Knife sideboard",
            "",
            "```json",
            json.dumps(summary.get("knife_sideboard"), indent=2)[:2000],
            "```",
            "",
            "## Must not",
            "",
        ]
    )
    for m in summary.get("must_not") or []:
        lines.append(f"- {m}")
    lines.extend(["", f"State: `{DEFAULT_LATEST}`", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def telegram_summary(summary: Dict[str, Any]) -> str:
    return str(summary.get("plain_english") or "jev_lab_calibration empty")
