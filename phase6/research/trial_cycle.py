#!/usr/bin/env python3
"""
Shared analyst trial lifecycle helpers (product-loop persistence).

Usage:
  python3 phase6/research/trial_cycle.py reindex
  python3 phase6/research/trial_cycle.py stale
  python3 phase6/research/trial_cycle.py status STOCH-RSI-PARALLEL-20260721
  python3 phase6/research/trial_cycle.py transition STOCH-RSI-PARALLEL-20260721 REPORT_READY
  python3 phase6/research/trial_cycle.py decide STOCH-RSI-PARALLEL-20260721 drop --note "no edge"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# CLI is often `python3 phase6/research/trial_cycle.py` without PYTHONPATH=.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
TRIALS_DIR = PROJECT_ROOT / "data" / "state" / "trials"
INDEX_PATH = TRIALS_DIR / "INDEX.json"
INBOX_DIR = PROJECT_ROOT / "docs" / "testing" / "inbox"
DECISIONS_DIR = PROJECT_ROOT / "docs" / "testing" / "decisions"
MASTER_PATH = PROJECT_ROOT / "docs" / "MASTER_TASK_TRACKING.md"
REGIMEN_DOC = "docs/testing/TEST_REGIMEN_E2E.md"

OUTCOME_CLASSES = {
    "HIT_CRITERIA",
    "EDGE_VS_BAGS_ONLY",
    "inconclusive_sparse_N",
    "unstable_or_no_edge",
    "process_incomplete",
}

FOLLOW_ON_ENUM = {"none", "extend", "scoped_shadow", "promotion_queue"}

ALLOWED = {
    "REGISTERED": {"INSTRUMENTED", "KILLED"},
    "INSTRUMENTED": {"RUNNING", "KILLED"},
    "RUNNING": {"DEGRADED", "REPORT_READY", "KILLED", "CLOSED"},
    "DEGRADED": {"RUNNING", "REPORT_READY", "KILLED"},
    "REPORT_READY": {"REVIEW_PENDING", "CLOSED", "KILLED"},
    "REVIEW_PENDING": {"CLOSED", "KILLED", "RUNNING"},  # RUNNING only for explicit reopen-as-extend mishap guard
    "CLOSED": set(),
    "KILLED": set(),
}

DECISION_ENUM = {
    "continue_observe_only",
    "extend_trial",
    "propose_scoped_experiment",
    "drop",
    "promote_blend",
    "promote_primary",
    "abort",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def trial_path(trial_id: str) -> Path:
    """Resolve trial JSON path: exact id filename, then underscore variant, then scan."""
    direct = TRIALS_DIR / f"{trial_id}.json"
    if direct.exists():
        return direct
    alt = TRIALS_DIR / f"{trial_id.replace('-', '_')}.json"
    if alt.exists():
        return alt
    # Scan for trial_id field (legacy short stems)
    if TRIALS_DIR.is_dir():
        for p in TRIALS_DIR.glob("*.json"):
            if p.name in ("INDEX.json", "PICKUP_QUEUE.json", "PICKUP_STATE.json") or p.name.startswith(
                "PICKUP_"
            ):
                continue
            try:
                t = json.loads(p.read_text())
            except Exception:
                continue
            if isinstance(t, dict) and t.get("trial_id") == trial_id:
                return p
    return direct


def load_trial(trial_id: str) -> Dict[str, Any]:
    p = trial_path(trial_id)
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text())


def save_trial(trial: Dict[str, Any]) -> Path:
    tid = trial["trial_id"]
    # Prefer existing path for this trial_id so we don't fork files
    p = trial_path(tid)
    if not p.exists():
        p = TRIALS_DIR / f"{tid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    trial["updated_at"] = _now()
    p.write_text(json.dumps(trial, indent=2) + "\n")
    reindex()
    return p


def reindex() -> Dict[str, Any]:
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for p in sorted(TRIALS_DIR.glob("*.json")):
        if p.name in ("INDEX.json", "PICKUP_QUEUE.json", "PICKUP_STATE.json") or p.name.startswith(
            "PICKUP_"
        ):
            continue
        try:
            t = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(t, dict) or "trial_id" not in t:
            continue
        rows.append(
            {
                "trial_id": t.get("trial_id") or p.stem,
                "status": t.get("status"),
                "family": t.get("family"),
                "start_at": t.get("start_at"),
                "final_at": t.get("final_at"),
                "master_id": t.get("master_id"),
                "path": str(p.relative_to(PROJECT_ROOT)),
            }
        )
    idx = {
        "schema_version": 1,
        "updated_at": _now(),
        "count": len(rows),
        "by_status": {},
        "trials": rows,
    }
    for r in rows:
        st = r.get("status") or "UNKNOWN"
        idx["by_status"][st] = idx["by_status"].get(st, 0) + 1
    INDEX_PATH.write_text(json.dumps(idx, indent=2) + "\n")
    return idx


def transition(
    trial_id: str,
    new_status: str,
    note: str = "",
    *,
    force: bool = False,
) -> Dict[str, Any]:
    t = load_trial(trial_id)
    cur = t.get("status") or "REGISTERED"
    new_status = new_status.upper()
    allowed = ALLOWED.get(cur, set())
    if new_status not in allowed and cur != new_status:
        raise ValueError(f"illegal transition {cur} → {new_status}; allowed={sorted(allowed)}")
    # Adoption-grade gate: bare transition to REPORT_READY requires finalize-report
    # (or force=True for legacy repair).
    if new_status == "REPORT_READY" and not force:
        issues = check_report_completeness(t)
        if issues:
            raise ValueError(
                "REPORT_READY blocked (regimen completeness). "
                f"Use finalize-report or fix: {issues}. See {REGIMEN_DOC}"
            )
    hist = t.setdefault("status_history", [])
    hist.append({"from": cur, "to": new_status, "at": _now(), "note": note})
    t["status"] = new_status
    if note:
        t.setdefault("notes", []).append({"at": _now(), "text": note})
    save_trial(t)
    return t


def _resolve_path(p: Optional[str]) -> Optional[Path]:
    if not p:
        return None
    path = Path(p)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def check_report_completeness(trial: Dict[str, Any]) -> List[str]:
    """Return list of missing regimen fields for REPORT_READY (empty = ok)."""
    issues: List[str] = []
    tid = trial.get("trial_id") or "?"
    sc = trial.get("success_criteria")
    if not isinstance(sc, dict) or not sc.get("primary_window"):
        issues.append("success_criteria.primary_window")
    if not isinstance(sc, dict) or sc.get("min_n_trades") is None:
        issues.append("success_criteria.min_n_trades")

    proto = trial.get("protocol")
    design = trial.get("design")
    proto_ok = False
    if proto:
        pp = _resolve_path(str(proto))
        proto_ok = bool(pp and pp.exists())
    if not proto_ok and not isinstance(design, dict):
        issues.append("protocol file or design{} block")

    fr = trial.get("final_report")
    fp = _resolve_path(str(fr) if fr else None)
    if not fp or not fp.exists():
        issues.append("final_report path missing on disk")

    rec = trial.get("final_recommendation")
    if not rec:
        # allow last reports[] entry
        reps = trial.get("reports") or []
        if isinstance(reps, list) and reps:
            last = reps[-1]
            if isinstance(last, dict):
                rec = last.get("recommendation")
            elif isinstance(last, str):
                rec = trial.get("final_recommendation")
        if not rec:
            issues.append("final_recommendation enum")
    if rec:
        r = str(rec).strip().lower()
        if r not in DECISION_ENUM and not r.startswith("propose_scoped_"):
            issues.append(f"final_recommendation not in enum: {rec}")

    outcome = trial.get("outcome")
    if not isinstance(outcome, dict):
        issues.append("outcome{} block")
    else:
        cls = outcome.get("class") or outcome.get("outcome_class")
        if cls not in OUTCOME_CLASSES:
            issues.append(f"outcome.class one of {sorted(OUTCOME_CLASSES)}")
        if "primary_pass" not in outcome:
            issues.append("outcome.primary_pass")
    return issues


def finalize_report(
    trial_id: str,
    *,
    report: str,
    report_json: str = "",
    enum: str,
    outcome_class: str,
    primary_pass: bool,
    note: str = "",
    n_primary: Optional[int] = None,
    delta_ret_pp: Optional[float] = None,
    delta_dd_pp: Optional[float] = None,
    plain_english: str = "",
    allow_incomplete_design: bool = False,
) -> Dict[str, Any]:
    """
    Record outcome + mark REPORT_READY under TEST_REGIMEN_E2E gates.
    """
    t = load_trial(trial_id)
    enum_l = enum.strip().lower()
    if enum_l not in DECISION_ENUM and not enum_l.startswith("propose_scoped_"):
        raise ValueError(f"enum must be decision enum, got {enum}")
    oc = outcome_class.strip()
    if oc not in OUTCOME_CLASSES:
        raise ValueError(f"outcome_class must be one of {sorted(OUTCOME_CLASSES)}")

    rp = _resolve_path(report)
    if not rp or not rp.exists():
        raise FileNotFoundError(f"report not found: {report}")
    jp = _resolve_path(report_json) if report_json else None
    if report_json and (not jp or not jp.exists()):
        raise FileNotFoundError(f"report json not found: {report_json}")

    # Ensure success_criteria skeleton exists (legacy repair path)
    sc = t.get("success_criteria")
    if not isinstance(sc, dict):
        if not allow_incomplete_design:
            raise ValueError(
                "success_criteria missing — set on trial before finalize, "
                f"or pass allow_incomplete_design for legacy debt only. {REGIMEN_DOC}"
            )
        t["success_criteria"] = {
            "primary_window": "unspecified_legacy",
            "min_n_trades": 15,
            "sparse_is": "inconclusive_not_promote",
            "live_promote_allowed": False,
            "legacy_debt": True,
        }
        oc = "process_incomplete"
        primary_pass = False

    if not t.get("protocol") and not isinstance(t.get("design"), dict):
        if not allow_incomplete_design:
            raise ValueError("protocol or design{} required")
        t["design"] = {
            "legacy_debt": True,
            "note": "finalized without protocol; process_incomplete",
        }

    rel_report = str(rp.relative_to(PROJECT_ROOT)) if rp.is_relative_to(PROJECT_ROOT) else str(rp)
    t["final_report"] = rel_report
    t["final_report_at"] = _now()
    t["final_recommendation"] = enum_l
    t["outcome"] = {
        "class": oc,
        "primary_pass": bool(primary_pass),
        "n_primary": n_primary,
        "delta_ret_pp": delta_ret_pp,
        "delta_dd_pp": delta_dd_pp,
        "plain_english": plain_english or note,
        "at": _now(),
    }
    reps = t.get("reports")
    if not isinstance(reps, list):
        reps = []
    entry: Dict[str, Any] = {
        "phase": "final",
        "path": rel_report,
        "recommendation": enum_l,
        "outcome_class": oc,
        "at": _now(),
    }
    if jp and jp.exists():
        entry["json"] = (
            str(jp.relative_to(PROJECT_ROOT)) if jp.is_relative_to(PROJECT_ROOT) else str(jp)
        )
    reps.append(entry)
    t["reports"] = reps
    t.setdefault("notes", []).append(
        {"at": _now(), "text": note or f"finalize-report enum={enum_l} class={oc}"}
    )
    save_trial(t)

    issues = check_report_completeness(t)
    if issues:
        raise ValueError(f"still incomplete after finalize fields: {issues}")

    cur = (t.get("status") or "REGISTERED").upper()
    if cur in ("CLOSED", "KILLED"):
        raise ValueError(f"cannot finalize terminal status {cur}")
    if cur == "REPORT_READY":
        return t
    # Allow jump from thin REGISTERED-like statuses used by offline digs
    if cur not in ALLOWED and cur not in (
        "REGISTERED",
        "INSTRUMENTED",
        "RUNNING",
        "DEGRADED",
        "REVIEW_PENDING",
    ):
        pass
    # Direct set with history if transition graph too strict for thin digs
    if cur in ALLOWED and "REPORT_READY" in ALLOWED.get(cur, set()):
        return transition(trial_id, "REPORT_READY", note="finalize-report", force=True)
    # Thin offline digs often only have REPORT_READY-bound fields without full graph
    t = load_trial(trial_id)
    prev = t.get("status")
    t["status"] = "REPORT_READY"
    t.setdefault("status_history", []).append(
        {
            "from": prev,
            "to": "REPORT_READY",
            "at": _now(),
            "note": "finalize-report (offline/legacy path)",
        }
    )
    save_trial(t)
    return t


def _cr_label(decision: str) -> str:
    d = decision.lower()
    if d in ("promote_primary", "promote_blend") or d.startswith("propose_scoped"):
        return "ACCEPT"
    if d in ("drop", "abort"):
        return "REJECT"
    return "NO_CR"


def write_decision_packet(
    trial: Dict[str, Any],
    *,
    decision: str,
    note: str,
    decided_by: str,
    follow_on: str,
    follow_on_detail: str = "",
) -> Path:
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    tid = trial["trial_id"]
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = DECISIONS_DIR / f"DEC_{tid}_{day}.md"
    outcome = trial.get("outcome") if isinstance(trial.get("outcome"), dict) else {}
    sc = trial.get("success_criteria") if isinstance(trial.get("success_criteria"), dict) else {}
    design = trial.get("design") if isinstance(trial.get("design"), dict) else {}
    cr = _cr_label(decision)
    cr_id = ""
    if cr == "ACCEPT":
        fam = (trial.get("family") or "test").replace("_", "-")
        cr_id = f"CR-{fam}-{day}"
    body = f"""# Decision packet — {tid}

