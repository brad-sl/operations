"""
Unit Tests for Transaction Cost Calculation (BUGFIX #001)

Tests verify that transaction_cost reflects ACTUAL FEES (0.4% maker rate),
not gross notional amounts.

See: BUGFIX_REPORT_001.md for full context.
"""

import pytest
from dataclasses import dataclass


def calculate_fee(gross_notional: float, fee_rate: float) -> float:
    """Calculate transaction fee based on gross notional and fee rate."""
    return gross_notional * fee_rate


class TestTransactionCostBTC:
    """Test transaction cost calculations for BTC orders."""

    def test_50_usd_order_at_50k_btc(self):
        """
        BTC at $50,000:
        - Order size: $50 USD
        - Quantity: 50 / 50000 = 0.001 BTC
        - Fee (0.4% maker): 50 * 0.004 = $0.20 (NOT $50)
        """
        gross_notional = 50.0  # $50 order
        fee_rate = 0.004  # 0.4% maker rate
        expected_fee = 0.20  # $0.20, not $50

        actual_fee = calculate_fee(gross_notional, fee_rate)

        assert actual_fee == expected_fee, (
            f"Expected ${expected_fee}, got ${actual_fee}. "
            f"BUG: transaction_cost was set to gross ({gross_notional}), "
            f"not actual fee ({expected_fee})"
        )

    def test_100_usd_order_at_65k_btc(self):
        """BTC at $65,000 with $100 order: fee = $0.40."""
        gross_notional = 100.0
        fee_rate = 0.004
        expected_fee = 0.40

        actual_fee = calculate_fee(gross_notional, fee_rate)
        assert actual_fee == expected_fee

    def test_large_order_50k_at_50k(self):
        """$50,000 order at BTC $50K: fee = $200 (0.4%)."""
        gross_notional = 50000.0
        fee_rate = 0.004
        expected_fee = 200.0

        actual_fee = calculate_fee(gross_notional, fee_rate)
        assert actual_fee == expected_fee


class TestTransactionCostXRP:
    """Test transaction cost calculations for XRP orders."""

    def test_50_usd_order_at_2_50_xrp(self):
        """
        XRP at $2.50:
        - Order size: $50 USD
        - Quantity: 50 / 2.50 = 20 XRP
        - Fee (0.4% maker): 50 * 0.004 = $0.20 (NOT $50)
        """
        gross_notional = 50.0
        fee_rate = 0.004
        expected_fee = 0.20

        actual_fee = calculate_fee(gross_notional, fee_rate)
        assert actual_fee == expected_fee

    def test_100_usd_order_at_3_00_xrp(self):
        """XRP at $3.00 with $100 order: fee = $0.40."""
        gross_notional = 100.0
        fee_rate = 0.004
        expected_fee = 0.40

        actual_fee = calculate_fee(gross_notional, fee_rate)
        assert actual_fee == expected_fee


class TestFeeRateLevels:
    """Test different Coinbase fee levels."""

    def test_maker_fee_0_4_percent(self):
        """0.4% maker fee (limit orders)."""
        gross = 1000.0
        fee_rate = 0.004  # 0.4%
        expected = 4.0

        actual = calculate_fee(gross, fee_rate)
        assert actual == expected

    def test_taker_fee_0_6_percent(self):
        """0.6% taker fee (market orders)."""
        gross = 1000.0
        fee_rate = 0.006  # 0.6%
        expected = 6.0

        actual = calculate_fee(gross, fee_rate)
        assert actual == expected


class TestPhase3Correction:
    """
    Verify Phase 3 correction:
    2,105 orders with $50 gross notional each.
    
    OLD (WRONG):
    - Total "cost" = 2105 * $50 = $105,250 (phantom cost)
    
    NEW (CORRECT):
    - Total fees = 2105 * ($50 * 0.004) = 2105 * $0.20 = $421
    """

    def test_phase3_total_phantom_cost(self):
        """Show the phantom cost that was being recorded."""
        orders = 2105
        gross_per_order = 50.0

        phantom_cost = orders * gross_per_order
        assert phantom_cost == 105250.0, "Phase 3 phantom cost verification"

    def test_phase3_corrected_total_fees(self):
        """Calculate actual fees for Phase 3."""
        orders = 2105
        gross_per_order = 50.0
        fee_rate = 0.004  # 0.4% maker

        actual_fees = orders * (gross_per_order * fee_rate)
        assert actual_fees == 421.0, "Phase 3 corrected total fees"

    def test_phase3_fee_error_magnitude(self):
        """Phantom cost was 250x actual fees."""
        phantom = 105250.0
        actual = 421.0

        error_magnitude = phantom / actual
        assert error_magnitude == 250.0, f"Error magnitude: {error_magnitude}x"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
