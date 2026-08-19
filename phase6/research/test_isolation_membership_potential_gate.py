#!/usr/bin/env python3
"""Isolation tests — membership heightened potential boundary."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.membership_potential_gate import (  # noqa: E402
    REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP,
    evaluate_membership_swap,
)


def test_deploy_ready_never_required() -> None:
    assert REQUIRE_DEPLOY_READY_FOR_MEMBERSHIP is False
    v = evaluate_membership_swap(
        add="ZEC-USD",
        remove="RAVE-USD",
        active=["BTC-USD", "ETH-USD", "RAVE-USD", "LINK-USD"],
        inbound_potential=0.55,
        outbound_potential=0.20,
        quote_vol_24h=5_000_000,
        ret_24h=0.04,
        mom_3d=0.03,
        mom_7d=0.05,
        held_usd_remove=0.0,
    )
    assert v.ok
    assert v.require_deploy_ready is False
    assert "deploy_ready_not_required" in v.reasons
    print("PASS deploy never required + happy path")


def test_reject_sticky_and_expand() -> None:
    v = evaluate_membership_swap(
        add="ZEC-USD",
        remove="BTC-USD",
        active=["BTC-USD", "ETH-USD"],
        inbound_potential=0.9,
        outbound_potential=0.1,
        quote_vol_24h=9e9,
        mom_3d=0.1,
    )
    assert not v.ok and v.layer_failed in ("M0", "M2")
    v2 = evaluate_membership_swap(
        add="ZEC-USD",
        remove="RAVE-USD",
        active=["BTC-USD", "RAVE-USD", "ZEC-USD"],  # already in → expand/already
        inbound_potential=0.9,
        outbound_potential=0.1,
        quote_vol_24h=9e9,
        mom_3d=0.1,
    )
    assert not v2.ok and v2.layer_failed == "M0"
    print("PASS sticky/expand reject")


def test_reject_low_delta_and_pump() -> None:
    v = evaluate_membership_swap(
        add="HYPE-USD",
        remove="ARB-USD",
        active=["BTC-USD", "ARB-USD"],
        inbound_potential=0.40,
        outbound_potential=0.39,
        quote_vol_24h=3e6,
        mom_3d=0.01,
        ret_24h=0.02,
    )
    assert not v.ok and v.layer_failed == "M3"
    v2 = evaluate_membership_swap(
        add="PUMP-USD",
        remove="ARB-USD",
        active=["BTC-USD", "ARB-USD"],
        inbound_potential=0.9,
        outbound_potential=0.1,
        quote_vol_24h=3e6,
        mom_3d=0.1,
        ret_24h=0.95,  # pump
    )
    assert not v2.ok and v2.layer_failed == "M1"
    print("PASS delta + pump")


def test_arm_scale_delta() -> None:
    """risk_adj style large scores: delta>0 enough."""
    v = evaluate_membership_swap(
        add="ZEC-USD",
        remove="RAVE-USD",
        active=["BTC-USD", "RAVE-USD", "SOL-USD"],
        inbound_potential=4.45,
        outbound_potential=0.2,
        precomputed_delta=4.0,
        quote_vol_24h=5e6,
        mom_3d=0.05,
        skip_inbound_score_floor=True,
    )
    assert v.ok, v
    print("PASS arm-scale delta")


if __name__ == "__main__":
    test_deploy_ready_never_required()
    test_reject_sticky_and_expand()
    test_reject_low_delta_and_pump()
    test_arm_scale_delta()
    print("ALL membership_potential_gate ISOLATION PASSED")
