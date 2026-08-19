#!/usr/bin/env python3
"""
Analyst Test Strategy — portfolio driver for MASTER Type:test emission.

CLI:
  status | seed | sync-active | emit [--dry-run] | mark-done PLAN_ID
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

STRATEGY_PATH = PROJECT_ROOT / "data" / "state" / "trials" / "TEST_STRATEGY.json"
MASTER_PATH = PROJECT_ROOT / "docs" / "MASTER_TASK_TRACKING.md"
TRIALS_DIR = PROJECT_ROOT / "data" / "state" / "trials"
HANDOFFS = PROJECT_ROOT / "handoffs" / "analyst"

DEFAULT_CAPACITY = {
    "max_parallel_instrumentation": 1,
    "max_offline_analysis": 1,
    "max_emit_per_run": 1,
    "max_review_pending": 2,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> Dict[str, Any]:
    if STRATEGY_PATH.exists():
        return json.loads(STRATEGY_PATH.read_text())
    return {}


def _save(s: Dict[str, Any]) -> None:
    STRATEGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    s["updated_at"] = _now()
    STRATEGY_PATH.write_text(json.dumps(s, indent=2) + "\n")


def seed(force: bool = False) -> Dict[str, Any]:
    if STRATEGY_PATH.exists() and not force:
        s = _load()
        if s.get("roadmap"):
            return s
    s = {
        "schema_version": 1,
        "north_star": (
            "Maximize risk-adjusted return and minimize losses via regime-aware knobs, "
            "sizing, signals, and methodology tests — evidence before live change."
        ),
        "created_at": _now(),
        "capacity": dict(DEFAULT_CAPACITY),
        "workstreams": [
            {
                "id": "WS-REGIME-KNOBS",
                "priority": 1,
                "status": "active",
                "note": "Per-regime optimal gates/caps vs live policy + USDC hurdle",
            },
            {
                "id": "WS-SIZING",
                "priority": 2,
                "status": "active",
                "note": "Kelly / deploy_pct / risk budget",
            },
            {
                "id": "WS-SIGNAL",
                "priority": 3,
                "status": "active",
                "note": "Stoch/RSI/sentiment instrumentation and thresholds",
            },
            {
                "id": "WS-METHODOLOGY",
                "priority": 4,
                "status": "active",
                "note": "ANALYST-OPT packs: rotation, cadence, park rules",
            },
            {
                "id": "WS-PROMOTION",
                "priority": 5,
                "status": "gated",
                "note": "Shadow→audit→operator only",
            },
        ],
        "roadmap": [
            {
                "plan_id": "PLAN-SIGNAL-STOCH-001",
                "title": "StochRSI parallel instrumentation vs plain RSI",
                "workstream": "WS-SIGNAL",
                "priority": 5,
                "status": "running",
                "trial_kind": "parallel_instrumentation",
                "family": "stoch_rsi",
                "duration_days": 14,
                "blocked_on": [],
                "master_id": "ANALYST-STOCH-RSI-COMPARE",
                "trial_id": "STOCH-RSI-PARALLEL-20260721",
                "hypothesis": "Stoch adds SL/risk timing edge beyond RSI alone",
                "success_metric": "Decision enum from real fills + disagreement analysis",
                "regime_focus": ["all"],
                "auto_pickup": False,
            },
            {
                "plan_id": "PLAN-SIZING-KELLY-001",
                "title": "Fractional Kelly risk budget vs fixed deploy_pct",
                "workstream": "WS-SIZING",
                "priority": 10,
                "status": "running",
                "trial_kind": "offline_analysis",
                "family": "kelly_sizing",
                "duration_days": 3,
                "blocked_on": [],
                "master_id": "ANALYST-KELLY-SIZING-TEST-20260721",
                "trial_id": "ANALYST-KELLY-SIZING-TEST-20260721-TRIAL",
                "hypothesis": "Half/quarter Kelly risk-at-SL improves growth/DD vs fixed knobs",
                "success_metric": "Real ledger p,b,n + counterfactual paths; go/no-go shadow",
                "regime_focus": ["all"],
                "auto_pickup": True,
            },
            {
                "plan_id": "PLAN-FLAT-KNOBS-001",
                "title": "Flat regime: cap/RSI/sentiment grid vs live option B",
                "workstream": "WS-REGIME-KNOBS",
                "priority": 20,
                "status": "planned",
                "trial_kind": "offline_analysis",
                "family": "regime_flat_knobs",
                "duration_days": 3,
                "blocked_on": [],
                "depends_on_plans": [],
                "master_id": None,
                "hypothesis": (
                    "Live flat B (cap $75, RSI≤55, sent≥0.25) is not optimal on real "
                    "flat-labeled windows; a nearby grid improves return or DD."
                ),
                "success_metric": (
                    "Best grid cell beats live-B fingerprint on real OHLCV/overlap; "
                    "min n; no live write — shadow candidate only if wins"
                ),
                "regime_focus": ["flat"],
                "auto_pickup": True,
                "opt_hook": "regime_cash_param_sweep_or_scorecard",
            },
            {
                "plan_id": "PLAN-BULL-KNOBS-001",
                "title": "Bull regime: util/cap/RSI vs leaving edge on table",
                "workstream": "WS-REGIME-KNOBS",
                "priority": 30,
                "status": "planned",
                "trial_kind": "offline_analysis",
                "family": "regime_bull_knobs",
                "duration_days": 3,
                "blocked_on": [],
                "master_id": None,
                "hypothesis": "Bull live knobs under-deploy or over-trade vs scorecard winner",
                "success_metric": "Beat live bull + USDC hurdle on bull windows; DD bound",
                "regime_focus": ["bull"],
                "auto_pickup": True,
            },
            {
                "plan_id": "PLAN-BEAR-PARK-001",
                "title": "Bear: full park vs small tactical deploy",
                "workstream": "WS-REGIME-KNOBS",
                "priority": 40,
                "status": "planned",
                "trial_kind": "offline_analysis",
                "family": "regime_bear_park",
                "duration_days": 3,
                "blocked_on": [],
                "master_id": None,
                "hypothesis": "Strict park minimizes loss vs any tactical bear deploy on real bears",
                "success_metric": "Lower max DD / higher terminal vs tactical; USDC compare",
                "regime_focus": ["bear"],
                "auto_pickup": True,
            },
            {
                "plan_id": "PLAN-METHOD-ROTATION-001",
                "title": "Methodology: defensive_rotation_21d vs current live path (ARCH-4)",
                "workstream": "WS-METHODOLOGY",
                "priority": 50,
                "status": "planned",
                "trial_kind": "offline_analysis",
                "family": "method_rotation_21d",
                "duration_days": 2,
                "blocked_on": [],
                "master_id": None,
                "hypothesis": "Scorecard rotation winner still beats production path on fresh window",
                "success_metric": "Leaderboard delta + --compare-production; honest brief",
                "regime_focus": ["bull", "flat"],
                "auto_pickup": True,
                "opt_hook": "analyst_opt_scenario_pack",
            },
            {
                "plan_id": "PLAN-TRANSITION-001",
                "title": "Transition regime: park vs limited cap sensitivity",
                "workstream": "WS-REGIME-KNOBS",
                "priority": 60,
                "status": "planned",
                "trial_kind": "offline_analysis",
                "family": "regime_transition",
                "duration_days": 2,
                "blocked_on": [],
                "master_id": None,
                "hypothesis": "Transition cap/park settings drive unnecessary whipsaw or idle cash",
                "success_metric": "Real transition slices; prefer lower whipsaw cost",
                "regime_focus": ["transition"],
                "auto_pickup": True,
            },
        ],
        "completed": [],
        "emission_log": [],
        "notes": [
            "Seeded 2026-07-21 with Stoch+Kelly as running; regime/methodology planned.",
            "Emit only when capacity free; pickup launches Type:test.",
        ],
    }
    _save(s)
    return s


def _master_task_ids() -> Dict[str, str]:
    """task_id -> status token from MASTER headers/status lines."""
    if not MASTER_PATH.exists():
        return {}
    text = MASTER_PATH.read_text()
    out: Dict[str, str] = {}
    parts = re.split(r"(?m)^(## .+)$", text)
    i = 1
    while i < len(parts) - 1:
        header, body = parts[i].strip(), parts[i + 1]
        i += 2
        m = re.match(r"##\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", header)
        if not m:
            continue
        tid = m.group(1)
        sm = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        st = "UNKNOWN"
        if sm:
            raw = sm.group(1)
            raw = re.sub(r"\*\*", "", raw)
            st = re.split(r"[—-]", raw)[0].strip().split()[0].upper()
        elif "RUNNING" in header.upper():
            st = "RUNNING"
        elif "DONE" in header.upper():
            st = "DONE"
        out[tid] = st
    return out


def _count_slots() -> Dict[str, int]:
    offline = 0
    instru = 0
    review = 0
    for p in TRIALS_DIR.glob("*.json"):
        if p.name.startswith("PICKUP") or p.name == "INDEX.json" or p.name == "TEST_STRATEGY.json":
            continue
        try:
            t = json.loads(p.read_text())
        except Exception:
            continue
        if "trial_id" not in t:
            continue
        st = (t.get("status") or "").upper()
        kind = (t.get("trial_kind") or "").lower()
        if st in ("REPORT_READY", "REVIEW_PENDING"):
            review += 1
        if st not in ("RUNNING", "DEGRADED", "LAUNCHED", "INSTRUMENTED", "REGISTERED"):
            continue
        if kind == "parallel_instrumentation":
            instru += 1
        else:
            offline += 1
    return {"offline_running": offline, "instru_running": instru, "review_pending": review}


def sync_active(s: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = s or seed()
    master = _master_task_ids()
    for item in s.get("roadmap") or []:
        mid = item.get("master_id")
        if not mid:
            if item.get("status") == "emitted":
                item["status"] = "planned"
            continue
        mst = master.get(mid)
        if not mst:
            continue
        if mst in ("DONE", "CLOSED", "COMPLETE", "COMPLETED", "KILLED"):
            if item.get("status") != "done":
                item["status"] = "done"
                s.setdefault("completed", []).append(
                    {
                        "plan_id": item.get("plan_id"),
                        "master_id": mid,
                        "at": _now(),
                        "source": "sync_master",
                    }
                )
        elif mst in ("RUNNING", "LAUNCHED", "READY", "PICKED_UP", "IN_PROGRESS"):
            item["status"] = "running"
        elif mst in ("QUEUED", "READY") and item.get("status") == "planned":
            item["status"] = "emitted"
    # trial files
    for item in s.get("roadmap") or []:
        tid = item.get("trial_id")
        if not tid:
            continue
        tp = TRIALS_DIR / f"{tid}.json"
        if not tp.exists():
            continue
        try:
            tr = json.loads(tp.read_text())
        except Exception:
            continue
        st = (tr.get("status") or "").upper()
        if st == "CLOSED":
            item["status"] = "done"
        elif st in ("RUNNING", "DEGRADED", "REPORT_READY", "REVIEW_PENDING"):
            if item.get("status") not in ("done",):
                item["status"] = "running"
    s["active_master_ids"] = [
        i["master_id"]
        for i in s.get("roadmap") or []
        if i.get("master_id") and i.get("status") in ("emitted", "running")
    ]
    s["slots"] = _count_slots()
    _save(s)
    return s



def _live_regime_label() -> str:
    """Best-effort live regime token for emit gates (bull/bear/flat/transition)."""
    try:
        st_path = PROJECT_ROOT / "data" / "state" / "regime_cash_status.json"
        if st_path.exists():
            st = json.loads(st_path.read_text())
            for k in ("regime", "status", "regime_label", "label"):
                v = st.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().lower().split()[0]
            det = st.get("detection") or st.get("detector") or {}
            if isinstance(det, dict):
                v = det.get("regime") or det.get("label")
                if isinstance(v, str) and v.strip():
                    return v.strip().lower().split()[0]
    except Exception:
        pass
    try:
        from phase6.research.regime_detector import detect_regime
        d = detect_regime(use_live_price=True)
        v = (d or {}).get("regime")
        if isinstance(v, str) and v.strip():
            return v.strip().lower().split()[0]
    except Exception:
        pass
    return ""

def _master_id_for_plan(plan: Dict[str, Any]) -> str:
    if plan.get("master_id"):
        return plan["master_id"]
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    fam = re.sub(r"[^A-Z0-9]+", "-", (plan.get("family") or "TEST").upper()).strip("-")
    return f"ANALYST-{fam}-{day}"


def _write_handoff(plan: Dict[str, Any], master_id: str) -> str:
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    path = HANDOFFS / f"Handoff_{master_id}.md"
    if path.exists():
        return str(path.relative_to(PROJECT_ROOT))
    path.write_text(
        f"""# Handoff — {master_id}

