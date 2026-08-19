#!/usr/bin/env python3
"""
MASTER → trial cycle pickup.

Scans docs/MASTER_TASK_TRACKING.md for machine fields:

  **Type:** test
  **Status:** QUEUED | READY | ...
  **auto_pickup:** true
  **blocked_on:** `TASK-ID` or none
  **trial_kind:** offline_analysis | parallel_instrumentation
  **family:** stoch_rsi | kelly_sizing | ...
  **duration_days:** 14
  **Handoff:** `path`
  **Protocol:** `path` (optional)

Usage:
  python3 phase6/research/master_test_pickup.py scan
  python3 phase6/research/master_test_pickup.py claim
  python3 phase6/research/master_test_pickup.py launch --dry-run
  python3 phase6/research/master_test_pickup.py launch
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

MASTER_PATH = PROJECT_ROOT / "docs" / "MASTER_TASK_TRACKING.md"
TRIALS_DIR = PROJECT_ROOT / "data" / "state" / "trials"
QUEUE_PATH = TRIALS_DIR / "PICKUP_QUEUE.json"
STATE_PATH = TRIALS_DIR / "PICKUP_STATE.json"
INBOX_DIR = PROJECT_ROOT / "docs" / "testing" / "inbox"
PROTOCOLS_DIR = PROJECT_ROOT / "docs" / "testing" / "trials"

# Caps
MAX_RUNNING_AUTO = 1
MAX_LAUNCH_PER_RUN = 1

TERMINAL_MASTER = {
    "DONE",
    "CLOSED",
    "COMPLETE",
    "COMPLETED",
    "KILLED",
    "CANCELLED",
    "CANCELED",
}
ACTIVE_TRIAL = {"RUNNING", "DEGRADED", "LAUNCHED", "INSTRUMENTED", "REGISTERED", "REPORT_READY", "REVIEW_PENDING"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_s() -> str:
    return _now().isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def _field(block: str, key: str) -> Optional[str]:
    """Extract **Key:** value from a MASTER section body."""
    # Allow bold markers and optional backticks around value
    pat = rf"\*\*{re.escape(key)}:\*\*\s*(.+?)(?:\n|$)"
    m = re.search(pat, block, flags=re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).strip()
    # strip trailing markdown noise
    val = re.sub(r"\s{2,}$", "", val)
    return val


def _strip_md(val: str) -> str:
    val = val.strip()
    val = re.sub(r"^\*\*(.+)\*\*", r"\1", val)
    val = val.strip("`").strip()
    # first token / first clause for status
    return val


def _status_token(raw: Optional[str]) -> str:
    if not raw:
        return "UNKNOWN"
    s = _strip_md(raw)
    # "**QUEUED** — blocked..." → QUEUED
    s = re.sub(r"[—-].*$", "", s).strip()
    s = s.split()[0] if s.split() else s
    s = s.upper().strip(".,;:")
    # normalize LAUNCHED / RUNNING combo
    if "RUNNING" in _strip_md(raw).upper() and "QUEUED" not in s:
        if s in ("LAUNCHED", "OFFICIAL"):
            return "RUNNING"
    return s


def parse_master_sections(text: str) -> List[Dict[str, Any]]:
    """Split MASTER on ## headers; return dicts for Type:test sections."""
    # Split keeping headers
    parts = re.split(r"(?m)^(## .+)$", text)
    # parts[0] preamble, then pairs (header, body)
    sections: List[Dict[str, Any]] = []
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        body = parts[i + 1]
        i += 2
        # ID from "## FOO — title" or "## FOO"
        hm = re.match(r"##\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", header)
        if not hm:
            continue
        task_id = hm.group(1)
        type_raw = _field(body, "Type") or _field(body, "type")
        if not type_raw:
            continue
        type_tok = _strip_md(type_raw).split()[0].lower()
        if type_tok not in ("test", "trial", "experiment"):
            continue

        auto_raw = (_field(body, "auto_pickup") or _field(body, "Auto_pickup") or "false").lower()
        auto = _strip_md(auto_raw).split()[0].lower() in ("true", "yes", "1", "on")

        blocked = _field(body, "blocked_on") or _field(body, "Blocked_on") or ""
        blocked = _strip_md(blocked)
        if blocked.lower() in ("none", "n/a", "-", ""):
            blocked_on: List[str] = []
        else:
            # support `A` + `B` or comma-separated
            blocked_on = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", blocked)
            blocked_on = [b for b in blocked_on if b.upper() not in ("NONE", "N", "A")]

        kind = _strip_md(_field(body, "trial_kind") or "offline_analysis").split()[0].lower()
        family = _strip_md(_field(body, "family") or task_id.lower()).split()[0].lower()
        dur_s = _strip_md(_field(body, "duration_days") or "14").split()[0]
        try:
            duration_days = int(float(dur_s))
        except ValueError:
            duration_days = 14

        handoff = _strip_md(_field(body, "Handoff") or _field(body, "handoff") or "")
        protocol = _strip_md(_field(body, "Protocol") or _field(body, "protocol") or "")
        role = _strip_md(_field(body, "Role") or "crypto-analyst")
        trial_id_field = _field(body, "Trial ID") or _field(body, "trial_id")
        trial_id = _strip_md(trial_id_field) if trial_id_field else None
        status = _status_token(_field(body, "Status") or _field(body, "status"))

        title = header
        if "—" in header:
            title = header.split("—", 1)[-1].strip()
        elif "-" in header[3:]:
            pass

        sections.append(
            {
                "task_id": task_id,
                "header": header,
                "title": title,
                "type": type_tok,
                "status": status,
                "auto_pickup": auto,
                "blocked_on": blocked_on,
                "trial_kind": kind,
                "family": family,
                "duration_days": duration_days,
                "handoff": handoff,
                "protocol": protocol,
                "role": role,
                "trial_id": trial_id,
                "body_excerpt": body[:800],
            }
        )
    return sections


