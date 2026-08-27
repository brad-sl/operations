#!/usr/bin/env python3
"""
Structure break-of-structure (BOS) exit — shadow.

Encodes the chart read Brad described on LINK:
  uptrend (HH/HL) → healthy pullback holds → new high → hard turn →
  break last higher-low → keep falling.

Pure eval is timeframe-agnostic (pass 1h/6h candles). Live path is
**shadow only** — no orders. SL still owns hard downside.

Spec / MASTER: P6-STRUCTURE-BOS-EXIT-SHADOW-20260826
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = PROJECT_ROOT / "config" / "structure_bos_exit.json"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "structure_bos_exit_status.json"
EVENTS_PATH = PROJECT_ROOT / "data" / "state" / "structure_bos_exit_events.jsonl"
DEDUPE_PATH = PROJECT_ROOT / "data" / "state" / "structure_bos_exit_dedupe.json"
ENTRY_LOTS_PATH = PROJECT_ROOT / "data" / "state" / "entry_driver_lots.json"
LIVE_STATE_PATH = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"

UA = {"User-Agent": "phase6-structure-bos/1.0"}

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "mode": "shadow",  # shadow | off  (live sells forbidden in this module)
    "granularity_sec": 3600,  # 1h — Coinbase public (no 4h; 21600=6h alt)
    "candle_limit": 240,
    "swing_left": 2,
    "swing_right": 2,
    "arm_mfe_pct": 0.04,  # only arm after real run vs entry
    "confirm_closes": 1,  # closes below structure low to fire
    "min_position_usd": 25.0,
    "min_structure_low_gap_pct": 0.002,  # ignore micro swing noise vs entry
    "notify_telegram": False,
    "notify_dedupe_hours": 12.0,
    "ballast_pairs": ["PAXG-USD", "PAXG-USDC", "USDC-USD"],
    "note": "Shadow BOS: arm on MFE, exit when close breaks last higher-low after run.",
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_bos_config(path: Optional[Path] = None, overlay: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = json.loads(json.dumps(DEFAULTS))
    p = path or CFG_PATH
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out.update(raw)
        except Exception as e:
            logger.warning("structure_bos config load failed: %s", e)
    # optional trading_config nest
    if overlay and isinstance(overlay, dict):
        block = overlay.get("structure_bos_exit")
        if isinstance(block, dict):
            out.update(block)
    return out


def normalize_candles(raw: Sequence[Any]) -> List[Dict[str, float]]:
    """
    Accept Coinbase arrays [t, low, high, open, close, vol] or dicts with o/h/l/c/t.
    Return oldest→newest dicts.
    """
    rows: List[Dict[str, float]] = []
    for x in raw or []:
        if isinstance(x, dict):
            t = _f(x.get("t") or x.get("time") or x.get("start"), 0.0)
            o = _f(x.get("o") or x.get("open"), 0.0)
            h = _f(x.get("h") or x.get("high"), 0.0)
            l = _f(x.get("l") or x.get("low"), 0.0)
            c = _f(x.get("c") or x.get("close"), 0.0)
            v = _f(x.get("v") or x.get("volume"), 0.0)
        elif isinstance(x, (list, tuple)) and len(x) >= 5:
            # Coinbase: time, low, high, open, close, volume
            t = _f(x[0], 0.0)
            l = _f(x[1], 0.0)
            h = _f(x[2], 0.0)
            o = _f(x[3], 0.0)
            c = _f(x[4], 0.0)
            v = _f(x[5], 0.0) if len(x) > 5 else 0.0
        else:
            continue
        if t > 1e12:
            t = t / 1000.0
        if h <= 0 or l <= 0 or c <= 0:
            continue
        rows.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    rows.sort(key=lambda r: r["t"])
    return rows


def fetch_candles_public(
    pair: str,
    *,
    granularity_sec: int = 3600,
    limit: int = 240,
) -> List[Dict[str, float]]:
    """Coinbase Exchange public candles. Oldest→newest."""
    # API returns newest-first up to 300 bars; request without start for latest window
    url = (
        f"https://api.exchange.coinbase.com/products/{pair}/candles"
        f"?granularity={int(granularity_sec)}"
    )
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = normalize_candles(data)
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def is_swing_high(highs: Sequence[float], i: int, left: int, right: int) -> bool:
    if i < left or i + right >= len(highs):
        return False
    h = highs[i]
    window = highs[i - left : i + right + 1]
    return h >= max(window) - 1e-15 and all(
        (j == i) or highs[j] < h - 1e-15 for j in range(i - left, i + right + 1)
    ) or (
        h == max(window)
        and sum(1 for j in range(i - left, i + right + 1) if highs[j] == h) == 1
    )


def is_swing_low(lows: Sequence[float], i: int, left: int, right: int) -> bool:
    if i < left or i + right >= len(lows):
        return False
    lo = lows[i]
    window = lows[i - left : i + right + 1]
    return lo == min(window) and sum(1 for j in range(i - left, i + right + 1) if lows[j] == lo) >= 1


def find_swing_indices(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
) -> Tuple[List[int], List[int]]:
    sh: List[int] = []
    sl: List[int] = []
    n = min(len(highs), len(lows))
    for i in range(left, n - right):
        # fractal: strict local extremum
        h = highs[i]
        if h >= max(highs[i - left : i]) and h > max(highs[i + 1 : i + right + 1]):
            sh.append(i)
        lo = lows[i]
        if lo <= min(lows[i - left : i]) and lo < min(lows[i + 1 : i + right + 1]):
            sl.append(i)
    return sh, sl


@dataclass
class StructureBosResult:
    pair: str = ""
    fired: bool = False
    kind: str = ""  # structure_bos | none | peak_fail_warn
    armed: bool = False
    entry_price: float = 0.0
    exit_price: float = 0.0
    exit_idx: int = -1
    exit_ts: float = 0.0
    peak_price: float = 0.0
    mfe_pct: float = 0.0
    structure_low: float = 0.0
    last_swing_high: float = 0.0
    giveback_from_peak_pct: float = 0.0
    ret_vs_entry_pct: float = 0.0
    reasons: List[str] = field(default_factory=list)
    mode: str = "shadow"
    shadow: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def walk_long_structure_bos(
    candles: Sequence[Dict[str, float]],
    *,
    entry_price: float,
    entry_idx: int = 0,
    pair: str = "",
    swing_left: int = 2,
    swing_right: int = 2,
    arm_mfe_pct: float = 0.04,
    confirm_closes: int = 1,
    min_structure_low_gap_pct: float = 0.002,
) -> StructureBosResult:
    """
    Walk bars after entry; arm on MFE; track last swing high / higher-low;
    fire when `confirm_closes` closes print below structure_low.
    """
    out = StructureBosResult(pair=pair, entry_price=entry_price, peak_price=entry_price)
    rows = list(candles)
    n = len(rows)
    if n < swing_left + swing_right + 3 or entry_price <= 0:
        out.reasons.append("insufficient_bars_or_entry")
        return out
    entry_idx = max(0, min(entry_idx, n - 1))

    highs = [r["h"] for r in rows]
    lows = [r["l"] for r in rows]
    closes = [r["c"] for r in rows]

    peak = entry_price
    armed = False
    last_sh = 0.0
    structure_low = 0.0
    saw_high_since_sl = False
    below_count = 0
    confirm_closes = max(1, int(confirm_closes))

    # First bar we can confirm a swing ending at j = i - right
    start_i = max(entry_idx + swing_right + 1, swing_left + swing_right)

    for i in range(start_i, n):
        j = i - swing_right  # candidate swing center fully confirmed
        c = closes[i]
        peak = max(peak, highs[i], c)
        mfe = (peak / entry_price) - 1.0
        if mfe >= arm_mfe_pct - 1e-12:
            armed = True

        # Confirm swing high at j
        if j >= swing_left and j + swing_right < n:
            h = highs[j]
            left_max = max(highs[j - swing_left : j]) if swing_left else h
            right_max = max(highs[j + 1 : j + swing_right + 1])
            if h >= left_max - 1e-15 and h > right_max:
                last_sh = h
                saw_high_since_sl = True
                out.last_swing_high = h

            lo = lows[j]
            left_min = min(lows[j - swing_left : j]) if swing_left else lo
            right_min = min(lows[j + 1 : j + swing_right + 1])
            if lo <= left_min + 1e-15 and lo < right_min:
                # Swing low: becomes structure floor after a high in the armed run
                # (or first pullback low once armed)
                if armed and (saw_high_since_sl or structure_low <= 0):
                    # require structure low not glued to entry noise
                    if lo >= entry_price * (1.0 - min_structure_low_gap_pct) or mfe >= arm_mfe_pct:
                        structure_low = lo
                        saw_high_since_sl = False
                        out.structure_low = lo

        out.armed = armed
        out.peak_price = peak
        out.mfe_pct = round((peak / entry_price) - 1.0, 6)

        if not armed or structure_low <= 0:
            below_count = 0
            continue

        if c < structure_low - 1e-12:
            below_count += 1
        else:
            below_count = 0

        if below_count >= confirm_closes:
            out.fired = True
            out.kind = "structure_bos"
            out.exit_price = c
            out.exit_idx = i
            out.exit_ts = rows[i]["t"]
            out.giveback_from_peak_pct = round((peak - c) / peak, 6) if peak > 0 else 0.0
            out.ret_vs_entry_pct = round((c / entry_price) - 1.0, 6)
            out.reasons = [
                f"arm_mfe>={arm_mfe_pct}",
                f"structure_low={structure_low:.6g}",
                f"close={c:.6g}",
                f"confirm={confirm_closes}",
                f"mfe={out.mfe_pct:.4f}",
                f"giveback={out.giveback_from_peak_pct:.4f}",
            ]
            return out

    out.kind = "none"
    out.reasons.append("no_bos_through_end")
    if armed:
        out.reasons.append("armed_held")
    return out


def evaluate_position_bos(
    *,
    pair: str,
    candles: Sequence[Any],
    entry_price: float,
    entry_ts: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> StructureBosResult:
    """Evaluate BOS for one open long using candles ending at 'now'."""
    c = cfg or DEFAULTS
    rows = normalize_candles(candles)
    if not rows or entry_price <= 0:
        return StructureBosResult(pair=pair, reasons=["no_candles_or_entry"])

    entry_idx = 0
    if entry_ts and entry_ts > 0:
        et = entry_ts / 1000.0 if entry_ts > 1e12 else entry_ts
        for i, r in enumerate(rows):
            if r["t"] >= et - 1e-6:
                entry_idx = i
                break
        else:
            entry_idx = 0

    return walk_long_structure_bos(
        rows,
        entry_price=entry_price,
        entry_idx=entry_idx,
        pair=pair,
        swing_left=int(c.get("swing_left") or 2),
        swing_right=int(c.get("swing_right") or 2),
        arm_mfe_pct=_f(c.get("arm_mfe_pct"), 0.04),
        confirm_closes=int(c.get("confirm_closes") or 1),
        min_structure_low_gap_pct=_f(c.get("min_structure_low_gap_pct"), 0.002),
    )


def _load_lots() -> List[Dict[str, Any]]:
    if not ENTRY_LOTS_PATH.exists():
        return []
    try:
        d = json.loads(ENTRY_LOTS_PATH.read_text())
        return [x for x in (d.get("lots") or []) if isinstance(x, dict)]
    except Exception:
        return []


def _positions_from_live() -> List[Dict[str, Any]]:
    if not LIVE_STATE_PATH.exists():
        return []
    try:
        live = json.loads(LIVE_STATE_PATH.read_text())
        return [r for r in (live.get("positions") or []) if isinstance(r, dict)]
    except Exception:
        return []


def run_structure_bos_shadow_cycle(
    *,
    config_dict: Optional[Dict[str, Any]] = None,
    candles_by_pair: Optional[Dict[str, Sequence[Any]]] = None,
    notify: bool = False,
) -> Dict[str, Any]:
    """
    Shadow cycle: evaluate open bags; append would-fire events; write status.
    Never places orders.
    """
    cfg = load_bos_config(overlay=config_dict)
    out: Dict[str, Any] = {
        "ts": _utcnow(),
        "mode": str(cfg.get("mode") or "shadow"),
        "enabled": bool(cfg.get("enabled", True)),
        "would_fire": [],
        "armed_held": [],
        "skipped": [],
        "n_pairs": 0,
    }
    mode = str(cfg.get("mode") or "shadow").lower()
    if not cfg.get("enabled", True) or mode in ("off", "disabled", "false", "0"):
        out["note"] = "structure_bos disabled"
        _write_state(out)
        return out
    if mode == "live":
        # Hard block — this module never sells
        out["note"] = "mode=live ignored; structure_bos is shadow-only (no sells)"
        mode = "shadow"
        out["mode"] = "shadow"

    ballast = {str(x) for x in (cfg.get("ballast_pairs") or [])}
    min_usd = _f(cfg.get("min_position_usd"), 25.0)
    gran = int(cfg.get("granularity_sec") or 3600)
    limit = int(cfg.get("candle_limit") or 240)

    lots_by_pair: Dict[str, Dict[str, Any]] = {}
    for lot in _load_lots():
        if not lot.get("open", True):
            continue
        p = str(lot.get("pair") or "")
        if p and p not in lots_by_pair:
            lots_by_pair[p] = lot

    positions = _positions_from_live()
    pairs_done = set()
    for row in positions:
        pair = str(row.get("pair") or "")
        if not pair or pair in ballast or pair in pairs_done:
            continue
        usd = _f(row.get("value_usd"), 0.0)
        if usd < min_usd:
            out["skipped"].append({"pair": pair, "reason": "min_usd"})
            continue
        entry = _f(row.get("entry_price"), 0.0)
        entry_ts = None
        lot = lots_by_pair.get(pair)
        if lot:
            entry = _f(lot.get("entry_price"), entry) or entry
            # lot ts iso
            ts_s = lot.get("ts") or lot.get("opened_at")
            if isinstance(ts_s, str) and ts_s:
                try:
                    entry_ts = datetime.fromisoformat(ts_s.replace("Z", "+00:00")).timestamp()
                except Exception:
                    entry_ts = None
        if entry <= 0:
            out["skipped"].append({"pair": pair, "reason": "no_entry"})
            continue

        pairs_done.add(pair)
        out["n_pairs"] += 1
        try:
            if candles_by_pair and pair in candles_by_pair:
                candles = candles_by_pair[pair]
            else:
                candles = fetch_candles_public(pair, granularity_sec=gran, limit=limit)
            res = evaluate_position_bos(
                pair=pair,
                candles=candles,
                entry_price=entry,
                entry_ts=entry_ts,
                cfg=cfg,
            )
            res.mode = "shadow"
            res.shadow = True
            d = res.as_dict()
            d["position_usd"] = usd
            d["mark"] = _f(row.get("current_price"), 0.0)
            if res.fired:
                out["would_fire"].append(d)
                _append_event(d)
            elif res.armed:
                out["armed_held"].append(
                    {
                        "pair": pair,
                        "mfe_pct": res.mfe_pct,
                        "structure_low": res.structure_low,
                        "peak_price": res.peak_price,
                    }
                )
        except Exception as e:
            out["skipped"].append({"pair": pair, "reason": f"err:{e}"})
            logger.warning("structure_bos %s: %s", pair, e)

    out["plain_english"] = _plain(out)
    _write_state(out)
    if notify and cfg.get("notify_telegram") and out["would_fire"]:
        _notify(out["would_fire"], _f(cfg.get("notify_dedupe_hours"), 12.0))
    return out


def apply_structure_bos_from_runner(runner: Any = None) -> Dict[str, Any]:
    """Hook for phase6_runner — shadow only."""
    cfg_overlay = None
    try:
        if runner is not None and getattr(runner, "config", None):
            cfg_overlay = runner.config if isinstance(runner.config, dict) else None
    except Exception:
        cfg_overlay = None
    if cfg_overlay is None:
        try:
            cfg_overlay = json.loads(
                (PROJECT_ROOT / "config" / "trading_config_phase6.json").read_text()
            )
        except Exception:
            cfg_overlay = {}
    return run_structure_bos_shadow_cycle(config_dict=cfg_overlay, notify=False)


def _plain(out: Dict[str, Any]) -> str:
    wf = out.get("would_fire") or []
    ah = out.get("armed_held") or []
    if wf:
        pairs = ", ".join(f"{x.get('pair')} ret={100*_f(x.get('ret_vs_entry_pct')):.1f}%" for x in wf[:4])
        return f"Structure BOS would-fire: {pairs} (shadow — no sell)."
    if ah:
        return f"Structure BOS armed/held on {len(ah)} pair(s); no break of last HL yet."
    return "Structure BOS: no armed runs or would-fire."


def _write_state(out: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(out, indent=2, default=str))
    except Exception as e:
        logger.debug("structure_bos state write: %s", e)


def _append_event(d: Dict[str, Any]) -> None:
    try:
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = dict(d)
        row["ts"] = row.get("ts") or _utcnow()
        with EVENTS_PATH.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def _notify(rows: List[Dict[str, Any]], dedupe_hours: float) -> None:
    try:
        dedupe = {}
        if DEDUPE_PATH.exists():
            dedupe = json.loads(DEDUPE_PATH.read_text())
        now = datetime.now(timezone.utc)
        fresh = []
        for r in rows:
            key = f"{r.get('pair')}|structure_bos"
            last = dedupe.get(key)
            if last:
                try:
                    prev = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if (now - prev).total_seconds() < dedupe_hours * 3600:
                        continue
                except Exception:
                    pass
            dedupe[key] = now.isoformat()
            fresh.append(r)
        DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEDUPE_PATH.write_text(json.dumps(dedupe, indent=2))
        if not fresh:
            return
        # best-effort TG via existing helper if present
        try:
            from phase6.core.telegram_notify import send_telegram_message  # type: ignore

            lines = ["Structure BOS would-fire (shadow):"]
            for r in fresh[:5]:
                lines.append(
                    f"- {r.get('pair')} exit≈{r.get('exit_price')} "
                    f"ret={100*_f(r.get('ret_vs_entry_pct')):.1f}% "
                    f"mfe={100*_f(r.get('mfe_pct')):.1f}%"
                )
            send_telegram_message("\n".join(lines))
        except Exception:
            logger.info("structure_bos would-fire: %s", fresh)
    except Exception as e:
        logger.debug("structure_bos notify: %s", e)


# --- Offline CF helpers (real OHLCV walk) ---

def simulate_entry_to_bos(
    candles: Sequence[Dict[str, float]],
    entry_idx: int,
    entry_price: float,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One entry → walk to BOS or end; also compute peak and naive trail/SL refs."""
    c = cfg or DEFAULTS
    rows = normalize_candles(candles)
    bos = walk_long_structure_bos(
        rows,
        entry_price=entry_price,
        entry_idx=entry_idx,
        swing_left=int(c.get("swing_left") or 2),
        swing_right=int(c.get("swing_right") or 2),
        arm_mfe_pct=_f(c.get("arm_mfe_pct"), 0.04),
        confirm_closes=int(c.get("confirm_closes") or 1),
        min_structure_low_gap_pct=_f(c.get("min_structure_low_gap_pct"), 0.002),
    )
    # path stats through end or bos
    end_i = bos.exit_idx if bos.fired else len(rows) - 1
    end_i = max(entry_idx, min(end_i, len(rows) - 1))
    peak = entry_price
    sl_hit = False
    sl_px = entry_price * (1.0 - 0.03)
    trail_arm = 0.04
    trail_give = 0.02
    trail_exit = None
    peak_for_trail = entry_price
    trail_armed = False
    for i in range(entry_idx, end_i + 1):
        h, l, cl = rows[i]["h"], rows[i]["l"], rows[i]["c"]
        peak = max(peak, h)
        peak_for_trail = max(peak_for_trail, h)
        if (peak_for_trail / entry_price - 1.0) >= trail_arm:
            trail_armed = True
        if trail_armed and cl <= peak_for_trail * (1.0 - trail_give):
            if trail_exit is None:
                trail_exit = cl
        if l <= sl_px and not sl_hit:
            sl_hit = True
            sl_exit = sl_px
    hold_end = rows[end_i]["c"] if bos.fired else rows[-1]["c"]
    # if BOS didn't fire, hold to last bar
    if not bos.fired:
        hold_end = rows[-1]["c"]
        peak = max(peak, max(r["h"] for r in rows[entry_idx:]))

    bos_ret = (bos.exit_price / entry_price - 1.0) if bos.fired else (hold_end / entry_price - 1.0)
    return {
        "bos": bos.as_dict(),
        "bos_fired": bos.fired,
        "bos_ret": bos_ret,
        "mfe": peak / entry_price - 1.0,
        "hold_to_path_end_ret": hold_end / entry_price - 1.0,
        "sl_3pct_ret": (sl_px / entry_price - 1.0) if sl_hit else None,
        "trail_4_2_ret": (trail_exit / entry_price - 1.0) if trail_exit else None,
        "entry_idx": entry_idx,
        "entry_price": entry_price,
    }