| Field | Value |
|-------|--------|
| Trial | `{tid}` |
| Family | `{trial.get("family")}` |
| Decided at (UTC) | {trial.get("decision", {}).get("at") or _now()} |
| By | {decided_by} |
| Enum | `{decision}` |
| CR | **{cr}**{f" `{cr_id}`" if cr_id else ""} |
| Follow-on | `{follow_on}` |
| Regimen | `{REGIMEN_DOC}` |

## Design (summary)
- Hypothesis: {(design.get("hypothesis") if isinstance(design, dict) else None) or trial.get("title") or "—"}
- Primary window: `{sc.get("primary_window", "—") if isinstance(sc, dict) else "—"}`
- Success bar (frozen): min_n={sc.get("min_n_trades", "—") if isinstance(sc, dict) else "—"}; beat ret+dd={sc.get("require_both_ret_and_dd", True) if isinstance(sc, dict) else True}

## Outcome (measured)
- Primary pass: **{outcome.get("primary_pass", "—") if isinstance(outcome, dict) else "—"}**
- Class: `{outcome.get("class", "—") if isinstance(outcome, dict) else "—"}`
- N (primary): {outcome.get("n_primary", "—") if isinstance(outcome, dict) else "—"}
- Δret vs baseline (pp): {outcome.get("delta_ret_pp", "—") if isinstance(outcome, dict) else "—"}
- ΔDD vs baseline (pp): {outcome.get("delta_dd_pp", "—") if isinstance(outcome, dict) else "—"}
- Report: `{trial.get("final_report") or "—"}`
- Plain English: {(outcome.get("plain_english") if isinstance(outcome, dict) else None) or "—"}

