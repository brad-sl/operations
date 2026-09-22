#!/usr/bin/env python3
"""Isolation: P1 transition knob-map restore + scorecard preserve guard."""
from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_live_transition_deploy_after_p1():
    from phase6.core.regime_cash_policy import load_policy, resolve_regime_cash

    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={
            "regime": "transition",
            "regime_layer": "climb",
            "confidence": 1.0,
            "btc_return_pct": 11.0,
            "shadow_stance": "transition_deploy",
        },
    )
    assert snap.regime == "transition", snap.regime
    assert snap.strategy_mode == "deploy", snap.strategy_mode
    assert snap.allow_new_buys is True
    assert float(snap.rebalance_cap_usd) > 0, snap.rebalance_cap_usd
    assert snap.knob_map_scenario != "usdc_hold", snap.knob_map_scenario
    print(
        "OK live transition",
        snap.strategy_mode,
        snap.allow_new_buys,
        snap.rebalance_cap_usd,
        snap.knob_map_scenario,
    )


def test_knob_map_has_operator_protect():
    km = json.loads((ROOT / "config/regime_knob_map.json").read_text())
    tr = (km.get("regimes") or {}).get("transition") or {}
    ov = tr.get("operator_override") or {}
    assert tr.get("strategy_mode") == "deploy"
    assert float((tr.get("live_overlay") or {}).get("global_settings.rebalance_cap_usd") or 0) >= 75
    assert ov.get("protect") is True
    assert "transition" in (km.get("operator_overrides_preserved") or [])
    print("OK knob_map protect", ov.get("reason"), km.get("operator_overrides_preserved"))


def test_scorecard_apply_preserves_transition(tmp_path: Path | None = None):
    """Writer must not clobber protected transition even if scorecard says usdc_hold."""
    import phase6.research.apply_regime_knob_map_from_scorecard as app

    td = Path(tempfile.mkdtemp()) if tmp_path is None else Path(tmp_path)
    km_src = json.loads((ROOT / "config/regime_knob_map.json").read_text())
    assert (km_src.get("regimes") or {}).get("transition", {}).get("strategy_mode") == "deploy"

    fake_km = td / "regime_knob_map.json"
    fake_sc = td / "scorecard.json"
    fake_km.write_text(json.dumps(km_src, indent=2))
    # minimal scorecard that would re-park transition via "recent"
    fake_sc.write_text(
        json.dumps(
            {
                "generated_at": "2099-01-01T00:00:00+00:00",
                "regimes": [
                    {
                        "regime": "recent",
                        "winner_id": "usdc_hold",
                        "optimal_strategy_id": "usdc_hold",
                        "beats_baseline": True,
                        "date_range": {"start": "2099-01-01", "end": "2099-06-01"},
                        "usdc_optimal": {
                            "optimal_strategy_id": "usdc_hold",
                            "optimal_annualized_return_pct": 3.5,
                            "optimal_is_usdc": True,
                            "alt_beats_usdc_carry": False,
                        },
                    }
                ],
            },
            indent=2,
        )
    )

    old_km, old_sc = app.KNOB_MAP, app.SCORECARD
    try:
        app.KNOB_MAP = fake_km
        app.SCORECARD = fake_sc
        rc = app.main()
        assert rc == 0
        out = json.loads(fake_km.read_text())
        tr = (out.get("regimes") or {}).get("transition") or {}
        assert tr.get("strategy_mode") == "deploy", tr
        assert float((tr.get("live_overlay") or {}).get("global_settings.rebalance_cap_usd") or 0) >= 75
        assert "transition" in (out.get("operator_overrides_preserved") or [])
        # research crumb attached, live law intact
        assert tr.get("scorecard_research_only") or tr.get("note")
        print("OK scorecard preserve", out.get("operator_overrides_preserved"), tr.get("scenario_id"))
    finally:
        app.KNOB_MAP, app.SCORECARD = old_km, old_sc


def test_park_payload_honesty():
    from phase6.core.tryout_readiness import PairDoor, build_readiness_payload

    door = PairDoor(
        pair="ETH-USD",
        eligible=True,
        force_eligible=False,
        allowed=False,
        reasons=["regime_cash_park"],
        eng_sent=0.1,
        rsi=45.0,
        rsi_ok=True,
    )
    p = build_readiness_payload(
        doors=[door],
        floors={"live_floor_used": 0.3},
        sensor={"broken": False},
        cash_usd=200.0,
        seats_used_today=0,
        max_new_seats_per_day=4,
        tryout_cap_usd=25.0,
        eligible_tryout_pairs=["ETH-USD"],
        regime="transition",
        equity_health="unknown",
        sent_mode="x_reddit_bridge",
        next_x_refresh_pt="21:00",
        next_rebalance_pt="~21:05",
        strategy_mode="usdc_park",
        allow_new_buys=False,
        rebalance_cap_usd=0.0,
        regime_layer="climb",
        knob_map_scenario="usdc_hold",
    )
    assert p["park_blocked"] is True
    assert p["can_buy_before_next_rebalance"] is False
    assert "park" in (p["plain_english"] or "").lower()
    print("OK park honesty", p["plain_english"][:80])


def main() -> int:
    test_knob_map_has_operator_protect()
    test_live_transition_deploy_after_p1()
    test_scorecard_apply_preserves_transition()
    test_park_payload_honesty()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
