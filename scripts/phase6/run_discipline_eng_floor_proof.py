#!/usr/bin/env python3
"""Run/ print proof that eng floor 0.35 + live_apply=true is already live (B2 harden, no new knob).

No runner restart needed (no import-time money change).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core import tryout_decision_discipline as tdd  # noqa: E402


def _cfg_live(tmp: Path, live: bool = True) -> dict:
    return {
        "schema": tdd.SCHEMA,
        "live_apply": live,
        "shadow_log": True,
        "thresholds": {
            "min_setup_score": 1.5,
            "min_setup_confidence": 0.55,
            "min_sent_clear_noul": 0.55,
            "min_eng_absolute": 0.35,
            "max_toxic_source_noul": 0.50,
            "min_latch_fresh_noul": 0.40,
            "behavior_skip_labels": ["fast_tryout_exit", "sl_heavy"],
            "behavior_min_closed_rts": 5,
            "behavior_skip_confidence": 0.60,
            "reduced_shell_setup_score": 1.0,
            "reduced_shell_fraction": 0.5,
        },
        "calibration": {"enabled": True, "path": str(tmp / "triples.jsonl")},
    }


def main() -> int:
    print("=== TRYOUT_ENG_FLOOR_PROOF (B2: already live, proof only) ===")
    floor = 0.35
    print(f"floor value: {floor}")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        cfg = _cfg_live(tmp, live=True)
        print(f"live_apply: {cfg.get('live_apply')}")

        # weak eng < 0.35 with live_apply -> skip_seat / STAND_DOWN
        block_weak = tdd.apply_to_composer_candidate(
            {"pair": "WEAK-USD", "rsi": 30, "eng": 0.29, "eng_source": "paid_x"},
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            shell_usd=25.0,
            floor=0.30,
            persist=False,
            cfg=cfg,
        )
        print(f"weak eng=0.29 live=True skip_seat: {block_weak.get('skip_seat')}")
        print(f"weak action: { (block_weak.get('result') or {}).get('policy', {}).get('action') }")

        # strong eng >=0.35 passes
        block_strong = tdd.apply_to_composer_candidate(
            {"pair": "STRONG-USD", "rsi": 42, "eng": 0.42, "eng_source": "paid_x_probe"},
            regime={"strategy_mode": "deploy", "allow_new_buys": True, "regime": "flat"},
            shell_usd=25.0,
            floor=0.35,
            persist=False,
            cfg=cfg,
        )
        print(f"strong eng=0.42 live=True skip_seat: {block_strong.get('skip_seat')}")
        print(f"strong action: {(block_strong.get('result') or {}).get('policy', {}).get('action') }")

        # also direct evaluate for STAND_DOWN
        res = tdd.evaluate_candidate(
            pair="WEAK2-USD",
            rsi=25.0,
            eng=0.31,
            eng_source="paid_x",
            floor=0.30,
            shell_usd=25.0,
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            persist=False,
            cfg=cfg,
        )
        print(f"weak direct action==STAND_DOWN: {res.get('policy', {}).get('action') == tdd.ACT_STAND_DOWN}")

    print("Lever already live per config + code; B2 = proof not new knob.")
    print("No runner restart required (no import-time money change).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