**Plan ID:** `{plan.get('plan_id')}`  
**Workstream:** `{plan.get('workstream')}`  
**Status:** QUEUED (strategy-emitted)  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `{master_id}`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Protocol:** `{plan.get('protocol_template') or 'docs/testing/trials/<ID>_PROTOCOL.md'}`

## Hypothesis
{plan.get('hypothesis') or (plan.get('design') or {}).get('hypothesis')}

## Success metric
{plan.get('success_metric')}

## Success criteria (frozen)
```json
{json.dumps(plan.get('success_criteria') or {}, indent=2)}
```

## Regime focus
{', '.join(plan.get('regime_focus') or [])}

## Kind
`{plan.get('trial_kind')}` · family `{plan.get('family')}`

## Must
- Real data only; isolation where code changes
- Freeze success_criteria **before** scoring
- Report under `reports/` + JSON with `outcome.class` + N
- `finalize-report` → REVIEW → Brad `decide` + `--follow-on` + decision packet
- No live config write without Brad + promotion gates

## Must not
- Fake prices / synthetic edge when ledger empty
- Silent promote to `regime_cash_policy.json`
- Promote on sparse N or EDGE_VS_BAGS_ONLY alone
- Close as drop without evidence if this is a real planned test (not zombie)

## Hooks
- OPT: `{plan.get('opt_hook') or 'n/a'}`
- Live policy fingerprint: read `config/regime_cash_policy.json` at start; record hash in report

