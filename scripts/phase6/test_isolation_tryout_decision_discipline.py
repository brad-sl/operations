#!/usr/bin/env python3
"""Isolation tests: tryout decision discipline (no live I/O money path)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import tryout_decision_discipline as tdd  # noqa: E402


def _cfg_live(tmp: Path, live: bool = False) -> Dict:
    return {
        "schema": tdd.SCHEMA,
        "live_apply": live,
        "shadow_log": True,
        "thresholds": {
            "min_setup_score": 1.5,
            "min_setup_confidence": 0.55,
            "min_sent_clear_noul": 0.30,
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


# fix typing import
from typing import Any, Dict  # noqa: E402


def test_good_setup_full_buy() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        cfg = _cfg_live(tmp, live=False)
        res = tdd.evaluate_candidate(
            pair="LINK-USD",
            rsi=35.0,
            eng=0.45,
            eng_source="paid_x_probe",
            floor=0.30,
            rsi_max=55.0,
            shell_usd=25.0,
            regime={"strategy_mode": "deploy", "allow_new_buys": True, "regime": "flat"},
            seats_used_today=1,
            seats_max_day=6,
            open_tryout_seats=1,
            max_open_tryout=6,
            latch_age_min=10.0,
            latch_ttl_min=180.0,
            persist=True,
            cfg=cfg,
        )
        pol = res["policy"]
        assert pol["action"] == tdd.ACT_BUY_FULL, pol
        assert pol["would_block_if_live"] is False
        assert pol["live_apply"] is False
        assert res["triple_log"]["logged"] is True


def test_toxic_source_stand_down() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        cfg = _cfg_live(tmp)
        res = tdd.evaluate_candidate(
            pair="ETH-USD",
            rsi=40.0,
            eng=0.50,
            eng_source="free_rss_tee",
            floor=0.30,
            shell_usd=25.0,
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            persist=False,
            cfg=cfg,
        )
        assert res["policy"]["action"] == tdd.ACT_STAND_DOWN
        assert res["policy"]["would_block_if_live"] is True


def test_live_apply_blocks_seat() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        cfg = _cfg_live(tmp, live=True)
        block = tdd.apply_to_composer_candidate(
            {"pair": "AAA-USD", "rsi": 30, "eng": 0.1, "eng_source": "paid_x"},
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            shell_usd=25.0,
            floor=0.30,
            persist=False,
            cfg=cfg,
        )
        assert block["skip_seat"] is True
        assert block["live_apply"] is True


def test_shadow_does_not_skip() -> None:
    """Even weak setups must not skip seat while live_apply=false."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        cfg = _cfg_live(tmp, live=False)
        block = tdd.apply_to_composer_candidate(
            {"pair": "BBB-USD", "rsi": 30, "eng": 0.1, "eng_source": "paid_x"},
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            shell_usd=25.0,
            floor=0.30,
            persist=False,
            cfg=cfg,
        )
        assert block["skip_seat"] is False
        assert block["would_block_if_live"] is True


def test_behavior_skip_with_n() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tdd.STATE_DIR = tmp  # type: ignore[attr-defined]
        tdd.LATEST_PATH = tmp / "latest.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH = tmp / "profiles.json"  # type: ignore[attr-defined]
        tdd.PROFILES_PATH.write_text(
            json.dumps(
                {
                    "pairs": {
                        "TAX-USD": {
                            "pattern_hint": "fast_tryout_exit,sl_heavy",
                            "n_closed_rts": 8,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        cfg = _cfg_live(tmp, live=False)
        res = tdd.evaluate_candidate(
            pair="TAX-USD",
            rsi=28.0,
            eng=0.50,
            eng_source="composer_hold:paid_x",
            floor=0.30,
            shell_usd=25.0,
            regime={"strategy_mode": "deploy", "allow_new_buys": True},
            latch_age_min=5.0,
            seats_used_today=0,
            seats_max_day=6,
            persist=False,
            cfg=cfg,
        )
        assert res["policy"]["action"] == tdd.ACT_SKIP_PAIR, res["policy"]
        assert res["policy"]["would_block_if_live"] is True


def test_kill_blocks() -> None:
    cfg = _cfg_live(Path("/tmp"), live=False)
    res = tdd.evaluate_candidate(
        pair="LINK-USD",
        rsi=30,
        eng=0.5,
        eng_source="paid_x",
        kill=True,
        persist=False,
        cfg=cfg,
    )
    assert res["policy"]["action"] == tdd.ACT_STAND_DOWN


def test_config_file_loads() -> None:
    cfg = tdd.load_config()
    assert cfg.get("schema") == tdd.SCHEMA
    assert cfg.get("live_apply") is False


def main() -> int:
    tests = [
        test_good_setup_full_buy,
        test_toxic_source_stand_down,
        test_live_apply_blocks_seat,
        test_shadow_does_not_skip,
        test_behavior_skip_with_n,
        test_kill_blocks,
        test_config_file_loads,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