## Decision rationale
{note or "—"}

## Follow-on
- Mode: `{follow_on}`
- Detail: {follow_on_detail or "—"}

## Notify
- Inbox: `docs/testing/inbox/DECIDED_{tid}_{day}.md`
- Packet: `{path.relative_to(PROJECT_ROOT)}`

## Live boundary
- Config writes this decision: **none**
"""
    path.write_text(body)
    trial["decision_packet"] = str(path.relative_to(PROJECT_ROOT))
    return path


def record_decision(
    trial_id: str,
    decision: str,
    note: str = "",
    decided_by: str = "brad",
    follow_on: str = "none",
    follow_on_detail: str = "",
) -> Dict[str, Any]:
    decision = decision.strip().lower()
    # allow propose_scoped_* prefix
    ok = decision in DECISION_ENUM or decision.startswith("propose_scoped_")
    if not ok:
        raise ValueError(f"decision must be one of {sorted(DECISION_ENUM)} or propose_scoped_*")
    fo = (follow_on or "none").strip().lower()
    if fo not in FOLLOW_ON_ENUM:
        raise ValueError(f"follow_on must be one of {sorted(FOLLOW_ON_ENUM)}")
    t = load_trial(trial_id)
    prev = t.get("status") or "UNKNOWN"
    t["decision"] = {
        "value": decision,
        "at": _now(),
        "by": decided_by,
        "note": note,
        "follow_on": fo,
        "follow_on_detail": follow_on_detail,
        "cr": _cr_label(decision),
    }
    t["follow_on"] = {"mode": fo, "detail": follow_on_detail, "at": _now()}
    t.setdefault("status_history", []).append(
        {"from": prev, "to": "CLOSED", "at": _now(), "note": f"decision={decision}"}
    )
    t["status"] = "CLOSED"
    t["closed_at"] = _now()
    packet = write_decision_packet(
        t,
        decision=decision,
        note=note,
        decided_by=decided_by,
        follow_on=fo,
        follow_on_detail=follow_on_detail,
    )
    save_trial(t)
    # inbox receipt
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    receipt = INBOX_DIR / f"DECIDED_{trial_id}_{day}.md"
    receipt.write_text(
        f"# Decision — {trial_id}\n\n"
        f"- **decision:** `{decision}`\n"
        f"- **CR:** **{_cr_label(decision)}**\n"
        f"- **by:** {decided_by}\n"
        f"- **at:** {t['decision']['at']}\n"
        f"- **note:** {note}\n"
        f"- **follow_on:** `{fo}` {follow_on_detail}\n"
        f"- **packet:** `{packet.relative_to(PROJECT_ROOT)}`\n"
        f"- **unblocks:** {t.get('unblocks')}\n"
        f"- **regimen:** `{REGIMEN_DOC}`\n"
    )
    # Patch MASTER so auto-pickup blocked_on can resolve
    master_id = t.get("master_id")
    if master_id:
        try:
            from phase6.research.master_test_pickup import patch_master_status, scan

            patch_master_status(
                master_id,
                "DONE",
                note=f"trial `{trial_id}` decision=`{decision}`",
            )
            scan()  # refresh PICKUP_QUEUE so next cron can launch dependents
            # Mark strategy roadmap item done if linked
            try:
                from phase6.research.analyst_test_strategy import sync_active
                sync_active()
            except Exception:
                pass
        except Exception as e:
            receipt.write_text(receipt.read_text() + f"\n- **master_patch_error:** {e}\n")
    # Always refresh strategy slots (review_pending) even without master_id
    try:
        from phase6.research.analyst_test_strategy import sync_active

        sync_active()
    except Exception:
        pass
    return t


def apply_health_result(
    trial_id: str,
    ok: bool,
    issues: List[str],
    facts: Dict[str, Any],
    kill_after_consecutive: int = 3,
) -> Dict[str, Any]:
    """Update consecutive fail counters; DEGRADED/KILLED transitions."""
    t = load_trial(trial_id)
    st = t.get("status")
    if st in ("CLOSED", "KILLED"):
        return t
    consec = int(t.get("consecutive_health_fails") or 0)
    if ok:
        t["consecutive_health_fails"] = 0
        if st == "DEGRADED":
            t["status"] = "RUNNING"
            t.setdefault("status_history", []).append(
                {"from": "DEGRADED", "to": "RUNNING", "at": _now(), "note": "health recovered"}
            )
    else:
        consec += 1
        t["consecutive_health_fails"] = consec
        if st == "RUNNING":
            t["status"] = "DEGRADED"
            t.setdefault("status_history", []).append(
                {
                    "from": "RUNNING",
                    "to": "DEGRADED",
                    "at": _now(),
                    "note": "; ".join(issues)[:300],
                }
            )
        if consec >= kill_after_consecutive and t.get("status") != "KILLED":
            t["status"] = "KILLED"
            t["killed_at"] = _now()
            t["kill_reason"] = {
                "type": "consecutive_health_fails",
                "n": consec,
                "issues": issues,
            }
            t.setdefault("status_history", []).append(
                {
                    "from": "DEGRADED",
                    "to": "KILLED",
                    "at": _now(),
                    "note": f"consecutive_health_fails={consec}",
                }
            )
    t["last_health"] = {"at": _now(), "ok": ok, "facts": facts, "issues": issues}
    log = t.setdefault("health_log", [])
    log.append(t["last_health"])
    t["health_log"] = log[-90:]
    save_trial(t)
    return t


def scan_stale(grace_hours: float = 48.0) -> List[Dict[str, Any]]:
    """Trials past final_at still open."""
    reindex()
    now = datetime.now(timezone.utc)
    stale = []
    for p in TRIALS_DIR.glob("*.json"):
        if p.name == "INDEX.json":
            continue
        t = json.loads(p.read_text())
        st = t.get("status")
        if st in ("CLOSED", "KILLED", "REVIEW_PENDING", "REPORT_READY"):
            # REPORT_READY past grace without decision also stale review
            if st in ("REPORT_READY", "REVIEW_PENDING"):
                fr = _parse_ts(t.get("final_report_at") or t.get("final_at"))
                if fr and (now - fr).total_seconds() > grace_hours * 3600:
                    stale.append({"trial_id": t.get("trial_id"), "reason": "review_overdue", "status": st})
            continue
        final_at = _parse_ts(t.get("final_at"))
        if final_at and now > final_at and (now - final_at).total_seconds() > grace_hours * 3600:
            stale.append(
                {
                    "trial_id": t.get("trial_id"),
                    "reason": "past_final_still_open",
                    "status": st,
                    "final_at": t.get("final_at"),
                }
            )
            # mark flag on trial
            t["stale_open"] = True
            save_trial(t)
    return stale


def write_review_request(trial_id: str) -> Path:
    t = load_trial(trial_id)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = INBOX_DIR / f"REVIEW_{trial_id}.md"
    final = t.get("final_report") or "(missing)"
    rec = t.get("final_recommendation") or (
        (t.get("reports") or [{}])[-1].get("recommendation") if t.get("reports") else None
    )
    outcome = t.get("outcome") if isinstance(t.get("outcome"), dict) else {}
    sc = t.get("success_criteria") if isinstance(t.get("success_criteria"), dict) else {}
    issues = check_report_completeness(t)
    path.write_text(
        f"# Review request — {trial_id}\n\n"
        f"**Status:** {t.get('status')}\n\n"
        f"**Regimen:** `{REGIMEN_DOC}`\n\n"
        f"**Final report:** `{final}`\n\n"
        f"**Proposed recommendation:** `{rec}`\n\n"
        f"**Outcome class:** `{outcome.get('class', '—')}` · primary_pass={outcome.get('primary_pass', '—')}\n\n"
        f"**Success primary_window:** `{sc.get('primary_window', '—')}` · min_n={sc.get('min_n_trades', '—')}\n\n"
        f"**Completeness issues:** {issues or 'none'}\n\n"
        f"**Unblocks if closed:** {t.get('unblocks')}\n\n"
        f"## Decide (CR accept/reject)\n\n"
        f"```bash\n"
        f"cd /home/brad/projects/crypto-trading-bot\n"
        f"python3 phase6/research/trial_cycle.py decide {trial_id} <enum> \\\n"
        f"  --note 'why' --follow-on none|extend|scoped_shadow|promotion_queue\n"
        f"```\n\n"
        f"Enums: `continue_observe_only` | `extend_trial` | `propose_scoped_experiment` | "
        f"`drop` | `promote_blend` | `promote_primary` | `abort`\n\n"
        f"CR: promote_*/propose_scoped_* = ACCEPT · drop/abort = REJECT · observe/extend = NO_CR\n"
    )
    if t.get("status") == "REPORT_READY":
        try:
            transition(trial_id, "REVIEW_PENDING", note="review request written", force=True)
        except ValueError:
            pass
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Analyst trial cycle CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reindex")
    sub.add_parser("stale")
    p_st = sub.add_parser("status")
    p_st.add_argument("trial_id")
    p_tr = sub.add_parser("transition")
    p_tr.add_argument("trial_id")
    p_tr.add_argument("new_status")
    p_tr.add_argument("--note", default="")
    p_tr.add_argument(
        "--force",
        action="store_true",
        help="Bypass REPORT_READY completeness gate (legacy repair only)",
    )
    p_de = sub.add_parser("decide")
    p_de.add_argument("trial_id")
    p_de.add_argument("decision")
    p_de.add_argument("--note", default="")
    p_de.add_argument(
        "--follow-on",
        default="none",
        choices=sorted(FOLLOW_ON_ENUM),
        help="Required follow-on mode after decide",
    )
    p_de.add_argument("--follow-on-detail", default="", dest="follow_on_detail")
    p_rv = sub.add_parser("review-request")
    p_rv.add_argument("trial_id")
    p_fin = sub.add_parser(
        "finalize-report",
        help="Gate + attach outcome and set REPORT_READY (TEST_REGIMEN_E2E)",
    )
    p_fin.add_argument("trial_id")
    p_fin.add_argument("--report", required=True)
    p_fin.add_argument("--json", default="", dest="report_json")
    p_fin.add_argument("--enum", required=True)
    p_fin.add_argument("--outcome-class", required=True, dest="outcome_class")
    p_fin.add_argument(
        "--primary-pass",
        required=True,
        choices=["true", "false"],
        dest="primary_pass",
    )
    p_fin.add_argument("--note", default="")
    p_fin.add_argument("--n-primary", type=int, default=None, dest="n_primary")
    p_fin.add_argument("--delta-ret-pp", type=float, default=None, dest="delta_ret_pp")
    p_fin.add_argument("--delta-dd-pp", type=float, default=None, dest="delta_dd_pp")
    p_fin.add_argument("--plain-english", default="", dest="plain_english")
    p_fin.add_argument(
        "--allow-incomplete-design",
        action="store_true",
        help="Legacy debt only — marks process_incomplete",
    )
    p_chk = sub.add_parser("check-complete")
    p_chk.add_argument("trial_id")

    args = ap.parse_args(argv)
    if args.cmd == "reindex":
        idx = reindex()
        print(json.dumps(idx, indent=2))
        return 0
    if args.cmd == "stale":
        s = scan_stale()
        print(json.dumps(s, indent=2))
        if s:
            print(f"STALE_COUNT={len(s)}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "status":
        print(json.dumps(load_trial(args.trial_id), indent=2))
        return 0
    if args.cmd == "transition":
        t = transition(
            args.trial_id, args.new_status, note=args.note, force=bool(args.force)
        )
        print(t["status"])
        return 0
    if args.cmd == "decide":
        t = record_decision(
            args.trial_id,
            args.decision,
            note=args.note,
            follow_on=args.follow_on,
            follow_on_detail=args.follow_on_detail,
        )
        print(json.dumps(t.get("decision"), indent=2))
        return 0
    if args.cmd == "review-request":
        path = write_review_request(args.trial_id)
        print(path)
        return 0
    if args.cmd == "finalize-report":
        t = finalize_report(
            args.trial_id,
            report=args.report,
            report_json=args.report_json,
            enum=args.enum,
            outcome_class=args.outcome_class,
            primary_pass=args.primary_pass == "true",
            note=args.note,
            n_primary=args.n_primary,
            delta_ret_pp=args.delta_ret_pp,
            delta_dd_pp=args.delta_dd_pp,
            plain_english=args.plain_english,
            allow_incomplete_design=bool(args.allow_incomplete_design),
        )
        print(json.dumps({"status": t.get("status"), "outcome": t.get("outcome")}, indent=2))
        return 0
    if args.cmd == "check-complete":
        t = load_trial(args.trial_id)
        issues = check_report_completeness(t)
        print(json.dumps({"trial_id": args.trial_id, "ok": not issues, "issues": issues}, indent=2))
        return 0 if not issues else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
