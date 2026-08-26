#!/usr/bin/env python3
"""Ops triage finding → durable registry (+ optional GitHub issue). See docs/OPS_TRIAGE_TASK_WORKFLOW.md."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/state/ops_task_registry.jsonl"


def _load_registry() -> list[dict]:
    if not REGISTRY.exists():
        return []
    rows = []
    for line in REGISTRY.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _save_registry(rows: list[dict]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n")


def _next_id(rows: list[dict], day: str) -> str:
    prefix = f"P6-OPS-{day.replace('-', '')}-"
    nums = []
    for r in rows:
        rid = r.get("id", "")
        if rid.startswith(prefix):
            try:
                nums.append(int(rid.split("-")[-1]))
            except ValueError:
                pass
    n = max(nums, default=0) + 1
    return f"{prefix}{n:03d}"


def _slug(s: str, n: int = 48) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return t[:n]


def cmd_list(args: argparse.Namespace) -> int:
    rows = _load_registry()
    if args.open:
        rows = [r for r in rows if r.get("status") == "open"]
    for r in rows:
        print(
            f"{r.get('id')}\t{r.get('status')}\tissue={r.get('github_issue')}\t{r.get('finding', '')[:80]}"
        )
    return 0


def promote_finding(
    finding: str,
    *,
    priority: str = "medium",
    evidence: list[str] | str | None = None,
    master_ref: str = "",
    no_github: bool = False,
    source: str = "ops_triage",
    extra: dict | None = None,
) -> dict:
    """Idempotent promote → registry (+ optional GH). Returns entry or skipped dict."""
    rows = _load_registry()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slug(finding)
    for r in rows:
        if r.get("status") in ("open", "in_progress") and _slug(r.get("finding", "")) == slug:
            return {"skipped": "duplicate", "existing": r}

    task_id = _next_id(rows, day)
    if not master_ref:
        master_ref = f"P6-OPS-{slug.upper()[:32]}"

    if isinstance(evidence, str):
        evidence_list = [p.strip() for p in evidence.split(",") if p.strip()]
    else:
        evidence_list = list(evidence or [])

    entry: dict = {
        "id": task_id,
        "opened": day,
        "source": source,
        "priority": priority,
        "status": "open",
        "finding": finding,
        "master_ref": master_ref,
        "evidence": evidence_list,
    }
    if extra:
        entry.update(extra)

    if not no_github:
        body = (
            f"## Source\nOps promote (`{task_id}`, source={source}).\n\n"
            f"## Finding\n{finding}\n\n"
            f"## Evidence\n"
            + "\n".join(f"- `{p}`" for p in evidence_list)
            + f"\n\n## MASTER\n`docs/MASTER_TASK_TRACKING.md` — **{master_ref}**\n"
            + "\n## Loop\nAfter promote: `ops_issue_loop.py run --gh-assign --dispatch` "
            "→ Kanban `crypto-bot-project` for auto pickup.\n"
        )
        title = f"P6-OPS: {finding[:72]}"
        try:
            out = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    title,
                    "--label",
                    "bug,Trading Bot",
                    "--body",
                    body,
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            url = (out.stdout or "").strip()
            issue_num = url.rstrip("/").split("/")[-1] if url else None
            if issue_num and issue_num.isdigit():
                entry["github_issue"] = int(issue_num)
                entry["github_url"] = url
        except subprocess.CalledProcessError as e:
            entry["github_error"] = (e.stderr or e.stdout or str(e))[:500]

    rows.append(entry)
    _save_registry(rows)
    return entry


def cmd_promote(args: argparse.Namespace) -> int:
    entry = promote_finding(
        args.finding,
        priority=args.priority,
        evidence=args.evidence,
        master_ref=args.master_ref or "",
        no_github=bool(args.no_github),
        source="ops_triage",
    )
    print(json.dumps(entry, indent=2))
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    rows = _load_registry()
    found = False
    for r in rows:
        if r.get("id") == args.id:
            r["status"] = "done"
            r["closed"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if args.note:
                r["resolution_note"] = args.note
            found = True
            issue = r.get("github_issue")
            if issue and not args.no_github:
                subprocess.run(
                    ["gh", "issue", "close", str(issue), "--comment", args.note or "Resolved per ops workflow."],
                    cwd=str(ROOT),
                    check=False,
                )
    if not found:
        print(f"not found: {args.id}", flush=True)
        return 1
    _save_registry(rows)
    print(json.dumps({"closed": args.id}, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Ops triage task registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list")
    lp.add_argument("--open", action="store_true")
    lp.set_defaults(func=cmd_list)

    pp = sub.add_parser("promote")
    pp.add_argument("--finding", required=True)
    pp.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    pp.add_argument("--evidence", default="", help="comma-separated paths")
    pp.add_argument("--master-ref", default="")
    pp.add_argument("--no-github", action="store_true")
    pp.set_defaults(func=cmd_promote)

    cp = sub.add_parser("close")
    cp.add_argument("--id", required=True)
    cp.add_argument("--note", default="")
    cp.add_argument("--no-github", action="store_true")
    cp.set_defaults(func=cmd_close)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())