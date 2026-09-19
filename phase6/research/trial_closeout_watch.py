#!/usr/bin/env python3
"""
Trial closeout watchdog — stop quiet deaths.

Problem Brad named: a trial hits final_at (or REPORT_READY) and nothing
forces a summary + decision ask into Telegram / inbox / MASTER. It ends quietly.

This job is measure + notify only:
  - never decide
  - never edit live trading knobs
  - never auto-promote
  - does write REVIEW_/OVERDUE_ inbox packets + optional short TG body

Deliver rules (cron --deliver):
  - print short card only when ≥1 item needs Brad action
  - empty stdout when nothing overdue (silent)
  - full JSON always on disk
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.paths import load_project_dotenv

load_project_dotenv()

from phase6.research.trial_cycle import (  # noqa: E402
    INBOX_DIR,
    TRIALS_DIR,
    check_report_completeness,
    load_trial,
    reindex,
    scan_stale,
    write_review_request,
)

STATE = ROOT / "data" / "state"
OUT_JSON = STATE / "trial_closeout_watch_latest.json"
OUT_MD = STATE / "trial_closeout_watch_latest.md"
OUT_TXT = STATE / "trial_closeout_watch_latest.txt"
PREV_FP = STATE / "trial_closeout_watch_fingerprint.txt"
HISTORY = STATE / "trial_closeout_watch_history.jsonl"
MASTER = ROOT / "docs" / "MASTER_TASK_TRACKING.md"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat().replace("+00:00", "Z")


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _trial_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in sorted(TRIALS_DIR.glob("*.json")):
        if p.name in {"INDEX.json", "PICKUP_QUEUE.json", "PICKUP_STATE.json", "TEST_STRATEGY.json"}:
            continue
        try:
            t = json.loads(p.read_text() or "{}")
        except Exception:
            continue
        if not isinstance(t, dict) or not t.get("trial_id"):
            continue
        rows.append(t)
    return rows


def _write_overdue_packet(t: Dict[str, Any], reason: str, issues: List[str]) -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    tid = str(t.get("trial_id"))
    path = INBOX_DIR / f"OVERDUE_{tid}.md"
    rec = t.get("final_recommendation") or "—"
    final = t.get("final_report") or "—"
    body = (
        f"# Closeout overdue — {tid}\n\n"
        f"**Status:** `{t.get('status')}`\n\n"
        f"**Reason:** `{reason}`\n\n"
        f"**final_at:** `{t.get('final_at')}`\n\n"
        f"**Final report:** `{final}`\n\n"
        f"**Proposed recommendation:** `{rec}`\n\n"
        f"**Completeness issues:** {issues or 'none'}\n\n"
        f"**Family:** `{t.get('family')}` · **MASTER:** `{t.get('master_id')}`\n\n"
        f"## Why this ping exists\n\n"
        f"Trials must not end quietly. Past `final_at` without finalize → review → "
        f"`decide` is a process bug. This packet is the forced decision ask.\n\n"
        f"## Operator path\n\n"
        f"```bash\n"
        f"cd /home/brad/projects/crypto-trading-bot\n"
        f"# 1) If report missing, run the family final/report runner, then:\n"
        f".venv/bin/python3 phase6/research/trial_cycle.py finalize-report {tid} \\\n"
        f"  --report reports/<STEM>.md --json reports/<STEM>.json \\\n"
        f"  --enum drop|continue_observe_only|… --outcome-class <class> \\\n"
        f"  --primary-pass false --plain-english '…'\n"
        f".venv/bin/python3 phase6/research/trial_cycle.py review-request {tid}\n"
        f"# 2) Brad decide (closes trial + MASTER):\n"
        f".venv/bin/python3 phase6/research/trial_cycle.py decide {tid} <enum> \\\n"
        f"  --note '…' --follow-on none|extend|scoped_shadow|promotion_queue\n"
        f"```\n\n"
        f"Enums: `continue_observe_only` | `extend_trial` | `propose_scoped_experiment` | "
        f"`drop` | `promote_blend` | `promote_primary` | `abort`\n"
    )
    path.write_text(body)
    return path


def _orphan_review_files(open_ids: set) -> List[Dict[str, Any]]:
    """REVIEW_*.md whose trial is already CLOSED/KILLED — inbox hygiene."""
    out: List[Dict[str, Any]] = []
    if not INBOX_DIR.exists():
        return out
    for p in sorted(INBOX_DIR.glob("REVIEW_*.md")):
        tid = p.name[len("REVIEW_") : -len(".md")]
        if tid in open_ids:
            continue
        # trial closed or missing
        tp = TRIALS_DIR / f"{tid}.json"
        st = None
        if tp.exists():
            try:
                st = (json.loads(tp.read_text()) or {}).get("status")
            except Exception:
                st = None
        if st in ("CLOSED", "KILLED") or st is None:
            out.append(
                {
                    "trial_id": tid,
                    "kind": "orphan_review_inbox",
                    "status": st or "missing_trial",
                    "path": str(p.relative_to(ROOT)),
                    "action": "archive_or_delete_REVIEW_md",
                }
            )
    return out


def build_watch(grace_hours: float = 48.0, write_packets: bool = True) -> Dict[str, Any]:
    reindex()
    stale = scan_stale(grace_hours=grace_hours)
    by_id = {s["trial_id"]: s for s in stale if s.get("trial_id")}

    actions: List[Dict[str, Any]] = []
    open_ids: set = set()

    for t in _trial_rows():
        tid = str(t.get("trial_id"))
        st = str(t.get("status") or "")
        if st not in ("CLOSED", "KILLED"):
            open_ids.add(tid)

        item: Optional[Dict[str, Any]] = None
        reason = None
        if tid in by_id:
            reason = by_id[tid].get("reason")
        elif st == "REPORT_READY":
            # no final_report_at age yet — still needs review packet
            reason = "report_ready_needs_review"
        elif st == "REVIEW_PENDING":
            fr = _parse_ts(t.get("final_report_at") or t.get("updated_at") or t.get("final_at"))
            if fr and (_now() - fr).total_seconds() > grace_hours * 3600:
                reason = "review_overdue"
            else:
                reason = "review_pending_awaiting_brad"

        if not reason:
            continue

        issues = check_report_completeness(t) if st in ("RUNNING", "DEGRADED", "REPORT_READY", "REVIEW_PENDING") else []
        packet = None
        if write_packets:
            if st == "REPORT_READY" and reason in ("report_ready_needs_review", "review_overdue"):
                try:
                    packet = str(write_review_request(tid).relative_to(ROOT))
                    # reload status after review-request may flip to REVIEW_PENDING
                    t = load_trial(tid)
                    st = str(t.get("status") or st)
                except Exception as e:
                    packet = f"review_request_failed:{e}"
            elif reason in ("past_final_still_open", "review_overdue") or (
                st in ("RUNNING", "DEGRADED") and reason
            ):
                try:
                    packet = str(_write_overdue_packet(t, reason, issues).relative_to(ROOT))
                except Exception as e:
                    packet = f"overdue_packet_failed:{e}"

        item = {
            "trial_id": tid,
            "status": st,
            "reason": reason,
            "family": t.get("family"),
            "master_id": t.get("master_id"),
            "final_at": t.get("final_at"),
            "final_report": t.get("final_report"),
            "final_recommendation": t.get("final_recommendation"),
            "completeness_issues": issues,
            "packet": packet,
            "needs_brad": True,
            "severity": "high"
            if reason in ("past_final_still_open", "review_overdue")
            else "medium",
        }
        actions.append(item)

    orphans = _orphan_review_files(open_ids)
    # orphans are hygiene, not necessarily TG-page every day — include in board, TG only if any high needs_brad

    # fingerprint = actionable set (not orphan noise)
    fp_payload = sorted(
        f"{a['trial_id']}|{a['status']}|{a['reason']}|{a.get('final_recommendation')}"
        for a in actions
    )
    raw = json.dumps(fp_payload, sort_keys=True)
    fp = hashlib.sha256(raw.encode()).hexdigest()[:16]
    prev = PREV_FP.read_text().strip() if PREV_FP.exists() else ""
    changed = (not prev) or (prev != fp)

    board = {
        "schema": "trial_closeout_watch_v1",
        "as_of": _iso(),
        "grace_hours": grace_hours,
        "n_actions": len(actions),
        "n_orphans": len(orphans),
        "actions": actions,
        "orphans": orphans,
        "fingerprint": fp,
        "fingerprint_changed": changed,
        # TG when something needs Brad AND (new fingerprint OR high severity still open)
        "tg_deliver": bool(actions) and (changed or any(a.get("severity") == "high" for a in actions)),
        "plain_english": _plain(actions, orphans),
    }
    return board


def _plain(actions: List[Dict[str, Any]], orphans: List[Dict[str, Any]]) -> str:
    if not actions and not orphans:
        return "No trial closeout debt. Nothing needs a decide ping."
    bits = []
    for a in actions:
        bits.append(
            f"{a['trial_id']} is {a['status']} ({a['reason']})"
            + (f" — missing: {', '.join(a['completeness_issues'][:3])}" if a.get("completeness_issues") else "")
        )
    if orphans:
        bits.append(f"{len(orphans)} orphan REVIEW inbox file(s) after CLOSED trial")
    return "; ".join(bits)


def format_tg(board: Dict[str, Any]) -> str:
    lines = [
        f"Trial closeout watch · {_iso()[:16].replace('T', ' ')}",
        f"n_actions={board.get('n_actions')} · orphans={board.get('n_orphans')}",
    ]
    for a in board.get("actions") or []:
        lines.append(
            f"• {a.get('trial_id')} · {a.get('status')} · {a.get('reason')}"
            + (f" · issues={a.get('completeness_issues')}" if a.get("completeness_issues") else "")
        )
        if a.get("packet"):
            lines.append(f"  packet: {a['packet']}")
        lines.append(
            "  next: finalize-report (if needed) → review-request → "
            f"trial_cycle.py decide {a.get('trial_id')} <enum>"
        )
    for o in (board.get("orphans") or [])[:3]:
        lines.append(f"• orphan REVIEW: {o.get('trial_id')} ({o.get('status')}) — archive inbox file")
    lines.append("No auto-decide. No live knobs.")
    lines.append("")
    return "\n".join(lines)


def format_md(board: Dict[str, Any]) -> str:
    lines = [
        "# Trial closeout watch",
        "",
        f"- as_of: `{board.get('as_of')}`",
        f"- n_actions: **{board.get('n_actions')}**",
        f"- n_orphans: {board.get('n_orphans')}",
        f"- tg_deliver: {board.get('tg_deliver')}",
        f"- plain: {board.get('plain_english')}",
        "",
        "## Actions",
        "",
    ]
    if not board.get("actions"):
        lines.append("_none_")
    for a in board.get("actions") or []:
        lines.append(
            f"- **{a.get('trial_id')}** · `{a.get('status')}` · `{a.get('reason')}` · "
            f"packet=`{a.get('packet')}`"
        )
        if a.get("completeness_issues"):
            lines.append(f"  - issues: {a['completeness_issues']}")
    lines.extend(["", "## Orphan REVIEW inbox", ""])
    if not board.get("orphans"):
        lines.append("_none_")
    for o in board.get("orphans") or []:
        lines.append(f"- {o.get('trial_id')} · {o.get('path')}")
    lines.append("")
    return "\n".join(lines)


def persist(board: Dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(board, indent=2, default=str) + "\n")
    OUT_MD.write_text(format_md(board))
    OUT_TXT.write_text(format_tg(board) if board.get("actions") else "quiet\n")
    if board.get("fingerprint"):
        PREV_FP.write_text(str(board["fingerprint"]))
    try:
        with HISTORY.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "as_of": board.get("as_of"),
                        "n_actions": board.get("n_actions"),
                        "tg_deliver": board.get("tg_deliver"),
                        "fingerprint": board.get("fingerprint"),
                        "ids": [a.get("trial_id") for a in board.get("actions") or []],
                    },
                    default=str,
                )
                + "\n"
            )
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grace-hours", type=float, default=48.0)
    ap.add_argument("--deliver", action="store_true", help="Cron: print TG only when action needed")
    ap.add_argument("--force", action="store_true", help="Always print TG card")
    ap.add_argument("--print", action="store_true", help="Print full markdown")
    ap.add_argument("--no-write-packets", action="store_true")
    args = ap.parse_args(argv)

    board = build_watch(
        grace_hours=float(args.grace_hours),
        write_packets=not args.no_write_packets,
    )
    persist(board)

    if args.print:
        print(format_md(board), end="")
        return 0 if not board.get("actions") else 0

    should = bool(args.force) or (args.deliver and board.get("tg_deliver"))
    if not args.deliver and not args.force:
        # human CLI default: show card if actions else quiet note
        should = bool(board.get("actions"))
        if not should:
            print("trial closeout watch: quiet (no debt)")
            return 0
    if should:
        print(format_tg(board), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
