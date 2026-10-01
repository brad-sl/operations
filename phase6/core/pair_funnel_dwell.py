#!/usr/bin/env python3
"""Pair funnel stage dwell — measure-only profiles (Brad 2026-09-26).

Job
---
Track how long each pair spends in each funnel stage so we can later
spot behavior patterns (fast SL, long dual-clear starve, ladder survivors).

**Not prediction yet.** `predict_enabled` stays false in config until N exists.
No orders. No knobs. Crumbs only.

Stages SSOT: `config/pair_funnel_stages.json` (not hardcoded lists in callers).

Artifacts
---------
  data/state/pair_funnel_dwell_latest.json   — open segments + tick summary
  data/state/pair_funnel_profiles.json       — per-pair dwell aggregates
  data/state/pair_funnel_dwell_events.jsonl  — stage transitions
  reports/PAIR_FUNNEL_DWELL_LATEST.md
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "pair_funnel_dwell_v1"
PROFILE_SCHEMA = "pair_funnel_profile_v1"
CONFIG_PATH = PROJECT_ROOT / "config" / "pair_funnel_stages.json"
LATEST_PATH = STATE_DIR / "pair_funnel_dwell_latest.json"
PROFILES_PATH = STATE_DIR / "pair_funnel_profiles.json"
EVENTS_PATH = STATE_DIR / "pair_funnel_dwell_events.jsonl"
OPEN_LOTS_PATH = STATE_DIR / "tryout_scale_up_open_lots.json"
COMPOSER_LATEST = STATE_DIR / "rsi_event_tryout_seat_composer_latest.json"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "PAIR_FUNNEL_DWELL_LATEST.md"

# Fallback only if config missing — prefer file SSOT
_FALLBACK_STAGES = [
    {"id": "door_eligible", "order": 10, "terminal": False},
    {"id": "rsi_wash", "order": 20, "terminal": False},
    {"id": "dual_clear", "order": 30, "terminal": False},
    {"id": "tryout_open", "order": 40, "terminal": False},
    {"id": "ladder", "order": 50, "terminal": False},
    {"id": "exit_sl", "order": 90, "terminal": True, "outcome_class": "loss_or_tax"},
    {"id": "exit_tp", "order": 91, "terminal": True, "outcome_class": "win"},
    {"id": "exit_other", "order": 92, "terminal": True, "outcome_class": "other"},
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    except Exception:
        return None


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("load %s failed: %s", path, e)
    return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def load_stages_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """SSOT stage definitions from config file."""
    p = path or CONFIG_PATH
    raw = _load_json(p, None)
    if not isinstance(raw, dict) or not isinstance(raw.get("stages"), list):
        return {
            "schema": "pair_funnel_stages_v1",
            "stages": list(_FALLBACK_STAGES),
            "profile": {"min_closed_rts_for_pattern": 5, "predict_enabled": False},
            "tick": {
                "include_composer_candidates": True,
                "include_open_lots": True,
                "include_ledger_exits": True,
                "ledger_lookback_rows": 4000,
            },
            "config_path": str(p),
            "config_ok": False,
        }
    out = dict(raw)
    out["config_path"] = str(p)
    out["config_ok"] = True
    return out


def stage_ids(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    c = cfg or load_stages_config()
    raw_stages = c.get("stages")
    stages: List[Any] = raw_stages if isinstance(raw_stages, list) else list(_FALLBACK_STAGES)
    ordered = sorted(
        [s for s in stages if isinstance(s, dict) and s.get("id")],
        key=lambda s: int(s.get("order") or 0),
    )
    return [str(s["id"]) for s in ordered]


def is_terminal_stage(stage_id: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    c = cfg or load_stages_config()
    for s in c.get("stages") or []:
        if isinstance(s, dict) and str(s.get("id")) == stage_id:
            return bool(s.get("terminal"))
    return str(stage_id).startswith("exit_")


def classify_exit_stage(exit_reason: Any, cfg: Optional[Dict[str, Any]] = None) -> str:
    """Map ledger/exit reason → terminal stage id (tryout_exit_taxonomy SSOT)."""
    try:
        from phase6.core.tryout_exit_taxonomy import (
            classify_closed_class,
            closed_class_to_dwell_stage,
        )

        return closed_class_to_dwell_stage(classify_closed_class(exit_reason))
    except Exception:
        r = str(exit_reason or "").lower()
        if any(
            k in r
            for k in (
                "stop",
                "sl_",
                "_sl",
                "stop_loss",
                "missfire",
                "hard_exit",
                "liquidation",
            )
        ):
            return "exit_sl"
        if any(
            k in r
            for k in (
                "take_profit",
                "tp_",
                "trail",
                "dual_peak",
                "profit",
                "fixed_tp",
            )
        ):
            return "exit_tp"
        if "tryout_scale_window" in r or "scale_window" in r:
            return "exit_scale_window"
        return "exit_other"


@dataclass
class OpenSegment:
    pair: str
    stage: str
    entered_at: str
    source: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _empty_state() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "open": {},  # pair -> OpenSegment dict
        "updated_at": _utc_iso(),
        "last_tick": None,
    }


def load_dwell_state(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load open-segment state.

    `pair_funnel_dwell_latest.json` is a **tick payload** with nested
    `state.open`. Older/partial writes may put `open` at the top level.
    Always unwrap so monthly + hooks see live segments.
    """
    raw = _load_json(path or LATEST_PATH, None)
    if not isinstance(raw, dict):
        return _empty_state()
    nested = raw.get("state") if isinstance(raw.get("state"), dict) else None
    src = nested if nested is not None else raw
    out = _empty_state()
    # Prefer nested state fields; fall back to top-level open if present
    open_raw = src.get("open")
    if not isinstance(open_raw, dict):
        open_raw = raw.get("open") if isinstance(raw.get("open"), dict) else {}
    out["open"] = open_raw if isinstance(open_raw, dict) else {}
    for k in ("updated_at", "last_tick", "open_summary", "stages", "schema"):
        if src.get(k) is not None:
            out[k] = src.get(k)
        elif raw.get(k) is not None and k in ("open_summary", "stages"):
            out[k] = raw.get(k)
    out["schema"] = SCHEMA
    if not out.get("updated_at"):
        out["updated_at"] = str(raw.get("as_of") or raw.get("updated_at") or _utc_iso())
    return out


