#!/usr/bin/env python3
"""
Deterministic Phase 6 ops triage discovery (Phase1 cost — no LLM).

Writes data/state/ops_triage.md. Prints summary to stdout only when
high/medium open findings exist (Telegram-friendly). Exit 0 always unless
hard failure.

By default **auto-promotes** medium/high findings into ops_task_registry
(+ GitHub) so ops_issue_loop can ensure Kanban cards for auto pickup.

Usage:
  python3 scripts/phase6/ops_triage_discover.py
  python3 scripts/phase6/ops_triage_discover.py --json
  python3 scripts/phase6/ops_triage_discover.py --no-auto-promote
  python3 scripts/phase6/ops_triage_discover.py --run-issue-loop
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/state/ops_triage.md"
RUNNER_LOG = ROOT / "logs/phase6_runner.log"
MONITOR_LOG = ROOT / "logs/monitor.log"
STATE = ROOT / "data/state/phase6_runner_state.json"
JOBS_JSON = Path.home() / ".hermes/cron/jobs.json"


def _run(cmd: list[str], timeout: int = 60) -> str:
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (cp.stdout or "") + (cp.stderr or "")
    except Exception as e:
        return f"ERR: {e}"


def _auto_promote(findings: list[dict], *, no_github: bool = False) -> list[dict]:
    """Promote medium/high into registry (idempotent)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.phase6.ops_triage_tasks import promote_finding  # type: ignore

    out: list[dict] = []
    for f in findings:
        if f.get("priority") not in ("high", "medium"):
            continue
        if f.get("status") not in ("open", None, ""):
            continue
        entry = promote_finding(
            f["finding"],
            priority=str(f.get("priority") or "medium"),
            evidence=f.get("evidence") or "ops_triage_discover",
            no_github=no_github,
            source="ops_triage_discover_auto",
            extra={
                "auto_promoted": True,
                "cron_job_id": f.get("cron_job_id"),
                "cron_name": f.get("cron_name"),
            },
        )
        out.append(entry)
        existing = entry.get("existing") if entry.get("skipped") else None
        if existing:
            f["task"] = existing.get("id")
            f["status"] = "open"
        else:
            f["task"] = entry.get("id")
            f["github_issue"] = entry.get("github_issue")
            f["status"] = "promoted"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--no-auto-promote",
        action="store_true",
        help="Discover only (legacy). Default promotes medium/high → registry.",
    )
    ap.add_argument(
        "--no-github",
        action="store_true",
        help="When auto-promoting, skip gh issue create",
    )
    ap.add_argument(
        "--run-issue-loop",
        action="store_true",
        help="After promote, run ops_issue_loop (Kanban ensure + dispatch)",
    )
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    findings: list[dict] = []

    # Runner liveness
    runner_out = _run(["pgrep", "-af", "phase6.core.phase6_runner"])
    runner_up = bool(runner_out.strip()) and not runner_out.startswith("ERR:")
    if not runner_up:
        findings.append(
            {
                "priority": "high",
                "status": "open",
                "finding": "Phase6 runner not running (pgrep empty)",
                "evidence": "pgrep phase6.core.phase6_runner",
            }
        )

    # Same-session SL (optional)
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from phase6.core.same_session_sl import ops_finding_if_any, summarize as ss_sum

        _ = ss_sum(persist=True)
        finding = ops_finding_if_any(lookback_days=3.0)
        if finding:
            findings.append(
                {
                    "priority": finding.get("priority") or "medium",
                    "status": "open",
                    "finding": finding["finding"][:180],
                    "evidence": finding.get("evidence")
                    or "data/state/same_session_sl_latest.json",
                }
            )
    except Exception:
        pass

    # Hermes cron errors via jobs.json SSOT (not sticky TG delivery text)
    try:
        raw = json.loads(JOBS_JSON.read_text()) if JOBS_JSON.exists() else []
        jobs = raw if isinstance(raw, list) else raw.get("jobs", [])
    except Exception:
        jobs = []
    for j in jobs:
        if not j.get("enabled", True):
            continue
        if str(j.get("last_status") or "").lower() != "error":
            continue
        name = str(j.get("name") or j.get("id") or "unknown")
        jid = str(j.get("id") or "")
        findings.append(
            {
                "priority": "medium",
                "status": "open",
                "finding": f"Hermes cron recent error: {name}",
                "evidence": f"~/.hermes/cron/jobs.json id={jid}",
                "cron_job_id": jid,
                "cron_name": name,
            }
        )

    pri_rank = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(findings, key=lambda f: pri_rank.get(f["priority"], 9))[:3]

    promoted: list[dict] = []
    if not args.no_auto_promote:
        try:
            promoted = _auto_promote(findings, no_github=bool(args.no_github))
        except Exception as exc:
            promoted = [{"error": str(exc)}]

    loop_rc = None
    if args.run_issue_loop and not args.no_auto_promote:
        cp = subprocess.run(
            [
                str(ROOT / ".venv/bin/python3"),
                str(ROOT / "scripts/phase6/ops_issue_loop.py"),
                "run",
                "--gh-assign",
                "--dispatch",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        loop_rc = cp.returncode

    lines = [
        f"# Ops triage — {day}",
        "",
        f"_Generated by `ops_triage_discover.py` (no LLM) at {now}_",
        "",
        "| Finding | Evidence | Priority | Status | Task |",
        "|---------|----------|----------|--------|------|",
    ]
    if not findings:
        lines.append("| (none) | runner/logs/cron clean enough | low | ok | |")
    else:
        for f in findings:
            tid = f.get("task") or ""
            lines.append(
                f"| {f['finding'][:100]} | `{f['evidence']}` | {f['priority']} | "
                f"{f.get('status', 'open')} | {tid} |"
            )
    lines += [
        "",
        "## Notes",
        f"- Runner up: **{runner_up}**",
        f"- Auto-promote: **{not args.no_auto_promote}** (medium/high → registry → Kanban loop)",
        "- Issue loop: `python3 scripts/phase6/ops_issue_loop.py run --gh-assign --dispatch`",
        "- Full agent skill `phase6-ops-triage` only if this script is insufficient.",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    actionable = [f for f in findings if f["priority"] in ("high", "medium")]
    payload = {
        "as_of": now,
        "runner_up": runner_up,
        "findings": findings,
        "actionable": len(actionable),
        "promoted": promoted,
        "issue_loop_rc": loop_rc,
        "path": str(OUT),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    elif actionable:
        print(
            f"OPS_TRIAGE {day}: {len(actionable)} actionable "
            f"(auto-promote={not args.no_auto_promote})"
        )
        for f in actionable:
            print(f"- [{f['priority']}] {f['finding']} → {f.get('task') or f.get('status')}")
        print(f"See {OUT}")
        print("Kanban: ops_issue_loop ensures cards on crypto-bot-project")
    else:
        # Quiet when healthy — Hermes no_agent empty stdout = no TG filler
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
