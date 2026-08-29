"""Phase-2 stabilize scoreboard (no LLM).

Used by the twice-daily decision brief and ad-hoc ops checks.
Bars match recovery_path_soft_down Phase 2 exit criteria.
"""
from __future__ import annotations

import json
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "phase2_stabilize_check_v1"
LATEST_PATH = PROJECT_ROOT / "data/state/phase2_stabilize_check_latest.json"
RECOVERY_PATH = PROJECT_ROOT / "data/state/recovery_path_soft_down_20260828.json"
TREND_PATH = PROJECT_ROOT / "data/state/trend_repair_status.json"
RCP_PATH = PROJECT_ROOT / "phase6/core/regime_cash_policy.py"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
PERF_URL = "http://127.0.0.1:8502/api/performance?deposit_adjusted=true"

BLOCK_PAIRS = ("UNI-USD", "RAVE-USD")
TP_OR_ROTATION_HINTS = (
    "take_profit",
    "fixed_tp",
    "trail",
    "rotation",
    "lifecycle",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _fetch_perf_tiles(timeout_s: float = 4.0) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {"d1": None, "d7": None, "d14": None, "d30": None}
    try:
        with urllib.request.urlopen(PERF_URL, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    # Live dash shape: top-level today/h24/d7/d14/d30 floats
    flat_map = {
        "d1": ("today", "h24", "d1", "1d", "1D"),
        "d7": ("d7", "7d", "7D"),
        "d14": ("d14", "14d", "14D"),
        "d30": ("d30", "30d", "30D"),
    }
    for dest, aliases in flat_map.items():
        for a in aliases:
            if data.get(a) is None:
                continue
            try:
                out[dest] = float(data[a])
                break
            except (TypeError, ValueError):
                pass
    windows = data.get("windows") or data.get("periods")
    if not isinstance(windows, dict):
        return out
    nested_map = {
        "d1": ("1d", "1D", "24h", "d1", "day_1"),
        "d7": ("7d", "7D", "d7", "week"),
        "d14": ("14d", "14D", "d14"),
        "d30": ("30d", "30D", "d30", "month"),
    }
    for dest, aliases in nested_map.items():
        if out.get(dest) is not None:
            continue
        for a in aliases:
            node = windows.get(a)
            if isinstance(node, (int, float)):
                out[dest] = float(node)
                break
            if isinstance(node, dict):
                for k in (
                    "return_pct",
                    "deposit_adjusted_return_pct",
                    "pct",
                    "value",
                ):
                    if node.get(k) is not None:
                        try:
                            out[dest] = float(node[k])
                            break
                        except (TypeError, ValueError):
                            pass
                if out[dest] is not None:
                    break
    return out


def _tiles_from_trend(trend: Dict[str, Any]) -> Dict[str, Any]:
    eq = trend.get("equity_trend") or {}
    health = eq.get("health") or {}
    if isinstance(health, dict):
        health_s = str(health.get("state") or health.get("label") or "n/a")
        slope = health.get("slope_pct_per_day")
    else:
        health_s = str(health or "n/a")
        slope = None
    tr = eq.get("trend") or {}
    if slope is None:
        slope = tr.get("slope_pct_per_day") or tr.get("slope_index_per_day")
    try:
        slope_f = float(slope) if slope is not None else None
    except (TypeError, ValueError):
        slope_f = None
    d30 = None
    wr = eq.get("window_return_pct")
    if wr is not None:
        try:
            d30 = float(wr)
        except (TypeError, ValueError):
            d30 = None
    d7 = None
    rr = eq.get("recent_return_pct")
    if rr is not None:
        try:
            d7 = float(rr)
        except (TypeError, ValueError):
            d7 = None
    return {
        "d7": d7,
        "d14": None,  # prefer live perf API
        "d30": d30,
        "slope": slope_f,
        "health": health_s.replace(" ", "_").lower() if health_s else "n/a",
    }


def _recovery_go_at(recovery: Dict[str, Any]) -> datetime:
    for k in ("brad_go_at", "go_at", "as_of", "created_at"):
        dt = _parse_ts(recovery.get(k))
        if dt:
            return dt
    # filename epoch fallback: 20260828T183930Z style in nested fields
    for v in recovery.values():
        if isinstance(v, str) and "20260828" in v:
            dt = _parse_ts(v)
            if dt:
                return dt
    return datetime(2026, 8, 28, 18, 39, 30, tzinfo=timezone.utc)


def _ledger_rows(since: datetime) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not LEDGER_PATH.exists():
        return rows
    try:
        with LEDGER_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_ts(r.get("timestamp") or r.get("ts") or r.get("time"))
                if ts is None or ts < since:
                    continue
                rows.append(r)
    except Exception:
        return rows
    return rows


def _is_buy(r: Dict[str, Any]) -> bool:
    side = str(r.get("side") or r.get("action") or r.get("type") or "").lower()
    return side in ("buy", "b") or str(r.get("event") or "").lower() == "buy"


def _is_sell(r: Dict[str, Any]) -> bool:
    side = str(r.get("side") or r.get("action") or r.get("type") or "").lower()
    return side in ("sell", "s") or str(r.get("event") or "").lower() == "sell"


def _pnl(r: Dict[str, Any]) -> float:
    for k in ("pnl", "realized_pnl_usd", "pnl_usd", "realized_pnl"):
        if r.get(k) is not None:
            try:
                return float(r[k])
            except (TypeError, ValueError):
                pass
    return 0.0


def _reason(r: Dict[str, Any]) -> str:
    return str(
        r.get("exit_reason")
        or r.get("reason")
        or r.get("sell_reason")
        or r.get("tag")
        or ""
    )


def _row_ts(r: Dict[str, Any]) -> Optional[datetime]:
    return _parse_ts(r.get("timestamp") or r.get("ts") or r.get("time"))


def _code_wire_ok() -> bool:
    try:
        text = RCP_PATH.read_text()
    except Exception:
        return False
    return (
        "BUY_BLOCK_PAIRS_RECOVERY_SOFT_DOWN_20260828" in text
        or "collect_buy_block_pairs" in text
    ) and "evaluate_buy_entry" in text


def compute_phase2_check(*, persist: bool = True) -> Dict[str, Any]:
    recovery = _load_json(RECOVERY_PATH)
    trend = _load_json(TREND_PATH)
    tiles = _tiles_from_trend(trend)
    perf = _fetch_perf_tiles()
    for k in ("d1", "d7", "d14", "d30"):
        if perf.get(k) is not None:
            tiles[k] = perf[k]

    go_at = _recovery_go_at(recovery)
    since_7d = _utc_now() - timedelta(days=7)
    # ledger scan: from min(go_at - 1d, 7d) for TP; go_at for reopen
    ledger_since = min(go_at - timedelta(days=1), since_7d)
    rows = _ledger_rows(ledger_since)

    uni_rave_buys: List[Dict[str, Any]] = []
    sells_7d: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "sum": 0.0, "w": 0, "l": 0}
    )
    tp_green = 0
    for r in rows:
        ts = _row_ts(r)
        pair = _norm_pair(str(r.get("pair") or r.get("symbol") or ""))
        if _is_buy(r) and ts and ts >= go_at and pair in BLOCK_PAIRS:
            uni_rave_buys.append(
                {
                    "ts": ts.isoformat(),
                    "pair": pair,
                    "reason": _reason(r)[:80],
                }
            )
        if not _is_sell(r) or ts is None or ts < since_7d:
            continue
        reason = _reason(r) or "unknown"
        key = reason[:64] if reason else "unknown"
        pnl = _pnl(r)
        bucket = sells_7d[key]
        bucket["n"] += 1
        bucket["sum"] += pnl
        if pnl > 0:
            bucket["w"] += 1
        elif pnl < 0:
            bucket["l"] += 1
        low = reason.lower()
        if pnl > 0 and any(h in low for h in TP_OR_ROTATION_HINTS):
            tp_green += 1

    d14 = tiles.get("d14")
    slope = tiles.get("slope")
    bars = {
        "14D >= -2%": bool(d14 is not None and float(d14) >= -2.0),
        "slope >= -0.03/d": bool(slope is not None and float(slope) >= -0.03),
        ">=1 clean TP/rotation green in last 7d": tp_green >= 1,
        "no UNI/RAVE reopen since Phase1": len(uni_rave_buys) == 0,
        "code wire PASS": _code_wire_ok(),
    }
    ready = all(bars.values())
    out = {
        "schema": SCHEMA,
        "as_of": _utc_now().isoformat(),
        "tiles": {
            "d1": tiles.get("d1"),
            "d7": tiles.get("d7"),
            "d14": tiles.get("d14"),
            "d30": tiles.get("d30"),
            "slope": tiles.get("slope"),
            "health": tiles.get("health"),
        },
        "bars": bars,
        "phase2_ready": ready,
        "uni_rave_buys_since_go": uni_rave_buys,
        "tp_or_rotation_green_7d": tp_green,
        "sells_7d_by_reason": dict(sells_7d),
        "recovery_go_at": go_at.isoformat(),
        "verdict": (
            "GO phase2 exit bar met — Phase3 still needs Brad"
            if ready
            else "NO-GO phase2 exit bar not met"
        ),
    }
    if persist:
        try:
            LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            LATEST_PATH.write_text(json.dumps(out, indent=2) + "\n")
        except Exception:
            pass
    return out


