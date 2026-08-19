#!/usr/bin/env python3
"""
Ops Issue Loop — identify → triage → auto-assign → Kanban → resolve → close.

Kanban is the work engine (crypto-bot-project). This script is the deterministic
glue: sync GitHub issues into the ops registry, route assignee/priority, ensure
a Kanban card exists, and reconcile closed Kanban/GH back to the registry.

See docs/OPS_ISSUE_LOOP.md and docs/OPS_TRIAGE_TASK_WORKFLOW.md.

Usage:
  python3 scripts/phase6/ops_issue_loop.py status
  python3 scripts/phase6/ops_issue_loop.py run          # full tick (default)
  python3 scripts/phase6/ops_issue_loop.py sync
  python3 scripts/phase6/ops_issue_loop.py route
  python3 scripts/phase6/ops_issue_loop.py ensure-kanban
  python3 scripts/phase6/ops_issue_loop.py reconcile
  python3 scripts/phase6/ops_issue_loop.py dispatch     # hermes kanban dispatch once
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/state/ops_task_registry.jsonl"
LATEST = ROOT / "data/state/ops_issue_loop_latest.json"
HISTORY = ROOT / "data/state/ops_issue_loop_history.jsonl"
BOARD = "crypto-bot-project"
REPO = "brad-sl/operations"
GH_LABEL = "Trading Bot"

# Keyword → (assignee profile, priority int 1=highest, skill hints)
ROUTES: list[tuple[re.Pattern[str], str, int, list[str]]] = [
    (re.compile(r"missing protective stop|sl_attached|stop.?loss|protective.?order", re.I), "crypto-engineer", 1, ["trading-bot-operations", "phase6-ops-triage"]),
    (re.compile(r"_clear_deferred|AttributeError|rebalance blocked|missed rebalance|cycle_coordinator", re.I), "crypto-engineer", 1, ["trading-bot-operations"]),
    (re.compile(r"runner|phase6_runner|RUNNER_DOWN|dashboard.?pnl|price.?stale|quote fresh", re.I), "crypto-engineer", 2, ["trading-bot-operations", "phase6-capital-and-dashboard-kpis"]),
    (re.compile(r"analyst.?opt|regime.?cash.?validation|TypeError|param.?audit|scorecard", re.I), "crypto-engineer", 2, ["trading-bot-operations", "crypto-analyst-scenario-run"]),
    (re.compile(r"sentiment|x.?api|cron|hermes cron", re.I), "crypto-engineer", 3, ["hermes-operations", "trading-bot-operations"]),
    (re.compile(r"doc.?boundary|documentation|MASTER", re.I), "crypto-orchestrator", 4, ["kanban-orchestrator"]),
]
DEFAULT_ASSIGNEE = "crypto-engineer"
DEFAULT_PRIORITY = 3
DEFAULT_SKILLS = ["trading-bot-operations", "phase6-ops-triage"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in REGISTRY.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _save_registry(rows: list[dict[str, Any]]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
        encoding="utf-8",
    )


def _next_id(rows: list[dict[str, Any]], day: str) -> str:
    prefix = f"P6-OPS-{day.replace('-', '')}-"
    nums = []
    for r in rows:
        rid = str(r.get("id", ""))
        if rid.startswith(prefix):
            try:
                nums.append(int(rid.split("-")[-1]))
            except ValueError:
                pass
    return f"{prefix}{max(nums, default=0) + 1:03d}"


def _slug(s: str, n: int = 40) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-")
    return t[:n] or "issue"


def _route_text(title: str, body: str = "") -> tuple[str, int, list[str]]:
    blob = f"{title}\n{body}"
    for pat, assignee, pri, skills in ROUTES:
        if pat.search(blob):
            return assignee, pri, skills
    return DEFAULT_ASSIGNEE, DEFAULT_PRIORITY, list(DEFAULT_SKILLS)


def _gh_open_issues() -> list[dict[str, Any]]:
    """Open issues on operations repo with Trading Bot label (or all open if label filter empty)."""
    cp = _run(
        [
            "gh",
            "issue",
            "list",
            "-R",
            REPO,
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,body,labels,assignees,createdAt,updatedAt,url",
        ]
    )
    if cp.returncode != 0:
        print(f"gh issue list failed: {cp.stderr[:300]}", file=sys.stderr)
        return []
    try:
        issues = json.loads(cp.stdout or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for it in issues:
        labels = {str(x.get("name", "")) for x in (it.get("labels") or [])}
        # Prefer Trading Bot; still ingest unlabeled P6-OPS titles
        title = it.get("title") or ""
        if GH_LABEL in labels or title.startswith("P6-OPS") or "ops triage" in title.lower():
            out.append(it)
    return out


def cmd_sync(args: argparse.Namespace) -> int:
    """Pull open GH issues into registry if missing."""
    rows = _load_registry()
    by_issue = {int(r["github_issue"]): r for r in rows if r.get("github_issue")}
    created = 0
    linked = 0
    for it in _gh_open_issues():
        num = int(it["number"])
        title = it.get("title") or ""
        body = it.get("body") or ""
        finding = title
        if title.startswith("P6-OPS:"):
            finding = title[len("P6-OPS:") :].strip()
        if num in by_issue:
            r = by_issue[num]
            if r.get("status") == "done":
                # reopened on GH — reopen registry
                r["status"] = "open"
                r.pop("closed", None)
                r["reopened_by_loop"] = _now()
                linked += 1
            continue
        # match open row by slug without github_issue
        slug = _slug(finding)
        matched = None
        for r in rows:
            if r.get("status") == "open" and not r.get("github_issue") and _slug(r.get("finding", "")) == slug:
                matched = r
                break
        if matched:
            matched["github_issue"] = num
            matched["github_url"] = it.get("url")
            linked += 1
            continue
        day = _day()
        task_id = _next_id(rows, day)
        assignee, pri, skills = _route_text(title, body)
        entry = {
            "id": task_id,
            "opened": day,
            "source": "github_sync",
            "priority": "high" if pri <= 1 else ("medium" if pri <= 3 else "low"),
            "priority_rank": pri,
            "status": "open",
            "finding": finding[:500],
            "master_ref": f"P6-OPS-{slug.upper()[:32]}",
            "evidence": [],
            "github_issue": num,
            "github_url": it.get("url"),
            "assignee": assignee,
            "skills": skills,
            "loop": {"synced_at": _now()},
        }
        rows.append(entry)
        by_issue[num] = entry
        created += 1
    _save_registry(rows)
    print(json.dumps({"sync": True, "created": created, "linked": linked, "open_gh": len(_gh_open_issues())}, indent=2))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    """Fill assignee/priority/skills on open registry rows; optional gh assignee."""
    rows = _load_registry()
    updated = 0
    for r in rows:
        if r.get("status") != "open":
            continue
        title = r.get("finding") or ""
        assignee, pri, skills = _route_text(title, "")
        changed = False
        if not r.get("assignee"):
            r["assignee"] = assignee
            changed = True
        if "priority_rank" not in r:
            r["priority_rank"] = pri
            changed = True
        if not r.get("skills"):
            r["skills"] = skills
            changed = True
        if r.get("priority") not in ("high", "medium", "low"):
            r["priority"] = "high" if pri <= 1 else ("medium" if pri <= 3 else "low")
            changed = True
        # GitHub assignee = human owner (brad-sl); Kanban assignee = profile
        issue = r.get("github_issue")
        if issue and args.gh_assign and not r.get("gh_assigned"):
            cp = _run(["gh", "issue", "edit", str(issue), "-R", REPO, "--add-assignee", "@me"])
            if cp.returncode == 0:
                r["gh_assigned"] = "brad-sl"
                r["gh_assigned_at"] = _now()
                changed = True
            else:
                r["gh_assign_error"] = (cp.stderr or cp.stdout or "")[:200]
        if changed:
            r.setdefault("loop", {})["routed_at"] = _now()
            updated += 1
    _save_registry(rows)
    print(json.dumps({"route": True, "updated": updated}, indent=2))
    return 0


def _kanban_create(r: dict[str, Any]) -> dict[str, Any]:
    issue = r.get("github_issue")
    idem = f"ops-issue-{issue}" if issue else f"ops-reg-{r.get('id')}"
    title = f"P6-OPS fix: {str(r.get('finding', ''))[:70]}"
    if issue:
        title = f"#{issue} {title}"
    body = (
        f"## Ops Issue Loop\n"
        f"- Registry: `{r.get('id')}`\n"
        f"- GitHub: {r.get('github_url') or ('#' + str(issue) if issue else 'n/a')}\n"
        f"- Priority: {r.get('priority')} (rank {r.get('priority_rank')})\n"
        f"- Source: {r.get('source')}\n\n"
        f"## Finding\n{r.get('finding')}\n\n"
        f"## Must Do (OPS_TRIAGE_TASK_WORKFLOW)\n"
        f"1. Reproduce with tools (audit scripts, logs, live state) — real data only.\n"
        f"2. Fix root cause; add/adjust isolation test if code change.\n"
        f"3. Verify live (audit green / error gone / API OK).\n"
        f"4. Close GH issue with evidence comment; "
        f"`python3 scripts/phase6/ops_triage_tasks.py close --id {r.get('id')} --note '...'`\n"
        f"5. Append MASTER DONE line; update ops_triage.md if listed.\n\n"
        f"## Must Not\n"
        f"- Fake prices/positions; silent config promotion; scope creep into marketing.\n\n"
        f"## Skills\n"
        + ", ".join(r.get("skills") or DEFAULT_SKILLS)
        + f"\n\nIdempotency: `{idem}`\n"
    )
    assignee = r.get("assignee") or DEFAULT_ASSIGNEE
    pri = int(r.get("priority_rank") or DEFAULT_PRIORITY)
    cmd = [
        "hermes",
        "kanban",
        "--board",
        BOARD,
        "create",
        title,
        "--assignee",
        assignee,
        "--body",
        body,
        "--priority",
        str(pri),
        "--idempotency-key",
        idem,
        "--workspace",
        f"dir:{ROOT}",
        "--max-runtime",
        "45m",
        "--created-by",
        "ops-issue-loop",
        "--json",
    ]
    for sk in r.get("skills") or DEFAULT_SKILLS:
        cmd.extend(["--skill", sk])
    # Phase1 cost (2026-07-20): default NO --goal (was 25-turn loops).
    # --goal enables goal mode only for priority_rank <= 1; --force-goal for any rank.
    # Max turns capped at 12 when goal is on.
    pri = int(r.get("priority_rank") or DEFAULT_PRIORITY)
    use_goal = False
    if _FORCE_GOAL:
        use_goal = True
    elif _ALLOW_GOAL and pri <= 1:
        use_goal = True
    if use_goal:
        cmd.append("--goal")
        cmd.extend(["--goal-max-turns", str(_GOAL_MAX_TURNS)])
    cp = _run(cmd, timeout=90)
    out: dict[str, Any] = {
        "returncode": cp.returncode,
        "stdout": (cp.stdout or "")[:2000],
        "stderr": (cp.stderr or "")[:500],
    }
    # parse json id
    text = (cp.stdout or "").strip()
    tid = None
    try:
        # last json object in output
        if text.startswith("{"):
            data = json.loads(text)
            tid = data.get("id") or data.get("task_id")
        else:
            m = re.search(r'"id"\s*:\s*"(t_[a-f0-9]+)"', text)
            if m:
                tid = m.group(1)
            else:
                m2 = re.search(r"\b(t_[a-f0-9]{8,})\b", text)
                if m2:
                    tid = m2.group(1)
    except json.JSONDecodeError:
        m = re.search(r"\b(t_[a-f0-9]{8,})\b", text)
        if m:
            tid = m.group(1)
    out["task_id"] = tid
    out["idempotency_key"] = idem
    return out


_ALLOW_GOAL = False  # set True only when CLI --goal
_FORCE_GOAL = False  # set True when CLI --force-goal
_GOAL_MAX_TURNS = 12
_DRY_GOAL = True  # legacy alias: True means "skip goal" (Phase1 default)


def args_dry_goal() -> bool:
    """Deprecated name: True = do not attach --goal."""
    return not (_FORCE_GOAL or (_ALLOW_GOAL and True))


def cmd_ensure_kanban(args: argparse.Namespace) -> int:
    global _ALLOW_GOAL, _FORCE_GOAL, _DRY_GOAL, _GOAL_MAX_TURNS
    # --no-goal is default; --goal enables high-only; --force-goal any rank
    _FORCE_GOAL = bool(getattr(args, "force_goal", False))
    _ALLOW_GOAL = bool(getattr(args, "goal", False)) or _FORCE_GOAL
    _DRY_GOAL = not _ALLOW_GOAL
    if getattr(args, "goal_max_turns", None):
        _GOAL_MAX_TURNS = int(args.goal_max_turns)
    rows = _load_registry()
    results = []
    for r in rows:
        if r.get("status") not in ("open", "in_progress"):
            continue
        if r.get("kanban_task_id") and not args.force:
            results.append({"id": r.get("id"), "skipped": "has_kanban", "task": r.get("kanban_task_id")})
            continue
        if args.dry_run:
            assignee, pri, skills = _route_text(r.get("finding") or "", "")
            pri = int(r.get("priority_rank") or pri)
            would_goal = _FORCE_GOAL or (_ALLOW_GOAL and pri <= 1)
            results.append(
                {
                    "id": r.get("id"),
                    "dry_run": True,
                    "would_assignee": r.get("assignee") or assignee,
                    "priority_rank": pri,
                    "skills": r.get("skills") or skills,
                    "would_goal": would_goal,
                    "goal_max_turns": _GOAL_MAX_TURNS if would_goal else 0,
                }
            )
            continue
        out = _kanban_create(r)
        if out.get("task_id"):
            r["kanban_task_id"] = out["task_id"]
            r["kanban_board"] = BOARD
            r["kanban_idempotency_key"] = out.get("idempotency_key")
            r.setdefault("loop", {})["kanban_ensured_at"] = _now()
            r["status"] = "in_progress"
            # label GH
            issue = r.get("github_issue")
            if issue:
                _run(
                    [
                        "gh",
                        "issue",
                        "comment",
                        str(issue),
                        "-R",
                        REPO,
                        "--body",
                        f"Ops Issue Loop: Kanban `{out['task_id']}` on `{BOARD}` "
                        f"(assignee profile `{r.get('assignee')}`). "
                        f"Worker will fix → verify → close.",
                    ]
                )
        results.append({"id": r.get("id"), "issue": r.get("github_issue"), **out})
    _save_registry(rows)
    print(json.dumps({"ensure_kanban": True, "results": results}, indent=2))
    return 0


def _kanban_show(task_id: str) -> dict[str, Any] | None:
    cp = _run(["hermes", "kanban", "--board", BOARD, "show", task_id, "--json"], timeout=60)
    if cp.returncode != 0:
        # try without json
        cp2 = _run(["hermes", "kanban", "--board", BOARD, "show", task_id], timeout=60)
        text = (cp2.stdout or "") + (cp2.stderr or "")
        status = None
        m = re.search(r"status[:\s]+(\w+)", text, re.I)
        if m:
            status = m.group(1).lower()
        return {"id": task_id, "status": status, "raw": text[:500]} if status else None
    try:
        return json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        text = cp.stdout or ""
        m = re.search(r'"status"\s*:\s*"([^"]+)"', text)
        return {"id": task_id, "status": m.group(1) if m else None, "raw": text[:500]}


def cmd_reconcile(args: argparse.Namespace) -> int:
    """If Kanban done or GH closed → registry done + close the other side."""
    rows = _load_registry()
    actions = []
    for r in rows:
        if r.get("status") not in ("open", "in_progress"):
            continue
        issue = r.get("github_issue")
        ktid = r.get("kanban_task_id")
        gh_closed = False
        if issue:
            cp = _run(
                ["gh", "issue", "view", str(issue), "-R", REPO, "--json", "state"],
                timeout=30,
            )
            try:
                st = json.loads(cp.stdout or "{}").get("state", "").upper()
                gh_closed = st == "CLOSED"
            except json.JSONDecodeError:
                pass
        kanban_done = False
        if ktid:
            info = _kanban_show(str(ktid))
            st = (info or {}).get("status") or ""
            if str(st).lower() in ("done", "completed", "complete", "archived"):
                kanban_done = True
            r.setdefault("loop", {})["kanban_status"] = st

        if gh_closed or kanban_done:
            note = []
            if kanban_done:
                note.append(f"kanban {ktid} done")
            if gh_closed:
                note.append(f"gh #{issue} closed")
            r["status"] = "done"
            r["closed"] = _day()
            r["resolution_note"] = r.get("resolution_note") or ("loop reconcile: " + ", ".join(note))
            r.setdefault("loop", {})["reconciled_at"] = _now()
            # close GH if still open
            if issue and not gh_closed:
                _run(
                    [
                        "gh",
                        "issue",
                        "close",
                        str(issue),
                        "-R",
                        REPO,
                        "--comment",
                        f"Closed by ops_issue_loop reconcile — Kanban `{ktid}` complete.",
                    ]
                )
            # complete kanban if GH closed but card still open
            if ktid and gh_closed and not kanban_done:
                _run(
                    [
                        "hermes",
                        "kanban",
                        "--board",
                        BOARD,
                        "complete",
                        str(ktid),
                    ]
                )
            actions.append({"id": r.get("id"), "closed": True, "note": note})
    _save_registry(rows)
    print(json.dumps({"reconcile": True, "actions": actions}, indent=2))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    cp = _run(["hermes", "kanban", "--board", BOARD, "dispatch"], timeout=180)
    print(cp.stdout or "")
    if cp.stderr:
        print(cp.stderr, file=sys.stderr)
    return cp.returncode


def cmd_status(args: argparse.Namespace) -> int:
    rows = _load_registry()
    open_rows = [r for r in rows if r.get("status") in ("open", "in_progress")]
    payload = {
        "as_of": _now(),
        "board": BOARD,
        "open_count": len(open_rows),
        "open": [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "issue": r.get("github_issue"),
                "kanban": r.get("kanban_task_id"),
                "assignee": r.get("assignee"),
                "priority": r.get("priority"),
                "finding": (r.get("finding") or "")[:100],
            }
            for r in open_rows
        ],
        "done_recent": [
            {"id": r.get("id"), "closed": r.get("closed"), "issue": r.get("github_issue")}
            for r in rows
            if r.get("status") == "done"
        ][-8:],
    }
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full tick: sync → route → ensure-kanban → reconcile → status → optional dispatch."""
    started = _now()
    results: dict[str, Any] = {"started_at": started}
    # chain
    for name, fn in [
        ("sync", cmd_sync),
        ("route", cmd_route),
        ("ensure_kanban", cmd_ensure_kanban),
        ("reconcile", cmd_reconcile),
    ]:
        # capture printed json by re-running logic is hard; call and note rc
        rc = fn(args)
        results[name] = {"rc": rc}
        if rc != 0:
            results["failed"] = name
            break
    if args.dispatch and "failed" not in results:
        results["dispatch"] = {"rc": cmd_dispatch(args)}
    cmd_status(args)
    results["finished_at"] = _now()
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(results, separators=(",", ":")) + "\n")
    print(json.dumps({"run_complete": results}, indent=2))
    return 0 if "failed" not in results else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Ops Issue Loop (GH ↔ registry ↔ Kanban)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sync", help="Ingest open GH issues into registry")
    sp.set_defaults(func=cmd_sync)

    rp = sub.add_parser("route", help="Auto-assign profile + priority")
    rp.add_argument("--gh-assign", action="store_true", help="Also assign GH issue to @me")
    rp.set_defaults(func=cmd_route)

    ep = sub.add_parser("ensure-kanban", help="Create Kanban cards for open registry rows")
    ep.add_argument("--dry-run", action="store_true")
    ep.add_argument("--force", action="store_true", help="Recreate even if kanban_task_id set")
    ep.add_argument(
        "--goal",
        action="store_true",
        help="Allow --goal on Kanban create for priority_rank<=1 only (default: off)",
    )
    ep.add_argument(
        "--force-goal",
        action="store_true",
        help="Allow --goal for any priority rank (expensive; avoid)",
    )
    ep.add_argument("--goal-max-turns", type=int, default=12, help="Goal turn cap when goal enabled")
    ep.add_argument(
        "--no-goal",
        action="store_true",
        help="Deprecated no-op: goal is off by default (Phase1 cost)",
    )
    ep.set_defaults(func=cmd_ensure_kanban)

    cp = sub.add_parser("reconcile", help="Close registry/GH when Kanban or GH finished")
    cp.set_defaults(func=cmd_reconcile)

    dp = sub.add_parser("dispatch", help="One hermes kanban dispatch pass")
    dp.set_defaults(func=cmd_dispatch)

    stp = sub.add_parser("status", help="Write ops_issue_loop_latest.json")
    stp.set_defaults(func=cmd_status)

    runp = sub.add_parser("run", help="Full loop tick")
    runp.add_argument("--gh-assign", action="store_true")
    runp.add_argument("--dispatch", action="store_true", help="Run kanban dispatch after ensure")
    runp.add_argument("--dry-run", action="store_true")
    runp.add_argument("--force", action="store_true")
    runp.add_argument("--goal", action="store_true")
    runp.add_argument("--force-goal", action="store_true")
    runp.add_argument("--goal-max-turns", type=int, default=12)
    runp.add_argument("--no-goal", action="store_true", help="Deprecated no-op")
    runp.set_defaults(func=cmd_run)

    args = p.parse_args()
    # defaults for shared flags
    if not hasattr(args, "gh_assign"):
        args.gh_assign = False
    if not hasattr(args, "dry_run"):
        args.dry_run = False
    if not hasattr(args, "force"):
        args.force = False
    if not hasattr(args, "goal"):
        args.goal = False
    if not hasattr(args, "force_goal"):
        args.force_goal = False
    if not hasattr(args, "goal_max_turns"):
        args.goal_max_turns = 12
    if not hasattr(args, "no_goal"):
        args.no_goal = False
    if not hasattr(args, "dispatch"):
        args.dispatch = False
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
