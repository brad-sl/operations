#!/usr/bin/env python3
"""Idempotent MASTER open-set → Hermes Kanban (crypto-bot-project).

Maps product states onto Hermes fixed columns + title tags.
See docs/KANBAN_MASTER_STATUS_FRAMEWORK.md

Does NOT assign workers for parked/watch/staged (no auto thrash).
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

BOARD = "crypto-bot-project"
ROOT = Path(__file__).resolve().parents[2]
WORKDIR = str(ROOT)

Mode = Literal["blocked"]


@dataclass(frozen=True)
class Card:
    master_id: str
    title: str  # includes tag prefix
    body: str
    mode: Mode
    priority: int
    block_kind: str = "needs_input"  # needs_input | transient | dependency | capability
    block_reason: str = ""


# Open / staged / watch set only (DONE items stay MASTER-only unless reopened)
# IMPORTANT: never use triage — auto-decomposer fans out and assigns workers.
CARDS: list[Card] = [
    Card(
        master_id="P6-SCALE-BACKLOG-HUB-20260818",
        title="[HUB] Phase6 scale + hygiene backlog (scan here)",
        body=(
            "Parent hub for scale/hygiene tracking on Kanban.\n"
            "Framework: docs/KANBAN_MASTER_STATUS_FRAMEWORK.md\n"
            "MASTER: docs/MASTER_TASK_TRACKING.md (SSOT)\n"
            "Children are tagged [STAGED]/[WATCH]/[PARKED]/[SHADOW]/[GATED].\n"
            "Do not assign this hub — tracking only.\n"
            "Staff next default: GAP-03 after GAP-05b watch running.\n"
        ),
        mode="blocked",
        priority=9,
        block_kind="needs_input",
        block_reason="HUB tracking only - do not assign",
    ),
    Card(
        master_id="P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816",
        title="[STAGED] GAP-03 Cap scope matrix ($ rebalance envelope)",
        body=(
            "MASTER: P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816\n"
            "Status: STAGED NEXT after GAP-05 closeout.\n"
            "Kind: offline + isolation. Enum keep_cash_only | extend_to_rotations | …\n"
            "Must-not: live cap flip without Brad go.\n"
            "When staffing: assign crypto-engineer, workspace dir:project root, unblock → ready.\n"
            "Reports under reports/.\n"
        ),
        mode="blocked",
        priority=8,
        block_kind="needs_input",
        block_reason="STAGED NEXT - staff GAP-03 offline when Brad picks",
    ),
    Card(
        master_id="P6-SCALE-GAP-05b-ENFORCE-WATCH-20260818",
        title="[WATCH] GAP-05b 14d post-SL 72h enforce gate",
        body=(
            "MASTER: P6-SCALE-GAP-05b-ENFORCE-WATCH-20260818\n"
            "Watch after enforce ship 2026-08-18.\n"
            "Pass: early_rebuy_lt_72h ≤0.10; zero auto-BUY in lockout; ISO green; SL% unchanged.\n"
            "Fail early_rebuy >0.20 → path re-audit.\n"
            "At day 14: re-run scripts/phase6/run_post_sl_reentry_eff.py + decide packet.\n"
            "Do not assign until closeout day.\n"
        ),
        mode="blocked",
        priority=8,
        block_kind="transient",
        block_reason="14d WATCH - measure only no worker",
    ),
    Card(
        master_id="P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816",
        title="[PARKED] GAP-04 Hard-exit evidence clock",
        body=(
            "MASTER: P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816\n"
            "QUEUED — evidence maturity; not BoN winner.\n"
            "Offline/ops clock only. No live hard-exit flip.\n"
        ),
        mode="blocked",
        priority=3,
        block_reason="PARKED backlog",
    ),
    Card(
        master_id="P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816",
        title="[PARKED] GAP-08 Promo firedrill (ISO/OPS)",
        body=(
            "MASTER: P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816\n"
            "P3 scale hygiene. Staff one-at-a-time later.\n"
        ),
        mode="blocked",
        priority=2,
        block_reason="PARKED backlog",
    ),
    Card(
        master_id="P6-SCALE-GAP-09-NRUNNER-ISOLATION-20260816",
        title="[PARKED] GAP-09 N-runner isolation",
        body=(
            "MASTER: P6-SCALE-GAP-09-NRUNNER-ISOLATION-20260816\n"
            "May align SCALING-1000-RUNTIME-SLICE. ISO only.\n"
        ),
        mode="blocked",
        priority=2,
        block_reason="PARKED backlog",
    ),
    Card(
        master_id="P6-SCALE-GAP-10-BASKET-CF-LONGTAPE-20260816",
        title="[SHADOW] GAP-10 Basket CF long-tape",
        body=(
            "MASTER: P6-SCALE-GAP-10-BASKET-CF-LONGTAPE-20260816\n"
            "Shadow/offline long-tape CF. Not live basket change.\n"
        ),
        mode="blocked",
        priority=2,
        block_kind="needs_input",
        block_reason="SHADOW offline research only",
    ),
    Card(
        master_id="P6-MID-CYCLE-ALLOCATOR-EVAL-20260807",
        title="[PARKED] Mid-cycle allocator eval (keep_off live)",
        body=(
            "MASTER: P6-MID-CYCLE-ALLOCATOR-EVAL-20260807\n"
            "Study OK; live enable needs Brad OK. mid_cycle_allocator_enabled=false.\n"
        ),
        mode="blocked",
        priority=2,
        block_reason="PARKED keep_off live",
    ),
    Card(
        master_id="SCALING-1000-RUNTIME-SLICE-20260807",
        title="[GATED] SCALING-1000 first runtime multi-tenant slice",
        body=(
            "MASTER: SCALING-1000-RUNTIME-SLICE-20260807\n"
            "Blocked on GHL-T0 admin / epic plans. Not full SCALING-1000 epic.\n"
            "Do not merge multi-tenant into Brad live book without gates.\n"
        ),
        mode="blocked",
        priority=3,
        block_kind="dependency",
        block_reason="Gated on SCALING-1000 GHL-T0",
    ),
    Card(
        master_id="P6-SSOT-DOC-HYGIENE-20260807",
        title="[PARKED] SSOT doc hygiene (banners/archive)",
        body=(
            "MASTER: P6-SSOT-DOC-HYGIENE-20260807\n"
            "Docs hygiene only. Partial banners already done.\n"
        ),
        mode="blocked",
        priority=1,
        block_reason="PARKED docs hygiene",
    ),
    Card(
        master_id="P6-EXIT-PROFIT-LIVE-GATES-20260807",
        title="[GATED] Profit-exit live path gates",
        body=(
            "MASTER: P6-EXIT-PROFIT-LIVE-GATES-20260807\n"
            "Needs regime exit map collection + Brad OK. Shadow first.\n"
        ),
        mode="blocked",
        priority=4,
        block_kind="needs_input",
        block_reason="GATED Brad OK + shadow evidence",
    ),
    Card(
        master_id="P6-HARD-EXIT-AUTO-APPLY-GATES-20260807",
        title="[GATED] Hard-exit auto-apply promotion criteria",
        body=(
            "MASTER: P6-HARD-EXIT-AUTO-APPLY-GATES-20260807\n"
            "Operator-loop evidence + Brad OK. No auto-apply yet.\n"
        ),
        mode="blocked",
        priority=4,
        block_kind="needs_input",
        block_reason="GATED Brad OK + evidence",
    ),
    Card(
        master_id="FEAT-PARK-USDC-PAXG-PACKAGE-20260807",
        title="[LIVE-OFF] USDC+PAXG park package (W0 shipped)",
        body=(
            "MASTER: FEAT-PARK-USDC-PAXG-PACKAGE-20260807\n"
            "W0 shipped; live enable OFF until Brad OK + checklist.\n"
            "USDC OFF till gates; PAXG ballast separate.\n"
        ),
        mode="blocked",
        priority=5,
        block_kind="needs_input",
        block_reason="LIVE OFF until Brad OK",
    ),
]


def _force_park(task_id: str, block_kind: str, reason: str) -> None:
    """Force scheduled park: scan-only; no dispatch. Avoid triage/auto-decompose."""
    import sqlite3
    import time

    db = Path.home() / ".hermes/kanban/boards/crypto-bot-project/kanban.db"
    con = sqlite3.connect(str(db))
    now = int(time.time())
    con.execute(
        """update tasks set status='scheduled', assignee=NULL, block_kind=NULL,
           claim_lock=NULL, claim_expires=NULL, worker_pid=NULL, started_at=NULL
           where id=?""",
        (task_id,),
    )
    con.execute(
        "insert into task_comments(task_id, author, body, created_at) values (?,?,?,?)",
        (task_id, "scotty-master-sync", f"SCHEDULED_PARK {reason} kind_hint={block_kind}", now),
    )
    con.commit()
    con.close()


def upsert(card: Card) -> str:
    key = f"master:{card.master_id}"
    create_args = [
        "create",
        card.title,
        "--body",
        card.body,
        "--priority",
        str(card.priority),
        "--idempotency-key",
        key,
        "--workspace",
        f"dir:{WORKDIR}",
        "--created-by",
        "scotty-master-sync",
        "--initial-status",
        "blocked",
        "--json",
    ]

    cmd = ["hermes", "kanban", "--board", BOARD, *create_args]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKDIR)
    if p.returncode != 0:
        raise RuntimeError(f"create failed {card.master_id}: {p.stderr}\n{p.stdout}")
    out = (p.stdout or "").strip()
    tid = None
    try:
        data = json.loads(out)
        tid = data.get("id") or data.get("task_id")
    except json.JSONDecodeError:
        for tok in out.replace(",", " ").split():
            if tok.startswith("t_"):
                tid = tok.strip()
                break
    if not tid:
        raise RuntimeError(f"no task id for {card.master_id}: {out[:500]}")

    _force_park(tid, card.block_kind, card.block_reason or "parked")
    return tid


def main() -> int:
    results = []
    for c in CARDS:
        tid = upsert(c)
        results.append({"master_id": c.master_id, "task_id": tid, "title": c.title, "mode": c.mode})
        print(f"{tid}\t{c.mode}\t{c.title}")
    out_path = ROOT / "data" / "state" / "kanban_master_sync_latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"board": BOARD, "cards": results}, indent=2) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