def load_profiles(path: Optional[Path] = None) -> Dict[str, Any]:
    raw = _load_json(path or PROFILES_PATH, None)
    if not isinstance(raw, dict):
        return {
            "schema": PROFILE_SCHEMA,
            "pairs": {},
            "updated_at": _utc_iso(),
            "predict_enabled": False,
        }
    out = {
        "schema": PROFILE_SCHEMA,
        "pairs": raw.get("pairs") if isinstance(raw.get("pairs"), dict) else {},
        "updated_at": str(raw.get("updated_at") or _utc_iso()),
        "predict_enabled": bool(raw.get("predict_enabled")),
        "note": raw.get("note"),
    }
    return out


def _ensure_pair_profile(profiles: Dict[str, Any], pair: str) -> Dict[str, Any]:
    pairs = profiles.setdefault("pairs", {})
    p = _norm_pair(pair)
    row = pairs.get(p)
    if not isinstance(row, dict):
        row = {
            "pair": p,
            "stage_dwell": {},  # stage -> {n, total_h, samples_h, last_h, mean_h, p50_h}
            "transitions": 0,
            "closed_rts": 0,
            "outcomes": {"win": 0, "loss_or_tax": 0, "other": 0},
            "last_stage": None,
            "last_event_at": None,
            "pattern_hint": None,
        }
        pairs[p] = row
    if not isinstance(row.get("stage_dwell"), dict):
        row["stage_dwell"] = {}
    if not isinstance(row.get("outcomes"), dict):
        row["outcomes"] = {"win": 0, "loss_or_tax": 0, "other": 0}
    return row


