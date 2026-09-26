#!/usr/bin/env python3
"""RSI-event tryout seat — approval → autonomous policy (Brad 2026-09-25).

Ladder
------
1. **approval** (default): dual-clear → dry seat plan + quiet TG approval card.
   Money stays OFF until Brad runs `--go-buy --live` (counts as one manual GO).
2. After `required_manual_gos` (default 2) successful live seats are recorded,
   Brad can **arm autonomous** (`auto_armed=true`).
3. **autonomous**: post-RSI path may place the $shell seat when dual-clear
   (still killed by kill file / policy.kill / POST_RSI_COMPOSER=0).

Hard fences
-----------
- Default mode=approval, auto_armed=false — no surprise money.
- Recording a GO only on real filled receipt (or explicit record-go).
- Flip to autonomous is explicit arm, not silent after N.
- Kill file or policy.kill freezes money and TG noise.

Artifacts
---------
  data/state/rsi_event_tryout_seat_brad_policy.json
  data/state/rsi_event_tryout_seat_approval_seen.json
  data/state/rsi_event_tryout_seat_KILL   (presence = kill)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import STATE_DIR

SCHEMA = "rsi_event_tryout_seat_policy_v1"
POLICY_PATH = STATE_DIR / "rsi_event_tryout_seat_brad_policy.json"
APPROVAL_SEEN_PATH = STATE_DIR / "rsi_event_tryout_seat_approval_seen.json"
KILL_PATH = STATE_DIR / "rsi_event_tryout_seat_KILL"
APPROVAL_DEDUPE_HOURS = 6.0
DEFAULT_REQUIRED_MANUAL_GOS = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def kill_switch_on() -> bool:
    if KILL_PATH.exists():
        return True
    pol = load_policy()
    return bool(pol.get("kill"))


def default_policy() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "mode": "approval",  # approval | autonomous
        "required_manual_gos": DEFAULT_REQUIRED_MANUAL_GOS,
        "manual_gos": [],
        "auto_armed": False,
        "kill": False,
        "note": (
            "First N dual-clear seats need Brad GO (--go-buy --live). "
            "Then arm autonomous explicitly."
        ),
        "updated_at": _utc_iso(),
    }


def load_policy() -> Dict[str, Any]:
    raw = _load_json(POLICY_PATH, None)
    if not isinstance(raw, dict):
        pol = default_policy()
        _write_json(POLICY_PATH, pol)
        return pol
    out = default_policy()
    out.update({k: v for k, v in raw.items() if v is not None})
    if not isinstance(out.get("manual_gos"), list):
        out["manual_gos"] = []
    try:
        out["required_manual_gos"] = int(out.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    except (TypeError, ValueError):
        out["required_manual_gos"] = DEFAULT_REQUIRED_MANUAL_GOS
    mode = str(out.get("mode") or "approval").strip().lower()
    out["mode"] = mode if mode in ("approval", "autonomous") else "approval"
    out["auto_armed"] = bool(out.get("auto_armed"))
    out["kill"] = bool(out.get("kill"))
    return out


def save_policy(pol: Dict[str, Any]) -> Dict[str, Any]:
    out = load_policy()
    out.update(pol)
    out["schema"] = SCHEMA
    out["updated_at"] = _utc_iso()
    _write_json(POLICY_PATH, out)
    return out


def manual_go_count(pol: Optional[Dict[str, Any]] = None) -> int:
    p = pol or load_policy()
    gos = p.get("manual_gos") if isinstance(p.get("manual_gos"), list) else []
    return len(gos)


def ready_to_arm_autonomous(pol: Optional[Dict[str, Any]] = None) -> bool:
    p = pol or load_policy()
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    return manual_go_count(p) >= need and not bool(p.get("auto_armed"))


def autonomous_money_allowed(pol: Optional[Dict[str, Any]] = None) -> bool:
    """True when post-RSI path may place a live seat without Brad on the wire."""
    if kill_switch_on():
        return False
    p = pol or load_policy()
    if str(p.get("mode") or "") != "autonomous":
        return False
    if not bool(p.get("auto_armed")):
        return False
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    if manual_go_count(p) < need:
        return False
    return True


def record_manual_go(
    *,
    pair: str,
    shell_usd: float,
    receipt_id: str = "",
    note: str = "",
    source: str = "live_fill",
) -> Dict[str, Any]:
    """Append one successful Brad GO seat. Idempotent on receipt_id."""
    p = load_policy()
    gos: List[Dict[str, Any]] = list(p.get("manual_gos") or [])
    rid = str(receipt_id or "").strip()
    if rid and any(str(g.get("receipt_id") or "") == rid for g in gos if isinstance(g, dict)):
        return p
    gos.append(
        {
            "ts": _utc_iso(),
            "pair": str(pair or "").strip().upper().replace("_", "-"),
            "shell_usd": float(shell_usd or 0),
            "receipt_id": rid,
            "note": note or "",
            "source": source,
        }
    )
    p["manual_gos"] = gos
    p["updated_at"] = _utc_iso()
    if ready_to_arm_autonomous(p):
        p["note"] = (
            f"{len(gos)}/{p.get('required_manual_gos')} manual GOs done — "
            "ready to arm autonomous: "
            "python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --arm-auto"
        )
    _write_json(POLICY_PATH, p)
    return p


def arm_autonomous(*, force: bool = False) -> Dict[str, Any]:
    """Flip mode=autonomous + auto_armed. Refuses until N GOs unless force."""
    p = load_policy()
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    n = manual_go_count(p)
    if n < need and not force:
        p["arm_refused"] = f"need {need} manual GOs, have {n}"
        return p
    p["mode"] = "autonomous"
    p["auto_armed"] = True
    p["kill"] = False
    p["arm_refused"] = None
    p["note"] = f"Autonomous armed at {_utc_iso()} after {n} manual GOs"
    p["updated_at"] = _utc_iso()
    _write_json(POLICY_PATH, p)
    return p


def disarm(*, kill: bool = False) -> Dict[str, Any]:
    p = load_policy()
    p["mode"] = "approval"
    p["auto_armed"] = False
    if kill:
        p["kill"] = True
    p["note"] = f"Disarmed to approval at {_utc_iso()}"
    p["updated_at"] = _utc_iso()
    _write_json(POLICY_PATH, p)
    return p


def approval_fingerprint(pair: str, shell_usd: float, rsi: Any, eng: Any) -> str:
    try:
        rsi_s = f"{float(rsi):.1f}" if rsi is not None else "?"
    except (TypeError, ValueError):
        rsi_s = "?"
    try:
        eng_s = f"{float(eng):.2f}" if eng is not None else "?"
    except (TypeError, ValueError):
        eng_s = "?"
    pair_n = str(pair or "").strip().upper().replace("_", "-")
    return f"{pair_n}:{float(shell_usd or 0):.0f}:{rsi_s}:{eng_s}"


def _should_send_approval(
    fingerprint: str,
    *,
    dedupe_hours: float = APPROVAL_DEDUPE_HOURS,
    mark: bool = True,
) -> bool:
    fp = str(fingerprint or "").strip()
    if not fp:
        return False
    now = _utc_now()
    seen = _load_json(APPROVAL_SEEN_PATH, {"fingerprints": {}})
    if not isinstance(seen, dict):
        seen = {"fingerprints": {}}
    fps = seen.get("fingerprints") if isinstance(seen.get("fingerprints"), dict) else {}
    last_raw = str(fps.get(fp) or "")
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            last = None
    if last is not None and (now - last).total_seconds() < float(dedupe_hours) * 3600.0:
        return False
    if mark:
        fps[fp] = _utc_iso(now)
        # prune ~7d
        horizon = max(float(dedupe_hours), 24.0) * 3600.0 * 7.0
        keep: Dict[str, str] = {}
        for k, v in fps.items():
            try:
                t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if (now - t).total_seconds() <= horizon:
                    keep[str(k)] = str(v)
            except Exception:
                continue
        seen["fingerprints"] = keep
        seen["updated_at"] = _utc_iso(now)
        _write_json(APPROVAL_SEEN_PATH, seen)
    return True


def approval_telegram_card(
    payload: Dict[str, Any],
    *,
    force: bool = False,
    mark_sent: bool = True,
    dedupe_hours: float = APPROVAL_DEDUPE_HOURS,
) -> str:
    """Quiet TG body: only when dual-clear dry_would_buy and still on approval ladder.

    Empty when: kill, autonomous money path owns it, no candidate, seat not
    dry_would_buy/planned, or same fingerprint within dedupe window.
    """
    if kill_switch_on():
        return ""
    if not isinstance(payload, dict):
        return ""
    pol = load_policy()
    # Once fully autonomous + armed, no approval spam (money path handles it)
    if autonomous_money_allowed(pol):
        return ""

    cand = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
    seat = payload.get("seat_receipt") if isinstance(payload.get("seat_receipt"), dict) else {}
    if not cand:
        return ""
    arts = seat.get("artifacts") if isinstance(seat.get("artifacts"), dict) else {}
    plan = arts.get("plan") if isinstance(arts.get("plan"), dict) else {}
    plan_status = str(plan.get("status") or seat.get("status") or "")
    # Only page when evaluate cleared and we would buy dry
    if plan_status not in ("dry_would_buy", "planned", "dry_run"):
        # seat receipt top-level status dry_run with plan dry_would_buy
        if str(seat.get("status") or "") not in ("dry_run", "ok"):
            return ""
        if plan_status and plan_status not in ("dry_would_buy", "planned"):
            return ""
    if plan_status == "blocked" or str(seat.get("status") or "") == "blocked":
        return ""

    pair = str(cand.get("pair") or plan.get("pair") or "")
    shell = float(plan.get("shell_usd") or 0) or 25.0
    rsi = cand.get("rsi") if cand.get("rsi") is not None else plan.get("rsi")
    eng = cand.get("eng")
    fp = approval_fingerprint(pair, shell, rsi, eng)
    if not force and not _should_send_approval(fp, dedupe_hours=dedupe_hours, mark=mark_sent):
        return ""

    n = manual_go_count(pol)
    need = int(pol.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    left = max(need - n, 0)
    mode = pol.get("mode")
    lines = [
        "TRYOUT SEAT APPROVAL (money OFF until you GO)",
        f"mode={mode} · manual GOs {n}/{need} · left={left} · fp={fp}",
        f"RECOMMEND: open ${shell:.0f} tryout seat on {pair}",
        f"Why: RSI-event dual-clear eng={eng} rsi={rsi} src={cand.get('eng_source')}",
        "Factors:",
        f"  · regime doors scanned · rsi_door ok · evaluate_buy_entry cleared (dry)",
        f"  · shell=quality_tryout abs_cap · not full rebalance",
        f"  · seat status={seat.get('status')} plan={plan_status}",
        "GO (counts toward autonomous ladder):",
        f"  python3 scripts/phase6/run_tryout_seat_buy.py --pair {pair} "
        f"--sentiment {eng} --rsi {rsi} --go --live",
        "  # or composer: --go-x --go-buy --live",
    ]
    if left == 0 and not pol.get("auto_armed"):
        lines.append(
            "Ladder complete — arm autonomous when ready:\n"
            "  python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --arm-auto"
        )
    elif left > 0:
        lines.append(f"After {left} more live GO(s) you can arm full autonomous (24×7).")
    return "\n".join(lines)


def policy_status_plain() -> str:
    p = load_policy()
    n = manual_go_count(p)
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED_MANUAL_GOS)
    return (
        f"tryout_seat_policy mode={p.get('mode')} auto_armed={p.get('auto_armed')} "
        f"kill={kill_switch_on()} gos={n}/{need} "
        f"autonomous_money={autonomous_money_allowed(p)} "
        f"ready_to_arm={ready_to_arm_autonomous(p)}"
    )
