#!/usr/bin/env python3
"""
Deterministic Phase 6 ops triage discovery (Phase1 cost — no LLM).

Writes data/state/ops_triage.md. Prints summary to stdout only when
high/medium open findings exist (Telegram-friendly). Exit 0 always unless
hard failure.

Usage:
  python3 scripts/phase6/ops_triage_discover.py
  python3 scripts/phase6/ops_triage_discover.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/state/ops_triage.md"
RUNNER_LOG = ROOT / "logs/phase6_runner.log"
MONITOR_LOG = ROOT / "logs/monitor.log"
STATE = ROOT / "data/state/phase6_runner_state.json"


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


def _tail(path: Path, n: int = 80) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(errors="ignore").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    findings: list[dict] = []

    # Runner alive
    ps = _run(["pgrep", "-af", "phase6.core.phase6_runner"])
    runner_up = bool(ps.strip()) and "phase6" in ps
    if not runner_up:
        findings.append(
            {
                "priority": "high",
                "status": "open",
                "finding": "Phase6 runner process not found (pgrep empty)",
                "evidence": "pgrep -af phase6.core.phase6_runner",
            }
        )

    log = _tail(RUNNER_LOG, 100)
    if "AttributeError" in log and "_clear_deferred" in log:
        findings.append(
            {
                "priority": "high",
                "status": "open",
                "finding": "Recent AttributeError _clear_deferred_rebalance_slot in runner log",
                "evidence": str(RUNNER_LOG),
            }
        )
    if re.search(r"Traceback \(most recent call last\)", log):
        # only if last 40 lines
        if "Traceback" in "\n".join(log.splitlines()[-40:]):
            findings.append(
                {
                    "priority": "medium",
                    "status": "open",
                    "finding": "Traceback in last ~40 lines of phase6_runner.log",
                    "evidence": str(RUNNER_LOG),
                }
            )

    # SL gaps audit (best-effort)
    audit = _run(
        [sys.executable, "scripts/phase6/audit_rebalance_sl_gaps.py"],
        timeout=120,
    )
    if "missing" in audit.lower() and "protective" in audit.lower():
        # take first actionable line
        line = next(
            (ln.strip() for ln in audit.splitlines() if "missing" in ln.lower()),
            audit[:200],
        )
        findings.append(
            {
                "priority": "medium",
                "status": "open",
                "finding": f"SL audit signal: {line[:180]}",
                "evidence": "scripts/phase6/audit_rebalance_sl_gaps.py",
            }
        )

    # Same-session BUY→SL (ledger metric; quiet when 0)
    try:
        sys.path.insert(0, str(ROOT))
        from phase6.core.same_session_sl import ops_finding_if_any, summarize as ss_sum

        ss = ss_sum(persist=True)
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

    # Hermes cron errors (last *run* status only).
    # last_status ok + Telegram delivery timeout ≠ fail (sticky "delivery error" text).
    cron_out = _run(["hermes", "cron", "list"], timeout=45)
    for block in re.split(r"\n\s*\n", cron_out):
        if "Name:" not in block:
            continue
        if "paused" in block.lower() or "enabled=False" in block:
            continue
        # hermes CLI: "Last run:  <ts>  ok" or "Last run:  <ts>  error: ..."
        status_m = re.search(
            r"Last run:\s+\S+\s+(ok|error)\b", block, flags=re.IGNORECASE
        )
        if not status_m or status_m.group(1).lower() != "error":
            continue
        name_m = re.search(r"Name:\s+(\S.+)", block)
        name = name_m.group(1).strip() if name_m else "unknown"
        findings.append(
            {
                "priority": "medium",
                "status": "open",
                "finding": f"Hermes cron recent error: {name}",
                "evidence": "hermes cron list",
            }
        )

    # Cap 3
    pri_rank = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(findings, key=lambda f: pri_rank.get(f["priority"], 9))[:3]

    lines = [
        f"# Ops triage — {day}",
        "",
        f"_Generated by `ops_triage_discover.py` (no LLM) at {now}_",
        "",
        "| Finding | Evidence | Priority | Status |",
        "|---------|----------|----------|--------|",
    ]
    if not findings:
        lines.append("| (none) | runner/logs/cron clean enough | low | ok |")
    else:
        for f in findings:
            lines.append(
                f"| {f['finding'][:120]} | `{f['evidence']}` | {f['priority']} | {f['status']} |"
            )
    lines += [
        "",
        "## Notes",
        f"- Runner up: **{runner_up}**",
        "- Promote medium/high: `python3 scripts/phase6/ops_triage_tasks.py promote ...`",
        "- Then: `python3 scripts/phase6/ops_issue_loop.py run --gh-assign --dispatch`",
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
        "path": str(OUT),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    elif actionable:
        # Telegram / cron delivery body
        print(f"OPS_TRIAGE {day}: {len(actionable)} actionable")
        for f in actionable:
            print(f"- [{f['priority']}] {f['finding']}")
        print(f"See {OUT}")
    else:
        # Silent-ish for deliver-local; still print OK for logs
        print("OPS_TRIAGE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
