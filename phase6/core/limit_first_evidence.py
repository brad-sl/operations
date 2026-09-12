"""
Limit-first fill evidence (PC-05).

Honest attempt/fill/skip/market_fallback counters + drought note.
market_fallback must stay 0 while market_fallback_max_usd=0 (no grind).
Measure-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "limit_first_evidence_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "limit_first_evidence_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "LIMIT_FIRST_EVIDENCE_LATEST.md"
PILOT_STATE = PROJECT_ROOT / "data" / "state" / "limit_first_buy_pilot_state.json"
PILOT_EVENTS = PROJECT_ROOT / "data" / "state" / "limit_first_buy_pilot_events.jsonl"
SHADOW_LATEST = PROJECT_ROOT / "data" / "state" / "limit_first_buy_shadow_latest.json"
TRYOUT_READY = PROJECT_ROOT / "data" / "state" / "tryout_readiness_latest.json"
FEE_SNAP = PROJECT_ROOT / "data" / "state" / "fee_tier_snapshot_latest.json"
TRADING_CFG = PROJECT_ROOT / "config" / "trading_config_phase6.json"

# Design bar: ≥30 attempts OR 14d observation before promote talk
MIN_ATTEMPTS_FOR_RATE = 30
DROUGHT_DAYS = 14


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _utc_now().isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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


def load_events(path: Path = PILOT_EVENTS) -> List[Dict[str, Any]]:
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


def aggregate_events(
    events: Sequence[Mapping[str, Any]],
    *,
    since: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Roll up pilot event outcomes. Honest zeros OK."""
    counts = {
        "attempted": 0,
        "filled": 0,
        "unfilled": 0,
        "error": 0,
        "elevated_abort": 0,
        "over_cap_market": 0,
        "kill_market": 0,
        "other": 0,
    }
    usd_attempted = 0.0
    usd_filled = 0.0
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    pairs: Dict[str, int] = {}

    for ev in events:
        ts = _parse_ts(ev.get("ts") or ev.get("timestamp"))
        if since and ts and ts < since:
            continue
        if ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
        outcome = str(ev.get("outcome") or "").strip().lower()
        if outcome in counts:
            counts[outcome] += 1
        elif outcome:
            counts["other"] += 1
        if outcome == "attempted":
            try:
                usd_attempted += float(ev.get("usd") or 0)
            except (TypeError, ValueError):
                pass
        if outcome == "filled":
            try:
                usd_filled += float(ev.get("filled_usd") or ev.get("usd") or 0)
            except (TypeError, ValueError):
                pass
        pair = str(ev.get("pair") or "")
        if pair:
            pairs[pair] = pairs.get(pair, 0) + 1

    attempts = int(counts["attempted"])
    filled = int(counts["filled"])
    fill_rate = (filled / attempts) if attempts else None
    market_fb = int(counts["over_cap_market"]) + int(counts["kill_market"])
    return {
        "counts": counts,
        "limit_attempts": attempts,
        "limit_filled": filled,
        "limit_unfilled": int(counts["unfilled"]),
        "limit_errors": int(counts["error"]),
        "elevated_aborts": int(counts["elevated_abort"]),
        "market_fallback_events": market_fb,
        "usd_attempted": round(usd_attempted, 4),
        "usd_filled": round(usd_filled, 4),
        "fill_rate": fill_rate,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "pairs": pairs,
    }


