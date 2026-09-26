#!/usr/bin/env python3
"""
BTC-regime preferred-arm switcher for basket swap shadow arms.

Maps trailing BTC 7d return → paper-primary arm between:
  - rel_btc_stable  (btc_up / btc_chop)
  - risk_adj_mom    (btc_down)

Modes
-----
shadow      Compute + log; optional apply updates preferred_arm only.
production  Same preferred_arm selector path used by serious_consider / L2
            attention. NEVER enables live_membership_swaps.

Honesty
-------
- L1 CF excess is ADD vs REMOVE — not live book PnL.
- preferred_arm = operator attention / paper-primary only.
- live_membership_swaps stays false unless Brad edits decision file by hand
  for a *specific* swap (this module always forces false on apply).
- dual_agree remains collect-only; not touched here.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT

STATE_DIR = PROJECT_ROOT / "data" / "state"
OHLCV_DIR = PROJECT_ROOT / "data" / "ohlcv"
BRAD_DECISION_JSON = STATE_DIR / "basket_swap_brad_decision.json"
SWITCH_LATEST = STATE_DIR / "regime_arm_switch_latest.json"
SWITCH_JSONL = STATE_DIR / "regime_arm_switch_crumbs.jsonl"
BTC_CACHE = OHLCV_DIR / "BTC-USD_1d_coinbase.json"
REPORT_MD = PROJECT_ROOT / "reports" / "REGIME_ARM_SWITCH_LATEST.md"

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-regime-arm-switch/1.0"}

ARM_UP_CHOP = "rel_btc_stable"
ARM_DOWN = "risk_adj_mom"
VALID_ARMS = (ARM_UP_CHOP, ARM_DOWN)

# Dig defaults (2026-09-12 external BTC join): up/chop → rel, down → ram
ENTER_UP_PCT = 2.0
ENTER_DOWN_PCT = -2.0
# Hysteresis exits (leave regime only after reclaiming deadband)
EXIT_UP_PCT = 0.5
EXIT_DOWN_PCT = -0.5
MIN_DWELL_HOURS = 24.0
LOOKBACK_DAYS = 7


@dataclass
class RegimeSnapshot:
    as_of: str
    btc_ret_7d_pct: Optional[float]
    raw_tape: str  # btc_up | btc_down | btc_chop | unknown
    sticky_tape: str
    preferred_arm: str
    previous_preferred_arm: Optional[str]
    flipped: bool
    dwell_blocked: bool
    reason: str
    close: Optional[float] = None
    close_day: Optional[str] = None
    map: Dict[str, str] = field(
        default_factory=lambda: {
            "btc_up": ARM_UP_CHOP,
            "btc_chop": ARM_UP_CHOP,
            "btc_down": ARM_DOWN,
            "unknown": ARM_UP_CHOP,
        }
    )
    thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "enter_up_pct": ENTER_UP_PCT,
            "enter_down_pct": ENTER_DOWN_PCT,
            "exit_up_pct": EXIT_UP_PCT,
            "exit_down_pct": EXIT_DOWN_PCT,
            "min_dwell_hours": MIN_DWELL_HOURS,
            "lookback_days": float(LOOKBACK_DAYS),
        }
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        if v > 1e12:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def fetch_btc_daily(
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    cache_path: Path = BTC_CACHE,
    use_network: bool = True,
    min_days: int = 40,
) -> List[Dict[str, Any]]:
    """
    Daily BTC-USD OHLCV — D4: marketdata.db first, then network+cache fallback.
    Live climate must not depend on stale JSON alone.
    """
    # Prefer marketdata SSOT (thin D3/D4)
    try:
        from phase6.core.marketdata_store import get_daily_candles

        md = get_daily_candles("BTC-USD", limit=max(min_days + 20, 90))
        if len(md) >= min_days:
            # drop run_phase keys; keep arm-switch shape
            out = []
            for c in md:
                out.append(
                    {
                        "time": c.get("time"),
                        "open": c.get("open"),
                        "high": c.get("high"),
                        "low": c.get("low"),
                        "close": c.get("close"),
                        "volume": c.get("volume"),
                    }
                )
            return out
    except Exception:
        pass

    end = end or _utc_now()
    start = start or (end - timedelta(days=max(min_days, 45)))
    candles: List[Dict[str, Any]] = []

    if use_network:
        try:
            # Coinbase caps ~300 candles/request; one shot is enough for ~40–90d
            params = {
                "granularity": 86400,
                "start": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            r = requests.get(
                f"{PUBLIC}/products/BTC-USD/candles",
                params=params,
                headers=UA,
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json()
            # [time, low, high, open, close, volume] newest first
            rows = []
            for c in raw or []:
                if not isinstance(c, (list, tuple)) or len(c) < 5:
                    continue
                ts = _parse_ts(c[0])
                cl = _num(c[4])
                if ts is None or cl is None:
                    continue
                rows.append(
                    {
                        "time": _iso(ts).replace("+00:00", "Z"),
                        "open": _num(c[3]),
                        "high": _num(c[2]),
                        "low": _num(c[1]),
                        "close": cl,
                        "volume": _num(c[5]) if len(c) > 5 else None,
                    }
                )
            rows.sort(key=lambda x: x["time"])
            if rows:
                candles = rows
                _write_json_list(cache_path, candles)
        except Exception:
            candles = []

    if not candles and cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text())
            if isinstance(raw, list):
                candles = [c for c in raw if isinstance(c, dict)]
        except Exception:
            candles = []
    return candles


def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, default=str) + "\n")


def closes_by_day(candles: Sequence[Dict[str, Any]]) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for c in candles:
        ts = _parse_ts(c.get("time") or c.get("ts") or c.get("date"))
        cl = _num(c.get("close") or c.get("c"))
        if ts is None or cl is None:
            continue
        out.append((ts.astimezone(timezone.utc).date().isoformat(), cl))
    out.sort(key=lambda x: x[0])
    # last close wins per day
    merged: Dict[str, float] = {}
    for d, cl in out:
        merged[d] = cl
    return sorted(merged.items(), key=lambda x: x[0])


def btc_ret_nd(
    day_closes: Sequence[Tuple[str, float]],
    *,
    n: int = LOOKBACK_DAYS,
    as_of_day: Optional[str] = None,
) -> Tuple[Optional[float], Optional[str], Optional[float]]:
    """Return (ret_pct, close_day, close) for n-day lookback ending as_of_day or last."""
    if len(day_closes) <= n:
        return None, None, None
    if as_of_day:
        # find index of as_of_day or last day <= as_of_day
        idx = None
        for i, (d, _) in enumerate(day_closes):
            if d <= as_of_day:
                idx = i
            else:
                break
        if idx is None or idx < n:
            return None, None, None
    else:
        idx = len(day_closes) - 1
    day, cl = day_closes[idx]
    prev_day, prev_cl = day_closes[idx - n]
    if prev_cl <= 0:
        return None, day, cl
    ret = (cl / prev_cl - 1.0) * 100.0
    return ret, day, cl


def classify_raw_tape(
    ret_7d: Optional[float],
    *,
    enter_up: float = ENTER_UP_PCT,
    enter_down: float = ENTER_DOWN_PCT,
) -> str:
    if ret_7d is None:
        return "unknown"
    if ret_7d >= enter_up:
        return "btc_up"
    if ret_7d <= enter_down:
        return "btc_down"
    return "btc_chop"


def apply_hysteresis(
    raw_tape: str,
    prev_sticky: Optional[str],
    ret_7d: Optional[float],
    *,
    exit_up: float = EXIT_UP_PCT,
    exit_down: float = EXIT_DOWN_PCT,
    enter_up: float = ENTER_UP_PCT,
    enter_down: float = ENTER_DOWN_PCT,
) -> str:
    """
    Sticky regime with deadband exits so we don't thrash near ±2%.
    """
    if ret_7d is None:
        return prev_sticky or "unknown"
    prev = prev_sticky or raw_tape

    if prev == "btc_up":
        # stay up until reclaim below exit_up, then reclassify
        if ret_7d >= exit_up:
            return "btc_up"
        return classify_raw_tape(ret_7d, enter_up=enter_up, enter_down=enter_down)

    if prev == "btc_down":
        if ret_7d <= exit_down:
            return "btc_down"
        return classify_raw_tape(ret_7d, enter_up=enter_up, enter_down=enter_down)

    # chop / unknown: enter only on hard thresholds
    return classify_raw_tape(ret_7d, enter_up=enter_up, enter_down=enter_down)


def arm_for_tape(tape: str, mapping: Optional[Dict[str, str]] = None) -> str:
    m = mapping or {
        "btc_up": ARM_UP_CHOP,
        "btc_chop": ARM_UP_CHOP,
        "btc_down": ARM_DOWN,
        "unknown": ARM_UP_CHOP,
    }
    arm = m.get(tape) or ARM_UP_CHOP
    if arm not in VALID_ARMS:
        return ARM_UP_CHOP
    return arm


def compute_snapshot(
    *,
    candles: Optional[Sequence[Dict[str, Any]]] = None,
    prev_state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    min_dwell_hours: float = MIN_DWELL_HOURS,
    use_network: bool = True,
) -> RegimeSnapshot:
    now = now or _utc_now()
    prev_state = prev_state if prev_state is not None else _load_json(SWITCH_LATEST)
    if candles is None:
        candles = fetch_btc_daily(use_network=use_network)
    day_closes = closes_by_day(candles)
    ret, close_day, close = btc_ret_nd(day_closes, n=LOOKBACK_DAYS)
    raw = classify_raw_tape(ret)
    prev_sticky = str(prev_state.get("sticky_tape") or "") or None
    sticky = apply_hysteresis(raw, prev_sticky, ret)
    target = arm_for_tape(sticky)

    prev_arm = None
    if BRAD_DECISION_JSON.exists():
        brad = _load_json(BRAD_DECISION_JSON)
        prev_arm = (brad.get("preferred_arm") or "").strip() or None
    if not prev_arm:
        prev_arm = (prev_state.get("preferred_arm") or "").strip() or None

    dwell_blocked = False
    flipped = bool(prev_arm and prev_arm != target)
    reason = f"tape={sticky} (raw={raw}) ret7={None if ret is None else round(ret, 3)} → {target}"

    # dwell: if last flip too recent and would flip again, hold previous arm
    last_flip_at = _parse_ts(prev_state.get("last_flip_at") or prev_state.get("applied_at"))
    if flipped and prev_arm and last_flip_at is not None:
        hours = (now - last_flip_at).total_seconds() / 3600.0
        if hours < float(min_dwell_hours):
            dwell_blocked = True
            flipped = False
            target = prev_arm
            reason = (
                f"dwell_hold {hours:.1f}h<{min_dwell_hours}h; "
                f"would_be tape={sticky}→{arm_for_tape(sticky)}; keeping {prev_arm}"
            )

    if not prev_arm:
        flipped = True  # first seed
        reason = f"seed preferred_arm={target}; {reason}"

    return RegimeSnapshot(
        as_of=_iso(now),
        btc_ret_7d_pct=None if ret is None else round(float(ret), 4),
        raw_tape=raw,
        sticky_tape=sticky,
        preferred_arm=target,
        previous_preferred_arm=prev_arm,
        flipped=bool(prev_arm != target) if prev_arm else True,
        dwell_blocked=dwell_blocked,
        reason=reason,
        close=close,
        close_day=close_day,
    )


def apply_to_decision(
    snap: RegimeSnapshot,
    *,
    mode: str = "shadow",
    apply: bool = False,
    force_live_swaps: bool = False,  # ignored unless True AND mode=production — still default refuse
    decided_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update basket_swap_brad_decision.json preferred_arm when apply=True.
    Always forces live_membership_swaps/live_apply false (module never promotes live seats).
    """
    mode = (mode or "shadow").strip().lower()
    if mode not in ("shadow", "production"):
        raise ValueError(f"mode must be shadow|production, got {mode!r}")

    brad = _load_json(BRAD_DECISION_JSON)
    if not brad:
        brad = {
            "schema": "basket_swap_brad_decision_v1",
            "continue_arms": [
                "dual_agree",
                "anti_pump",
                "risk_adj_mom",
                "baseline_hybrid",
                "rel_btc_stable",
                "control_no_swap",
            ],
        }

    before = (brad.get("preferred_arm") or "").strip() or None
    after = snap.preferred_arm
    changed = before != after

    result: Dict[str, Any] = {
        "schema": "regime_arm_switch_result_v1",
        "as_of": snap.as_of,
        "mode": mode,
        "apply": bool(apply),
        "snapshot": asdict(snap),
        "before_preferred_arm": before,
        "after_preferred_arm": after,
        "changed": changed,
        "decision_written": False,
        "live_membership_swaps": False,
        "live_apply": False,
        "note": None,
    }

    refuse_live_note = None
    # Safety: this module never turns live membership on.
    if force_live_swaps:
        refuse_live_note = (
            "force_live_swaps requested but refused — live membership requires "
            "explicit Brad GO on a *specific* swap, not regime arm switch."
        )
        result["note"] = refuse_live_note

    if not apply:
        dry = " dry-run (apply=false)"
        result["note"] = ((result.get("note") or "") + dry).strip()
        _persist_switch_state(snap, result, wrote_decision=False)
        _write_report(snap, result)
        return result

    if snap.dwell_blocked and before == after:
        result["note"] = snap.reason
        if refuse_live_note:
            result["note"] = f"{result['note']}; {refuse_live_note}"
        _persist_switch_state(snap, result, wrote_decision=False)
        _write_report(snap, result)
        return result

    now = _utc_now()
    if changed:
        brad["previous_preferred_arm"] = before
    brad["preferred_arm"] = after
    # Preserve Brad GO production stamp when present (mode=production).
    go_raw = brad.get("brad_go_arm_production")
    go: Dict[str, Any] = dict(go_raw) if isinstance(go_raw, dict) else {}
    production_ssot = mode == "production" or bool(go)
    if production_ssot:
        brad["preferred_arm_role"] = "production_preferred_arm_attention_ssot"
        brad["preferred_arm_note"] = (
            f"regime_arm_switch mode={mode}: {snap.reason}. "
            f"BTC 7d={snap.btc_ret_7d_pct}% sticky={snap.sticky_tape}. "
            "Production preferred-arm attention SSOT (Brad GO 2026-09-25). "
            "Does not auto-swap live basket."
        )
        # Keep human GO as provenance; append switcher only when arm actually flipped.
        if changed:
            brad["decided_by"] = decided_by or f"regime_arm_switch:{mode}+brad_go_production"
            brad["decided_at"] = _iso(now)
        else:
            brad["decided_by"] = brad.get("decided_by") or "brad_go_2026-09-25_rel_btc_stable_production"
    else:
        brad["preferred_arm_role"] = "paper_primary_for_operator_attention"
        brad["preferred_arm_note"] = (
            f"regime_arm_switch mode={mode}: {snap.reason}. "
            f"BTC 7d={snap.btc_ret_7d_pct}% sticky={snap.sticky_tape}. "
            "Does not auto-swap live basket."
        )
        brad["decided_at"] = _iso(now)
        brad["decided_by"] = decided_by or f"regime_arm_switch:{mode}"
    if brad.get("prior_decided_at") is None and brad.get("decided_at"):
        pass
    elif changed and before:
        # keep human prior if present; else stamp
        if not brad.get("prior_decided_at"):
            brad["prior_decided_at"] = brad.get("decided_at")
    # HARD fence
    brad["live_membership_swaps"] = False
    brad["live_apply"] = False

    # secondary status notes — preserve production_preferred on winner arm when GO stamp exists
    other = ARM_DOWN if after == ARM_UP_CHOP else ARM_UP_CHOP
    go_arm = str(go.get("arm") or ARM_UP_CHOP)
    if production_ssot and after == go_arm:
        raw_prev = brad.get(after)
        prev_arm_block: Dict[str, Any] = dict(raw_prev) if isinstance(raw_prev, dict) else {}
        prev_arm_block["status"] = "production_preferred"
        prev_arm_block["note"] = (
            f"Production preferred arm (Brad GO). Active via regime switch ({snap.sticky_tape}). "
            "Not auto live seats."
        )
        brad[after] = prev_arm_block
    else:
        brad[after] = {
            "status": "paper_primary_regime" if not production_ssot else "production_preferred_regime_map",
            "note": f"Active preferred via regime switch ({snap.sticky_tape}); live seats OFF.",
        }
    brad[other] = {
        "status": "continue_shadow_secondary_regime_down" if other == ARM_DOWN else "continue_shadow_secondary",
        "note": f"Secondary collect while preferred={after} (regime={snap.sticky_tape}).",
    }
    if production_ssot:
        plain = (
            f"Brad GO production preferred-arm path ({mode}): preferred_arm={after} "
            f"(BTC 7d={snap.btc_ret_7d_pct}%, tape={snap.sticky_tape}). "
            "Live membership swaps OFF. Collecting arms stay on for regime correlation."
        )
    else:
        plain = (
            f"Regime arm switch ({mode}): preferred_arm={after} "
            f"(BTC 7d={snap.btc_ret_7d_pct}%, tape={snap.sticky_tape}). "
            "Live membership swaps OFF."
        )
    if refuse_live_note:
        plain = f"{plain} {refuse_live_note}"
    brad["plain_english"] = plain
    raw_ras = brad.get("regime_arm_switch")
    prev_ras: Dict[str, Any] = dict(raw_ras) if isinstance(raw_ras, dict) else {}
    brad["regime_arm_switch"] = {
        **{k: v for k, v in prev_ras.items() if str(k).startswith("brad_go")},
        "mode": mode,
        "sticky_tape": snap.sticky_tape,
        "raw_tape": snap.raw_tape,
        "btc_ret_7d_pct": snap.btc_ret_7d_pct,
        "as_of": snap.as_of,
        "thresholds": snap.thresholds,
    }

    _write_json(BRAD_DECISION_JSON, brad)
    result["decision_written"] = True
    result["changed"] = changed
    result["after_preferred_arm"] = after
    result["note"] = plain
    if changed:
        result["last_flip_at"] = _iso(now)

    _persist_switch_state(snap, result, wrote_decision=True, last_flip=changed)
    _write_report(snap, result)
    return result


