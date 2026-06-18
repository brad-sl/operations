"""
Synthetic Trade Generator
Generates realistic trade history for testing the PerformanceCalculator.
Never used against live accounts or production ledgers.
"""

import random
from datetime import datetime, timedelta
from phase6.core.performance_calculator import Trade, PerformanceCalculator


def generate_synthetic_trades(num_trades: int = 60, days_back: int = 120) -> list[Trade]:
    """Generate synthetic trades for testing."""
    pairs = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]
    trades = []
    base_date = datetime.now() - timedelta(days=days_back)

    for _ in range(num_trades):
        pair = random.choice(pairs)
        timestamp = base_date + timedelta(
            days=random.randint(0, days_back),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )

        side = random.choice(["BUY", "SELL"])
        price = round(random.uniform(80, 65000), 2)
        qty = round(random.uniform(0.01, 800), 4)
        usd_value = round(price * qty, 2)

        trades.append(Trade(
            timestamp=timestamp,
            pair=pair,
            side=side,
            qty=qty,
            price=price,
            usd_value=usd_value
        ))

    return sorted(trades, key=lambda t: t.timestamp)


if __name__ == "__main__":
    print("Generating synthetic trade data (non-production)...")
    synthetic_trades = generate_synthetic_trades(num_trades=70, days_back=100)

    calc = PerformanceCalculator(synthetic_trades)
    results = calc.get_all_periods()

    print("\n=== Synthetic Performance Results ===")
    for period, data in results.items():
        print(f"{period:12} → {data}")

    print("\n✅ Test completed successfully using only synthetic data.")
