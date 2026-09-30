"""
Pair lifecycle by crypto class — measure-only board.

Compares how the bot handles each class across closed tryout/trade RTs:
seat→exit quality, exit mix, hold time, process tax, optional vol bucket.

No live writes, no threshold flips, no edge claim below N.
Purpose: raise opportunity-window decisions with class evidence (Brad 2026-09-29).
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from phase6.core.attribution_rt_weekly import (
    classify_exit_reason,
    index_buys,
    is_process_tax,
    match_entry_lot,
)
from phase6.core.paths import PROJECT_ROOT

SCHEMA = "pair_lifecycle_by_class_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "pair_lifecycle_by_class_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "PAIR_LIFECYCLE_BY_CLASS_LATEST.md"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
CONFIG_PATH = PROJECT_ROOT / "config" / "pair_lifecycle_by_class.json"

# Class labels — static SSOT for rollup (vol is separate axis when computable)
DEFAULT_CLASS_MAP: Dict[str, str] = {
    "BTC-USD": "mega",
    "BTC-USDC": "mega",
    "ETH-USD": "mega",
    "ETH-USDC": "mega",
    "SOL-USD": "large",
    "SOL-USDC": "large",
    "XRP-USD": "large",
    "XRP-USDC": "large",
    "LINK-USD": "large",
    "LINK-USDC": "large",
    "AVAX-USD": "large",
    "AVAX-USDC": "large",
    "ADA-USD": "mid",
    "DOGE-USD": "mid",
    "DOT-USD": "mid",
    "MATIC-USD": "mid",
    "OP-USD": "mid",
    "ARB-USD": "mid",
    "SUI-USD": "mid",
    "TIA-USD": "mid",
    "NEAR-USD": "mid",
    "ICP-USD": "mid",
    "STX-USD": "mid",
    "AAVE-USD": "mid",
    "UNI-USD": "mid",
    "ZEC-USD": "mid",
    "HYPE-USD": "high_beta",
    "WLD-USD": "high_beta",
    "PENGU-USD": "high_beta",
    "RAVE-USD": "high_beta",
    "PEPE-USD": "high_beta",
    "SHIB-USD": "high_beta",
    "WIF-USD": "high_beta",
    "BONK-USD": "high_beta",
    "PAXG-USD": "ballast",
    "PAXG-USDC": "ballast",
}

# Implied vol rank when realized vol missing (for display only)
CLASS_IMPLIED_VOL: Dict[str, str] = {
    "ballast": "low",
    "mega": "low_med",
    "large": "med",
    "mid": "med_high",
    "high_beta": "high",
    "other": "unknown",
}

STABLE_BASES = {"USDT", "USDC", "DAI", "USD"}

# Honesty bars
COMPARE_MIN_N = 8  # class rollup language
EDGE_MIN_N = 20  # edge-style language never below this
DEFAULT_LOOKBACK_DAYS = 90.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pnl(row: Mapping[str, Any]) -> float:
    for k in ("pnl", "realized_pnl", "pnl_usd"):
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def is_stable_pair(pair: str) -> bool:
    p = _norm_pair(pair)
    if p in {"USDT-USDC", "USDC-USDT", "USD-USD"}:
        return True
    base = p.split("-")[0] if "-" in p else p
    return base in STABLE_BASES


def load_class_config(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or CONFIG_PATH
    cfg: Dict[str, Any] = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "compare_min_n": COMPARE_MIN_N,
        "edge_min_n": EDGE_MIN_N,
        "class_map": dict(DEFAULT_CLASS_MAP),
        "measure_only": True,
        "live_apply": False,
        "note": "Class×lifecycle measure board. No threshold auto-tune.",
    }
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: v for k, v in raw.items() if k != "class_map"})
                cm = raw.get("class_map")
                if isinstance(cm, dict) and cm:
                    merged = dict(DEFAULT_CLASS_MAP)
                    merged.update({_norm_pair(k): str(v) for k, v in cm.items()})
                    cfg["class_map"] = merged
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def pair_class(pair: str, class_map: Optional[Mapping[str, str]] = None) -> str:
    p = _norm_pair(pair)
    if is_stable_pair(p):
        return "stable"
    m = class_map or DEFAULT_CLASS_MAP
    if p in m:
        return str(m[p])
    # USDC twin of known USD pair
    if p.endswith("-USDC"):
        twin = p.replace("-USDC", "-USD")
        if twin in m:
            return str(m[twin])
    return "other"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    except OSError:
        return []
    return out


def _hold_hours(buy: Optional[Mapping[str, Any]], sell: Mapping[str, Any]) -> Optional[float]:
    st = _parse_ts(sell.get("timestamp") or sell.get("ts"))
    if not buy or st is None:
        # try indicators lag
        ind = sell.get("indicators_at_trade")
        if isinstance(ind, dict) and ind.get("lag_hours_entry_to_exit") is not None:
            return _f(ind.get("lag_hours_entry_to_exit"))
        return None
    bt = _parse_ts(buy.get("timestamp") or buy.get("ts"))
    if bt is None:
        return None
    return max(0.0, (st - bt).total_seconds() / 3600.0)


def _entry_px(buy: Optional[Mapping[str, Any]], sell: Mapping[str, Any]) -> Optional[float]:
    for src in (sell, buy or {}):
        for k in ("entry_price", "avg_entry", "average_filled_price"):
            if src is sell and k == "average_filled_price":
                continue
            v = _f(src.get(k))
            if v and v > 0:
                return v
    return _f(sell.get("entry_price"))


def _exit_px(sell: Mapping[str, Any]) -> Optional[float]:
    for k in ("exit_price", "average_filled_price", "price"):
        v = _f(sell.get(k))
        if v and v > 0:
            return v
    return None


def _pnl_pct(sell: Mapping[str, Any], buy: Optional[Mapping[str, Any]]) -> Optional[float]:
    v = _f(sell.get("pnl_pct"))
    if v is not None:
        # ledger sometimes stores fraction, sometimes percent
        if abs(v) > 2.0:
            return v / 100.0
        return v
    ep = _entry_px(buy, sell)
    xp = _exit_px(sell)
    if ep and xp and ep > 0:
        return xp / ep - 1.0
    return None


def _regime_hint(sell: Mapping[str, Any], buy: Optional[Mapping[str, Any]]) -> str:
    for src in (sell, buy or {}):
        for k in ("regime", "regime_layer", "entry_regime", "market_regime"):
            v = src.get(k)
            if v:
                return str(v)
        ind = src.get("indicators_at_trade")
        if isinstance(ind, dict):
            for k in ("regime", "regime_layer"):
                if ind.get(k):
                    return str(ind.get(k))
    return "unknown"


def realized_vol_bucket(
    pair: str,
    *,
    lookback_days: int = 30,
    class_name: Optional[str] = None,
) -> Tuple[Optional[float], str]:
    """
    Best-effort 30d daily vol from OHLCV JSON mirror; fail soft → class-implied.
    Returns (daily_vol or None, bucket_label).
    """
    del lookback_days  # reserved for marketdata path later
    # Prefer static class implied when no clean tape helper
    implied = CLASS_IMPLIED_VOL.get(class_name or pair_class(pair), "unknown")
    try:
        base = _norm_pair(pair).split("-")[0]
        candidates = [
            PROJECT_ROOT / "data" / "ohlcv" / f"{base}_1d_coinbase.json",
            PROJECT_ROOT / "data" / "ohlcv" / f"{_norm_pair(pair)}_1d.json",
        ]
        closes: List[float] = []
        for path in candidates:
            if not path.exists():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else (raw.get("candles") or raw.get("bars") or [])
            for row in rows:
                if isinstance(row, dict):
                    c = _f(row.get("close") or row.get("c"))
                elif isinstance(row, (list, tuple)) and len(row) >= 5:
                    c = _f(row[4])
                else:
                    c = None
                if c and c > 0:
                    closes.append(c)
            if len(closes) >= 10:
                break
        if len(closes) < 10:
            return None, implied
        window = closes[-31:]
        rets = []
        for i in range(1, len(window)):
            a, b = float(window[i - 1]), float(window[i])
            if a > 0 and b > 0:
                rets.append(math.log(b / a))
        if len(rets) < 8:
            return None, implied
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        daily = math.sqrt(max(var, 0.0))
        if daily < 0.012:
            bucket = "low"
        elif daily < 0.022:
            bucket = "med"
        elif daily < 0.035:
            bucket = "high"
        else:
            bucket = "very_high"
        return daily, bucket
    except Exception:
        return None, implied


def build_lifecycle_rts(
    ledger: Sequence[Mapping[str, Any]],
    *,
    since: datetime,
    until: Optional[datetime] = None,
    class_map: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    until = until or _utc_now()
    buys_by = index_buys(ledger)
    out: List[Dict[str, Any]] = []
    for sell in ledger:
        if str(sell.get("side") or sell.get("action") or "").upper() != "SELL":
            continue
        ts = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        if ts is None or ts < since or ts > until:
            continue
        pair = _norm_pair(str(sell.get("pair") or sell.get("product_id") or ""))
        if not pair:
            continue
        if is_stable_pair(pair):
            continue
        buy = match_entry_lot(sell, buys_by)
        bucket = classify_exit_reason(sell)
        # skip pure test cleanup noise from primary compare
        if bucket == "test_cleanup":
            continue
        raw_reason = str(sell.get("reason") or sell.get("exit_reason") or "")
        if "process_bug" in raw_reason.lower():
            # keep as process tax adjacent
            bucket = "process_bug"
        cls = pair_class(pair, class_map)
        hold_h = _hold_hours(buy, sell)
        pnl = _pnl(sell)
        pct = _pnl_pct(sell, buy)
        qty = _f(sell.get("qty") or sell.get("size") or sell.get("filled_qty")) or 0.0
        ep = _entry_px(buy, sell)
        notional = (ep * qty) if ep and qty else None
        out.append(
            {
                "pair": pair,
                "class": cls,
                "sell_ts": ts.isoformat(),
                "exit_bucket": bucket,
                "process_tax": is_process_tax(bucket) or bucket == "process_bug",
                "pnl": round(pnl, 4),
                "pnl_pct": round(pct, 6) if pct is not None else None,
                "hold_hours": round(hold_h, 3) if hold_h is not None else None,
                "entry_notional_usd": round(notional, 2) if notional else None,
                "regime_at_entry": _regime_hint(sell, buy),
                "exit_reason_raw": raw_reason[:180] if raw_reason else None,
                "win": bool(pnl > 0.01) if pct is None else bool(pct > 0.0 and pnl >= 0),
            }
        )
    return out


def _safe_mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _safe_rate(n_num: int, n_den: int) -> Optional[float]:
    if n_den <= 0:
        return None
    return n_num / n_den


def aggregate_group(rows: Sequence[Mapping[str, Any]], *, key: str, min_n: int) -> List[Dict[str, Any]]:
    by: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by[str(r.get(key) or "unknown")].append(r)
    out: List[Dict[str, Any]] = []
    for name, grp in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        n = len(grp)
        pnls = [float(r["pnl"]) for r in grp]
        holds = [float(r["hold_hours"]) for r in grp if r.get("hold_hours") is not None]
        pcts = [float(r["pnl_pct"]) for r in grp if r.get("pnl_pct") is not None]
        buckets = Counter(str(r.get("exit_bucket")) for r in grp)
        n_sl = buckets.get("sl_exchange", 0)
        n_tp = buckets.get("tp_profit", 0)
        n_dual = buckets.get("dual_peak", 0)
        n_tax = sum(1 for r in grp if r.get("process_tax"))
        n_win = sum(1 for r in grp if r.get("win"))
        claim = "none"
        if n >= EDGE_MIN_N:
            claim = "describe_only"  # still no auto edge
        elif n >= min_n:
            claim = "compare_ok"
        else:
            claim = "thin_n"
        out.append(
            {
                "key": name,
                "n_rt": n,
                "n_win": n_win,
                "win_rate": round(_safe_rate(n_win, n) or 0.0, 4),
                "n_sl": n_sl,
                "sl_rate": round(_safe_rate(n_sl, n) or 0.0, 4),
                "n_tp": n_tp,
                "tp_rate": round(_safe_rate(n_tp, n) or 0.0, 4),
                "n_dual_peak": n_dual,
                "dual_peak_rate": round(_safe_rate(n_dual, n) or 0.0, 4),
                "n_process_tax": n_tax,
                "process_tax_rate": round(_safe_rate(n_tax, n) or 0.0, 4),
                "pnl_sum": round(sum(pnls), 4),
                "pnl_mean": round(_safe_mean(pnls) or 0.0, 4),
                "hold_hours_mean": (round(float(_safe_mean(holds) or 0.0), 3) if holds else None),
                "pnl_pct_mean": (round(float(_safe_mean(pcts) or 0.0), 6) if pcts else None),
                "exit_mix": dict(buckets.most_common()),
                "claim_level": claim,
                "implied_vol": CLASS_IMPLIED_VOL.get(name, "unknown") if key == "class" else None,
            }
        )
    return out


def _hypothesis_notes(by_class: Sequence[Mapping[str, Any]], min_n: int) -> List[str]:
    """Plain-English compare notes — never promote knobs."""
    notes: List[str] = []
    usable = [c for c in by_class if int(c.get("n_rt") or 0) >= min_n]
    if len(usable) < 2:
        notes.append(
            f"Need ≥{min_n} closed RTs in ≥2 classes before class compare. "
            "Soft-up door fills feed this board — do not tune thresholds yet."
        )
        return notes
    # high_beta vs large/mid if present
    by = {c["key"]: c for c in usable}
    hb = by.get("high_beta")
    large = by.get("large")
    mid = by.get("mid")
    mega = by.get("mega")
    if hb and large:
        if hb["sl_rate"] <= large["sl_rate"] + 0.05 and hb["pnl_mean"] >= large["pnl_mean"] - 0.5:
            notes.append(
                "high_beta SL/pnl not worse than large within thin tolerance — "
                "hypothesis 'vol is fine under shell+lifecycle' remains open (not proved)."
            )
        elif hb["sl_rate"] > large["sl_rate"] + 0.15:
            notes.append(
                "high_beta SL rate materially above large — class-conditional shadow "
                "(size/trail) may be worth staffing; live_apply still OFF."
            )
        else:
            notes.append("high_beta vs large mixed — keep collecting under same lifecycle.")
    if mid and large:
        notes.append(
            f"mid n={mid['n_rt']} sl={mid['sl_rate']:.0%} tp={mid['tp_rate']:.0%} "
            f"vs large n={large['n_rt']} sl={large['sl_rate']:.0%} tp={large['tp_rate']:.0%}."
        )
    if mega:
        notes.append(
            f"mega n={mega['n_rt']} mostly ballast/structure path — don't blend with tryout shells."
        )
    tax = sorted(usable, key=lambda c: float(c.get("process_tax_rate") or 0), reverse=True)
    if tax:
        top = tax[0]
        notes.append(
            f"Highest process-tax rate among usable classes: {top['key']} "
            f"({top['process_tax_rate']:.0%}, n={top['n_rt']})."
        )
    notes.append(
        "Opportunity window: if mid/high_beta match large on tax-adjusted win under $shell, "
        "widen doors by class evidence — not global fear caps."
    )
    return notes


def build_pair_lifecycle_by_class(
    *,
    lookback_days: Optional[float] = None,
    write: bool = True,
    ledger_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    cfg = load_class_config(config_path)
    lb = float(lookback_days if lookback_days is not None else cfg.get("lookback_days") or DEFAULT_LOOKBACK_DAYS)
    min_n = int(cfg.get("compare_min_n") or COMPARE_MIN_N)
    edge_n = int(cfg.get("edge_min_n") or EDGE_MIN_N)
    class_map = cfg.get("class_map") or DEFAULT_CLASS_MAP
    now = now or _utc_now()
    since = now - timedelta(days=lb)

    ledger = _read_jsonl(ledger_path or LEDGER_PATH)
    rts = build_lifecycle_rts(ledger, since=since, until=now, class_map=class_map)

    # optional vol annotation (best-effort, cached per pair)
    vol_cache: Dict[str, Tuple[Optional[float], str]] = {}
    for r in rts:
        p = str(r["pair"])
        cls = str(r.get("class") or "other")
        if p not in vol_cache:
            vol_cache[p] = realized_vol_bucket(p, class_name=cls)
        daily, vb = vol_cache[p]
        r["vol_daily"] = round(daily, 6) if daily is not None else None
        r["vol_bucket"] = vb or CLASS_IMPLIED_VOL.get(cls, "unknown")

    by_class = aggregate_group(rts, key="class", min_n=min_n)
    by_pair = aggregate_group(rts, key="pair", min_n=min_n)
    by_vol = aggregate_group(rts, key="vol_bucket", min_n=min_n)
    by_regime = aggregate_group(rts, key="regime_at_entry", min_n=min_n)

    # pair detail strip (top by |n|)
    pair_rows = sorted(by_pair, key=lambda x: -int(x.get("n_rt") or 0))[:40]
    for pr in pair_rows:
        p = pr["key"]
        pr["class"] = pair_class(p, class_map)
        daily, vb = vol_cache.get(p, (None, "unknown"))
        pr["vol_daily"] = round(daily, 6) if daily is not None else None
        pr["vol_bucket"] = vb

    n = len(rts)
    notes = _hypothesis_notes(by_class, min_n)
    claim_allowed = False  # board never claims edge
    plain = (
        f"lookback={lb:.0f}d n_rt={n} classes={len(by_class)} "
        f"compare_min_n={min_n} edge_claim=False. "
        + (notes[0] if notes else "")
    )

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "measure_only": True,
        "live_apply": False,
        "mutates_config": False,
        "places_orders": False,
        "lookback_days": lb,
        "window_start": since.isoformat(),
        "window_end": now.isoformat(),
        "compare_min_n": min_n,
        "edge_min_n": edge_n,
        "edge_claim_allowed": claim_allowed,
        "n_rt": n,
        "by_class": by_class,
        "by_vol_bucket": by_vol,
        "by_regime_at_entry": by_regime,
        "by_pair": pair_rows,
        "hypothesis_notes": notes,
        "plain_english": plain,
        "class_map_source": str(config_path or CONFIG_PATH),
        "docs": {
            "purpose": "Class×lifecycle compare to optimize thresholds later with N",
            "not": "auto-tune, promote, or live risk scalar",
        },
        "rts_sample": rts[-15:],  # tail only — full stays derivable
    }

    md = render_report(payload)
    payload["report_path"] = str(REPORT_PATH)
    payload["state_path"] = str(STATE_PATH)

    if write:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        REPORT_PATH.write_text(md, encoding="utf-8")
    return payload


def render_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Pair lifecycle by crypto class",
        "",
        f"_as_of {payload.get('as_of')} · lookback {payload.get('lookback_days')}d · "
        f"**measure-only** · edge_claim={payload.get('edge_claim_allowed')}_",
        "",
        f"**n_rt = {payload.get('n_rt')}** · compare_min_n={payload.get('compare_min_n')} · "
        f"edge_min_n={payload.get('edge_min_n')}",
        "",
        str(payload.get("plain_english") or ""),
        "",
        "## By class",
        "",
        "| class | n | win% | SL% | TP% | dual% | tax% | pnl_sum | pnl_mean | hold_h | claim |",
        "|-------|---|------|-----|-----|-------|------|---------|----------|--------|-------|",
    ]
    for c in payload.get("by_class") or []:
        lines.append(
            f"| {c.get('key')} | {c.get('n_rt')} | {100*float(c.get('win_rate') or 0):.0f}% | "
            f"{100*float(c.get('sl_rate') or 0):.0f}% | {100*float(c.get('tp_rate') or 0):.0f}% | "
            f"{100*float(c.get('dual_peak_rate') or 0):.0f}% | {100*float(c.get('process_tax_rate') or 0):.0f}% | "
            f"{c.get('pnl_sum')} | {c.get('pnl_mean')} | {c.get('hold_hours_mean')} | {c.get('claim_level')} |"
        )
    lines += ["", "## Hypothesis / opportunity notes", ""]
    for n in payload.get("hypothesis_notes") or []:
        lines.append(f"- {n}")
    lines += ["", "## Top pairs (by n)", ""]
    lines.append("| pair | class | n | win% | SL% | TP% | tax% | pnl_sum | claim |")
    lines.append("|------|-------|---|------|-----|-----|------|---------|-------|")
    for p in (payload.get("by_pair") or [])[:20]:
        lines.append(
            f"| {p.get('key')} | {p.get('class')} | {p.get('n_rt')} | "
            f"{100*float(p.get('win_rate') or 0):.0f}% | {100*float(p.get('sl_rate') or 0):.0f}% | "
            f"{100*float(p.get('tp_rate') or 0):.0f}% | {100*float(p.get('process_tax_rate') or 0):.0f}% | "
            f"{p.get('pnl_sum')} | {p.get('claim_level')} |"
        )
    lines += [
        "",
        "## Rules",
        "",
        "- No live knob writes from this board.",
        "- `thin_n` = describe coverage only.",
        "- `compare_ok` = class differences may inform **shadow** threshold design.",
        "- Edge language requires separate GO + N≥edge_min_n + offline honesty gates.",
        "",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "SCHEMA",
    "STATE_PATH",
    "REPORT_PATH",
    "pair_class",
    "build_pair_lifecycle_by_class",
    "build_lifecycle_rts",
    "aggregate_group",
    "load_class_config",
]