def _persist_switch_state(
    snap: RegimeSnapshot,
    result: Dict[str, Any],
    *,
    wrote_decision: bool,
    last_flip: bool = False,
) -> None:
    prev = _load_json(SWITCH_LATEST)
    payload = {
        "schema": "regime_arm_switch_state_v1",
        "as_of": snap.as_of,
        "mode": result.get("mode"),
        "apply": result.get("apply"),
        "btc_ret_7d_pct": snap.btc_ret_7d_pct,
        "raw_tape": snap.raw_tape,
        "sticky_tape": snap.sticky_tape,
        "preferred_arm": snap.preferred_arm if not snap.dwell_blocked else result.get("after_preferred_arm"),
        "previous_preferred_arm": snap.previous_preferred_arm,
        "flipped": bool(result.get("changed")),
        "dwell_blocked": snap.dwell_blocked,
        "reason": snap.reason,
        "close": snap.close,
        "close_day": snap.close_day,
        "decision_written": wrote_decision,
        "live_membership_swaps": False,
        "thresholds": snap.thresholds,
        "map": snap.map,
        "last_flip_at": (
            result.get("last_flip_at")
            or ( _iso(_utc_now()) if last_flip else prev.get("last_flip_at"))
        ),
        "applied_at": _iso(_utc_now()) if wrote_decision else prev.get("applied_at"),
    }
    # if dwell held arm, preferred in state should reflect held
    if snap.dwell_blocked and snap.previous_preferred_arm:
        payload["preferred_arm"] = snap.previous_preferred_arm
        payload["sticky_tape"] = snap.sticky_tape  # tape can move; arm held
    _write_json(SWITCH_LATEST, payload)
    _append_jsonl(
        SWITCH_JSONL,
        {
            "ts": snap.as_of,
            "mode": result.get("mode"),
            "apply": result.get("apply"),
            "btc_ret_7d_pct": snap.btc_ret_7d_pct,
            "raw_tape": snap.raw_tape,
            "sticky_tape": snap.sticky_tape,
            "preferred_arm": payload.get("preferred_arm"),
            "changed": result.get("changed"),
            "dwell_blocked": snap.dwell_blocked,
            "decision_written": wrote_decision,
        },
    )