def find_run_entries(
    candles: Sequence[Dict[str, float]],
    *,
    arm_mfe_pct: float = 0.04,
    lookback_trough: int = 24,
    cooldown_bars: int = 12,
) -> List[Tuple[int, float]]:
    """
    Heuristic run starts: local trough then forward MFE hits arm within window.
    Returns list of (entry_idx, entry_price=close at trough).
    """
    rows = list(candles)
    n = len(rows)
    out: List[Tuple[int, float]] = []
    i = lookback_trough
    last_entry = -cooldown_bars
    while i < n - 10:
        window = rows[i - lookback_trough : i + 1]
        trough_i = min(range(i - lookback_trough, i + 1), key=lambda k: rows[k]["l"])
        if trough_i != i and rows[i]["l"] > rows[trough_i]["l"]:
            i += 1
            continue
        # trough near i
        entry_i = trough_i
        if entry_i - last_entry < cooldown_bars:
            i += 1
            continue
        ep = rows[entry_i]["c"]
        # look ahead for arm
        peak = ep
        armed_at = None
        for j in range(entry_i + 1, min(n, entry_i + 120)):
            peak = max(peak, rows[j]["h"])
            if peak / ep - 1.0 >= arm_mfe_pct:
                armed_at = j
                break
        if armed_at is not None:
            out.append((entry_i, ep))
            last_entry = entry_i
            i = armed_at + cooldown_bars
        else:
            i += 1
    return out