def _record_dwell(
    profiles: Dict[str, Any],
    *,
    pair: str,
    stage: str,
    dwell_h: float,
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    if dwell_h < 0:
        dwell_h = 0.0
    row = _ensure_pair_profile(profiles, pair)
    sd = row["stage_dwell"]
    cell = sd.get(stage) if isinstance(sd.get(stage), dict) else None
    if cell is None:
        cell = {
            "n": 0,
            "total_h": 0.0,
            "samples_h": [],
            "last_h": None,
            "mean_h": None,
            "p50_h": None,
        }
        sd[stage] = cell
    samples: List[float] = list(cell.get("samples_h") or [])
    # Cap sample list to keep profiles small
    samples.append(round(float(dwell_h), 4))
    if len(samples) > 50:
        samples = samples[-50:]
    n = int(cell.get("n") or 0) + 1
    total = float(cell.get("total_h") or 0.0) + float(dwell_h)
    mean = total / n if n else None
    p50 = statistics.median(samples) if samples else None
    cell.update(
        {
            "n": n,
            "total_h": round(total, 4),
            "samples_h": samples,
            "last_h": round(float(dwell_h), 4),
            "mean_h": round(mean, 4) if mean is not None else None,
            "p50_h": round(float(p50), 4) if p50 is not None else None,
        }
    )
    row["transitions"] = int(row.get("transitions") or 0) + 1
    row["last_stage"] = stage
    row["last_event_at"] = _utc_iso()


def _outcome_class_for_stage(stage: str, cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    c = cfg or load_stages_config()
    for s in c.get("stages") or []:
        if isinstance(s, dict) and str(s.get("id")) == stage:
            oc = s.get("outcome_class")
            return str(oc) if oc else None
    if stage == "exit_tp":
        return "win"
    if stage == "exit_sl":
        return "loss_or_tax"
    if stage.startswith("exit_"):
        return "other"
    return None


def _pattern_hint(row: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[str]:
    """Cheap heuristic label — not a model. Needs min closed RTs."""
    prof_raw = cfg.get("profile")
    prof: Dict[str, Any] = prof_raw if isinstance(prof_raw, dict) else {}
    need = int(prof.get("min_closed_rts_for_pattern") or 5)
    closed = int(row.get("closed_rts") or 0)
    if closed < need:
        return f"insufficient_n closed_rts={closed}<{need}"
    sd_raw = row.get("stage_dwell")
    sd: Dict[str, Any] = sd_raw if isinstance(sd_raw, dict) else {}
    tryout_raw = sd.get("tryout_open")
    dual_raw = sd.get("dual_clear")
    tryout: Dict[str, Any] = tryout_raw if isinstance(tryout_raw, dict) else {}
    dual: Dict[str, Any] = dual_raw if isinstance(dual_raw, dict) else {}
    outcomes_raw = row.get("outcomes")
    outcomes: Dict[str, Any] = outcomes_raw if isinstance(outcomes_raw, dict) else {}
    wins = int(outcomes.get("win") or 0)
    losses = int(outcomes.get("loss_or_tax") or 0)
    mean_try = tryout.get("mean_h")
    mean_dual = dual.get("mean_h")
    hints: List[str] = []
    if mean_try is not None and float(mean_try) < 2.0 and losses >= wins:
        hints.append("fast_tryout_exit")
    if mean_try is not None and float(mean_try) >= 24.0:
        hints.append("long_tryout_dwell")
    if mean_dual is not None and float(mean_dual) >= 6.0 and int(dual.get("n") or 0) >= 3:
        hints.append("slow_dual_clear_convert")
    if wins > 0 and losses == 0 and closed >= need:
        hints.append("clean_exits_so_far")
    if losses >= max(3, wins * 2):
        hints.append("sl_heavy")
    return ",".join(hints) if hints else "no_strong_pattern"


def transition(
    state: Dict[str, Any],
    profiles: Dict[str, Any],
    *,
    pair: str,
    new_stage: str,
    source: str,
    at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    emit_event: bool = True,
) -> Dict[str, Any]:
    """Move pair into new_stage; close prior segment dwell into profile."""
    cfg = cfg or load_stages_config()
    p = _norm_pair(pair)
    if not p or not new_stage:
        return {"ok": False, "reason": "bad_pair_or_stage"}
    now = at or _utc_now()
    now_iso = _utc_iso(now)
    open_map: Dict[str, Any] = state.setdefault("open", {})
    prev = open_map.get(p) if isinstance(open_map.get(p), dict) else None
    dwell_h = None
    closed_prev = None
    if prev and str(prev.get("stage") or "") == new_stage:
        # same stage — refresh meta only
        prev["meta"] = {**(prev.get("meta") or {}), **(meta or {})}
        prev["source"] = source or prev.get("source")
        return {
            "ok": True,
            "pair": p,
            "stage": new_stage,
            "same_stage": True,
            "dwell_h": None,
        }

    if prev:
        entered = _parse_ts(prev.get("entered_at"))
        if entered is not None:
            dwell_h = max(0.0, (now - entered).total_seconds() / 3600.0)
            _record_dwell(
                profiles,
                pair=p,
                stage=str(prev.get("stage") or "unknown"),
                dwell_h=dwell_h,
                cfg=cfg,
            )
            closed_prev = {
                "stage": prev.get("stage"),
                "entered_at": prev.get("entered_at"),
                "exited_at": now_iso,
                "dwell_h": round(dwell_h, 4),
            }

    terminal = is_terminal_stage(new_stage, cfg)
    row = _ensure_pair_profile(profiles, p)
    if terminal:
        # record zero-length mark on terminal for outcome counts; dwell already
        # captured on prior stage
        oc = _outcome_class_for_stage(new_stage, cfg)
        if oc:
            outs = row.setdefault("outcomes", {})
            outs[oc] = int(outs.get(oc) or 0) + 1
        row["closed_rts"] = int(row.get("closed_rts") or 0) + 1
        row["pattern_hint"] = _pattern_hint(row, cfg)
        open_map.pop(p, None)
    else:
        open_map[p] = {
            "pair": p,
            "stage": new_stage,
            "entered_at": now_iso,
            "source": source,
            "meta": dict(meta or {}),
        }
        row["last_stage"] = new_stage
        row["last_event_at"] = now_iso
        row["pattern_hint"] = _pattern_hint(row, cfg)

    event = {
        "ts": now_iso,
        "pair": p,
        "stage": new_stage,
        "source": source,
        "terminal": terminal,
        "closed_prev": closed_prev,
        "meta": meta or {},
    }
    if emit_event:
        _append_jsonl(EVENTS_PATH, event)
    state["updated_at"] = now_iso
    return {
        "ok": True,
        "pair": p,
        "stage": new_stage,
        "terminal": terminal,
        "dwell_h_closed": dwell_h,
        "event": event,
    }


def _composer_stage_hints(cfg: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """From latest composer: dual_clear vs rsi_wash candidates."""
    if not bool((cfg.get("tick") or {}).get("include_composer_candidates", True)):
        return []
    raw = _load_json(COMPOSER_LATEST, None)
    if not isinstance(raw, dict):
        return []
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    cand = raw.get("candidate") if isinstance(raw.get("candidate"), dict) else None
    if cand and cand.get("pair"):
        pair = _norm_pair(str(cand.get("pair")))
        if bool(cand.get("clears_floor")) or float(cand.get("eng") or 0) > 0:
            out.append(
                (
                    pair,
                    "dual_clear",
                    {
                        "eng": cand.get("eng"),
                        "rsi": cand.get("rsi"),
                        "eng_source": cand.get("eng_source"),
                        "from": "composer_candidate",
                    },
                )
            )
    # universe scan rows if present
    scan = raw.get("universe_scan") if isinstance(raw.get("universe_scan"), list) else []
    for row in scan:
        if not isinstance(row, dict):
            continue
        pair = _norm_pair(str(row.get("pair") or ""))
        if not pair:
            continue
        in_door = bool(row.get("in_rsi_door") or row.get("rsi_door"))
        clears = bool(row.get("clears_floor"))
        if clears:
            out.append(
                (
                    pair,
                    "dual_clear",
                    {"from": "universe_scan", "rsi": row.get("rsi"), "eng": row.get("eng")},
                )
            )
        elif in_door:
            out.append(
                (
                    pair,
                    "rsi_wash",
                    {"from": "universe_scan", "rsi": row.get("rsi"), "eng": row.get("eng")},
                )
            )
        elif bool(row.get("eligible") or row.get("tryout_eligible")):
            out.append((pair, "door_eligible", {"from": "universe_scan"}))
    return out


def _open_lot_stage_hints(cfg: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    tick = cfg.get("tick") if isinstance(cfg.get("tick"), dict) else {}
    if not bool(tick.get("include_open_lots", True)):
        return []
    raw = _load_json(OPEN_LOTS_PATH, None)
    if not isinstance(raw, dict):
        return []
    lots_raw = raw.get("lots")
    lots: Dict[str, Any] = lots_raw if isinstance(lots_raw, dict) else {}
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for pair, lot in lots.items():
        if not isinstance(lot, dict):
            continue
        p = _norm_pair(str(pair))
        st = str(lot.get("status") or "").lower()
        if st in ("scored", "closed", "exited"):
            # historical scored — don't re-open; exits handled via score/ledger
            continue
        if bool(lot.get("scaled") or lot.get("live_scaled") or lot.get("paper_scaled")):
            stage = "ladder"
        elif bool(lot.get("tryout_shell") or lot.get("tryout_tagged_buy") or st == "tryout_open"):
            stage = "tryout_open"
        else:
            continue
        meta = {
            "from": "open_lots",
            "entry_ts": lot.get("entry_ts"),
            "entry_price": lot.get("entry_price"),
            "shell_usd": lot.get("shell_usd"),
            "status": lot.get("status"),
            "scaled": bool(lot.get("scaled")),
        }
        out.append((p, stage, meta))
    return out


def _ledger_exit_events(
    cfg: Dict[str, Any],
    *,
    seen_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Recent SELL rows → terminal transitions (deduped by receipt id)."""
    if not bool((cfg.get("tick") or {}).get("include_ledger_exits", True)):
        return []
    limit = int((cfg.get("tick") or {}).get("ledger_lookback_rows") or 4000)
    if not LEDGER_PATH.exists():
        return []
    seen = seen_ids if seen_ids is not None else set()
    rows: List[str] = []
    try:
        # efficient tail
        with LEDGER_PATH.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 2_000_000)
            f.seek(size - chunk)
            data = f.read().decode("utf-8", errors="replace")
        lines = data.splitlines()
        if chunk < size and lines:
            lines = lines[1:]  # drop partial first line
        rows = lines[-limit:]
    except Exception as e:
        logger.warning("ledger tail failed: %s", e)
        return []

    events: List[Dict[str, Any]] = []
    for line in rows:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        side = str(row.get("side") or row.get("action") or "").upper()
        if side not in ("SELL", "EXIT"):
            continue
        pair = _norm_pair(str(row.get("pair") or row.get("product_id") or ""))
        if not pair:
            continue
        rid = str(
            row.get("order_id")
            or row.get("trade_id")
            or row.get("id")
            or row.get("client_order_id")
            or ""
        )
        # stable-ish fingerprint
        fp = rid or f"{pair}:{row.get('timestamp') or row.get('ts') or row.get('exit_ts')}:{row.get('qty') or row.get('size')}"
        if fp in seen:
            continue
        seen.add(fp)
        reason = (
            row.get("exit_reason")
            or row.get("reason")
            or row.get("stop_reason")
            or row.get("tag")
            or ""
        )
        stage = classify_exit_stage(reason, cfg)
        ts = _parse_ts(row.get("timestamp") or row.get("ts") or row.get("exit_ts") or row.get("time"))
        events.append(
            {
                "pair": pair,
                "stage": stage,
                "at": ts,
                "source": "ledger_sell",
                "meta": {
                    "exit_reason": reason,
                    "fp": fp,
                    "pnl": row.get("pnl") or row.get("realized_pnl"),
                },
            }
        )
    return events


def run_tick(
    *,
    write: bool = True,
    state: Optional[Dict[str, Any]] = None,
    profiles: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """One measure tick: composer + open lots + ledger exits → dwell profiles."""
    cfg = cfg or load_stages_config()
    state = state if state is not None else load_dwell_state()
    profiles = profiles if profiles is not None else load_profiles()
    now = now or _utc_now()
    transitions: List[Dict[str, Any]] = []

    # Priority: inventory (open lots) > dual_clear/wash > door
    # Apply open lots first so held bags don't get overwritten by wash scan
    for pair, stage, meta in _open_lot_stage_hints(cfg):
        # If already in a later non-terminal stage, don't demote
        cur = (state.get("open") or {}).get(pair)
        if isinstance(cur, dict):
            cur_s = str(cur.get("stage") or "")
            order = {s: i for i, s in enumerate(stage_ids(cfg))}
            if order.get(cur_s, -1) > order.get(stage, -1) and not is_terminal_stage(cur_s, cfg):
                continue
        transitions.append(
            transition(
                state,
                profiles,
                pair=pair,
                new_stage=stage,
                source=str(meta.get("from") or "open_lots"),
                at=_parse_ts(meta.get("entry_ts")) or now,
                meta=meta,
                cfg=cfg,
            )
        )

    for pair, stage, meta in _composer_stage_hints(cfg):
        cur = (state.get("open") or {}).get(pair)
        if isinstance(cur, dict):
            cur_s = str(cur.get("stage") or "")
            # never demote tryout_open / ladder from composer wash noise
            if cur_s in ("tryout_open", "ladder") or is_terminal_stage(cur_s, cfg):
                continue
            order = {s: i for i, s in enumerate(stage_ids(cfg))}
            if order.get(cur_s, -1) > order.get(stage, -1):
                continue
        transitions.append(
            transition(
                state,
                profiles,
                pair=pair,
                new_stage=stage,
                source=str(meta.get("from") or "composer"),
                at=now,
                meta=meta,
                cfg=cfg,
            )
        )

    # Ledger exits — ONLY close pairs with a live open dwell segment,
    # and only if exit_ts >= segment.entered_at (no historical SELL backfill).
    seen_fp = set()
    prev_seen = (state.get("last_tick") or {}).get("ledger_fps") if isinstance(state.get("last_tick"), dict) else None
    if isinstance(prev_seen, list):
        seen_fp.update(str(x) for x in prev_seen[-2000:])

    exit_events = _ledger_exit_events(cfg, seen_ids=seen_fp)
    open_map = state.get("open") if isinstance(state.get("open"), dict) else {}
    for ev in exit_events[-200:]:
        pair = str(ev.get("pair") or "")
        seg = open_map.get(pair) if isinstance(open_map.get(pair), dict) else None
        if not seg:
            continue
        entered = _parse_ts(seg.get("entered_at"))
        exit_at = ev.get("at")
        if entered is not None and exit_at is not None and exit_at < entered:
            continue
        # if exit has no ts, only accept if segment is "fresh" this tick and source ledger is risky — skip
        if exit_at is None:
            continue
        transitions.append(
            transition(
                state,
                profiles,
                pair=pair,
                new_stage=str(ev["stage"]),
                source=str(ev.get("source") or "ledger"),
                at=exit_at or now,
                meta=ev.get("meta") or {},
                cfg=cfg,
            )
        )

    # Refresh pattern hints
    for prow in (profiles.get("pairs") or {}).values():
        if isinstance(prow, dict):
            prow["pattern_hint"] = _pattern_hint(prow, cfg)

    profiles["predict_enabled"] = bool(
        (cfg.get("profile") or {}).get("predict_enabled")
    )
    profiles["updated_at"] = _utc_iso(now)
    profiles["note"] = (
        "Measure-only dwell profiles. predict_enabled=false until Brad GO + N. "
        "Stages SSOT: config/pair_funnel_stages.json"
    )

    open_summary = []
    for pair, seg in sorted((state.get("open") or {}).items()):
        if not isinstance(seg, dict):
            continue
        entered = _parse_ts(seg.get("entered_at"))
        age_h = (
            round((now - entered).total_seconds() / 3600.0, 3) if entered else None
        )
        open_summary.append(
            {
                "pair": pair,
                "stage": seg.get("stage"),
                "entered_at": seg.get("entered_at"),
                "age_h": age_h,
                "source": seg.get("source"),
            }
        )

    state["last_tick"] = {
        "at": _utc_iso(now),
        "n_transitions": len([t for t in transitions if t.get("ok") and not t.get("same_stage")]),
        "n_open": len(open_summary),
        "n_profiles": len(profiles.get("pairs") or {}),
        "ledger_fps": list(seen_fp)[-500:],
        "config_ok": bool(cfg.get("config_ok")),
    }
    state["updated_at"] = _utc_iso(now)
    state["schema"] = SCHEMA
    state["open_summary"] = open_summary
    state["stages"] = stage_ids(cfg)

    payload = {
        "schema": SCHEMA,
        "as_of": _utc_iso(now),
        "config_path": cfg.get("config_path"),
        "config_ok": bool(cfg.get("config_ok")),
        "predict_enabled": bool(profiles.get("predict_enabled")),
        "open_summary": open_summary,
        "n_open": len(open_summary),
        "n_profiles": len(profiles.get("pairs") or {}),
        "n_transitions_this_tick": state["last_tick"]["n_transitions"],
        "top_profiles": _top_profiles(profiles, limit=12),
        "plain_english": _plain(open_summary, profiles),
        "state": state,
        "profiles": profiles,
    }

    if write:
        # persist state without huge ledger_fps duplication in latest board
        board_state = dict(state)
        lt = dict(board_state.get("last_tick") or {})
        fps = lt.get("ledger_fps")
        if isinstance(fps, list) and len(fps) > 100:
            lt["ledger_fps"] = fps[-100:]
        board_state["last_tick"] = lt
        _write_json(LATEST_PATH, {**payload, "state": board_state})
        _write_json(PROFILES_PATH, profiles)
        MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
        MD_REPORT.write_text(_md(payload), encoding="utf-8")

    return payload


def _top_profiles(profiles: Dict[str, Any], limit: int = 12) -> List[Dict[str, Any]]:
    rows = []
    for pair, prow in (profiles.get("pairs") or {}).items():
        if not isinstance(prow, dict):
            continue
        rows.append(
            {
                "pair": pair,
                "closed_rts": prow.get("closed_rts"),
                "transitions": prow.get("transitions"),
                "outcomes": prow.get("outcomes"),
                "last_stage": prow.get("last_stage"),
                "pattern_hint": prow.get("pattern_hint"),
                "tryout_open_mean_h": ((prow.get("stage_dwell") or {}).get("tryout_open") or {}).get(
                    "mean_h"
                ),
                "dual_clear_mean_h": ((prow.get("stage_dwell") or {}).get("dual_clear") or {}).get(
                    "mean_h"
                ),
                "ladder_mean_h": ((prow.get("stage_dwell") or {}).get("ladder") or {}).get("mean_h"),
            }
        )
    rows.sort(key=lambda r: (-int(r.get("closed_rts") or 0), -int(r.get("transitions") or 0)))
    return rows[:limit]


def _plain(open_summary: List[Dict[str, Any]], profiles: Dict[str, Any]) -> str:
    bits = [
        f"open={len(open_summary)}",
        f"profiles={len(profiles.get('pairs') or {})}",
        f"predict={'ON' if profiles.get('predict_enabled') else 'OFF'}",
    ]
    if open_summary:
        top = ", ".join(f"{o['pair']}:{o['stage']}@{o.get('age_h')}h" for o in open_summary[:5])
        bits.append(top)
    return " | ".join(bits)


def _md(payload: Dict[str, Any]) -> str:
    lines = [
        f"# Pair funnel dwell (measure-only)",
        f"",
        f"- as_of: `{payload.get('as_of')}`",
        f"- config: `{payload.get('config_path')}` ok={payload.get('config_ok')}",
        f"- predict_enabled: **{payload.get('predict_enabled')}** (off until N + Brad GO)",
        f"- open segments: **{payload.get('n_open')}**",
        f"- profiles: **{payload.get('n_profiles')}**",
        f"- transitions this tick: {payload.get('n_transitions_this_tick')}",
        f"",
        f"## Open",
        f"",
    ]
    for o in payload.get("open_summary") or []:
        lines.append(
            f"- `{o.get('pair')}` · **{o.get('stage')}** · age_h={o.get('age_h')} · src={o.get('source')}"
        )
    if not payload.get("open_summary"):
        lines.append("- (none)")
    lines.extend(["", "## Profiles (top)", ""])
    for r in payload.get("top_profiles") or []:
        lines.append(
            f"- `{r.get('pair')}` closed={r.get('closed_rts')} tryout_mean_h={r.get('tryout_open_mean_h')} "
            f"dual_mean_h={r.get('dual_clear_mean_h')} hint={r.get('pattern_hint')}"
        )
    if not payload.get("top_profiles"):
        lines.append("- (empty — crumbs accumulate as seats/exits flow)")
    lines.extend(
        [
            "",
            "## Stages SSOT",
            "",
            "Edit `config/pair_funnel_stages.json` — not code.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


# --- monthly summary (measure-only ping) ----------------------------------------

MONTHLY_REPORT_DIR = PROJECT_ROOT / "reports"
MONTHLY_LATEST_MD = MONTHLY_REPORT_DIR / "PAIR_FUNNEL_DWELL_MONTHLY_LATEST.md"
MONTHLY_LATEST_JSON = STATE_DIR / "pair_funnel_dwell_monthly_latest.json"


def _stage_short_label(stage_id: str) -> str:
    """Compact column header for TG mono tables."""
    m = {
        "door_eligible": "door",
        "rsi_wash": "rsi",
        "dual_clear": "dual",
        "tryout_open": "try",
        "ladder": "lad",
        "exit_sl": "SL",
        "exit_tp": "TP",
        "exit_other": "oth",
    }
    return m.get(stage_id, stage_id[:4])


def build_monthly_summary(
    *,
    profiles: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    month_key: Optional[str] = None,
    write: bool = True,
) -> Dict[str, Any]:
    """Pair × stage visit-count table (Brad long-term data exercise).

    Cells = closed-segment visit counts (stage_dwell.n). Open age is a side
    column only — not mixed into historical counts. predict stays OFF.
    """
    cfg = cfg or load_stages_config()
    profiles = profiles if profiles is not None else load_profiles()
    state = state if state is not None else load_dwell_state()
    stages = stage_ids(cfg)
    short = [_stage_short_label(s) for s in stages]
    mon_raw = cfg.get("monthly") if isinstance(cfg.get("monthly"), dict) else {}
    mon: Dict[str, Any] = mon_raw if isinstance(mon_raw, dict) else {}
    include_open = bool(mon.get("include_open_age_col", True))

    now = _utc_now()
    if not month_key:
        month_key = now.strftime("%Y-%m")

    pairs_raw = profiles.get("pairs")
    pairs_map: Dict[str, Any] = pairs_raw if isinstance(pairs_raw, dict) else {}
    open_raw = state.get("open")
    open_map: Dict[str, Any] = open_raw if isinstance(open_raw, dict) else {}

    rows: List[Dict[str, Any]] = []
    for pair in sorted(set(list(pairs_map.keys()) + list(open_map.keys()))):
        p = _norm_pair(str(pair))
        prow_raw = pairs_map.get(p)
        prow: Dict[str, Any] = prow_raw if isinstance(prow_raw, dict) else {}
        sd_raw = prow.get("stage_dwell")
        sd: Dict[str, Any] = sd_raw if isinstance(sd_raw, dict) else {}
        counts: Dict[str, int] = {}
        total_n = 0
        for sid in stages:
            cell_raw = sd.get(sid)
            cell: Dict[str, Any] = cell_raw if isinstance(cell_raw, dict) else {}
            n = int(cell.get("n") or 0)
            counts[sid] = n
            total_n += n
        open_row_raw = open_map.get(p)
        open_row: Optional[Dict[str, Any]] = (
            open_row_raw if isinstance(open_row_raw, dict) else None
        )
        open_stage = str(open_row.get("stage") or "") if open_row else ""
        open_age_h: Optional[float] = None
        if open_row:
            ent = _parse_ts(str(open_row.get("entered_at") or ""))
            if ent:
                open_age_h = round((now - ent).total_seconds() / 3600.0, 2)
        outcomes_raw = prow.get("outcomes")
        outcomes: Dict[str, Any] = outcomes_raw if isinstance(outcomes_raw, dict) else {}
        rows.append(
            {
                "pair": p,
                "counts": counts,
                "total_n": total_n,
                "closed_rts": int(prow.get("closed_rts") or 0),
                "outcomes": {
                    "win": int(outcomes.get("win") or 0),
                    "loss_or_tax": int(outcomes.get("loss_or_tax") or 0),
                    "other": int(outcomes.get("other") or 0),
                },
                "last_stage": prow.get("last_stage"),
                "open_stage": open_stage or None,
                "open_age_h": open_age_h,
                "pattern_hint": prow.get("pattern_hint"),
            }
        )

    # Prefer pairs with any crumbs or open; keep stable sort by pair
    rows.sort(key=lambda r: (-int(r.get("total_n") or 0), -int(r.get("closed_rts") or 0), str(r.get("pair"))))

    # ASCII table: Pair | stage… | Σn | closed [| open]
    col_w = {s: max(4, len(_stage_short_label(s))) for s in stages}
    pair_w = max([4] + [len(str(r["pair"])) for r in rows] + [4])
    pair_w = min(max(pair_w, 8), 14)

    def _fmt_n(n: int) -> str:
        return str(n) if n else "·"

    header_parts = [f"{'Pair':<{pair_w}}"]
    header_parts.extend(f"{_stage_short_label(s):>{col_w[s]}}" for s in stages)
    header_parts.append(f"{'Σn':>4}")
    header_parts.append(f"{'cls':>3}")
    if include_open:
        header_parts.append(f"{'open':>12}")
    header = " | ".join(header_parts)
    sep = "-+-".join(
        ["-" * pair_w]
        + ["-" * col_w[s] for s in stages]
        + ["-" * 4, "-" * 3]
        + (["-" * 12] if include_open else [])
    )

    body_lines: List[str] = []
    for r in rows:
        parts = [f"{str(r['pair']):<{pair_w}}"]
        for s in stages:
            parts.append(f"{_fmt_n(int((r.get('counts') or {}).get(s) or 0)):>{col_w[s]}}")
        parts.append(f"{int(r.get('total_n') or 0):>4}")
        parts.append(f"{int(r.get('closed_rts') or 0):>3}")
        if include_open:
            if r.get("open_stage"):
                age = r.get("open_age_h")
                age_s = f"{age:.1f}h" if isinstance(age, (int, float)) else "?"
                open_s = f"{_stage_short_label(str(r['open_stage']))} {age_s}"
            else:
                open_s = "—"
            parts.append(f"{open_s:>12}")
        body_lines.append(" | ".join(parts))

    if not body_lines:
        body_lines.append(f"{'(none yet)':<{pair_w}} | crumbs accumulate as seats cycle")

    table = "\n".join([header, sep] + body_lines)

    total_closed = sum(int(r.get("closed_rts") or 0) for r in rows)
    total_visits = sum(int(r.get("total_n") or 0) for r in rows)
    n_open = sum(1 for r in rows if r.get("open_stage"))

    pe_lines = [
        f"Pair funnel dwell — monthly (measure-only)",
        f"Month {month_key} UTC · pairs={len(rows)} · open={n_open} · "
        f"stage_visits={total_visits} · closed_RTs={total_closed} · predict=OFF",
        f"",
        f"```",
        table,
        f"```",
        f"",
        f"Counts = closed stage visits (n). open = current segment age (not a count).",
        f"SSOT stages: config/pair_funnel_stages.json · long-term bucket fuel, not a gate.",
    ]
    plain = "\n".join(pe_lines)

    md_lines = [
        f"# Pair funnel dwell — monthly {month_key}",
        f"",
        f"- measure-only · **predict_enabled=false**",
        f"- pairs={len(rows)} · open={n_open} · stage_visits={total_visits} · closed_RTs={total_closed}",
        f"- generated_at: `{_utc_iso(now)}`",
        f"",
        f"## Table (Pair × stage visit count)",
        f"",
        f"```",
        table,
        f"```",
        f"",
        f"## Legend",
        f"",
        f"| col | stage |",
        f"|-----|-------|",
    ]
    for s, sh in zip(stages, short):
        md_lines.append(f"| `{sh}` | `{s}` |")
    md_lines.extend(
        [
            f"",
            f"Cells = visit count when a segment **left** that stage. "
            f"Open age is side-info only.",
            f"",
            f"Next: accumulate until closed_RTs support behavior buckets "
            f"(fast SL, dual-clear starve, ladder survivor). No live gate yet.",
            f"",
        ]
    )
    md = "\n".join(md_lines)

    payload: Dict[str, Any] = {
        "schema": "pair_funnel_dwell_monthly_v1",
        "month": month_key,
        "generated_at": _utc_iso(now),
        "predict_enabled": bool((cfg.get("profile") or {}).get("predict_enabled")),
        "stages": stages,
        "stage_short": short,
        "n_pairs": len(rows),
        "n_open": n_open,
        "total_stage_visits": total_visits,
        "total_closed_rts": total_closed,
        "rows": rows,
        "table": table,
        "plain_english": plain,
        "markdown": md,
        "config_path": str(CONFIG_PATH),
        "note": "Long-term measure ping. Counts feed future behavior buckets — not entry/exit yet.",
    }

    if write:
        try:
            MONTHLY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
            MONTHLY_LATEST_MD.write_text(md, encoding="utf-8")
            month_md = MONTHLY_REPORT_DIR / f"PAIR_FUNNEL_DWELL_MONTHLY_{month_key}.md"
            month_md.write_text(md, encoding="utf-8")
            _write_json(MONTHLY_LATEST_JSON, payload)
        except OSError as exc:
            logger.warning("monthly dwell write failed: %s", exc)

    return payload


def on_tryout_seat_filled(
    pair: str,
    *,
    entry_ts: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call after live tryout seat fill (register open lot companion)."""
    cfg = load_stages_config()
    state = load_dwell_state()
    profiles = load_profiles()
    res = transition(
        state,
        profiles,
        pair=pair,
        new_stage="tryout_open",
        source="tryout_seat_fill",
        at=_parse_ts(entry_ts) or _utc_now(),
        meta=meta or {},
        cfg=cfg,
    )
    _write_json(LATEST_PATH, {"schema": SCHEMA, "state": state, "updated_at": _utc_iso(), "hook": "seat_fill"})
    # keep board thin on hook — full tick rewrites board
    profiles["updated_at"] = _utc_iso()
    _write_json(PROFILES_PATH, profiles)
    # merge open into latest properly
    run_tick(write=True, state=state, profiles=profiles, cfg=cfg)
    return res


def on_tryout_scaled(
    pair: str,
    *,
    scaled_at: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = load_stages_config()
    state = load_dwell_state()
    profiles = load_profiles()
    res = transition(
        state,
        profiles,
        pair=pair,
        new_stage="ladder",
        source="tryout_scale",
        at=_parse_ts(scaled_at) or _utc_now(),
        meta=meta or {},
        cfg=cfg,
    )
    run_tick(write=True, state=state, profiles=profiles, cfg=cfg)
    return res


def on_tryout_exit(
    pair: str,
    *,
    exit_reason: str = "",
    exit_ts: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = load_stages_config()
    state = load_dwell_state()
    profiles = load_profiles()
    stage = classify_exit_stage(exit_reason, cfg)
    res = transition(
        state,
        profiles,
        pair=pair,
        new_stage=stage,
        source="tryout_exit_hook",
        at=_parse_ts(exit_ts) or _utc_now(),
        meta={**(meta or {}), "exit_reason": exit_reason},
        cfg=cfg,
    )
    run_tick(write=True, state=state, profiles=profiles, cfg=cfg)
    # Calibration: attach outcome to decision-discipline triple trail
    try:
        from phase6.core.tryout_decision_discipline import attach_outcome

        stage_row = next(
            (s for s in (cfg.get("stages") or []) if isinstance(s, dict) and s.get("id") == stage),
            {},
        )
        oc = str((stage_row or {}).get("outcome_class") or stage)
        attach_outcome(
            pair=pair,
            outcome_class=oc,
            exit_reason=exit_reason or stage,
            meta={"stage": stage, **(meta or {})},
        )
    except Exception as exc:
        logger.warning("decision discipline outcome attach failed: %s", exc)
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    out = run_tick(write=True)
    print(out.get("plain_english"))
    print(f"wrote {LATEST_PATH}")
    print(f"profiles {PROFILES_PATH} n={out.get('n_profiles')}")
