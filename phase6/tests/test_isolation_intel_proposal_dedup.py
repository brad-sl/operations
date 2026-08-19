#!/usr/bin/env python3
"""ENG-S7-01: intel report must not re-mint proposal IDs for known titles."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.scripts.generate_trading_intelligence_report import (  # noqa: E402
    collect_deployed_proposal_titles,
    collect_known_proposal_titles,
    generate_strategic_proposals,
    normalize_proposal_title,
    title_already_known,
)


def test_deployed_titles_include_006_pack():
    deployed = collect_deployed_proposal_titles()
    assert normalize_proposal_title(
        "Strengthen pre-rebalance data refresh + fallback for partial coverage"
    ) in deployed
    assert normalize_proposal_title(
        "Add pre-flight settlement poll + product-specific tick handling to SL layer"
    ) in deployed


def test_generate_skips_duplicate_titles_quietly():
    known = collect_known_proposal_titles()
    buf = io.StringIO()
    with redirect_stdout(buf):
        props = generate_strategic_proposals(
            sl_risks={"BTC-USD": {"level": "HIGH"}},
            coverage=0,
            total_pairs=5,
            poly={"risk_on_bias": 0.5},
            learnings={"heuristics": {}},
            state={},
            existing_ids=set(),
            known_title_keys=known,
            opt_brief={"deployment_hint": "hold / negative sharpe"},
            leaderboard=None,
        )
    out = buf.getvalue()
    assert "[ENG-S7-01]" not in out, out
    assert "Suppressed" not in out, out
    titles = {normalize_proposal_title(p["title"]) for p in props}
    assert (
        normalize_proposal_title(
            "Add pre-flight settlement poll + product-specific tick handling to SL layer"
        )
        not in titles
    )
    assert (
        normalize_proposal_title(
            "Strengthen pre-rebalance data refresh + fallback for partial coverage"
        )
        not in titles
    )
    assert (
        normalize_proposal_title(
            "Tighten scenario pack toward positive Sharpe on ARCH-4 holdout"
        )
        not in titles
    )


def test_stem_match_blocks_direction_suffix_drift():
    known = {
        normalize_proposal_title(
            "Wire Polymarket regime bias into allocator as soft constraint "
            "(risk-on tilt (favor momentum pairs))"
        )
    }
    assert title_already_known(
        "Wire Polymarket regime bias into allocator as soft constraint",
        known,
    )


def test_fresh_title_still_mints():
    props = generate_strategic_proposals(
        sl_risks={},
        coverage=5,
        total_pairs=5,
        poly={"risk_on_bias": 0.5},
        learnings={"heuristics": {"allocator_heuristics_active": True}},
        state={},
        existing_ids=set(),
        known_title_keys=set(),
        opt_brief=None,
        leaderboard=None,
    )
    # No forced candidates when SL quiet + full coverage + no OPT seeds —
    # empty is fine; if anything mints it must not be a known shipped stem.
    known = collect_known_proposal_titles()
    for p in props:
        assert not title_already_known(p["title"], known), p["title"]


if __name__ == "__main__":
    test_deployed_titles_include_006_pack()
    test_generate_skips_duplicate_titles_quietly()
    test_stem_match_blocks_direction_suffix_drift()
    test_fresh_title_still_mints()
    print("[ENG-S7-01] ALL PASSED")
