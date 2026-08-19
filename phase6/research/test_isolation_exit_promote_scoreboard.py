#!/usr/bin/env python3
"""Isolation: exit promote scoreboard (GAP-01)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_exit_promote_scoreboard import (  # noqa: E402
    build_scoreboard,
    evaluate_gates,
    render_md,
)


def _write(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def main() -> int:
    now = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    started = (now - timedelta(days=10)).isoformat()

    # Partial: flat only, short calendar → collecting
    col_partial = {
        "started_at": started,
        "by_regime": {
            "flat": {"would_fire_episodes": 86, "by_kind": {"fixed_tp": 9}, "pairs": {}}
        },
        "days_regime_seen": {"flat": [f"2026-08-{d:02d}" for d in range(6, 17)]},
    }
    status = {
        "mode": "shadow",
        "live_apply": False,
        "regime": "flat",
        "plain_english": "test status",
        "signals": [],
        "promotion": {},
    }
    map_cfg = {"mode": "shadow", "live_apply": False, "auto_promote": False}
    tp_cfg = {"take_profit": {"mode": "shadow"}}

    g = evaluate_gates(
        collection=col_partial,
        status=status,
        map_cfg=map_cfg,
        tp_cfg=tp_cfg,
        now=now,
    )
    assert g["decision"] in (
        "collecting",
        "collecting_calendar",
        "collecting_partial_regime",
    ), g["decision"]
    assert g["live_tp_allowed"] is False
    assert g["per_regime"]["flat"]["episodes_ok"] is True
    assert g["per_regime"]["bull"]["episodes_ok"] is False
    assert g["checks"]["multi_regime_bull_bear_flat"]["pass"] is False

    # Full multi-regime + 60d → ready_for_brad_review
    started60 = (now - timedelta(days=61)).isoformat()
    col_full = {
        "started_at": started60,
        "by_regime": {
            "flat": {"would_fire_episodes": 20, "by_kind": {}, "pairs": {}},
            "bull": {"would_fire_episodes": 8, "by_kind": {}, "pairs": {}},
            "bear": {"would_fire_episodes": 6, "by_kind": {}, "pairs": {}},
        },
        "days_regime_seen": {
            "flat": ["2026-06-01"],
            "bull": ["2026-07-01"],
            "bear": ["2026-08-01"],
        },
    }
    g2 = evaluate_gates(
        collection=col_full,
        status=status,
        map_cfg=map_cfg,
        tp_cfg=tp_cfg,
        now=now,
    )
    assert g2["decision"] == "ready_for_brad_review", g2
    assert g2["checks"]["multi_regime_bull_bear_flat"]["pass"] is True
    assert g2["live_tp_allowed"] is False

    # Misconfig: auto_promote
    g3 = evaluate_gates(
        collection=col_full,
        status=status,
        map_cfg={**map_cfg, "auto_promote": True},
        tp_cfg=tp_cfg,
        now=now,
    )
    assert g3["decision"] == "blocked_misconfig", g3

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        _write(td_path / "col.json", col_partial)
        _write(td_path / "st.json", status)
        _write(td_path / "map.json", map_cfg)
        _write(td_path / "tp.json", tp_cfg)
        board = build_scoreboard(
            now=now,
            include_sl_cf=False,
            collection_path=td_path / "col.json",
            status_path=td_path / "st.json",
            map_path=td_path / "map.json",
            tp_path=td_path / "tp.json",
        )
        assert board["schema"] == "exit_promote_scoreboard_v1"
        assert board["flag"] == "COLLECTING"
        md = render_md(board)
        assert "Exit promote scoreboard" in md
        assert "Go/no-go" in md

    # Live smoke (real files; must not crash)
    live = build_scoreboard(include_sl_cf=True)
    assert "gates" in live and "decision" in live["gates"]
    print("PASS test_isolation_exit_promote_scoreboard")
    print(
        "  fixture_partial:",
        g["decision"],
        "fixture_full:",
        g2["decision"],
        "fixture_block:",
        g3["decision"],
    )
    print(
        "  live:",
        live["gates"].get("decision"),
        live.get("flag"),
        live["gates"].get("go_no_go", "")[:80],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
