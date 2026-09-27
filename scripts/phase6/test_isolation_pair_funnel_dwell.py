#!/usr/bin/env python3
"""Isolation tests for pair funnel dwell (no live I/O)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core import pair_funnel_dwell as pfd


def _cfg() -> dict:
    return {
        "schema": "pair_funnel_stages_v1",
        "stages": list(pfd._FALLBACK_STAGES),
        "profile": {"min_closed_rts_for_pattern": 2, "predict_enabled": False},
        "tick": {
            "include_composer_candidates": False,
            "include_open_lots": False,
            "include_ledger_exits": False,
            "ledger_lookback_rows": 10,
        },
        "config_ok": True,
        "config_path": "test",
    }


def test_stage_ids_from_config():
    ids = pfd.stage_ids(_cfg())
    assert "tryout_open" in ids
    assert "exit_sl" in ids
    assert ids.index("dual_clear") < ids.index("tryout_open")


def test_transition_records_dwell():
    cfg = _cfg()
    state = pfd._empty_state()
    profiles = {"schema": pfd.PROFILE_SCHEMA, "pairs": {}, "predict_enabled": False}
    t0 = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    r1 = pfd.transition(
        state,
        profiles,
        pair="LINK-USD",
        new_stage="tryout_open",
        source="test",
        at=t0,
        cfg=cfg,
        emit_event=False,
    )
    assert r1["ok"] and state["open"]["LINK-USD"]["stage"] == "tryout_open"
    t1 = t0 + timedelta(hours=3)
    r2 = pfd.transition(
        state,
        profiles,
        pair="LINK-USD",
        new_stage="exit_sl",
        source="test",
        at=t1,
        cfg=cfg,
        emit_event=False,
    )
    assert r2["ok"] and r2["terminal"]
    assert "LINK-USD" not in state["open"]
    dwell = profiles["pairs"]["LINK-USD"]["stage_dwell"]["tryout_open"]
    assert abs(float(dwell["last_h"]) - 3.0) < 1e-6
    assert profiles["pairs"]["LINK-USD"]["outcomes"]["loss_or_tax"] == 1
    assert profiles["pairs"]["LINK-USD"]["closed_rts"] == 1


def test_no_demote_same_stage():
    cfg = _cfg()
    state = pfd._empty_state()
    profiles = {"schema": pfd.PROFILE_SCHEMA, "pairs": {}, "predict_enabled": False}
    t0 = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    pfd.transition(
        state, profiles, pair="ETH-USD", new_stage="dual_clear", source="t", at=t0, cfg=cfg, emit_event=False
    )
    entered = state["open"]["ETH-USD"]["entered_at"]
    pfd.transition(
        state,
        profiles,
        pair="ETH-USD",
        new_stage="dual_clear",
        source="t2",
        at=t0 + timedelta(hours=1),
        cfg=cfg,
        emit_event=False,
    )
    assert state["open"]["ETH-USD"]["entered_at"] == entered


def test_classify_exit():
    assert pfd.classify_exit_stage("stop_loss_hit") == "exit_sl"
    assert pfd.classify_exit_stage("take_profit_trail") == "exit_tp"
    assert pfd.classify_exit_stage("manual") == "exit_other"


def test_pattern_hint_needs_n():
    cfg = _cfg()
    row = {
        "closed_rts": 0,
        "stage_dwell": {},
        "outcomes": {"win": 0, "loss_or_tax": 0, "other": 0},
    }
    h = pfd._pattern_hint(row, cfg)
    assert h and "insufficient_n" in h


def test_load_config_file_exists():
    c = pfd.load_stages_config()
    assert c.get("config_ok") is True
    assert "tryout_open" in pfd.stage_ids(c)
    assert c.get("profile", {}).get("predict_enabled") is False


def test_run_tick_write_tmp(monkeypatch_paths=True):
    cfg = _cfg()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        # redirect artifacts
        pfd.LATEST_PATH = tdir / "latest.json"
        pfd.PROFILES_PATH = tdir / "profiles.json"
        pfd.EVENTS_PATH = tdir / "events.jsonl"
        pfd.MD_REPORT = tdir / "report.md"
        pfd.OPEN_LOTS_PATH = tdir / "lots.json"
        pfd.COMPOSER_LATEST = tdir / "composer.json"
        pfd.LEDGER_PATH = tdir / "ledger.jsonl"
        pfd.OPEN_LOTS_PATH.write_text(
            '{"lots":{"AAA-USD":{"tryout_shell":true,"status":"tryout_open","entry_ts":"2026-09-26T10:00:00Z"}}}'
        )
        cfg["tick"]["include_open_lots"] = True
        out = pfd.run_tick(write=True, cfg=cfg)
        assert out["n_open"] >= 1
        assert pfd.LATEST_PATH.exists()
        assert pfd.PROFILES_PATH.exists()


def test_monthly_table_pair_x_stage() -> None:
    """Pair × stage visit counts — Brad long-term monthly ping shape."""
    cfg = pfd.load_stages_config()
    profiles = {
        "schema": pfd.PROFILE_SCHEMA,
        "pairs": {
            "AAA-USD": {
                "pair": "AAA-USD",
                "stage_dwell": {
                    "tryout_open": {"n": 3, "total_h": 12.0},
                    "exit_sl": {"n": 2, "total_h": 0.1},
                    "exit_tp": {"n": 1, "total_h": 0.0},
                },
                "closed_rts": 3,
                "outcomes": {"win": 1, "loss_or_tax": 2, "other": 0},
                "last_stage": "exit_sl",
            },
            "BBB-USD": {
                "pair": "BBB-USD",
                "stage_dwell": {"rsi_wash": {"n": 5, "total_h": 20.0}},
                "closed_rts": 0,
                "outcomes": {"win": 0, "loss_or_tax": 0, "other": 0},
                "last_stage": "rsi_wash",
            },
        },
        "updated_at": "2026-09-26T00:00:00Z",
        "predict_enabled": False,
    }
    state = {
        "schema": pfd.SCHEMA,
        "open": {
            "AAA-USD": {
                "pair": "AAA-USD",
                "stage": "tryout_open",
                "entered_at": "2026-09-26T00:00:00Z",
                "source": "test",
            }
        },
        "updated_at": "2026-09-26T00:00:00Z",
    }
    mon = pfd.build_monthly_summary(
        profiles=profiles, state=state, cfg=cfg, month_key="2026-09", write=False
    )
    assert mon.get("schema") == "pair_funnel_dwell_monthly_v1"
    assert mon.get("month") == "2026-09"
    assert mon.get("predict_enabled") is False
    assert mon.get("n_pairs") == 2
    table = mon.get("table") or ""
    assert "Pair" in table
    assert "AAA-USD" in table
    assert "BBB-USD" in table
    rows = {r["pair"]: r for r in (mon.get("rows") or [])}
    assert rows["AAA-USD"]["counts"].get("tryout_open") == 3
    assert rows["AAA-USD"]["counts"].get("exit_sl") == 2
    assert rows["AAA-USD"]["closed_rts"] == 3
    assert rows["AAA-USD"]["open_stage"] == "tryout_open"
    assert "try" in table
    assert mon.get("plain_english")


def test_load_dwell_state_unwraps_payload() -> None:
    """Latest file is a tick payload with nested state.open — must unwrap."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "latest.json"
        path.write_text(
            json.dumps(
                {
                    "schema": pfd.SCHEMA,
                    "as_of": "2026-09-26T12:00:00Z",
                    "n_open": 1,
                    "state": {
                        "schema": pfd.SCHEMA,
                        "open": {
                            "LINK-USD": {
                                "pair": "LINK-USD",
                                "stage": "tryout_open",
                                "entered_at": "2026-09-26T00:27:48Z",
                                "source": "open_lots",
                            }
                        },
                        "updated_at": "2026-09-26T12:00:00Z",
                    },
                }
            ),
            encoding="utf-8",
        )
        st = pfd.load_dwell_state(path)
        assert "LINK-USD" in (st.get("open") or {})
        assert st["open"]["LINK-USD"]["stage"] == "tryout_open"


def main() -> int:
    tests = [
        test_stage_ids_from_config,
        test_transition_records_dwell,
        test_no_demote_same_stage,
        test_classify_exit,
        test_pattern_hint_needs_n,
        test_load_config_file_exists,
        test_run_tick_write_tmp,
        test_monthly_table_pair_x_stage,
        test_load_dwell_state_unwraps_payload,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
