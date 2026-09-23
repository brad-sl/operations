#!/usr/bin/env python3
"""Isolation: basket CF TG only on concrete swap decisions (not CF research)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.basket_swap_shadow_cf import serious_consider_message  # noqa: E402


def _brad(**kw):
    base = {"preferred_arm": "rel_btc_stable", "live_membership_swaps": False}
    base.update(kw)
    return base


def test_cf_modify_selector_alone_silent():
    bundle = {
        "cf": {
            "decide": {
                "status": "modify_selector",
                "plain_english": "Baseline underperforms — modify selector.",
            }
        },
        "dual_agree": {"this_run": {"agreed": False}, "new_agreements": []},
        "arms_prop": {"written": []},
    }
    with patch(
        "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
    ) as p:
        p.exists.return_value = False
        assert serious_consider_message(bundle) is None


def test_promote_candidate_alone_silent():
    bundle = {
        "cf": {"decide": {"status": "promote_candidate", "plain_english": "x"}},
        "dual_agree": {},
        "arms_prop": {"written": []},
    }
    with patch(
        "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
    ) as p:
        p.exists.return_value = False
        assert serious_consider_message(bundle) is None


def test_dual_agree_this_run_pings():
    bundle = {
        "cf": {"decide": {"status": "modify_selector", "plain_english": "noise"}},
        "dual_agree": {
            "this_run": {"agreed": True, "remove": "AAA-USD", "add": "BBB-USD"},
            "new_agreements": [],
        },
        "arms_prop": {"written": []},
    }
    with patch(
        "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
    ) as p:
        p.exists.return_value = False
        msg = serious_consider_message(bundle)
    assert msg is not None
    assert "Swap decision needed" in msg
    assert "AAA-USD" in msg and "BBB-USD" in msg
    assert "dual_agree" in msg
    # CF can annotate, but must not be the sole reason
    assert "CF context" in msg or "noise" in msg


def test_preferred_arm_membership_ok_write_pings():
    bundle = {
        "cf": {"decide": {"status": "keep_shadow"}},
        "dual_agree": {"this_run": {"agreed": False}, "new_agreements": []},
        "arms_prop": {
            "written": [
                {
                    "arm": "rel_btc_stable",
                    "remove": "OLD-USD",
                    "add": "NEW-USD",
                    "membership_potential_ok": True,
                    "add_score": 1.2,
                    "remove_held_usd": 0.0,
                    "reason": "empty seat rotate",
                }
            ]
        },
    }
    with patch(
        "phase6.core.basket_swap_shadow_cf.json.loads", return_value=_brad()
    ), patch(
        "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
    ) as p:
        p.exists.return_value = True
        p.read_text.return_value = "{}"
        msg = serious_consider_message(bundle)
    assert msg is not None
    assert "OLD-USD" in msg and "NEW-USD" in msg
    assert "rel_btc_stable" in msg


def test_preferred_arm_membership_fail_silent():
    bundle = {
        "cf": {},
        "dual_agree": {},
        "arms_prop": {
            "written": [
                {
                    "arm": "rel_btc_stable",
                    "remove": "OLD-USD",
                    "add": "TOXIC-USD",
                    "membership_potential_ok": False,
                    "membership_potential": {"ok": False},
                }
            ]
        },
    }
    with patch(
        "phase6.core.basket_swap_shadow_cf.json.loads", return_value=_brad()
    ), patch(
        "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
    ) as p:
        p.exists.return_value = True
        p.read_text.return_value = "{}"
        assert serious_consider_message(bundle) is None


if __name__ == "__main__":
    test_cf_modify_selector_alone_silent()
    test_promote_candidate_alone_silent()
    test_dual_agree_this_run_pings()
    test_preferred_arm_membership_ok_write_pings()
    test_preferred_arm_membership_fail_silent()
    print("ALL PASS isolation_basket_swap_serious_consider")
