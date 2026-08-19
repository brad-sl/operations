#!/usr/bin/env python3
"""Activate BULL-DEFENSIVE-ROTATION-21D shadow only when gates pass.

Default is dry-run / status. Use --activate to write analyst_shadow_overlay.json.
Does NOT restart the runner — print restart commands after activate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

READY = ROOT / "config/shadow_overlays/BULL-DEFENSIVE-ROTATION-21D.ready.json"
WATCH = ROOT / "data/state/bull_reentry_watch.json"
STATUS = ROOT / "data/state/regime_cash_status.json"


def _btc_and_regime() -> dict:
    out: dict = {"regime": None, "btc_return_pct": None, "source": None}
    if STATUS.exists():
        st = json.loads(STATUS.read_text())
        out["regime"] = st.get("regime")
        det = st.get("detector") or {}
        out["btc_return_pct"] = det.get("btc_return_pct", st.get("btc_return_pct"))
        out["source"] = "regime_cash_status"
        out["as_of"] = st.get("as_of") or det.get("as_of")
    try:
        from phase6.research.regime_detector import detect_regime

        d = detect_regime()
        if isinstance(d, dict):
            out["regime_live"] = d.get("regime")
            out["btc_return_pct_live"] = d.get("btc_return_pct")
            out["detector_as_of"] = d.get("as_of")
    except Exception as exc:  # noqa: BLE001
        out["detector_error"] = str(exc)
    return out


def _param_audit() -> dict:
    try:
        from phase6.research.live_param_audit_gate import load_latest_param_audit_summary

        s = load_latest_param_audit_summary() or {}
        return {
            "fail_count": s.get("fail_count"),
            "confidence_score": s.get("confidence_score"),
            "ok": s.get("ok"),
            "verified_fills": s.get("verified_fills"),
            "run_id": s.get("run_id"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def evaluate_gates(ready: dict) -> tuple[bool, list[str], dict]:
    req = ready.get("do_not_activate_until") or {}
    btc_min = float(req.get("btc_30d_return_pct_min", 15.0))
    fail_max = int(req.get("live_param_audit_fail_count_max", 0))
    conf_min = float(req.get("live_param_audit_confidence_min", 0.85))
    need_regime = str(req.get("regime") or "bull")

    live = _btc_and_regime()
    audit = _param_audit()
    failures: list[str] = []

    regime = live.get("regime_live") or live.get("regime")
    btc = live.get("btc_return_pct_live")
    if btc is None:
        btc = live.get("btc_return_pct")

    if regime != need_regime:
        failures.append(f"regime={regime!r} need {need_regime!r}")
    if btc is None:
        failures.append("btc_30d missing")
    elif float(btc) < btc_min:
        failures.append(f"btc_30d={btc} < {btc_min}")

    fc = audit.get("fail_count")
    if fc is None:
        failures.append("param_audit summary missing fail_count")
    elif int(fc) > fail_max:
        failures.append(f"param_audit fail_count={fc} > {fail_max}")
    conf = audit.get("confidence_score")
    if conf is None:
        failures.append("param_audit confidence missing")
    elif float(conf) < conf_min:
        failures.append(f"param_audit confidence={conf} < {conf_min}")

    from phase6.research.shadow_overlay_store import load_state

    st = load_state()
    if st.get("active"):
        failures.append(f"shadow already active: {st.get('proposal_id')}")

    ctx = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "live": live,
        "param_audit": audit,
        "failures": failures,
        "gates_ok": len(failures) == 0,
        "proposal_id": ready.get("proposal_id"),
        "btc_min": btc_min,
        "need_regime": need_regime,
    }
    return len(failures) == 0, failures, ctx


def write_watch(ctx: dict) -> None:
    WATCH.parent.mkdir(parents=True, exist_ok=True)
    WATCH.write_text(json.dumps(ctx, indent=2) + "\n")


def activate(ready: dict) -> dict:
    from phase6.research.production_period_baseline import compute_since_go_live
    from phase6.research.shadow_overlay_store import activate_overlay

    proposal = {
        "id": ready["proposal_id"],
        "source_run_id": ready.get("source"),
        "scenario_id": ready["scenario_id"],
    }
    scenario = {
        "id": ready["scenario_id"],
        "engine": "arch4",
        "arch4": {"strategy": "rotation"},
        "backtest": {
            "initial_capital": 1000,
            "rebalance_frequency_days": 21,
            "rebalance_cap_usd": float(
                (ready.get("live_overlay") or {}).get(
                    "global_settings.rebalance_cap_usd", 100
                )
            ),
        },
    }
    pack = {"default_engine": "arch4", "scenarios": [scenario]}
    prod = compute_since_go_live()
    equity = float(prod.get("end_equity_usd") or prod.get("initial_capital_usd") or 1000)
    state = activate_overlay(
        proposal,
        scenario,
        pack,
        predicted_metrics=ready.get("predicted") or {},
        baseline_equity_usd=equity,
        enable_regime_policy=False,
    )
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--activate",
        action="store_true",
        help="Write shadow overlay if gates pass (default: status only)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Skip BTC/regime gates (still refuses if overlay already active). Ops escape only.",
    )
    args = ap.parse_args()

    ready = json.loads(READY.read_text())
    ok, failures, ctx = evaluate_gates(ready)
    if args.force and args.activate:
        # drop regime/btc failures only
        failures = [f for f in failures if "shadow already active" in f]
        ok = len(failures) == 0
        ctx["force"] = True
        ctx["failures"] = failures
        ctx["gates_ok"] = ok

    write_watch(ctx)
    print(json.dumps(ctx, indent=2))

    if not args.activate:
        print("\nStatus only. Re-run with --activate when gates_ok=true.")
        return 0 if ok else 2

    if not ok:
        print("REFUSED activate:", "; ".join(failures))
        return 2

    state = activate(ready)
    print(
        f"\nACTIVE shadow {state.get('proposal_id')} scenario={state.get('scenario_id')}"
    )
    print("Restart runner required:")
    print("  pkill -f 'python.* -m phase6.core.phase6_runner' || true")
    print("  rm -f logs/phase6_runner.pid phase6_live.pid")
    print("  bash scripts/phase6/start_phase6_runner.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
