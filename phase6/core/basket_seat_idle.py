#!/usr/bin/env python3
"""
Basket seat idle tracker — observational flag for membership cycling research.

Tracks calendar tenure + capital-idle days for each *active* trading basket seat.
Does NOT eject, promote, or place orders. Soft flag only for human/arm review.

Definitions (frozen for this tracker)
------------------------------------
- seat_days: calendar days since pair entered active basket (promote ledger /
  prior tracker state / first observation).
- days_since_buy: calendar days since last BUY fill in trades ledger (any time);
  null if no buy ever.
- buys_while_seated: BUY fills with timestamp >= active_since.
- flat: held_usd < flat_held_usd (default $40, same family as cycler protect).
- flat_day_streak: consecutive *calendar days* observed flat while active
  (requires daily refresh; first day sets 0 or 1).
- capital_idle_days: days_since_buy if seated with 0 buys; else max(0, days_since_buy)
  when flat; else 0 if held and recently bought.
- idle_cycle_flag (soft): not sticky AND seat_days >= min_seat_days AND
  (buys_while_seated == 0 OR days_since_buy >= min_idle_days) AND
  (flat OR require_flat is False).

This is the "long calendar idle as eject *candidate*" instrumentation —
compatible with membership design; not what M2 hard-gates today.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket
from phase6.core.pool_cycling import DEFAULT_STICKY, load_holdings_usd

STATE_DIR = PROJECT_ROOT / "data" / "state"
LATEST_PATH = STATE_DIR / "basket_seat_idle_latest.json"
HISTORY_JSONL = STATE_DIR / "basket_seat_idle_daily.jsonl"
PICK_METRICS_JSONL = STATE_DIR / "basket_pick_metrics.jsonl"
PROMOTE_LATEST = STATE_DIR / "basket_promote_latest.json"
TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

# Soft research defaults — not live eject thresholds.
DEFAULT_MIN_SEAT_DAYS = 7
DEFAULT_MIN_IDLE_DAYS = 7
DEFAULT_FLAT_HELD_USD = 40.0
STICKY_CORE = tuple(DEFAULT_STICKY)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _days_between(start: Optional[datetime], end: Optional[datetime] = None) -> Optional[int]:
    if start is None:
        return None
    end = end or _utc_now()
    d0 = start.astimezone(timezone.utc).date()
    d1 = end.astimezone(timezone.utc).date()
    return max(0, (d1 - d0).days)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def load_promote_seat_events(
    pick_path: Path = PICK_METRICS_JSONL,
    promote_latest_path: Path = PROMOTE_LATEST,
) -> List[Dict[str, Any]]:
    """Chronological seat add/remove events from pick metrics + promote latest."""
    events: List[Dict[str, Any]] = []
    for row in _load_jsonl(pick_path):
        ts = _parse_ts(row.get("promoted_at"))
        if ts is None:
            continue
        add = row.get("add_pair")
        rem = row.get("remove_pair")
        if add:
            events.append(
                {
                    "ts": ts,
                    "kind": "add",
                    "pair": str(add),
                    "source": str(row.get("source") or "pick_metrics"),
                    "pick_id": row.get("pick_id"),
                }
            )
        if rem:
            events.append(
                {
                    "ts": ts,
                    "kind": "remove",
                    "pair": str(rem),
                    "source": str(row.get("source") or "pick_metrics"),
                    "pick_id": row.get("pick_id"),
                }
            )
    pl = _load_json(promote_latest_path) or {}
    pts = _parse_ts(pl.get("ts") or pl.get("promoted_at"))
    for sw in pl.get("swaps") or []:
        if not isinstance(sw, dict):
            continue
        if pts is None:
            continue
        if sw.get("add"):
            events.append(
                {
                    "ts": pts,
                    "kind": "add",
                    "pair": str(sw["add"]),
                    "source": "promote_latest",
                    "pick_id": None,
                }
            )
        if sw.get("remove"):
            events.append(
                {
                    "ts": pts,
                    "kind": "remove",
                    "pair": str(sw["remove"]),
                    "source": "promote_latest",
                    "pick_id": None,
                }
            )
    events.sort(key=lambda e: e["ts"])
    # de-dupe identical (ts, kind, pair)
    seen = set()
    out: List[Dict[str, Any]] = []
    for e in events:
        key = (e["ts"].isoformat(), e["kind"], e["pair"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def load_config_bak_pair_presence(
    config_dir: Optional[Path] = None,
) -> List[Tuple[datetime, List[str], str]]:
    """
    Parse trading_config_phase6.json.bak_promote_YYYYMMDD_HHMMSS backups.
    Returns chronological (ts, pairs, path_name) — ts is bak filename time (when
    that snapshot was the live before-state at promote).
    """
    config_dir = config_dir or (PROJECT_ROOT / "config")
    out: List[Tuple[datetime, List[str], str]] = []
    if not config_dir.exists():
        return out
    for path in sorted(config_dir.glob("trading_config_phase6.json.bak_promote_*")):
        name = path.name
        # ...bak_promote_20260808_223445
        try:
            stamp = name.split("bak_promote_")[-1]
            dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        try:
            cfg = json.loads(path.read_text())
        except Exception:
            continue
        pairs = [str(p) for p in (cfg.get("global_settings") or {}).get("pairs") or []]
        if pairs:
            out.append((dt, pairs, name))
    out.sort(key=lambda x: x[0])
    return out


def lower_bound_active_since_from_baks(
    pair: str,
    *,
    baks: Optional[Sequence[Tuple[datetime, List[str], str]]] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Tuple[Optional[datetime], str]:
    """
    If pair never has a promote-add event after last remove, use earliest bak
    where pair is present and not later removed by a promote event before 'now'.
    This is a *lower bound* on tenure (pair may be older).
    """
    baks = list(baks if baks is not None else load_config_bak_pair_presence())
    events = list(events if events is not None else [])
    # last remove for pair
    last_rem: Optional[datetime] = None
    for e in events:
        if e.get("pair") == pair and e.get("kind") == "remove":
            last_rem = e["ts"]
    earliest: Optional[datetime] = None
    src = "config_bak_lower_bound"
    for ts, pairs, name in baks:
        if pair not in pairs:
            continue
        if last_rem is not None and ts < last_rem:
            continue
        if earliest is None or ts < earliest:
            earliest = ts
            src = f"config_bak_lower_bound:{name}"
    return earliest, src


def resolve_active_since(
    pair: str,
    *,
    events: Sequence[Dict[str, Any]],
    prior_row: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
    baks: Optional[Sequence[Tuple[datetime, List[str], str]]] = None,
) -> Tuple[Optional[datetime], str]:
    """
    Best active_since for a currently-active pair.

    Prefer last add event after any later remove. Fall back to prior tracker
    state, then config bak lower bound, then first_observation (caller stamps now).
    """
    now = now or _utc_now()
    last_add: Optional[datetime] = None
    last_rem: Optional[datetime] = None
    add_src = "promote_unknown"
    for e in events:
        if e.get("pair") != pair:
            continue
        if e["kind"] == "add":
            last_add = e["ts"]
            add_src = str(e.get("source") or "promote")
        elif e["kind"] == "remove":
            last_rem = e["ts"]
    if last_add is not None and (last_rem is None or last_add >= last_rem):
        return last_add, add_src

    if prior_row:
        pts = _parse_ts(prior_row.get("active_since"))
        if pts is not None:
            # If we saw a remove after prior active_since, don't trust prior.
            if last_rem is None or pts >= last_rem:
                src = str(prior_row.get("active_since_source") or "prior_state")
                # Prefer tighter (older) bak lower bound if prior was first_observation
                if src.startswith("first_observation") or src == "first_observation":
                    lb, lb_src = lower_bound_active_since_from_baks(
                        pair, baks=baks, events=events
                    )
                    if lb is not None and (last_rem is None or lb >= last_rem):
                        return lb, lb_src
                return pts, src

    lb, lb_src = lower_bound_active_since_from_baks(pair, baks=baks, events=events)
    if lb is not None and (last_rem is None or lb >= last_rem):
        return lb, lb_src

    return None, "first_observation"


def load_buy_events(trades_path: Path = TRADES_JSONL) -> List[Tuple[str, datetime]]:
    """Return (pair, ts) BUY fills chronological."""
    out: List[Tuple[str, datetime]] = []
    for row in _load_jsonl(trades_path):
        side = str(row.get("side") or row.get("action") or "").upper()
        if side != "BUY":
            continue
        pair = row.get("pair") or row.get("product_id")
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("time"))
        if not pair or ts is None:
            continue
        out.append((str(pair), ts))
    out.sort(key=lambda x: x[1])
    return out


def buys_for_pair(
    pair: str,
    buys: Sequence[Tuple[str, datetime]],
    *,
    since: Optional[datetime] = None,
) -> List[datetime]:
    rows = [ts for p, ts in buys if p == pair]
    if since is not None:
        rows = [ts for ts in rows if ts >= since]
    return rows


@dataclass
class SeatIdleConfig:
    min_seat_days: int = DEFAULT_MIN_SEAT_DAYS
    min_idle_days: int = DEFAULT_MIN_IDLE_DAYS
    flat_held_usd: float = DEFAULT_FLAT_HELD_USD
    require_flat_for_flag: bool = True
    sticky_pairs: Tuple[str, ...] = STICKY_CORE
    # When True, capital_idle uses "no buy while seated" even if older buys exist.
    idle_relative_to_seat: bool = True


@dataclass
class SeatIdleRow:
    pair: str
    active: bool
    sticky: bool
    active_since: Optional[str]
    active_since_source: str
    seat_days: Optional[int]
    held_usd: float
    flat: bool
    flat_day_streak: int
    last_buy_at: Optional[str]
    days_since_buy: Optional[int]
    buys_while_seated: int
    capital_idle_days: Optional[int]
    idle_cycle_flag: bool
    idle_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_idle_flag(
    *,
    sticky: bool,
    seat_days: Optional[int],
    buys_while_seated: int,
    days_since_buy: Optional[int],
    flat: bool,
    cfg: SeatIdleConfig,
) -> Tuple[bool, List[str], Optional[int]]:
    reasons: List[str] = []
    if sticky:
        return False, ["sticky_core"], 0

    # capital idle days for reporting
    if cfg.idle_relative_to_seat:
        if buys_while_seated == 0:
            cap_idle = seat_days
            reasons.append("no_buy_while_seated")
        else:
            cap_idle = days_since_buy
    else:
        cap_idle = days_since_buy if days_since_buy is not None else seat_days

    if seat_days is not None and seat_days >= cfg.min_seat_days:
        reasons.append(f"seat_days>={cfg.min_seat_days}")
    if cap_idle is not None and cap_idle >= cfg.min_idle_days:
        reasons.append(f"capital_idle_days>={cfg.min_idle_days}")
    if flat:
        reasons.append("flat_held")
    elif cfg.require_flat_for_flag:
        reasons.append("not_flat")

    seat_ok = seat_days is not None and seat_days >= cfg.min_seat_days
    idle_ok = cap_idle is not None and cap_idle >= cfg.min_idle_days
    # If never bought while seated, seat_days already counts as capital idle.
    if buys_while_seated == 0 and seat_ok:
        idle_ok = True
    flat_ok = flat if cfg.require_flat_for_flag else True

    flag = bool(seat_ok and idle_ok and flat_ok)
    if flag and "idle_cycle_candidate" not in reasons:
        reasons.append("idle_cycle_candidate")
    if not flag:
        # keep diagnostic reasons only
        pass
    return flag, reasons, cap_idle


def _prior_flat_streak(prior: Optional[Dict[str, Any]], today: date, flat: bool) -> int:
    if not flat:
        return 0
    if not prior:
        return 1
    prev_day_s = prior.get("as_of_date") or (str(prior.get("ts") or "")[:10] or None)
    prev_streak = int(prior.get("flat_day_streak") or 0)
    prev_flat = bool(prior.get("flat"))
    if not prev_day_s or not prev_flat:
        return 1
    try:
        prev_day = date.fromisoformat(str(prev_day_s)[:10])
    except ValueError:
        return 1
    delta = (today - prev_day).days
    if delta <= 0:
        # same calendar day re-run: keep streak
        return max(1, prev_streak)
    if delta == 1:
        return prev_streak + 1
    # gap in observations — restart streak but note discontinuity by returning 1
    return 1


def build_seat_idle_snapshot(
    *,
    active: Optional[Sequence[str]] = None,
    holdings: Optional[Dict[str, float]] = None,
    prior_latest: Optional[Dict[str, Any]] = None,
    buys: Optional[Sequence[Tuple[str, datetime]]] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
    cfg: Optional[SeatIdleConfig] = None,
    now: Optional[datetime] = None,
    write: bool = False,
) -> Dict[str, Any]:
    """Build full snapshot for active basket. Optionally persist latest + daily jsonl."""
    cfg = cfg or SeatIdleConfig()
    now = now or _utc_now()
    today = now.astimezone(timezone.utc).date()
    active_l = [str(p) for p in (active if active is not None else load_trading_basket())]
    holdings = holdings if holdings is not None else load_holdings_usd()
    prior_latest = prior_latest if prior_latest is not None else (_load_json(LATEST_PATH) or {})
    prior_pairs = (prior_latest.get("pairs") or {}) if isinstance(prior_latest, dict) else {}
    events = list(events if events is not None else load_promote_seat_events())
    buys = list(buys if buys is not None else load_buy_events())
    sticky_set = set(cfg.sticky_pairs)

    rows: List[SeatIdleRow] = []
    for pair in active_l:
        prior = prior_pairs.get(pair) if isinstance(prior_pairs, dict) else None
        if prior is not None and not isinstance(prior, dict):
            prior = None
        since_dt, since_src = resolve_active_since(pair, events=events, prior_row=prior, now=now)
        notes: List[str] = []
        if since_dt is None:
            since_dt = now
            since_src = "first_observation"
            notes.append("active_since_seeded_now")
        seat_days = _days_between(since_dt, now)
        held = float(holdings.get(pair, 0.0) or 0.0)
        flat = held < float(cfg.flat_held_usd)
        streak = _prior_flat_streak(prior, today, flat)

        all_buys = buys_for_pair(pair, buys, since=None)
        seated_buys = buys_for_pair(pair, buys, since=since_dt)
        last_buy = all_buys[-1] if all_buys else None
        days_since_buy = _days_between(last_buy, now) if last_buy else None
        sticky = pair in sticky_set
        flag, reasons, cap_idle = compute_idle_flag(
            sticky=sticky,
            seat_days=seat_days,
            buys_while_seated=len(seated_buys),
            days_since_buy=days_since_buy,
            flat=flat,
            cfg=cfg,
        )
        rows.append(
            SeatIdleRow(
                pair=pair,
                active=True,
                sticky=sticky,
                active_since=since_dt.isoformat(),
                active_since_source=since_src,
                seat_days=seat_days,
                held_usd=round(held, 4),
                flat=flat,
                flat_day_streak=streak,
                last_buy_at=last_buy.isoformat() if last_buy else None,
                days_since_buy=days_since_buy,
                buys_while_seated=len(seated_buys),
                capital_idle_days=cap_idle,
                idle_cycle_flag=flag,
                idle_reasons=reasons,
                notes=notes,
            )
        )

    flagged = [r for r in rows if r.idle_cycle_flag]
    snapshot: Dict[str, Any] = {
        "ts": now.isoformat(),
        "as_of_date": today.isoformat(),
        "schema": "basket_seat_idle_v1",
        "mode": "observe_only",
        "hard_eject": False,
        "config": {
            "min_seat_days": cfg.min_seat_days,
            "min_idle_days": cfg.min_idle_days,
            "flat_held_usd": cfg.flat_held_usd,
            "require_flat_for_flag": cfg.require_flat_for_flag,
            "sticky_pairs": list(cfg.sticky_pairs),
            "idle_relative_to_seat": cfg.idle_relative_to_seat,
        },
        "active_basket": active_l,
        "n_active": len(active_l),
        "n_idle_flagged": len(flagged),
        "idle_flagged_pairs": [r.pair for r in flagged],
        "pairs": {r.pair: r.as_dict() for r in rows},
        "rows": [r.as_dict() for r in rows],
        "note": (
            "Soft cycle-out candidate flag only. Does not change membership, "
            "scores, or orders. Wire into eject policy only after Brad OK + evidence."
        ),
    }

    if write:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(snapshot, indent=2, default=str) + "\n")
        # One compact daily line (overwrite same-day by rewrite filter)
        compact = {
            "ts": snapshot["ts"],
            "as_of_date": snapshot["as_of_date"],
            "n_idle_flagged": snapshot["n_idle_flagged"],
            "idle_flagged_pairs": snapshot["idle_flagged_pairs"],
            "pairs": {
                p: {
                    "seat_days": d.get("seat_days"),
                    "capital_idle_days": d.get("capital_idle_days"),
                    "flat_day_streak": d.get("flat_day_streak"),
                    "held_usd": d.get("held_usd"),
                    "idle_cycle_flag": d.get("idle_cycle_flag"),
                    "buys_while_seated": d.get("buys_while_seated"),
                    "active_since": d.get("active_since"),
                }
                for p, d in snapshot["pairs"].items()
            },
        }
        prev_lines = []
        if HISTORY_JSONL.exists():
            for line in HISTORY_JSONL.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    prev_lines.append(line)
                    continue
                if str(obj.get("as_of_date") or "") == today.isoformat():
                    continue  # replace today's line
                prev_lines.append(json.dumps(obj, default=str))
        prev_lines.append(json.dumps(compact, default=str))
        HISTORY_JSONL.write_text("\n".join(prev_lines) + "\n")

    return snapshot


def idle_flag_map(snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """pair -> {idle_cycle_flag, seat_days, capital_idle_days, ...} for cycler annotate."""
    snap = snapshot if snapshot is not None else (_load_json(LATEST_PATH) or {})
    pairs = snap.get("pairs") or {}
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(pairs, dict):
        return out
    for pair, row in pairs.items():
        if not isinstance(row, dict):
            continue
        out[str(pair)] = {
            "idle_cycle_flag": bool(row.get("idle_cycle_flag")),
            "seat_days": row.get("seat_days"),
            "capital_idle_days": row.get("capital_idle_days"),
            "flat_day_streak": row.get("flat_day_streak"),
            "held_usd": row.get("held_usd"),
            "idle_reasons": list(row.get("idle_reasons") or []),
        }
    return out


def annotate_scores_with_idle(
    scores: Iterable[Any],
    idle_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """
    Soft-annotate PairScore-like objects: append idle tag to reason string.
    Does not change score or propose swaps. Returns count annotated.
    """
    idle_map = idle_map if idle_map is not None else idle_flag_map()
    n = 0
    for s in scores:
        pair = getattr(s, "pair", None) or (s.get("pair") if isinstance(s, dict) else None)
        if not pair:
            continue
        info = idle_map.get(str(pair)) or {}
        if not info.get("idle_cycle_flag"):
            continue
        tag = (
            f" | IDLE_SEAT_FLAG seat_days={info.get('seat_days')} "
            f"cap_idle={info.get('capital_idle_days')} "
            f"flat_streak={info.get('flat_day_streak')}"
        )
        if isinstance(s, dict):
            reason = str(s.get("reason") or "")
            if "IDLE_SEAT_FLAG" not in reason:
                s["reason"] = reason + tag
                s["idle_cycle_flag"] = True
                n += 1
        else:
            reason = str(getattr(s, "reason", "") or "")
            if "IDLE_SEAT_FLAG" not in reason:
                try:
                    s.reason = reason + tag  # type: ignore[attr-defined]
                except Exception:
                    pass
                if hasattr(s, "__dict__"):
                    s.__dict__["idle_cycle_flag"] = True
                n += 1
    return n