## Done when
- Honest recommendation enum + n / uncertainty
- CR ACCEPT/REJECT logged; follow_on explicit
- Strategy roadmap item marked done after decide
"""
    )
    return str(path.relative_to(PROJECT_ROOT))


def _render_master_section(plan: Dict[str, Any], master_id: str, handoff: str) -> str:
    kind = plan.get("trial_kind") or "offline_analysis"
    fam = plan.get("family") or "test"
    dur = int(plan.get("duration_days") or 3)
    title = plan.get("title") or master_id
    blocked = plan.get("blocked_on") or []
    blocked_s = "none" if not blocked else ", ".join(f"`{b}`" for b in blocked)
    regimes = ", ".join(plan.get("regime_focus") or [])
    sc_json = json.dumps(plan.get("success_criteria") or {}, indent=2)
    return f"""## {master_id} — QUEUED (strategy)

**Type:** test  
**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  
**Role:** Crypto-Analyst  
**Status:** **QUEUED** — emitted from test strategy `{plan.get('plan_id')}`  
**auto_pickup:** true  
**blocked_on:** {blocked_s}  
**trial_kind:** {kind}  
**family:** {fam}  
**duration_days:** {dur}  
**Handoff:** `{handoff}`  
**Strategy plan:** `{plan.get('plan_id')}` · workstream `{plan.get('workstream')}`  
**Regime focus:** {regimes}  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Protocol:** `{plan.get('protocol_template') or 'TBD at pickup'}`  
**Launch mode:** `{plan.get('launch_mode') or 'ungated'}`  
**emit_only_when_regime:** `{plan.get('emit_only_when_regime') or '—'}`

