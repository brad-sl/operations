#!/usr/bin/env python3
"""Activate LAYERED-REENTRY-FLATB-75 live shadow only when gates pass.

Default dry-run. Refuses while STOCH-RSI-PARALLEL is RUNNING.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

READY = ROOT / "config/shadow_overlays/LAYERED-REENTRY-FLATB-75.ready.json"
PAPER = ROOT / "data/state/bull_reentry_layered_paper_shadow.json"
OVERLAY = ROOT / "data/state/analyst_shadow_overlay.json"
STOCH_ID = "STOCH-RSI-PARALLEL-20260721"


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def evaluate() -> tuple[bool, list[str], dict]:
    ready = json.loads(READY.read_text())
    req = ready.get("do_not_activate_until") or {}
    fails: list[str] = []
    info: dict = {"ready_proposal": ready.get("proposal_id")}

    # Stoch
    stoch_p = ROOT / "data/state/trials" / f"{STOCH_ID}.json"
    stoch_st = None
    if stoch_p.exists():
        stoch_st = json.loads(stoch_p.read_text()).get("status")
    info["stoch_status"] = stoch_st
    if stoch_st in ("RUNNING", "DEGRADED", "INSTRUMENTED"):
        fails.append(f"stoch trial still {stoch_st}")

    # not before
    nb = req.get("not_before_utc")
    if nb:
        if datetime.now(timezone.utc) < _parse_ts(nb):
            fails.append(f"before not_before_utc={nb}")
        info["not_before_utc"] = nb

    # other shadow
    if OVERLAY.exists():
        ov = json.loads(OVERLAY.read_text())
        if ov.get("active"):
            fails.append(f"overlay already active: {ov.get('proposal_id')}")
        info["overlay_active"] = ov.get("active")

    # audit
    try:
        from phase6.research.live_param_audit_gate import load_latest_param_audit_summary

        a = load_latest_param_audit_summary() or {}
        info["param_audit"] = {
            "fail_count": a.get("fail_count"),
            "confidence_score": a.get("confidence_score"),
        }
        if int(a.get("fail_count") or 0) > int(req.get("live_param_audit_fail_count_max", 0)):
            fails.append(f"param_audit fail_count={a.get('fail_count')}")
        conf = a.get("confidence_score")
        if conf is not None and float(conf) < float(req.get("live_param_audit_confidence_min", 0.85)):
            fails.append(f"param_audit conf={conf}")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"param_audit error: {exc}")

    # paper signal
    if PAPER.exists():
        paper = json.loads(PAPER.read_text())
        info["paper_layer"] = paper.get("would_layer")
        info["paper_cap"] = paper.get("would_set_cap_usd")
        allowed = set(req.get("signal_layer_in") or [])
        layer = paper.get("would_layer")
        if allowed and layer not in allowed:
            fails.append(f"paper layer={layer!r} not in {sorted(allowed)}")
    else:
        fails.append("paper shadow status missing — run paper script first")

    return len(fails) == 0, fails, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--activate", action="store_true", help="Write live overlay if gates pass")
    ap.add_argument("--force", action="store_true", help="Skip stoch/date gates (dangerous)")
    args = ap.parse_args()

    ok, fails, info = evaluate()
    if args.force:
        # still refuse if another overlay active
        fails = [f for f in fails if "overlay already active" in f or "param_audit" in f]
        ok = len(fails) == 0

    print(json.dumps({"gates_ok": ok, "failures": fails, "info": info}, indent=2))
    if not args.activate:
        print("dry-run only (pass --activate to write overlay)")
        return 0 if ok else 2

    if not ok:
        print("REFUSED activate", file=sys.stderr)
        return 2

    ready = json.loads(READY.read_text())
    state = {
        "active": True,
        "mode": "shadow",
        "proposal_id": ready["proposal_id"],
        "scenario_id": ready["scenario_id"],
        "source_run_id": ready.get("source_run_id"),
        "knobs": ready.get("knobs") or {},
        "live_overlay": ready.get("live_overlay") or {},
        "regime_policy": {"enabled": False},
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "spec": ready.get("spec"),
        "note": "LAYERED re-entry $75 — activated after Stoch clear",
    }
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY.write_text(json.dumps(state, indent=2) + "\n")
    print(f"WROTE {OVERLAY}")
    print("Restart phase6 runner to pick up overlay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
