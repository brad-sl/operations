"""Cron reliability nudge for daily rebalance slots.

When a continuous Phase6Runner is already up, Hermes morning/evening cron
touches ``force_rebalance.flag``. That was a dual-fire with the runner's own
``daily_rebalance_times`` (natural 09:00/21:00 + cron 09:05/21:05).

Policy (Brad 2026-09-23):
  Skip the force nudge if the *due* slot already completed successfully in the
  last ~10 minutes. Still nudge when the runner is up but the slot was missed
  or never finalized (outage / defer / crash recovery).

Manual ``touch force_rebalance.flag`` and ``--force-nudge`` on the cron wrapper
always bypass this skip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from phase6.core.paths import PHASE6_RUNNER_STATE, REBALANCE_HISTORY
from phase6.core.rebalance_quality_gate import HARD_FAIL_MARKERS

DEFAULT_WINDOW_MINUTES = 10.0
DEFAULT_SLOT_TIMES = ("09:00", "21:00")


@dataclass(frozen=True)
class NudgeDecision:
    """Whether the reliability cron should touch force_rebalance.flag."""

    should_touch: bool
    reason: str
    slot_id: Optional[str] = None
    age_minutes: Optional[float] = None
    last_event_ts: Optional[str] = None
    executed: Optional[int] = None
    skipped: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "should_touch": self.should_touch,
            "reason": self.reason,
            "slot_id": self.slot_id,
            "age_minutes": self.age_minutes,
            "last_event_ts": self.last_event_ts,
            "executed": self.executed,
            "skipped": self.skipped,
        }


def due_rebalance_slot_id(
    now: Optional[datetime] = None,
    slot_times: Sequence[str] = DEFAULT_SLOT_TIMES,
) -> Optional[str]:
    """Mirror Phase6Runner._due_rebalance_slot_id (latest past slot today)."""
    now = now or datetime.now()
    if now.tzinfo is not None:
        # Compare wall-clock local slot strings against local time components.
        now = now.astimezone().replace(tzinfo=None)
    current_date = now.date()
    current_t = now.time()
    parsed: List[tuple[str, dt_time]] = []
    for t_str in slot_times:
        try:
            parsed.append((str(t_str), dt_time.fromisoformat(str(t_str))))
        except ValueError:
            parsed.append((str(t_str), dt_time(9, 0)))
    parsed.sort(key=lambda x: x[1])
    due: Optional[tuple[str, dt_time]] = None
    for t_str, target in parsed:
        if current_t >= target:
            due = (t_str, target)
        else:
            break
    if due is None:
        return None
    return f"{current_date.isoformat()}|{due[0]}"


def _parse_event_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        # Heuristic: ms vs s
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
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
    except ValueError:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _tail_jsonl(path: Path, max_lines: int = 40) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines[-max_lines:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _completed_slots(runner_state: Dict[str, Any]) -> Set[str]:
    raw = runner_state.get("rebalance_slots_completed") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if x}


def _event_hard_failed(event: Dict[str, Any]) -> bool:
    """True if history row looks like outage / not a clean finalize."""
    blob_parts: List[str] = []
    for key in ("reason", "error", "status", "note"):
        if event.get(key) is not None:
            blob_parts.append(str(event.get(key)))
    skipped = event.get("skipped")
    # skipped may be int count or list of reason dicts
    if isinstance(skipped, list):
        for item in skipped:
            blob_parts.append(str(item))
    blob = " ".join(blob_parts).lower()
    if any(m in blob for m in HARD_FAIL_MARKERS):
        return True
    if str(event.get("gate") or "").lower() in {"blocked", "deferred", "fail"}:
        return True
    return False


def latest_daily_rebalance_event(
    history_rows: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Most recent daily_rebalance row (by timestamp)."""
    best: Optional[Dict[str, Any]] = None
    best_ts: Optional[datetime] = None
    for row in history_rows:
        reason = str(row.get("reason") or "")
        # Keep fresh_start / capital events out of the nudge window signal.
        if reason != "daily_rebalance":
            continue
        ts = _parse_event_ts(row.get("timestamp") or row.get("ts") or row.get("time"))
        if ts is None:
            continue
        if best_ts is None or ts >= best_ts:
            best_ts = ts
            best = dict(row)
            best["_parsed_ts"] = ts
    return best