def drought_note(
    *,
    attempts: int,
    last_ts: Optional[str],
    now: Optional[datetime] = None,
    tryout_can_buy: Optional[bool] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    last = _parse_ts(last_ts)
    days_since = None
    if last is not None:
        days_since = round((now - last).total_seconds() / 86400.0, 2)
    in_drought = attempts == 0 or (days_since is not None and days_since >= DROUGHT_DAYS and attempts < MIN_ATTEMPTS_FOR_RATE)
    reason_parts = []
    if attempts == 0:
        reason_parts.append("zero_limit_attempts_in_window")
    if days_since is not None and days_since >= DROUGHT_DAYS:
        reason_parts.append(f"last_attempt_{days_since}d_ago")
    if tryout_can_buy is False:
        reason_parts.append("linked_pc03_sleeve_drought_can_buy_false")
    elif tryout_can_buy is True and attempts == 0:
        reason_parts.append("can_buy_true_but_no_limit_attempt_yet")
    return {
        "drought": bool(in_drought or attempts == 0),
        "days_since_last_attempt": days_since,
        "min_attempts_bar": MIN_ATTEMPTS_FOR_RATE,
        "drought_day_bar": DROUGHT_DAYS,
        "reasons": reason_parts or (["ok_collecting"] if attempts else ["no_data"]),
        "honest_zero_ok": True,
        "promote_talk_ok": bool(attempts >= MIN_ATTEMPTS_FOR_RATE),
    }


def policy_snapshot(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    ee = cfg.get("entry_execution") if isinstance(cfg.get("entry_execution"), dict) else {}
    lf = ee.get("limit_first") if isinstance(ee.get("limit_first"), dict) else {}
    return {
        "mode": ee.get("mode"),
        "enabled": bool(lf.get("enabled")),
        "post_only": lf.get("post_only"),
        "market_fallback": bool(lf.get("market_fallback")),
        "market_fallback_max_usd": float(lf.get("market_fallback_max_usd") or 0.0),
        "pilot_max_buys_per_day": lf.get("pilot_max_buys_per_day"),
        "pilot_max_usd_per_day": lf.get("pilot_max_usd_per_day"),
        "fill_wait_s": lf.get("fill_wait_s"),
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    a = payload.get("aggregate") or {}
    d = payload.get("drought") or {}
    pol = payload.get("policy") or {}
    fee = payload.get("fee_tier") or {}
    lines = [
        "# Limit-first fill evidence (PC-05)",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Schema:** `{payload.get('schema')}`",
        "",
        "## Policy (must not enable market fallback without Brad GO)",
        "",
        f"- mode=`{pol.get('mode')}` enabled=`{pol.get('enabled')}` post_only=`{pol.get('post_only')}`",
        f"- market_fallback=`{pol.get('market_fallback')}` max_usd=**{pol.get('market_fallback_max_usd')}**",
        f"- pilot caps: buys/day={pol.get('pilot_max_buys_per_day')} usd/day={pol.get('pilot_max_usd_per_day')}",
        "",
        "## Counters (honest zeros OK)",
        "",
        f"- Limit attempts: **{a.get('limit_attempts')}**",
        f"- Filled: **{a.get('limit_filled')}** · Unfilled: **{a.get('limit_unfilled')}** · Errors: **{a.get('limit_errors')}**",
        (
            f"- Fill rate: **{100 * float(a['fill_rate']):.0f}%**"
            if a.get("fill_rate") is not None
            else "- Fill rate: **n/a (denom 0)**"
        ),
        f"- Market fallback events: **{a.get('market_fallback_events')}** (expect 0 while max_usd=0)",
        f"- USD attempted / filled: **${float(a.get('usd_attempted') or 0):.2f}** / **${float(a.get('usd_filled') or 0):.2f}**",
        f"- First/last attempt: `{a.get('first_ts')}` → `{a.get('last_ts')}`",
        "",
        "## Drought / denominator honesty",
        "",
        f"- Drought flag: **{d.get('drought')}**",
        f"- Days since last attempt: **{d.get('days_since_last_attempt')}**",
        f"- Promote-talk bar (≥{d.get('min_attempts_bar')} attempts): **{d.get('promote_talk_ok')}**",
        f"- Reasons: {', '.join(d.get('reasons') or [])}",
        f"- PC-03 link can_buy: `{payload.get('tryout_can_buy')}`",
        "",
        "## Fee tier (context only)",
        "",
        f"- maker={fee.get('maker')} taker={fee.get('taker')} tier=`{fee.get('tier')}`",
        "",
        "## Shadow CF note",
        "",
        f"- {payload.get('shadow_note')}",
        "",
        f"State: `{STATE_PATH.relative_to(PROJECT_ROOT)}`",
        "",
    ]
    return "\n".join(lines)


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")


def build_limit_first_evidence(
    *,
    write: bool = True,
    lookback_days: int = 30,
    events: Optional[Sequence[Mapping[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    since = now - timedelta(days=lookback_days)
    ev = list(events) if events is not None else load_events()
    agg = aggregate_events(ev, since=since)

    # also surface pilot day state (may be stale day)
    pilot = _read_json(PILOT_STATE)
    tryout = _read_json(TRYOUT_READY)
    can_buy = tryout.get("can_buy")
    if can_buy is None and isinstance(tryout.get("summary"), dict):
        can_buy = tryout["summary"].get("can_buy")

    drought = drought_note(
        attempts=int(agg.get("limit_attempts") or 0),
        last_ts=agg.get("last_ts"),
        now=now,
        tryout_can_buy=bool(can_buy) if can_buy is not None else None,
    )

    cfg = _read_json(TRADING_CFG)
    pol = policy_snapshot(cfg)
    fee_raw = _read_json(FEE_SNAP)
    fee = {
        "maker": fee_raw.get("maker_rate") or fee_raw.get("maker"),
        "taker": fee_raw.get("taker_rate") or fee_raw.get("taker"),
        "tier": fee_raw.get("tier") or fee_raw.get("fee_tier"),
        "source": str(FEE_SNAP.relative_to(PROJECT_ROOT)),
    }
    shadow = _read_json(SHADOW_LATEST)
    sh_sum = shadow.get("summary") or {}
    shadow_note = (
        f"shadow feeΔ upper-bound only (n_buys={sh_sum.get('n_buys')}); "
        "not realized maker savings until pilot attempts accumulate."
    )

    # Integrity: market_fallback_max_usd must be 0 without GO
    integrity = {
        "market_fallback_max_usd_is_zero": float(pol.get("market_fallback_max_usd") or 0) == 0.0,
        "market_fallback_flag_false": not bool(pol.get("market_fallback")),
        "market_fallback_events_zero_or_explained": int(agg.get("market_fallback_events") or 0) == 0
        or float(pol.get("market_fallback_max_usd") or 0) > 0,
    }

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "lookback_days": lookback_days,
        "policy": pol,
        "aggregate": agg,
        "pilot_day_state": {
            "utc_day": pilot.get("utc_day"),
            "limit_attempts": pilot.get("limit_attempts"),
            "limit_filled": pilot.get("limit_filled"),
            "updated_at": pilot.get("updated_at"),
        },
        "drought": drought,
        "tryout_can_buy": can_buy,
        "fee_tier": fee,
        "shadow_note": shadow_note,
        "integrity": integrity,
        "measure_only": True,
        "no_market_fallback_enable": True,
    }
    if write:
        write_artifacts(payload)
    return payload