def _write_report(snap: RegimeSnapshot, result: Dict[str, Any]) -> None:
    lines = [
        "# Regime arm switch (latest)",
        "",
        f"- **as_of:** `{snap.as_of}`",
        f"- **mode:** `{result.get('mode')}` apply=`{result.get('apply')}`",
        f"- **BTC 7d %:** `{snap.btc_ret_7d_pct}` (close_day=`{snap.close_day}` close=`{snap.close}`)",
        f"- **raw tape:** `{snap.raw_tape}` → **sticky:** `{snap.sticky_tape}`",
        f"- **preferred_arm:** `{result.get('after_preferred_arm')}` "
        f"(before=`{result.get('before_preferred_arm')}`)",
        f"- **changed:** `{result.get('changed')}` dwell_blocked=`{snap.dwell_blocked}`",
        f"- **decision_written:** `{result.get('decision_written')}`",
        f"- **live_membership_swaps:** `false` (hard fence)",
        "",
        f"**Reason:** {snap.reason}",
        "",
        "## Map",
        "",
        "| Tape | Arm |",
        "|------|-----|",
        f"| btc_up (≥{ENTER_UP_PCT}%) | `{ARM_UP_CHOP}` |",
        f"| btc_chop | `{ARM_UP_CHOP}` |",
        f"| btc_down (≤{ENTER_DOWN_PCT}%) | `{ARM_DOWN}` |",
        "",
        "## Honesty",
        "",
        "- preferred_arm = paper-primary / operator attention only.",
        "- Does **not** mutate `global_settings.pairs` or place orders.",
        "- dual_agree stays collect-only.",
        "",
    ]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n")


def run(
    *,
    mode: str = "shadow",
    apply: bool = False,
    use_network: bool = True,
    candles: Optional[Sequence[Dict[str, Any]]] = None,
    min_dwell_hours: float = MIN_DWELL_HOURS,
) -> Dict[str, Any]:
    snap = compute_snapshot(
        candles=candles,
        use_network=use_network,
        min_dwell_hours=min_dwell_hours,
    )
    return apply_to_decision(snap, mode=mode, apply=apply)


# --- helpers for tests ---
def synthetic_candles_from_closes(closes: Sequence[float], start_day: str = "2026-08-01") -> List[Dict[str, Any]]:
    """Build minimal daily candle list from close series (tests)."""
    d0 = datetime.fromisoformat(start_day).replace(tzinfo=timezone.utc)
    out = []
    for i, cl in enumerate(closes):
        day = d0 + timedelta(days=i)
        out.append(
            {
                "time": day.strftime("%Y-%m-%dT00:00:00Z"),
                "open": float(cl),
                "high": float(cl),
                "low": float(cl),
                "close": float(cl),
                "volume": 1.0,
            }
        )
    return out
