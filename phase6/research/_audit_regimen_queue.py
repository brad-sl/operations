#!/usr/bin/env python3
"""One-shot audit: regimen debt on trials + planned roadmap readiness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TRIALS = ROOT / "data" / "state" / "trials"
DECISIONS = ROOT / "docs" / "testing" / "decisions"


def main() -> int:
    rows = []
    for p in sorted(TRIALS.glob("*.json")):
        if p.name.startswith(("INDEX", "PICKUP", "TEST_STRATEGY")):
            continue
        try:
            t = json.loads(p.read_text())
        except Exception:
            continue
        if not isinstance(t, dict) or "trial_id" not in t:
            continue
        tid = t["trial_id"]
        dec_raw = t.get("decision")
        dec = dec_raw if isinstance(dec_raw, dict) else {}
        out_raw = t.get("outcome")
        out = out_raw if isinstance(out_raw, dict) else {}
        sc_raw = t.get("success_criteria")
        sc = sc_raw if isinstance(sc_raw, dict) else {}
        design_raw = t.get("design")
        design = design_raw if isinstance(design_raw, dict) else {}
        proto = t.get("protocol")
        packet = t.get("decision_packet")
        fr = t.get("final_report")
        fo_raw = t.get("follow_on")
        fo = fo_raw.get("mode") if isinstance(fo_raw, dict) else None
        fo = fo or dec.get("follow_on")
        debt = []
        if t.get("status") == "CLOSED":
            if not sc.get("primary_window"):
                debt.append("no_success_criteria")
            if not design and not proto:
                debt.append("no_design_protocol")
            if not out.get("class") and dec.get("value") not in ("abort",):
                debt.append("no_outcome")
            decs = list(DECISIONS.glob(f"DEC_{tid}_*.md")) if DECISIONS.is_dir() else []
            if not packet and not decs:
                debt.append("no_decision_packet")
            if not fo:
                debt.append("no_follow_on")
            if not fr and dec.get("value") != "abort":
                debt.append("no_final_report")
        rows.append(
            {
                "tid": tid,
                "st": t.get("status"),
                "dec": dec.get("value"),
                "cr": dec.get("cr"),
                "debt": debt,
                "path": p.name,
                "fo": fo,
                "fr": bool(fr),
            }
        )

    print("=== TRIALS ===")
    for r in rows:
        print(
            f"{r['tid'][:52]:52} {str(r['st'])[:8]:8} {str(r['dec'])[:20]:20} "
            f"fo={r['fo'] or '-':12} {r['debt'] or ['ok']}"
        )

    s = json.loads((TRIALS / "TEST_STRATEGY.json").read_text())
    print("\n=== PLANNED ROADMAP ===")
    for p in s.get("roadmap", []):
        if p.get("status") != "planned":
            continue
        need = []
        if not p.get("success_criteria"):
            need.append("success_criteria")
        if not p.get("design"):
            need.append("design")
        if not p.get("protocol_template"):
            need.append("protocol_template")
        if not p.get("hypothesis"):
            need.append("hypothesis")
        if not p.get("success_metric"):
            need.append("success_metric")
        print(p.get("plan_id"), "prio", p.get("priority"), "missing", need or ["ready-ish"])

    print("\nslots", s.get("slots"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
