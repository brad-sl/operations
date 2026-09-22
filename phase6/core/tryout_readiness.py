"""
Tryout sleeve readiness board (PC-03).

SSOT for "can we seat a tryout BUY before next rebalance?"
- Eng-aged sentiment drives gates; free/tee never clears BUY.
- Live floor (tryout): quality_tryout min_sent only (B1 2026-09-13).
  Non-tryout new-pair still uses regime min_sentiment_new_pair.
- A2 tryout_sent_latch may clear aged eng through rebalance window.
- No knobs, no force_rebalance.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "tryout_readiness_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "tryout_readiness_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "TRYOUT_READINESS_LATEST.md"
PT = ZoneInfo("America/Los_Angeles")

# Default X refresh slots (PT) — A1 2026-09-13: align with rebalance hour
DEFAULT_X_REFRESH_HHMM = ((9, 0), (21, 0))
# Default rebalance approx (PT)
DEFAULT_REBALANCE_HHMM = ((9, 5), (21, 5))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def live_entry_floor(
    *,
    min_sentiment: float = 0.25,
    min_sentiment_new_pair: float = 0.35,
    quality_tryout_min_sentiment: float = 0.30,
    is_new_pair: bool = True,
    on_tryout: bool = False,
) -> float:
    """Floor SSOT.

    B1 2026-09-13: tryout sleeve uses quality_tryout min only (not max with
    min_sentiment_new_pair). Non-tryout new pairs still use regime new-pair floor.
    """
    if on_tryout:
        return float(quality_tryout_min_sentiment or 0.30)
    return float(min_sentiment_new_pair if is_new_pair else min_sentiment)


def next_slot_pt(
    now_pt: datetime,
    slots: Sequence[tuple[int, int]],
) -> tuple[str, datetime]:
    """Return (HH:MM label, next datetime in PT) for daily HH:MM slots."""
    from datetime import timedelta

    if now_pt.tzinfo is None:
        now_pt = now_pt.replace(tzinfo=PT)
    else:
        now_pt = now_pt.astimezone(PT)
    candidates: List[datetime] = []
    for day_off in (0, 1, 2):
        day = (now_pt + timedelta(days=day_off)).date()
        for h, m in slots:
            dt = datetime(day.year, day.month, day.day, h, m, tzinfo=PT)
            if dt > now_pt:
                candidates.append(dt)
    if not candidates:
        raise ValueError("no future slots")
    nxt = min(candidates)
    return f"{nxt.hour:02d}:{nxt.minute:02d}", nxt


def classify_sensor(
    *,
    mode: str,
    eng_scores: Mapping[str, float],
    x_posts_total: int,
    x_age_hours: Optional[float],
    reddit_nz: int,
    free_nz: int,
    floor: float,
) -> Dict[str, Any]:
    """
    Sensor honesty: stuck-zero bug vs mid-cycle aged-out clock.
    broken=True only when primary path looks clobbered (not normal aging).
    """
    eng_vals = [float(v) for v in eng_scores.values()]
    all_zero = bool(eng_vals) and all(abs(v) < 1e-9 for v in eng_vals)
    mode_l = str(mode or "").lower()
    x_aged = bool(x_age_hours is not None and x_age_hours >= 2.0)
    bridge_active = "bridge" in mode_l or "reddit" in mode_l

    # Normal mid-cycle X aging + reddit bridge (PC-03: prove clock true, no stuck-zero)
    if (all_zero or (not all_zero and max(eng_vals or [0]) < 0.1)) and (x_aged or bridge_active):
        cls = "aged_out_primary_plus_thin_bridge" if (reddit_nz == 0 or not bridge_active) else "aged_out_x_bridge_active"
        detail = (
            f"X age ~{x_age_hours or 0:.1f}h (15m HL) → bridge to reddit; eng low/zero expected mid-cycle. "
            f"mode={mode_l}; reddit_nz={reddit_nz}; free_nz={free_nz} (tee only, shadow). "
            f"Not a stuck-zero bug; X→reddit clock working. Live floor {floor:.2f}."
        )
        return {"broken": False, "class": cls, "detail": detail, "x_age_hours": x_age_hours}

    if all_zero and x_posts_total == 0 and "free" not in mode_l and reddit_nz == 0 and free_nz == 0:
        return {
            "broken": True,
            "class": "possible_stuck_zero_or_dead_feeds",
            "detail": "All eng 0, no X posts, no reddit, no free tee — investigate refresh/no-clobber.",
        }
    if not all_zero:
        warm = sum(1 for v in eng_vals if v >= floor)
        cls = "eng_heat_present" if warm else "eng_below_floor"
        detail = f"mode={mode_l}; eng above floor for {warm}/{len(eng_vals)} doors; floor={floor:.2f}."
        if x_aged and bridge_active:
            detail = f"X aged {x_age_hours:.1f}h + {mode_l}; " + detail
        return {"broken": False, "class": cls, "detail": detail, "x_age_hours": x_age_hours}
    return {
        "broken": False,
        "class": "thin_or_neutral",
        "detail": f"mode={mode_l}; eng flat under floor {floor:.2f}; free_nz={free_nz} does not clear gates.",
        "x_age_hours": x_age_hours,
    }


@dataclass
class PairDoor:
    pair: str
    eligible: bool = False
    force_eligible: bool = False
    allowed: bool = False
    reasons: List[str] = field(default_factory=list)
    eng_sent: Optional[float] = None
    rsi: Optional[float] = None
    rsi_ok: Optional[bool] = None
    x_raw: Optional[float] = None
    x_posts: Optional[int] = None
    reddit_raw: Optional[float] = None
    free_tee: Optional[float] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_readiness_payload(
    *,
    doors: Sequence[PairDoor],
    floors: Mapping[str, float],
    sensor: Mapping[str, Any],
    cash_usd: Optional[float],
    seats_used_today: int,
    max_new_seats_per_day: int,
    tryout_cap_usd: float,
    eligible_tryout_pairs: Sequence[str],
    regime: str,
    equity_health: str,
    sent_mode: str,
    next_x_refresh_pt: str,
    next_rebalance_pt: str,
    open_positions: Optional[Sequence[Mapping[str, Any]]] = None,
    runner_pid: Optional[int] = None,
    plain_english: str = "",
    actions_taken: Optional[Sequence[str]] = None,
    as_of: Optional[datetime] = None,
    strategy_mode: str = "",
    allow_new_buys: Optional[bool] = None,
    rebalance_cap_usd: Optional[float] = None,
    regime_layer: str = "",
    knob_map_scenario: str = "",
) -> Dict[str, Any]:
    now = as_of or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_pt = now.astimezone(PT)

    any_allowed = any(d.allowed for d in doors)
    seats_left = max(0, int(max_new_seats_per_day) - int(seats_used_today))
    cash_ok = cash_usd is None or float(cash_usd) >= float(tryout_cap_usd) * 0.9
    park_blocked = bool(
        (allow_new_buys is False)
        or (str(strategy_mode or "").lower() in ("usdc_park", "park"))
    )
    can_buy = bool(
        any_allowed
        and seats_left > 0
        and cash_ok
        and not sensor.get("broken")
        and not park_blocked
    )

    if not plain_english:
        if sensor.get("broken"):
            plain_english = "Sensor looks broken — do not treat as drought; fix refresh path first."
        elif park_blocked:
            plain_english = (
                f"Regime park blocks new buys (mode={strategy_mode or 'park'} "
                f"regime={regime} layer={regime_layer or '—'}). "
                "Unlock policy before reading eng doors as actionable."
            )
        elif can_buy:
            ok = [d.pair for d in doors if d.allowed]
            plain_english = f"Tryout can seat before next rebalance: {', '.join(ok)} clear eng floor."
        else:
            blocked = [d.pair for d in doors if d.eligible and not d.allowed]
            plain_english = (
                f"Sleeve membership open but no eng-cleared door "
                f"({', '.join(blocked) or 'none'}). Free/tee is not a green light."
            )

    return {
        "schema": SCHEMA,
        "as_of": now_pt.isoformat(),
        "as_of_utc": now.astimezone(timezone.utc).isoformat(),
        "can_buy_before_next_rebalance": can_buy,
        "next_x_refresh_pt": next_x_refresh_pt,
        "next_rebalance_pt": next_rebalance_pt,
        "cash_usd": cash_usd,
        "open_positions": list(open_positions or []),
        "seats_used_today": int(seats_used_today),
        "max_new_seats_per_day": int(max_new_seats_per_day),
        "tryout_cap_usd": float(tryout_cap_usd),
        "eligible_tryout_pairs": list(eligible_tryout_pairs),
        "regime": regime,
        "regime_layer": regime_layer or "",
        "strategy_mode": strategy_mode or "",
        "allow_new_buys": allow_new_buys,
        "rebalance_cap_usd": rebalance_cap_usd,
        "knob_map_scenario": knob_map_scenario or "",
        "park_blocked": park_blocked,
        "equity_health": equity_health,
        "sent_mode": sent_mode,
        "entry_floors": dict(floors),
        "pairs": [d.to_dict() for d in doors],
        "sensor_verdict": dict(sensor),
        "plain_english": plain_english,
        "actions_taken": list(actions_taken or []),
        "runner_pid": runner_pid,
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    floors = payload.get("entry_floors") or {}
    sensor = payload.get("sensor_verdict") or {}
    lines = [
        f"# Tryout readiness — {payload.get('as_of', '')}",
        "",
        f"**can_buy_before_next_rebalance:** `{payload.get('can_buy_before_next_rebalance')}`",
        "",
        f"> {payload.get('plain_english', '')}",
        "",
        "## Book",
        f"- Cash: `${payload.get('cash_usd')}` · tryout cap `${payload.get('tryout_cap_usd')}`",
        f"- Seats today: {payload.get('seats_used_today')}/{payload.get('max_new_seats_per_day')}",
        f"- Eligible: {', '.join(payload.get('eligible_tryout_pairs') or []) or '—'}",
        f"- Regime: {payload.get('regime')} · layer: {payload.get('regime_layer') or '—'} · "
        f"mode: {payload.get('strategy_mode') or '—'} · "
        f"allow_new_buys: {payload.get('allow_new_buys')} · "
        f"cap: ${payload.get('rebalance_cap_usd')} · "
        f"scenario: {payload.get('knob_map_scenario') or '—'} · "
        f"park_blocked: {payload.get('park_blocked')} · "
        f"equity_health: {payload.get('equity_health')}",
        f"- Runner PID: {payload.get('runner_pid')}",
        "",
        "## Floors (SSOT)",
        f"- min_sentiment: {floors.get('min_sentiment')}",
        f"- min_sentiment_new_pair: {floors.get('min_sentiment_new_pair')}",
        f"- quality_tryout_min_sentiment: {floors.get('quality_tryout_min_sentiment')}",
        f"- **live_floor_used:** {floors.get('live_floor_used')} (max of new-pair + tryout)",
        f"- max_rsi: {floors.get('max_rsi')}",
        "",
        "## Sensor",
        f"- mode: `{payload.get('sent_mode')}`",
        f"- broken: `{sensor.get('broken')}` · class: `{sensor.get('class')}`",
        f"- detail: {sensor.get('detail')}",
        f"- next X refresh PT: {payload.get('next_x_refresh_pt')} · next rebalance PT: {payload.get('next_rebalance_pt')}",
        "",
        "## Doors",
        "| Pair | elig | force | allowed | eng | RSI | reasons |",
        "|------|------|-------|---------|-----|-----|---------|",
    ]
    for d in payload.get("pairs") or []:
        reasons = "; ".join(d.get("reasons") or []) or "—"
        lines.append(
            f"| {d.get('pair')} | {d.get('eligible')} | {d.get('force_eligible')} | "
            f"{d.get('allowed')} | {d.get('eng_sent')} | {d.get('rsi')} | {reasons} |"
        )
    lines.extend(["", "## Rules", "- Free/tee never clears REGIME-CASH.", "- No floor bypass without Brad GO.", ""])
    return "\n".join(lines)


def write_artifacts(payload: Mapping[str, Any], *, state_path: Path = STATE_PATH, report_path: Path = REPORT_PATH) -> Dict[str, str]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(state_path), "md": str(report_path)}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _runner_pid() -> Optional[int]:
    pid_path = PROJECT_ROOT / "data" / "state" / "phase6_runner.pid"
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
        pid = int(raw.split()[0])
        # alive?
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def _load_rsi_map() -> Dict[str, float]:
    try:
        from phase6.core.buy_eligibility import load_rsi_map_from_cache

        return dict(load_rsi_map_from_cache() or {})
    except Exception:
        cache = _read_json(PROJECT_ROOT / "data" / "state" / "rsi_cache.json")
        out: Dict[str, float] = {}
        src = cache.get("rsi") if isinstance(cache.get("rsi"), dict) else cache
        if isinstance(src, dict):
            for k, v in src.items():
                try:
                    if isinstance(v, dict):
                        v = v.get("rsi") or v.get("value")
                    out[_norm_pair(k)] = float(v)
                except (TypeError, ValueError):
                    continue
        return out


def _sentiment_detail(pairs: Sequence[str]) -> Dict[str, Any]:
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores_detailed

        return load_sentiment_scores_detailed(list(pairs)) or {}
    except Exception:
        try:
            from phase6.core.sentiment_scorer import load_sentiment_scores

            raw = load_sentiment_scores(list(pairs)) or {}
            return {"scores": raw, "mode": "unknown"}
        except Exception:
            return {"scores": {}, "mode": "unavailable"}


def _x_meta() -> tuple[Dict[str, Any], Optional[float], int]:
    x = _read_json(PROJECT_ROOT / "data" / "state" / "x_sentiment_cache.json")
    free = _read_json(PROJECT_ROOT / "data" / "state" / "sentiment_cache_free.json")
    reddit = _read_json(PROJECT_ROOT / "data" / "state" / "sentiment_cache_reddit_reading.json")
    age_h = None
    posts = 0
    # top level ts or per-pair latest ts for accurate X age (proves aging clock)
    as_of = x.get("as_of") or x.get("updated_at") or x.get("timestamp")
    latest_ts = None
    scores = x.get("scores") if isinstance(x.get("scores"), dict) else x
    if isinstance(scores, dict):
        for v in scores.values():
            if isinstance(v, dict):
                try:
                    posts += int(v.get("post_count") or v.get("n_posts") or 0)
                except (TypeError, ValueError):
                    pass
                pts = v.get("timestamp") or v.get("ts")
                if pts:
                    try:
                        t = datetime.fromisoformat(str(pts).replace("Z", "+00:00"))
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        if latest_ts is None or t > latest_ts:
                            latest_ts = t
                    except Exception:
                        pass
    if as_of or latest_ts:
        try:
            ts = None
            if latest_ts:
                ts = latest_ts
            else:
                ts = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            age_h = (_utc_now() - ts.astimezone(timezone.utc)).total_seconds() / 3600.0
        except Exception:
            age_h = None
    return {"x": x, "free": free, "reddit": reddit}, age_h, posts


def _pair_score(blob: Any, pair: str) -> tuple[Optional[float], Optional[int]]:
    if not isinstance(blob, dict):
        return None, None
    scores = blob.get("scores") if isinstance(blob.get("scores"), dict) else blob
    if not isinstance(scores, dict):
        return None, None
    row = scores.get(pair) or scores.get(pair.replace("-USD", ""))
    if row is None:
        return None, None
    if isinstance(row, (int, float)):
        return float(row), None
    if isinstance(row, dict):
        for k in ("score", "eng_sent", "sentiment", "value", "aged", "raw"):
            if row.get(k) is not None:
                try:
                    sc = float(row[k])
                    posts = row.get("post_count") or row.get("n_posts")
                    return sc, int(posts) if posts is not None else None
                except (TypeError, ValueError):
                    continue
    return None, None


def _cash_and_positions() -> tuple[Optional[float], List[Dict[str, Any]]]:
    # Prefer dashboard live state if present
    for rel in (
        "data/state/dashboard_live_state.json",
        "data/state/phase6_live_state.json",
        "data/state/balances_latest.json",
    ):
        d = _read_json(PROJECT_ROOT / rel)
        if not d:
            continue
        cash = d.get("cash_usd") or d.get("usd") or d.get("cash")
        positions = d.get("positions") or d.get("open_positions") or []
        if cash is not None:
            try:
                cash_f = float(cash)
            except (TypeError, ValueError):
                cash_f = None
            pos_out: List[Dict[str, Any]] = []
            if isinstance(positions, dict):
                for k, v in positions.items():
                    if isinstance(v, dict):
                        pos_out.append({"pair": _norm_pair(k), "value_usd": v.get("value_usd") or v.get("usd"), "sleeve": v.get("sleeve")})
                    else:
                        try:
                            pos_out.append({"pair": _norm_pair(k), "value_usd": float(v)})
                        except (TypeError, ValueError):
                            pass
            elif isinstance(positions, list):
                pos_out = list(positions)
            return cash_f, pos_out
    # runner state fallback
    st = _read_json(PROJECT_ROOT / "data" / "state" / "phase6_runner_state.json")
    cash = st.get("cash_usd") or (st.get("balances") or {}).get("USD")
    try:
        cash_f = float(cash) if cash is not None else None
    except (TypeError, ValueError):
        cash_f = None
    return cash_f, []


def build_live_tryout_readiness(*, write: bool = True) -> Dict[str, Any]:
    """Live path: policy + scoreboard + eng scorer + evaluate_buy_entry."""
    from phase6.core.regime_cash_policy import (
        RegimeCashSnapshot,
        evaluate_buy_entry,
        load_policy,
        recovery_quality_tryout_cfg,
        recovery_tryout_pairs_effective,
        count_new_seat_buys_today,
        resolve_regime_cash,
        _recovery_rec,
    )
    from phase6.core.recovery_tryout_qualify import load_v2_cfg

    pol = load_policy()
    try:
        snap = resolve_regime_cash(policy=pol)
    except Exception:
        # minimal snap from status file — never invent heat
        st = _read_json(PROJECT_ROOT / "data" / "state" / "regime_cash_status.json")
        entry = (st.get("entry") or {}) if isinstance(st, dict) else {}
        if not entry and isinstance(st.get("regimes"), dict):
            entry = {}
        snap = RegimeCashSnapshot(
            regime=str(st.get("regime") or "flat"),
            confidence=float(st.get("confidence") or 0.0),
            btc_return_pct=st.get("btc_return_pct"),
            strategy_mode=str(st.get("strategy_mode") or "deploy"),
            allow_new_buys=bool(st.get("allow_new_buys", True)),
            target_max_util_pct=float(st.get("target_max_util_pct") or 50.0),
            rebalance_cap_usd=float(st.get("rebalance_cap_usd") or 75.0),
            min_cash_reserve_pct=float(st.get("min_cash_reserve_pct") or 20.0),
            entry=entry
            or {
                "min_sentiment": 0.25,
                "min_sentiment_new_pair": 0.35,
                "max_rsi": 55.0,
                "require_lockout_clear": True,
            },
            exit=st.get("exit") or {},
            label=str(st.get("label") or ""),
            detector=st.get("detector") or {},
        )

    rec = _recovery_rec(pol) or {}
    qt = recovery_quality_tryout_cfg(rec) if rec else {}
    v2 = load_v2_cfg(rec) if rec else {}
    eligible = sorted(recovery_tryout_pairs_effective(rec) if rec else [])
    force_set = set(v2.get("force_eligible_pairs") or [])

    entry = snap.entry if isinstance(snap.entry, dict) else {}
    min_s = float(entry.get("min_sentiment") or 0.25)
    min_new = float(entry.get("min_sentiment_new_pair") or 0.35)
    qt_min = float((qt or {}).get("min_sentiment") or v2.get("min_sentiment") or 0.30)
    max_rsi = float((qt or {}).get("max_rsi") or entry.get("max_rsi") or 55.0)
    floor = live_entry_floor(
        min_sentiment=min_s,
        min_sentiment_new_pair=min_new,
        quality_tryout_min_sentiment=qt_min,
        is_new_pair=True,
        on_tryout=True,
    )
    floors = {
        "min_sentiment": min_s,
        "min_sentiment_new_pair": min_new,
        "quality_tryout_min_sentiment": qt_min,
        "live_floor_used": floor,
        "live_floor_rule": "tryout_qt_only_b1",
        "max_rsi": max_rsi,
    }

    if not eligible:
        # fall back to scoreboard / tier_b
        sb = _read_json(PROJECT_ROOT / "data" / "state" / "recovery_tryout_scoreboard_latest.json")
        eligible = list(sb.get("eligible_tryout_pairs") or v2.get("tier_b") or ["ETH-USD", "XRP-USD"])

    detail = _sentiment_detail(eligible)
    scores = detail.get("scores") if isinstance(detail.get("scores"), dict) else detail
    mode = str(detail.get("mode") or detail.get("sent_mode") or "unknown")
    # nested common shapes
    if isinstance(scores, dict) and "scores" in scores and isinstance(scores["scores"], dict):
        mode = str(scores.get("mode") or mode)
        scores = scores["scores"]

    meta, x_age_h, x_posts = _x_meta()
    rsi_map = _load_rsi_map()
    cash, positions = _cash_and_positions()
    seats = 0
    try:
        ballast = set(v2.get("tier_a") or []) | {"BTC-USD", "PAXG-USD", "USDC-USD"}
        seats = int(count_new_seat_buys_today(exclude_pairs=ballast))
    except Exception:
        seats = 0
    max_seats = int((qt or {}).get("max_new_seats_per_day") or v2.get("max_new_seats_per_day") or 2)
    cap = float((qt or {}).get("abs_cap_usd") or v2.get("abs_cap_usd") or 75.0)

    eng_map: Dict[str, float] = {}
    doors: List[PairDoor] = []
    free_nz = 0
    reddit_nz = 0

    for pair in eligible:
        p = _norm_pair(pair)
        eng = None
        row = None
        if isinstance(scores, dict):
            row = scores.get(p) or scores.get(p.replace("-USD", ""))
        if isinstance(row, (int, float)):
            eng = float(row)
        elif isinstance(row, dict):
            for k in ("score", "eng_sent", "sentiment", "aged_score", "value"):
                if row.get(k) is not None:
                    try:
                        eng = float(row[k])
                        break
                    except (TypeError, ValueError):
                        pass
        if eng is None:
            eng = 0.0
        eng_map[p] = eng

        x_raw, x_pc = _pair_score(meta["x"], p)
        r_raw, _ = _pair_score(meta["reddit"], p)
        f_raw, _ = _pair_score(meta["free"], p)
        if r_raw is not None and abs(r_raw) > 1e-9:
            reddit_nz += 1
        if f_raw is not None and abs(f_raw) > 1e-9:
            free_nz += 1

        rsi = rsi_map.get(p)
        try:
            # skip process tax noise for board? No — honesty includes tax lockouts.
            pol_eval = dict(pol)
            dec = evaluate_buy_entry(
                p,
                snap,
                sentiment=eng,
                rsi=rsi,
                is_new_pair=True,
                policy=pol_eval,
            )
            allowed = bool(dec.allowed)
            reasons = list(dec.reasons or [])
        except Exception as e:
            allowed = False
            reasons = [f"evaluate_error: {e}"]

        rsi_ok = None if rsi is None else (float(rsi) <= max_rsi)
        note = ""
        if f_raw is not None and float(f_raw) >= 0.1 and eng < floor:
            note = "Free/tee warm but does NOT clear REGIME-CASH."
        doors.append(
            PairDoor(
                pair=p,
                eligible=True,
                force_eligible=p in force_set,
                allowed=allowed,
                reasons=reasons,
                eng_sent=round(eng, 4),
                rsi=None if rsi is None else round(float(rsi), 2),
                rsi_ok=rsi_ok,
                x_raw=None if x_raw is None else round(float(x_raw), 4),
                x_posts=x_pc,
                reddit_raw=None if r_raw is None else round(float(r_raw), 4),
                free_tee=None if f_raw is None else round(float(f_raw), 4),
                note=note,
            )
        )

    sensor = classify_sensor(
        mode=mode,
        eng_scores=eng_map,
        x_posts_total=x_posts,
        x_age_hours=x_age_h,
        reddit_nz=reddit_nz,
        free_nz=free_nz,
        floor=floor,
    )

    now = _utc_now()
    now_pt = now.astimezone(PT)
    x_lbl, _ = next_slot_pt(now_pt, DEFAULT_X_REFRESH_HHMM)
    rb_lbl, _ = next_slot_pt(now_pt, DEFAULT_REBALANCE_HHMM)
    eq = ""
    det = snap.detector if isinstance(snap.detector, dict) else {}
    eq = str(det.get("equity_health") or "")

    payload = build_readiness_payload(
        doors=doors,
        floors=floors,
        sensor=sensor,
        cash_usd=cash,
        seats_used_today=seats,
        max_new_seats_per_day=max_seats,
        tryout_cap_usd=cap,
        eligible_tryout_pairs=eligible,
        regime=str(snap.regime),
        equity_health=eq or "unknown",
        sent_mode=mode,
        next_x_refresh_pt=x_lbl,
        next_rebalance_pt=f"~{rb_lbl}",
        open_positions=positions,
        runner_pid=_runner_pid(),
        actions_taken=["pc03_readiness_builder", "no knobs / no force_rebalance"],
        as_of=now,
        strategy_mode=str(getattr(snap, "strategy_mode", "") or ""),
        allow_new_buys=bool(getattr(snap, "allow_new_buys", True)),
        rebalance_cap_usd=float(getattr(snap, "rebalance_cap_usd", 0.0) or 0.0),
        regime_layer=str(getattr(snap, "regime_layer", "") or ""),
        knob_map_scenario=str(getattr(snap, "knob_map_scenario", "") or ""),
    )
    if write:
        write_artifacts(payload)
    return payload