def _all_sections_index(text: str) -> Dict[str, str]:
    """task_id -> status token for any ## section (for blocked_on resolution)."""
    parts = re.split(r"(?m)^(## .+)$", text)
    idx: Dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        body = parts[i + 1]
        i += 2
        hm = re.match(r"##\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", header)
        if not hm:
            continue
        tid = hm.group(1)
        st = _status_token(_field(body, "Status") or _field(body, "status") or header)
        # also infer from header "— DONE"
        if st == "UNKNOWN":
            hu = header.upper()
            for tok in TERMINAL_MASTER:
                if re.search(rf"\b{tok}\b", hu):
                    st = tok
                    break
            if "RUNNING" in hu or "LAUNCHED" in hu:
                st = "RUNNING"
            elif "QUEUED" in hu:
                st = "QUEUED"
        idx[tid] = st
    return idx


def _trial_status(trial_id: str) -> Optional[str]:
    p = TRIALS_DIR / f"{trial_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("status")
    except Exception:
        return None


def _blocker_resolved(blocker_id: str, master_idx: Dict[str, str]) -> Tuple[bool, str]:
    st = master_idx.get(blocker_id, "MISSING")
    if st in TERMINAL_MASTER:
        return True, f"master:{st}"
    # trial file with same id or common trial naming
    ts = _trial_status(blocker_id)
    if ts in ("CLOSED", "KILLED"):
        return True, f"trial:{ts}"
    # search trials for master_id match
    for p in TRIALS_DIR.glob("*.json"):
        if p.name == "INDEX.json":
            continue
        try:
            t = json.loads(p.read_text())
        except Exception:
            continue
        if t.get("master_id") == blocker_id and t.get("status") in ("CLOSED", "KILLED"):
            return True, f"trial_master:{t.get('status')}"
    return False, f"master:{st}"


def _count_running_auto() -> int:
    n = 0
    for p in TRIALS_DIR.glob("*.json"):
        if p.name in ("INDEX.json", "PICKUP_QUEUE.json", "PICKUP_STATE.json"):
            continue
        try:
            t = json.loads(p.read_text())
        except Exception:
            continue
        if t.get("source") == "master_auto_pickup" and t.get("status") in ACTIVE_TRIAL:
            n += 1
    return n


