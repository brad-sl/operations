import pytest
from phase6.scripts.deploy_capital import deploy_capital


def test_basic_deployment_preserves_capital():
    allocs = {"BTC-USD": 100.0, "ETH-USD": 100.0}
    sentiment = {"BTC-USD": 0.5, "ETH-USD": 0.1}

    result = deploy_capital(allocs, 50.0, sentiment, source="deposit")

    assert abs(sum(result.values()) - 250.0) < 0.1


def test_new_pairs_require_higher_sentiment():
    allocs = {"BTC-USD": 100.0}
    sentiment = {"BTC-USD": 0.3, "SOL-USD": 0.15, "AVAX-USD": 0.45}
    candidates = ["BTC-USD", "SOL-USD", "AVAX-USD"]

    result = deploy_capital(
        allocs, 80.0, sentiment,
        source="liquidation",
        candidate_pairs=candidates,
        allow_new_pairs=True,
        min_new_pair_sentiment=0.20
    )

    assert "AVAX-USD" in result          # Should be added (0.45 >= 0.20)
    assert "SOL-USD" not in result       # Should be rejected (0.15 < 0.20)


def test_reserve_only_deploys_to_positive_sentiment():
    allocs = {"BTC-USD": 100.0, "ETH-USD": 80.0}
    sentiment = {"BTC-USD": 0.4, "ETH-USD": -0.2}

    result = deploy_capital(
        allocs, 60.0, sentiment,
        source="reserve",
        min_sentiment=0.0
    )

    assert "ETH-USD" not in result or result["ETH-USD"] <= 80.0  # Should not grow
    assert "BTC-USD" in result