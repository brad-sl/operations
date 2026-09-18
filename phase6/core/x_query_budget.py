#!/usr/bin/env python3
"""Hard daily budget for paid X queries (RSI probe + rebalance candidates).

Doctrine (Brad GO 2026-09-18 validate):
- Count pair-queries, not API call batches (honest cost proxy).
- RSI probe and rebalance share one day counter unless separated explicitly.
- Never place orders from this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.paths import STATE_DIR

SCHEMA = "x_query_budget_v1"
DEFAULT_PATH = STATE_DIR / "x_query_budget.json"
PT = timezone.utc  # day key uses America/Los_Angeles via zoneinfo when available


def _pt_day_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo("America/Los_Angeles"))
    except Exception:
        local = now
    return local.strftime("%Y-%m-%d")


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if s and "-" not in s:
        s = f"{s}-USD"
    return s


@dataclass
class BudgetConfig:
    """Hard caps — Brad GO can tighten; do not loosen in code without GO."""

    max_pair_queries_per_day: int = 6  # total RSI+rebal pair-queries
    max_rsi_pair_queries_per_day: int = 2
    max_rebal_pair_queries_per_day: int = 4
    per_pair_cooldown_hours: float = 6.0
    path: Path = field(default_factory=lambda: DEFAULT_PATH)


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str
    day: str
    would_add: int
    remaining_day: int
    remaining_lane: int
    blocked_pairs: List[str] = field(default_factory=list)
    allowed_pairs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _empty_state(day: str) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "day_pt": day,
        "pair_queries": 0,
        "rsi_pair_queries": 0,
        "rebal_pair_queries": 0,
        "by_pair": {},  # pair -> {last_ts, count_day}
        "events": [],
    }


def load_budget(path: Optional[Path] = None, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    path = path or DEFAULT_PATH
    day = _pt_day_key(now)
    if not path.exists():
        return _empty_state(day)
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return _empty_state(day)
    if str(raw.get("day_pt") or "") != day:
        return _empty_state(day)
    raw.setdefault("schema", SCHEMA)
    raw.setdefault("pair_queries", 0)
    raw.setdefault("rsi_pair_queries", 0)
    raw.setdefault("rebal_pair_queries", 0)
    raw.setdefault("by_pair", {})
    raw.setdefault("events", [])
    return raw


def save_budget(state: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str) + "\n")
    os.replace(tmp, path)
    return path


def _pair_cooled(
    state: Dict[str, Any],
    pair: str,
    *,
    cooldown_h: float,
    now: datetime,
) -> bool:
    row = (state.get("by_pair") or {}).get(pair) or {}
    ts = row.get("last_ts")
    if not ts:
        return True
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    age_h = (now - last).total_seconds() / 3600.0
    return age_h >= float(cooldown_h)


def check_can_spend(
    pairs: Sequence[str],
    *,
    lane: str,  # "rsi" | "rebal"
    cfg: Optional[BudgetConfig] = None,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> BudgetDecision:
    cfg = cfg or BudgetConfig()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = _pt_day_key(now)
    state = state if state is not None else load_budget(cfg.path, now=now)
    norms = [_norm_pair(p) for p in pairs if _norm_pair(p)]
    # de-dupe preserve order
    seen = set()
    ordered: List[str] = []
    for p in norms:
        if p not in seen:
            seen.add(p)
            ordered.append(p)

    lane = (lane or "").strip().lower()
    if lane not in ("rsi", "rebal"):
        return BudgetDecision(
            allowed=False,
            reason=f"bad_lane:{lane}",
            day=day,
            would_add=0,
            remaining_day=0,
            remaining_lane=0,
            blocked_pairs=ordered,
        )

    day_used = int(state.get("pair_queries") or 0)
    lane_key = "rsi_pair_queries" if lane == "rsi" else "rebal_pair_queries"
    lane_used = int(state.get(lane_key) or 0)
    lane_cap = (
        int(cfg.max_rsi_pair_queries_per_day)
        if lane == "rsi"
        else int(cfg.max_rebal_pair_queries_per_day)
    )
    day_cap = int(cfg.max_pair_queries_per_day)
    rem_day = max(0, day_cap - day_used)
    rem_lane = max(0, lane_cap - lane_used)
    room = min(rem_day, rem_lane)

    allowed_pairs: List[str] = []
    blocked: List[str] = []
    for p in ordered:
        if not _pair_cooled(state, p, cooldown_h=cfg.per_pair_cooldown_hours, now=now):
            blocked.append(p)
            continue
        if len(allowed_pairs) >= room:
            blocked.append(p)
            continue
        allowed_pairs.append(p)

    if not ordered:
        return BudgetDecision(
            allowed=False,
            reason="empty_pairs",
            day=day,
            would_add=0,
            remaining_day=rem_day,
            remaining_lane=rem_lane,
        )
    if not allowed_pairs:
        why = "day_or_lane_exhausted" if room <= 0 else "all_pairs_cooldown_or_blocked"
        return BudgetDecision(
            allowed=False,
            reason=why,
            day=day,
            would_add=0,
            remaining_day=rem_day,
            remaining_lane=rem_lane,
            blocked_pairs=blocked or ordered,
        )
    return BudgetDecision(
        allowed=True,
        reason="ok",
        day=day,
        would_add=len(allowed_pairs),
        remaining_day=rem_day,
        remaining_lane=rem_lane,
        blocked_pairs=blocked,
        allowed_pairs=allowed_pairs,
    )


def record_spend(
    pairs: Sequence[str],
    *,
    lane: str,
    cfg: Optional[BudgetConfig] = None,
    now: Optional[datetime] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Persist spend after a successful paid X fetch. Caller must only pass pairs actually fetched."""
    cfg = cfg or BudgetConfig()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    state = load_budget(cfg.path, now=now)
    dec = check_can_spend(pairs, lane=lane, cfg=cfg, state=state, now=now)
    if not dec.allowed or not dec.allowed_pairs:
        return {"ok": False, "decision": dec.to_dict(), "state": state}

    ts = now.isoformat()
    by_pair = dict(state.get("by_pair") or {})
    for p in dec.allowed_pairs:
        prev = dict(by_pair.get(p) or {})
        prev["last_ts"] = ts
        prev["count_day"] = int(prev.get("count_day") or 0) + 1
        by_pair[p] = prev
    n = len(dec.allowed_pairs)
    state["by_pair"] = by_pair
    state["pair_queries"] = int(state.get("pair_queries") or 0) + n
    if lane == "rsi":
        state["rsi_pair_queries"] = int(state.get("rsi_pair_queries") or 0) + n
    else:
        state["rebal_pair_queries"] = int(state.get("rebal_pair_queries") or 0) + n
    ev = list(state.get("events") or [])
    ev.append(
        {
            "ts": ts,
            "lane": lane,
            "pairs": list(dec.allowed_pairs),
            "n": n,
            "note": note or "",
        }
    )
    state["events"] = ev[-50:]
    save_budget(state, cfg.path)
    return {"ok": True, "decision": dec.to_dict(), "state": state}