def scan() -> Dict[str, Any]:
    text = MASTER_PATH.read_text() if MASTER_PATH.exists() else ""
    tests = parse_master_sections(text)
    master_idx = _all_sections_index(text)
    ready: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    active: List[Dict[str, Any]] = []
    done: List[Dict[str, Any]] = []
    skipped_no_auto: List[str] = []

    for t in tests:
        if not t["auto_pickup"]:
            skipped_no_auto.append(t["task_id"])
            continue
        # resolve blocks
        unresolved = []
        for b in t["blocked_on"]:
            ok, why = _blocker_resolved(b, master_idx)
            if not ok:
                unresolved.append({"id": b, "state": why})
        t["blockers_unresolved"] = unresolved
        t["blockers_ok"] = len(unresolved) == 0

        st = t["status"]
        if st in TERMINAL_MASTER:
            done.append(t)
            continue
        if st in ("RUNNING", "LAUNCHED", "PICKED_UP", "LAUNCHING", "IN_PROGRESS", "REPORT_READY", "REVIEW_PENDING"):
            active.append(t)
            continue
        if st in ("QUEUED", "READY", "PENDING", "UNKNOWN"):
            if t["blockers_ok"]:
                t["pickup_status"] = "READY"
                ready.append(t)
            else:
                t["pickup_status"] = "BLOCKED"
                blocked.append(t)
            continue
        # default
        if t["blockers_ok"] and st not in TERMINAL_MASTER:
            t["pickup_status"] = "READY"
            ready.append(t)
        else:
            t["pickup_status"] = "BLOCKED"
            blocked.append(t)

    queue = {
        "schema_version": 1,
        "scanned_at": _now_s(),
        "master_path": str(MASTER_PATH.relative_to(PROJECT_ROOT)),
        "caps": {"max_running_auto": MAX_RUNNING_AUTO, "max_launch_per_run": MAX_LAUNCH_PER_RUN},
        "running_auto_count": _count_running_auto(),
        "ready": ready,
        "blocked": blocked,
        "active": active,
        "done": [{"task_id": d["task_id"], "status": d["status"]} for d in done],
        "skipped_no_auto": skipped_no_auto,
        "launchable_now": [],
    }
    slots = max(0, MAX_RUNNING_AUTO - queue["running_auto_count"])
    queue["launchable_now"] = ready[: min(slots, MAX_LAUNCH_PER_RUN)]
    _save_json(QUEUE_PATH, queue)
    return queue


def patch_master_status(task_id: str, new_status: str, note: str = "") -> bool:
    """Replace **Status:** line in the task's MASTER section."""
    text = MASTER_PATH.read_text()
    # Find section
    pat = rf"(?ms)^(## {re.escape(task_id)}\b.*?)(?=^## |\Z)"
    m = re.search(pat, text)
    if not m:
        return False
    section = m.group(1)
    status_line = f"**Status:** **{new_status}**"
    if note:
        status_line += f" — {note}"
    status_line += "  \n"
    if re.search(r"\*\*Status:\*\*.*\n", section):
        new_section = re.sub(r"\*\*Status:\*\*.*\n", status_line, section, count=1)
    else:
        # insert after header line
        lines = section.splitlines(True)
        lines.insert(1, status_line)
        new_section = "".join(lines)
    # ensure Type: test present
    if not re.search(r"\*\*Type:\*\*\s*test", new_section, re.I):
        lines = new_section.splitlines(True)
        lines.insert(1, "**Type:** test  \n")
        new_section = "".join(lines)
    new_text = text[: m.start()] + new_section + text[m.end() :]
    MASTER_PATH.write_text(new_text)
    return True


def ensure_protocol(task: Dict[str, Any], trial_id: str) -> Path:
    if task.get("protocol"):
        p = PROJECT_ROOT / task["protocol"]
        if p.exists():
            return p
    path = PROTOCOLS_DIR / f"{trial_id}_PROTOCOL.md"
    if path.exists():
        return path
    PROTOCOLS_DIR.mkdir(parents=True, exist_ok=True)
    handoff = task.get("handoff") or "(none)"
    path.write_text(
        f"""# Protocol — {trial_id}

**Master task:** `{task['task_id']}`  
**Type:** test (auto-pickup)  
**Kind:** `{task.get('trial_kind')}`  
**Family:** `{task.get('family')}`  
**Cycle:** `docs/testing/ANALYST_TEST_CYCLE.md`  
**Handoff:** `{handoff}`  

## Hypothesis
(Fill from handoff objective — pickup scaffold.)

## Non-goals
- No live trading config changes without Brad + gates.
- Real data only.

## Duration
- Kind offline_analysis: complete in one analyst run (tiers in handoff).
- Kind parallel_instrumentation: **{task.get('duration_days', 14)}** days mid/final.

## Success
- Report under `reports/` with recommendation enum.
- MASTER updated; trial CLOSED via `trial_cycle.py decide` after Brad (or offline auto-report → REVIEW_PENDING).

## Commands
See handoff. Generic:
```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py status {trial_id}
```
"""
    )
    return path