def format_phase2_section(check: Optional[Dict[str, Any]] = None) -> str:
    """Compact plain-English block for Telegram daily brief."""
    c = check or _load_json(LATEST_PATH)
    if not c:
        return (
            "=== Phase 2 stabilize ===\n"
            "• Scoreboard unavailable this cycle."
        )
    tiles = c.get("tiles") or {}
    bars = c.get("bars") or {}
    ready = bool(c.get("phase2_ready"))
    verdict = "GO" if ready else "NO-GO"
    lines = [
        "=== Phase 2 stabilize ===",
        f"Exit bar: {verdict} — {c.get('verdict') or ('ready' if ready else 'not ready')}",
    ]
    d7, d14, d30 = tiles.get("d7"), tiles.get("d14"), tiles.get("d30")
    slope = tiles.get("slope")
    health = str(tiles.get("health") or "?").replace("_", " ")
    tile_bits = [f"health {health}"]
    if d7 is not None:
        tile_bits.append(f"7D {float(d7):+.1f}%")
    if d14 is not None:
        tile_bits.append(f"14D {float(d14):+.1f}%")
    if d30 is not None:
        tile_bits.append(f"30D {float(d30):+.1f}%")
    if slope is not None:
        tile_bits.append(f"slope {float(slope):+.3f}/d")
    lines.append("· " + " · ".join(tile_bits))

    short_labels = {
        "14D >= -2%": "14D≥−2%",
        "slope >= -0.03/d": "slope≥−0.03",
        ">=1 clean TP/rotation green in last 7d": "≥1 TP/rot green 7d",
        "no UNI/RAVE reopen since Phase1": "no UNI/RAVE reopen",
        "code wire PASS": "buy-block wire",
    }
    passed = [str(short_labels.get(k, k)) for k, v in bars.items() if v]
    failed = [str(short_labels.get(k, k)) for k, v in bars.items() if not v]
    if failed:
        lines.append("• Still short: " + ", ".join(failed))
    if passed:
        lines.append("• Holding: " + ", ".join(passed))
    if ready:
        lines.append("• Next: Brad call only — no auto Phase 3 / reopen alts.")
    else:
        lines.append(
            "• Posture: stay Phase 1–2 gates; leave book; no Phase 3 earn/scale."
        )
    return "\n".join(lines)


def main() -> int:
    c = compute_phase2_check(persist=True)
    print(format_phase2_section(c))
    print()
    print(json.dumps({"phase2_ready": c["phase2_ready"], "tiles": c["tiles"], "bars": c["bars"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
