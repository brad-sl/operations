#!/usr/bin/env python3
"""Paper (log-only) shadow for layered bull re-entry.

Writes status + append-only log. Does NOT activate analyst_shadow_overlay
or change live REGIME-CASH / runner knobs.

Why paper while STOCH-RSI-PARALLEL is RUNNING:
  Stoch trial is parallel instrumentation on the live trade stream
  (allocator stays plain RSI). A live $75 re-entry sleeve would change
  fills/SL sample through final (~2026-08-04) and confound that trial.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.bull_reentry_layered import build_signal_series  # noqa: E402
from phase6.research import regime_detector as rd  # noqa: E402

STATUS = ROOT / "data/state/bull_reentry_layered_paper_shadow.json"
LOG = ROOT / "data/state/bull_reentry_layered_paper_shadow.jsonl"
SPEC = "docs/research/BULL_REENTRY_LAYERED_SPEC.md"
STOCH_TRIAL = "STOCH-RSI-PARALLEL-20260721"
LIVE_OK_AFTER = "2026-08-04T16:00:00+00:00"  # after Stoch final (~09:00 PT)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stoch_status() -> Dict[str, Any]:
    p = ROOT / "data/state/trials" / f"{STOCH_TRIAL}.json"
    if not p.exists():
        return {"trial_id": STOCH_TRIAL, "status": "missing"}
    t = json.loads(p.read_text())
    return {
        "trial_id": STOCH_TRIAL,
        "status": t.get("status"),
        "final_at": t.get("final_at"),
        "parallel_only": (t.get("intent") or {}).get("parallel_only"),
        "allocator_stays_plain_rsi": (t.get("intent") or {}).get("allocator_stays_plain_rsi"),
    }


def _audit() -> Dict[str, Any]:
    try:
        from phase6.research.live_param_audit_gate import load_latest_param_audit_summary

        s = load_latest_param_audit_summary() or {}
        return {
            "fail_count": s.get("fail_count"),
            "confidence_score": s.get("confidence_score"),
            "ok": s.get("ok"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _overlay_active() -> Dict[str, Any]:
    p = ROOT / "data/state/analyst_shadow_overlay.json"
    if not p.exists():
        return {"active": False}
    d = json.loads(p.read_text())
    return {
        "active": bool(d.get("active")),
        "proposal_id": d.get("proposal_id"),
        "scenario_id": d.get("scenario_id"),
    }


def main() -> int:
    btc_list, meta = rd._merge_live_close(rd._load_btc_closes())
    days = [d for d, _ in btc_list]
    px = {d: c for d, c in btc_list}
    sigs = build_signal_series(days, px, flat_deploy_without_breakout=True)
    last = sigs[-1] if sigs else None
    det = rd.detect_regime()
    stoch = _stoch_status()
    stoch_running = stoch.get("status") in ("RUNNING", "DEGRADED", "INSTRUMENTED")
    overlay = _overlay_active()
    audit = _audit()

    live_block_reasons = []
    if stoch_running:
        live_block_reasons.append(f"{STOCH_TRIAL} status={stoch.get('status')} (trade-stream confound)")
    if overlay.get("active"):
        live_block_reasons.append(f"another shadow active: {overlay.get('proposal_id')}")
    if audit.get("fail_count") not in (0, None) and audit.get("fail_count", 1) > 0:
        live_block_reasons.append(f"param_audit fail_count={audit.get('fail_count')}")

    payload: Dict[str, Any] = {
        "mode": "paper_log_only",
        "live_apply": False,
        "spec": SPEC,
        "as_of": _now(),
        "signal": asdict(last) if last else None,
        "detector": det,
        "live_merge": meta,
        "stoch_trial": stoch,
        "stoch_blocks_live_shadow": stoch_running,
        "overlay": overlay,
        "param_audit": audit,
        "live_activate_not_before": LIVE_OK_AFTER,
        "live_block_reasons": live_block_reasons,
        "would_set_cap_usd": last.cap_usd if last else None,
        "would_layer": last.layer if last else None,
        "would_allow_new_buys": last.allow_new_buys if last else None,
        "note": (
            "Paper shadow only. Live layered sleeve deferred until Stoch trial "
            "not RUNNING and not before live_activate_not_before."
        ),
    }

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(payload, indent=2) + "\n")
    with LOG.open("a") as f:
        f.write(
            json.dumps(
                {
                    "at": payload["as_of"],
                    "layer": payload["would_layer"],
                    "cap": payload["would_set_cap_usd"],
                    "breakout_on": (last.breakout_on if last else None),
                    "rsi": (last.rsi if last else None),
                    "regime": det.get("regime"),
                    "btc_30d": det.get("btc_return_pct"),
                    "stoch_status": stoch.get("status"),
                }
            )
            + "\n"
        )

    # Human one-liner
    print(
        json.dumps(
            {
                "paper_shadow": "ok",
                "layer": payload["would_layer"],
                "cap": payload["would_set_cap_usd"],
                "breakout_on": last.breakout_on if last else None,
                "rsi": last.rsi if last else None,
                "regime": det.get("regime"),
                "btc_30d": det.get("btc_return_pct"),
                "live_apply": False,
                "stoch_blocks_live": stoch_running,
                "status_path": str(STATUS),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