def register_trial(task: Dict[str, Any]) -> Dict[str, Any]:
    from phase6.research.trial_cycle import reindex, save_trial

    trial_id = task.get("trial_id") or f"{task['family'].upper()}-{_now().strftime('%Y%m%d')}-{task['task_id'][-8:]}"
    # Stable readable id
    if not task.get("trial_id"):
        trial_id = f"{task['task_id']}-TRIAL"
        # avoid collision
        if (TRIALS_DIR / f"{trial_id}.json").exists():
            trial_id = f"{task['task_id']}-{_now().strftime('%Y%m%d%H%M')}"

    protocol = ensure_protocol(task, trial_id)
    start = _now()
    dur = int(task.get("duration_days") or 14)
    mid = start + timedelta(days=max(1, dur // 2))
    end = start + timedelta(days=dur)

    trial = {
        "trial_id": trial_id,
        "title": task.get("title") or task["task_id"],
        "status": "REGISTERED",
        "source": "master_auto_pickup",
        "master_id": task["task_id"],
        "family": task.get("family"),
        "trial_kind": task.get("trial_kind"),
        "role": task.get("role"),
        "handoff": task.get("handoff"),
        "protocol": str(protocol.relative_to(PROJECT_ROOT)),
        "cycle": "docs/testing/ANALYST_TEST_CYCLE.md",
        "cycle_version": 2,
        "auto_pickup": True,
        "duration_days": dur,
        "start_at": None,
        "mid_at": mid.isoformat(),
        "final_at": end.isoformat(),
        "kill_after_consecutive_health_fails": 3,
        "cron_ids": {},
        "reports": [],
        "health_log": [],
        "decision": None,
        "unblocks": [],
        "created_at": _now_s(),
        "status_history": [{"from": None, "to": "REGISTERED", "at": _now_s(), "note": "master pickup"}],
    }
    save_trial(trial)
    reindex()
    return trial


def _hermes_cron_create(
    schedule: str,
    prompt: str,
    *,
    name: str,
    skill: Optional[str] = None,
    script: Optional[str] = None,
    no_agent: bool = False,
    deliver: str = "telegram",
) -> Optional[str]:
    cmd = [
        "hermes",
        "cron",
        "create",
        schedule,
    ]
    if prompt:
        cmd.append(prompt)
    cmd.extend(
        [
            "--name",
            name,
            "--deliver",
            deliver,
            "--workdir",
            str(PROJECT_ROOT),
        ]
    )
    if skill:
        cmd.extend(["--skill", skill])
    if script:
        cmd.extend(["--script", script])
    if no_agent:
        cmd.append("--no-agent")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        # try parse job id
        m = re.search(r"Created job:\s*([a-f0-9]{8,})", out, re.I)
        if not m:
            m = re.search(r"(?:job_id|id)['\"]?\s*[:=]\s*['\"]?([a-f0-9]{8,})", out, re.I)
        if not m:
            m = re.search(r"\b([a-f0-9]{12})\b", out)
        if r.returncode != 0 and not m:
            return f"error:rc={r.returncode}:{out.strip()[:300]}"
        return m.group(1) if m else (out.strip()[:200] or None)
    except Exception as e:
        return f"error:{e}"


def schedule_for_trial(trial: Dict[str, Any], task: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """Create hermes crons appropriate for trial_kind."""
    tid = trial["trial_id"]
    kind = (trial.get("trial_kind") or "offline_analysis").lower()
    cron_ids: Dict[str, Any] = {}
    if dry_run:
        return {"dry_run": True, "kind": kind, "would_schedule": True}

    if kind == "parallel_instrumentation":
        # health every 6h
        cron_ids["health"] = _hermes_cron_create(
            "15 */6 * * *",
            "",
            name=f"trial-health-{tid[:24]}",
            script="run_generic_trial_health.sh",
            no_agent=True,
        )
        mid_at = trial.get("mid_at") or (_now() + timedelta(days=7)).isoformat()
        final_at = trial.get("final_at") or (_now() + timedelta(days=14)).isoformat()
        # hermes once schedule wants local-ish iso
        cron_ids["mid"] = _hermes_cron_create(
            mid_at,
            f"Load skill analyst-trial-report. Run MID for trial {tid}. Workdir {PROJECT_ROOT}.",
            name=f"trial-mid-{tid[:24]}",
            skill="analyst-trial-report",
        )
        cron_ids["final"] = _hermes_cron_create(
            final_at,
            f"Load skill analyst-trial-report. Run FINAL for trial {tid}. Workdir {PROJECT_ROOT}.",
            name=f"trial-final-{tid[:24]}",
            skill="analyst-trial-report",
        )
    else:
        # offline_analysis: one-shot execute soon (2 minutes from now)
        run_at = (_now() + timedelta(minutes=2)).astimezone().isoformat(timespec="minutes")
        cron_ids["execute"] = _hermes_cron_create(
            run_at,
            (
                f"Load skill analyst-test-execute. Execute MASTER test task {task['task_id']} "
                f"trial {tid}. Handoff: {task.get('handoff')}. "
                f"Follow ANALYST_TEST_CYCLE. Real data only. No live config writes. "
                f"End in REPORT_READY + inbox review request."
            ),
            name=f"trial-exec-{tid[:24]}",
            skill="analyst-test-execute",
        )
    return cron_ids


def launch_one(task: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    from phase6.research.trial_cycle import load_trial, save_trial, transition

    result: Dict[str, Any] = {"task_id": task["task_id"], "ok": False}
    if dry_run:
        result["ok"] = True
        result["dry_run"] = True
        result["would_register"] = True
        return result

    trial = register_trial(task)
    tid = trial["trial_id"]
    result["trial_id"] = tid

    # INSTRUMENTED skip for offline; mark RUNNING after schedule
    try:
        transition(tid, "INSTRUMENTED", note="auto-pickup scaffold")
        transition(tid, "RUNNING", note="auto-pickup launch")
    except ValueError as e:
        result["transition_error"] = str(e)

    trial = load_trial(tid)
    trial["start_at"] = _now_s()
    trial["analysis_window_start"] = trial["start_at"]
    cron_ids = schedule_for_trial(trial, task, dry_run=False)
    trial["cron_ids"] = cron_ids
    trial["launched_at"] = _now_s()
    save_trial(trial)

    patch_master_status(
        task["task_id"],
        "RUNNING",
        note=f"auto-pickup trial `{tid}` at {trial['launched_at'][:19]}",
    )

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    note_path = INBOX_DIR / f"PICKED_UP_{task['task_id']}.md"
    note_path.write_text(
        f"# Auto-picked up — {task['task_id']}\n\n"
        f"- **trial_id:** `{tid}`\n"
        f"- **kind:** `{task.get('trial_kind')}`\n"
        f"- **cron_ids:** `{json.dumps(cron_ids)}`\n"
        f"- **handoff:** `{task.get('handoff')}`\n"
        f"- **at:** {_now_s()}\n"
    )
    result["ok"] = True
    result["cron_ids"] = cron_ids
    result["inbox"] = str(note_path.relative_to(PROJECT_ROOT))
    return result


def claim_and_launch(dry_run: bool = False) -> Dict[str, Any]:
    queue = scan()
    launched = []
    errors = []
    for task in queue.get("launchable_now") or []:
        try:
            launched.append(launch_one(task, dry_run=dry_run))
        except Exception as e:
            errors.append({"task_id": task.get("task_id"), "error": str(e)})
        if len(launched) >= MAX_LAUNCH_PER_RUN:
            break
    # also promote QUEUED→ ready note in queue file already
    out = {
        "at": _now_s(),
        "dry_run": dry_run,
        "ready_count": len(queue.get("ready") or []),
        "blocked_count": len(queue.get("blocked") or []),
        "launchable": [t["task_id"] for t in queue.get("launchable_now") or []],
        "launched": launched,
        "errors": errors,
    }
    state = _load_json(STATE_PATH, {"runs": []})
    state.setdefault("runs", []).append(out)
    state["runs"] = state["runs"][-50:]
    state["last"] = out
    _save_json(STATE_PATH, state)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="MASTER test auto-pickup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="Scan MASTER; write PICKUP_QUEUE.json (quiet if nothing ready)")
    p_launch = sub.add_parser("launch", help="Scan + launch up to cap")
    p_launch.add_argument("--dry-run", action="store_true")
    sub.add_parser("claim", help="Alias for launch")
    args = ap.parse_args(argv)

    if args.cmd == "scan":
        q = scan()
        ready = q.get("launchable_now") or []
        # no_agent friendly: silent if nothing to do
        if not ready and not q.get("blocked"):
            return 0
        # Always write queue; print only if action/alert useful
        if ready:
            print("MASTER TEST PICKUP — launchable")
            for t in ready:
                print(f"  READY {t['task_id']} kind={t.get('trial_kind')} family={t.get('family')}")
            print(f"Queue: {QUEUE_PATH}")
            return 0
        if q.get("blocked"):
            # silent blocked (normal while Stoch runs) unless VERBOSE
            if "--verbose" in (argv or []):
                print("blocked:", [b["task_id"] for b in q["blocked"]])
            return 0
        return 0

    if args.cmd in ("launch", "claim"):
        dry = bool(getattr(args, "dry_run", False))
        out = claim_and_launch(dry_run=dry)
        # Print summary when something happened or ready waiting without slot
        if out["launched"] or out["errors"] or out["ready_count"]:
            print(json.dumps(out, indent=2))
            return 0 if not out["errors"] else 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
