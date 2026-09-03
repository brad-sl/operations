#!/usr/bin/env python3
"""Isolation: sensor_preflight + Polymarket outcomePrices parse (Brad 2026-09-02).

Must pass before any Polymarket influence / offline scoreboard claims.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.sensor_preflight import (  # noqa: E402
    assert_feature_range,
    assert_join_rate,
    assert_parsed_prices_not_default,
    combine_preflights,
    map_preflight_to_outcome_class,
)
from hermes.skills.crypto_analyst.polymarket_overlay import (  # noqa: E402
    _get_yes_probability,
    _parse_outcome_prices,
    _get_sentiment_p,
)


def test_parse_gamma_string_prices():
    m = {"outcomePrices": '["0.72", "0.28"]', "question": "Will Bitcoin rise?"}
    assert _parse_outcome_prices(m) == ["0.72", "0.28"]
    assert abs(_get_yes_probability(m) - 0.72) < 1e-9

    m2 = {"outcomePrices": ["0.11", "0.89"]}
    assert abs(_get_yes_probability(m2) - 0.11) < 1e-9

    # Naive Gamma pitfall: indexing a JSON *string* yields '[' not 0.72
    naive = '["0.72", "0.28"]'
    try:
        float((naive or [0.5])[0])
        raise AssertionError("naive string index should fail")
    except ValueError:
        pass
    # our helper must NOT do that
    assert _get_yes_probability({"outcomePrices": '["0.33","0.67"]'}) == 0.33


def test_assert_parsed_prices_catches_string_all_default():
    raw = ['["0.5","0.5"]', '["0.5","0.5"]', '["0.5","0.5"]', '["0.5","0.5"]', '["0.5","0.5"]']
    # Naive parse that failed: all default
    parsed_bad = [0.5] * 5
    r = assert_parsed_prices_not_default(raw, parsed_bad, default=0.5)
    assert r.ok is False
    assert r.code == "sensor_broken"
    assert r.score_allowed is False

    parsed_good = [0.12, 0.44, 0.71, 0.08, 0.55]
    r2 = assert_parsed_prices_not_default(raw, parsed_good, default=0.5)
    assert r2.ok is True
    assert r2.code == "sensor_ok"


def test_feature_range_stuck_neutral():
    r = assert_feature_range(
        [0.5] * 20,
        name="bias",
        min_n=10,
        min_unique=3,
        min_stdev=0.01,
        forbid_all_equal_to=0.5,
    )
    assert r.ok is False
    assert r.code == "sensor_degenerate"
    assert map_preflight_to_outcome_class(r.code) == "sensor_degenerate"

    r2 = assert_feature_range(
        [0.42, 0.51, 0.63, 0.48, 0.55, 0.39, 0.71, 0.44, 0.58, 0.50, 0.47, 0.66],
        name="bias",
        min_n=10,
        min_unique=3,
        min_stdev=0.01,
        forbid_all_equal_to=0.5,
    )
    assert r2.ok is True
    assert r2.score_allowed is True


def test_join_rate_thin():
    r = assert_join_rate(n_events=100, n_joined=0, min_events=10, min_join_rate=0.3, min_joined=5)
    assert r.ok is False
    assert r.code == "sensor_thin"


def test_combine_first_failure_wins():
    a = assert_feature_range([0.5] * 12, name="x", forbid_all_equal_to=0.5)
    b = assert_feature_range([0.4, 0.5, 0.6] * 5, name="y", forbid_all_equal_to=0.5)
    c = combine_preflights(a, b)
    assert c.ok is False
    assert c.code == "sensor_degenerate"


def test_rate_cut_polarity_not_always_neutral():
    # "decrease interest rates" should map as bullish framing so yes_p is used
    q = "will the fed decrease interest rates by 25 bps after the september meeting"
    sp = _get_sentiment_p(q, 0.20)
    assert sp == 0.20, sp  # bullish framing keeps yes_p
    q2 = "will bitcoin crash below 40k"
    sp2 = _get_sentiment_p(q2, 0.30)
    # bearish framing → 1 - yes
    assert abs(sp2 - 0.70) < 1e-9, sp2


def test_backtest_runner_imports_and_preflight_path():
    from phase6.research import run_polymarket_influence_backtest as m

    assert hasattr(m, "run")
    out = m.run()
    assert out.get("schema") == "polymarket_influence_backtest_v1"
    assert out.get("live_promote_allowed") is False
    assert "preflight" in out
    # Historical log is stuck → must NOT claim edge scoreboard promote path
    oc = out.get("outcome_class")
    assert oc in {
        "sensor_degenerate",
        "sensor_thin",
        "sensor_broken",
        "method_invalid",
        "inconclusive_sparse_N",
        "inconclusive_no_bias_variance",  # legacy alias if any
        "unstable_or_no_edge",
        "ATTENTION_ONLY",
    }, oc
    # Stuck historical bias must not pass as HIT
    assert oc not in {"HIT_CRITERIA", "promote_primary", "promote_blend"}
    pf = out.get("preflight") or {}
    assert pf.get("schema") == "sensor_preflight_v1" or "code" in pf
    print("backtest outcome:", oc, "|", (out.get("plain_english") or "")[:160])


if __name__ == "__main__":
    test_parse_gamma_string_prices()
    print("PASS parse")
    test_assert_parsed_prices_catches_string_all_default()
    print("PASS assert_parsed")
    test_feature_range_stuck_neutral()
    print("PASS feature_range")
    test_join_rate_thin()
    print("PASS join")
    test_combine_first_failure_wins()
    print("PASS combine")
    test_rate_cut_polarity_not_always_neutral()
    print("PASS polarity")
    test_backtest_runner_imports_and_preflight_path()
    print("PASS backtest_runner")
    print("ALL sensor_preflight + polymarket isolation PASSED")