def decide_force_nudge(
    *,
    runner_running: bool,
    now: Optional[datetime] = None,
    window_minutes: float = DEFAULT_WINDOW_MINUTES,
    slot_times: Sequence[str] = DEFAULT_SLOT_TIMES,
    runner_state: Optional[Dict[str, Any]] = None,
    history_rows: Optional[Sequence[Dict[str, Any]]] = None,
    force_nudge: bool = False,
    runner_state_path: Path = PHASE6_RUNNER_STATE,
    history_path: Path = REBALANCE_HISTORY,
) -> NudgeDecision:
    """
    Return whether cron should touch force_rebalance.flag.

    Skip only when continuous runner is up AND due slot already completed AND
    a clean daily_rebalance finalize is within ``window_minutes``.
    """
    now_utc = datetime.now(timezone.utc)
    now_local = now or datetime.now()

    if force_nudge:
        return NudgeDecision(
            should_touch=True,
            reason="force_nudge_override",
            slot_id=due_rebalance_slot_id(now_local, slot_times),
        )

    if not runner_running:
        # Caller spawns one-shot runner; this helper is only for the flag path.
        return NudgeDecision(
            should_touch=False,
            reason="runner_not_running_use_oneshot",
            slot_id=due_rebalance_slot_id(now_local, slot_times),
        )

    slot_id = due_rebalance_slot_id(now_local, slot_times)
    if slot_id is None:
        # Before first daily slot — no reliability nudge needed.
        return NudgeDecision(
            should_touch=False,
            reason="no_due_slot_yet",
            slot_id=None,
        )

    state = runner_state if runner_state is not None else _load_json(Path(runner_state_path))
    completed = _completed_slots(state)
    if slot_id not in completed:
        return NudgeDecision(
            should_touch=True,
            reason="due_slot_not_completed",
            slot_id=slot_id,
        )

    rows = (
        list(history_rows)
        if history_rows is not None
        else _tail_jsonl(Path(history_path), max_lines=60)
    )
    latest = latest_daily_rebalance_event(rows)
    if latest is None:
        # Slot marked but no history — trust slot mark lightly; still nudge once
        # so a silent finalize hole can recover. Operator can tighten later.
        return NudgeDecision(
            should_touch=True,
            reason="slot_complete_but_no_history",
            slot_id=slot_id,
        )

    ts: datetime = latest["_parsed_ts"]  # type: ignore[assignment]
    age_min = (now_utc - ts.astimezone(timezone.utc)).total_seconds() / 60.0
    executed = latest.get("executed")
    skipped = latest.get("skipped")
    try:
        executed_i = int(executed) if executed is not None else None
    except (TypeError, ValueError):
        executed_i = None
    try:
        if isinstance(skipped, list):
            skipped_i = len(skipped)
        elif skipped is None:
            skipped_i = None
        else:
            skipped_i = int(skipped)
    except (TypeError, ValueError):
        skipped_i = None

    if _event_hard_failed(latest):
        return NudgeDecision(
            should_touch=True,
            reason="recent_event_hard_fail",
            slot_id=slot_id,
            age_minutes=round(age_min, 3),
            last_event_ts=str(latest.get("timestamp") or latest.get("ts") or ""),
            executed=executed_i,
            skipped=skipped_i,
        )

    if age_min <= float(window_minutes):
        return NudgeDecision(
            should_touch=False,
            reason="slot_completed_recently",
            slot_id=slot_id,
            age_minutes=round(age_min, 3),
            last_event_ts=str(latest.get("timestamp") or latest.get("ts") or ""),
            executed=executed_i,
            skipped=skipped_i,
        )

    return NudgeDecision(
        should_touch=True,
        reason="slot_complete_but_stale_finalize",
        slot_id=slot_id,
        age_minutes=round(age_min, 3),
        last_event_ts=str(latest.get("timestamp") or latest.get("ts") or ""),
        executed=executed_i,
        skipped=skipped_i,
    )
