#!/usr/bin/env python3
"""Isolation: dual_agree log + confidence board (no network)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.basket_swap_shadow_cf as m  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_dual_agree_and_board(tmp_path: Path) -> None:
    # redirect state paths
    m.ARMS_DIR = tmp_path / "arms"
    m.DUAL_AGREE_DIR = m.ARMS_DIR / "dual_agree"
    m.DUAL_AGREE_JSONL = m.DUAL_AGREE_DIR / "proposals.jsonl"
    m.DUAL_AGREE_LATEST = tmp_path / "dual_agree_latest.json"
    m.BOARD_MD = tmp_path / "BOARD.md"
    m.BOARD_JSON = tmp_path / "board.json"
    m.ARMS_DIR.mkdir(parents=True)

    day = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    # both arms same remove→add same day
    for arm, add in (("anti_pump", "HYPE-USD"), ("risk_adj_mom", "HYPE-USD")):
        d = m.ARMS_DIR / arm
        d.mkdir(parents=True)
        rec = {
            "proposal_id": f"id-{arm[:4]}",
            "ts": _iso(day),
            "arm": arm,
            "remove": "RAVE-USD",
            "add": add,
        }
        (d / "proposals.jsonl").write_text(json.dumps(rec) + "\n")

    # diverge day
    day2 = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    for arm, add in (("anti_pump", "DOT-USD"), ("risk_adj_mom", "LTC-USD")):
        path = m.ARMS_DIR / arm / "proposals.jsonl"
        rec = {
            "proposal_id": f"id2-{arm[:4]}",
            "ts": _iso(day2),
            "arm": arm,
            "remove": "XRP-USD",
            "add": add,
        }
        with path.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    dual = m.record_dual_agree_swaps(arms_prop=None, now=day2)
    assert dual["total_ledger_n"] == 1, dual
    assert dual["new_agreements"][0]["remove"] == "RAVE-USD"
    assert dual["new_agreements"][0]["add"] == "HYPE-USD"
    # idempotent
    dual2 = m.record_dual_agree_swaps(now=day2)
    assert dual2["new_agreements"] == []
    assert dual2["total_ledger_n"] == 1

    # board from synthetic CF
    cf = {
        "as_of": _iso(day2),
        "decide": {
            "status": "modify_selector",
            "plain_english": "Baseline soft.",
        },
        "aggregate_by_arm": {
            "baseline_hybrid": {
                "1d": {"n": 10, "mean_excess_pct": -1.0, "hit_excess_gt0": 0.3},
                "3d": {"n": 8, "mean_excess_pct": -0.5, "hit_excess_gt0": 0.4},
                "7d": {"n": 13, "mean_excess_pct": -6.0, "hit_excess_gt0": 0.38},
                "paper_sleeve_to_now": {"n": 10, "delta_usd": -40.0},
            },
            "anti_pump": {
                "1d": {"n": 16, "mean_excess_pct": 0.5, "hit_excess_gt0": 0.44},
                "3d": {"n": 12, "mean_excess_pct": 8.8, "hit_excess_gt0": 0.67},
                "7d": {"n": 5, "mean_excess_pct": 6.8, "hit_excess_gt0": 0.6},
                "paper_sleeve_to_now": {"n": 17, "delta_usd": 321.0},
            },
            "risk_adj_mom": {
                "1d": {"n": 19, "mean_excess_pct": -1.0, "hit_excess_gt0": 0.37},
                "3d": {"n": 15, "mean_excess_pct": 7.1, "hit_excess_gt0": 0.73},
                "7d": {"n": 7, "mean_excess_pct": 17.0, "hit_excess_gt0": 0.71},
                "paper_sleeve_to_now": {"n": 20, "delta_usd": 414.0},
            },
            "dual_agree": {
                "1d": {"n": 1, "mean_excess_pct": 2.0, "hit_excess_gt0": 1.0},
                "3d": {"n": 0},
                "7d": {"n": 0},
                "paper_sleeve_to_now": {"n": 1, "delta_usd": 5.0},
            },
        },
    }
    board = m.build_confidence_board(cf)
    assert board["any_arm_high_confidence"] is False
    assert "risk_adj_mom" in board["leaders_sleeve_and_3d"]
    assert "anti_pump" in board["leaders_sleeve_and_3d"]
    assert m.BOARD_MD.exists()
    text = m.BOARD_MD.read_text()
    assert "risk_adj_mom" in text
    assert "Any arm high-confidence right now?" in text
    assert "**NO**" in text
    # no hard false promote language
    assert "live batch promote" in text.lower() or "No live basket" in text

    # HC yes when gates clear
    cf_hc = {
        "as_of": _iso(day2),
        "decide": {"status": "ok", "plain_english": "x"},
        "aggregate_by_arm": {
            "risk_adj_mom": {
                "1d": {"n": 20, "mean_excess_pct": 1.0, "hit_excess_gt0": 0.5},
                "3d": {"n": 15, "mean_excess_pct": 2.0, "hit_excess_gt0": 0.55},
                "7d": {"n": 12, "mean_excess_pct": 3.0, "hit_excess_gt0": 0.5},
                "paper_sleeve_to_now": {"n": 12, "delta_usd": 50.0},
            }
        },
    }
    b2 = m.build_confidence_board(cf_hc)
    assert b2["any_arm_high_confidence"] is True
    assert b2["status"] == "high_confidence_shadow"
    print("  dual_agree + confidence board OK")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        test_dual_agree_and_board(Path(td))
    print("test_isolation_basket_dual_agree_board PASS")
