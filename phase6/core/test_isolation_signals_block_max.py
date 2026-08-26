"""Isolation: held over-target / zero add room → block_max for Signals telegraph."""
from __future__ import annotations

from phase6.core.add_risk_sizer import (
    AddRiskFactors,
    compute_max_add_usd,
    report_open_pairs_add_room,
    load_add_room_by_pair_for_dashboard,
)


def test_compute_zero_when_over_target_and_no_profit() -> None:
    factors = AddRiskFactors(
        enabled=True,
        allow_pyramid=True,
        k_profit=0.33,
        h_add=0.02,
        H_book=0.06,
        target_pair_weight=0.22,
        min_gap_pct=0.02,
        min_move_usd=50.0,
        min_position_usd=25.0,
        stop_loss_pct=0.03,
        cash_frac=0.25,
        regime="bull",
    )
    # Large bag, underwater → profit budget 0 → max_add 0
    max_add, detail = compute_max_add_usd(
        pair="LINK-USD",
        position_usd=1068.0,
        entry_price=11.60,
        current_price=11.53,
        stop_price=11.28,
        equity_usd=2370.0,
        cash_usd=500.0,
        factors=factors,
        other_book_heat_usd=0.0,
    )
    assert max_add == 0.0
    assert detail.get("reason") in ("zero_risk_budget", "capped_to_zero")


def test_report_sets_block_max_flag() -> None:
    factors = AddRiskFactors(
        enabled=True,
        allow_pyramid=True,
        k_profit=0.33,
        h_add=0.02,
        H_book=0.06,
        target_pair_weight=0.22,
        min_gap_pct=0.02,
        min_move_usd=50.0,
        min_position_usd=25.0,
        stop_loss_pct=0.03,
        cash_frac=0.25,
        regime="bull",
    )
    positions = [
        {
            "pair": "LINK-USD",
            "value_usd": 1068.0,
            "entry_price": 11.60,
            "current_price": 11.53,
        }
    ]
    rows = report_open_pairs_add_room(
        positions=positions,
        equity_usd=2370.0,
        cash_usd=500.0,
        factors=factors,
        stops={"LINK-USD": 11.28},
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["pair"] == "LINK-USD"
    assert r.get("block_max") is True
    assert float(r.get("max_add_usd") or 0) < 50.0


def test_live_dashboard_loader_marks_link_if_held_heavy() -> None:
    """Soft check against live state when present — does not fail CI if empty."""
    d = load_add_room_by_pair_for_dashboard()
    assert "by_pair" in d
    assert "max_blocked_pairs" in d
    link = (d.get("by_pair") or {}).get("LINK-USD")
    if link and float(link.get("position_usd") or 0) >= 500:
        # Live book still heavy LINK → must telegraph block-max
        assert link.get("block_max") is True, link
        assert "LINK-USD" in (d.get("max_blocked_pairs") or [])


def main() -> int:
    test_compute_zero_when_over_target_and_no_profit()
    test_report_sets_block_max_flag()
    test_live_dashboard_loader_marks_link_if_held_heavy()
    print("signals block-max isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