### Goal
{title}

### Hypothesis
{plan.get('hypothesis')}

### Success metric
{plan.get('success_metric')}

### Success criteria (frozen before run)
```json
{sc_json}
```

### Non-goals
- No live trading config / regime policy writes without Brad + promotion gates
- Real data only
- No promote on sparse N or bags-only edge
- Close only via `trial_cycle.py decide` with follow_on + decision packet

### Queue
Emitted by `phase6/research/analyst_test_strategy.py` → pickup via `master_test_pickup.py`.

---

"""


def _regime_emit_allowed(
    plan: Dict[str, Any],
    *,
    allow_historical_ids: Optional[List[str]] = None,
) -> tuple[bool, str]:
    """Park bear/bull (etc.) until live regime matches or Brad unlocks historical backtest.

    Returns (allowed, launch_mode) where launch_mode is live_regime | historical_backtest | ungated.
    """
    allow_historical_ids = allow_historical_ids or []
    pid = str(plan.get("plan_id") or "")
    need_reg = (plan.get("emit_only_when_regime") or "").strip().lower()
    if not need_reg:
        return True, "ungated"

    live_reg = _live_regime_label()
    if live_reg == need_reg:
        return True, "live_regime"

    # Explicit Brad unlock for historical bear/bull tape while live is flat/other
    hist_ok = bool(plan.get("allow_historical_backtest"))
    unlocked = pid in allow_historical_ids or bool(plan.get("historical_emit_unlocked"))
    if hist_ok and unlocked:
        return True, "historical_backtest"

    return False, f"parked_until_regime={need_reg}_or_historical_unlock (live={live_reg})"


def emit(
    dry_run: bool = False,
    max_n: Optional[int] = None,
    allow_historical_plan_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    s = sync_active(seed())
    cap = s.get("capacity") or DEFAULT_CAPACITY
    max_n = int(max_n if max_n is not None else cap.get("max_emit_per_run", 1))
    slots = s.get("slots") or _count_slots()
    review_cap = int(cap.get("max_review_pending", 2))
    allow_historical_plan_ids = list(allow_historical_plan_ids or [])
    if slots.get("review_pending", 0) >= review_cap:
        return {
            "emitted": [],
            "skipped_reason": "review_pending_full",
            "slots": slots,
            "dry_run": dry_run,
        }

    offline_free = slots["offline_running"] < int(cap.get("max_offline_analysis", 1))
    instru_free = slots["instru_running"] < int(cap.get("max_parallel_instrumentation", 1))

    master = _master_task_ids()
    candidates = [
        p
        for p in sorted(s.get("roadmap") or [], key=lambda x: int(x.get("priority") or 99))
        if p.get("status") == "planned" and p.get("auto_pickup", True)
    ]
    emitted: List[Dict[str, Any]] = []
    parked: List[Dict[str, str]] = []

    for plan in candidates:
        if len(emitted) >= max_n:
            break
        kind = (plan.get("trial_kind") or "offline_analysis").lower()
        if kind == "parallel_instrumentation" and not instru_free:
            continue
        if kind != "parallel_instrumentation" and not offline_free:
            continue
        # depends_on_plans
        deps = plan.get("depends_on_plans") or []
        dep_ok = True
        for d in deps:
            other = next((x for x in s["roadmap"] if x.get("plan_id") == d), None)
            if other and other.get("status") != "done":
                dep_ok = False
                break
        if not dep_ok:
            continue
        # Regime park: live match OR explicit historical-backtest unlock
        ok_reg, launch_mode = _regime_emit_allowed(
            plan, allow_historical_ids=allow_historical_plan_ids
        )
        if not ok_reg:
            parked.append(
                {
                    "plan_id": str(plan.get("plan_id") or ""),
                    "reason": launch_mode,
                }
            )
            plan["emit_blocked_reason"] = launch_mode
            continue
        plan["launch_mode"] = launch_mode

        # TEST_REGIMEN_E2E: no emit without frozen success_criteria + design
        sc = plan.get("success_criteria")
        design = plan.get("design")
        if not isinstance(sc, dict) or not sc.get("primary_window"):
            plan.setdefault("emit_blocked_reason", "missing_success_criteria")
            continue
        if not isinstance(design, dict) or not design.get("hypothesis"):
            # allow hypothesis at plan root as fallback
            if not plan.get("hypothesis"):
                plan.setdefault("emit_blocked_reason", "missing_design")
                continue

        master_id = _master_id_for_plan(plan)
        if master_id in master:
            plan["master_id"] = master_id
            plan["status"] = "emitted" if master[master_id] not in ("DONE", "CLOSED") else "done"
            continue

        handoff = _write_handoff(plan, master_id)
        section = _render_master_section(plan, master_id, handoff)
        if dry_run:
            emitted.append(
                {
                    "master_id": master_id,
                    "plan_id": plan["plan_id"],
                    "launch_mode": plan.get("launch_mode") or "ungated",
                    "dry_run": True,
                }
            )
            continue

        text = MASTER_PATH.read_text() if MASTER_PATH.exists() else ""
        # Prepend after first horizontal rule following top running tasks if possible —
        # simplest: insert after line 0 at top of file
        MASTER_PATH.write_text(section + text)
        plan["master_id"] = master_id
        plan["status"] = "emitted"
        plan["emitted_at"] = _now()
        plan["handoff"] = handoff
        if plan.get("launch_mode") == "historical_backtest":
            plan["historical_emit_unlocked"] = False
            plan["last_historical_emit_at"] = _now()
        emitted.append(
            {
                "master_id": master_id,
                "plan_id": plan["plan_id"],
                "handoff": handoff,
                "launch_mode": plan.get("launch_mode") or "ungated",
            }
        )
        s.setdefault("emission_log", []).append(
            {
                "at": _now(),
                "plan_id": plan["plan_id"],
                "master_id": master_id,
                "launch_mode": plan.get("launch_mode") or "ungated",
            }
        )
        # only one slot type consumed per emit defaults
        if kind == "parallel_instrumentation":
            instru_free = False
        else:
            offline_free = False

    if not dry_run:
        _save(s)
        # refresh pickup queue
        try:
            from phase6.research.master_test_pickup import scan

            scan()
        except Exception:
            pass
    return {
        "emitted": emitted,
        "parked": parked,
        "slots": slots,
        "live_regime": _live_regime_label(),
        "dry_run": dry_run,
    }


def status() -> Dict[str, Any]:
    s = sync_active(seed())
    roadmap = s.get("roadmap") or []
    by: Dict[str, List[str]] = {}
    for p in roadmap:
        by.setdefault(p.get("status") or "?", []).append(
            f"{p.get('plan_id')}:{p.get('master_id') or '-'}"
        )
    parked_plans = []
    for p in roadmap:
        if p.get("status") != "planned":
            continue
        need = (p.get("emit_only_when_regime") or "").strip()
        if not need:
            continue
        ok, mode = _regime_emit_allowed(p)
        if not ok:
            parked_plans.append(
                {
                    "plan_id": p.get("plan_id"),
                    "emit_only_when_regime": need,
                    "allow_historical_backtest": bool(p.get("allow_historical_backtest")),
                    "park_reason": p.get("park_reason") or mode,
                }
            )
    return {
        "north_star": s.get("north_star"),
        "slots": s.get("slots"),
        "capacity": s.get("capacity"),
        "by_status": by,
        "active_master_ids": s.get("active_master_ids"),
        "live_regime": _live_regime_label(),
        "parked_regime_plans": parked_plans,
        "path": str(STRATEGY_PATH.relative_to(PROJECT_ROOT)),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_seed = sub.add_parser("seed")
    p_seed.add_argument("--force", action="store_true")
    sub.add_parser("sync-active")
    p_em = sub.add_parser("emit")
    p_em.add_argument("--dry-run", action="store_true")
    p_em.add_argument("-n", type=int, default=None)
    p_em.add_argument(
        "--allow-historical-backtest",
        action="append",
        default=[],
        metavar="PLAN_ID",
        help=(
            "Unlock one parked bear/bull plan for historical-tape emit "
            "(plan must have allow_historical_backtest=true). Repeatable."
        ),
    )
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "seed":
        s = seed(force=bool(args.force))
        print(f"seeded roadmap={len(s.get('roadmap') or [])} → {STRATEGY_PATH}")
        return 0
    if args.cmd == "sync-active":
        s = sync_active()
        print(json.dumps({"slots": s.get("slots"), "active": s.get("active_master_ids")}, indent=2))
        return 0
    if args.cmd == "emit":
        out = emit(
            dry_run=bool(args.dry_run),
            max_n=args.n,
            allow_historical_plan_ids=list(args.allow_historical_backtest or []),
        )
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
