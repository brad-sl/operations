#!/usr/bin/env python3
"""Isolation: SL floor ratchet (multi-bagger / air-pocket)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.sl_floor_ratchet import compute_ratchet_stop, apply_ratchet_to_stop_bundle


def test_xlm_style_hard_multiple():
    # 0.54 → 1.35, genesis stop ~0.52
    entry, mark = 0.54, 1.35
    prop = entry * 0.97
    dec = compute_ratchet_stop(entry=entry, mark=mark, proposed_stop=prop)
    assert dec.applied, dec
    assert dec.new_stop > prop
    assert dec.new_stop > entry  # locks open profit above entry
    # ~50% lock of run: 0.54 + 0.5*(1.35-0.54) * (1-0.005) ≈ 0.94
    assert dec.new_stop > 0.85, dec


def test_small_r_no_raise():
    entry, mark = 10.0, 10.5  # +5%
    prop = 9.7
    dec = compute_ratchet_stop(entry=entry, mark=mark, proposed_stop=prop)
    assert not dec.applied, dec
    assert abs(dec.new_stop - prop) < 1e-9


def test_never_loosen_existing():
    dec = compute_ratchet_stop(
        entry=10.0,
        mark=12.0,
        proposed_stop=9.7,
        existing_stop=11.0,
    )
    assert dec.new_stop >= 11.0 - 1e-12


def test_link_air_pocket():
    # genesis stop under fat runner
    entry, mark = 8.277, 11.76
    prop = 8.028
    dec = compute_ratchet_stop(entry=entry, mark=mark, proposed_stop=prop)
    assert dec.applied, dec
    # gap capped ~20% under mark → stop ~9.41
    assert dec.new_stop > 9.0, dec
    assert dec.new_stop < mark


def test_bundle():
    stop, limit, dec = apply_ratchet_to_stop_bundle(
        pair="XLM-USD",
        entry=0.54,
        mark=1.35,
        proposed_stop=0.5238,
        proposed_limit=0.521,
    )
    assert stop > 0.8
    assert limit < stop


def test_fresh_buy_ignores_ghost_existing():
    """LINK wound: prior bag stop must not floor a new bag."""
    from phase6.core.sl_floor_ratchet import usable_existing_stop_for_ratchet

    gated = usable_existing_stop_for_ratchet(
        existing_stop=12.228,
        entry=12.55,
        mark=12.55,
        registry_entry=12.658,
        fresh_buy=True,
        continuous_bag=False,
    )
    assert gated is None
    stop, limit, dec = apply_ratchet_to_stop_bundle(
        pair="LINK-USD",
        entry=12.55,
        mark=12.55,
        proposed_stop=12.55 * 0.97,
        proposed_limit=12.55 * 0.97 * 0.995,
        existing_stop=12.228,
        fresh_buy=True,
    )
    assert abs(stop - 12.55 * 0.97) < 1e-6, (stop, dec)


def test_existing_at_mark_ignored():
    """Ghost stop above mark must not force clamp-only ratchet on fresh attach."""
    stop, limit, dec = apply_ratchet_to_stop_bundle(
        pair="LINK-USD",
        entry=12.004,
        mark=12.004,
        proposed_stop=12.004 * 0.97,
        proposed_limit=11.5,
        existing_stop=12.228,  # prior bag, above mark
        fresh_buy=True,
    )
    assert abs(stop - 12.004 * 0.97) < 1e-4, (stop, dec.reasons)
    assert "clamped_below_mark" not in (dec.reasons or [])


def test_continuous_bag_keeps_existing():
    stop, limit, dec = apply_ratchet_to_stop_bundle(
        pair="PAXG-USD",
        entry=4055.92,
        mark=4398.0,
        proposed_stop=4055.92 * 0.97,
        proposed_limit=3900.0,
        existing_stop=3937.6,
        registry_entry=4055.92,
        fresh_buy=False,
        continuous_bag=True,
    )
    assert stop >= 3937.6 - 1e-6, (stop, dec)


def main() -> int:
    test_xlm_style_hard_multiple()
    test_small_r_no_raise()
    test_never_loosen_existing()
    test_link_air_pocket()
    test_bundle()
    test_fresh_buy_ignores_ghost_existing()
    test_existing_at_mark_ignored()
    test_continuous_bag_keeps_existing()
    print("PASS sl_floor_ratchet isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
