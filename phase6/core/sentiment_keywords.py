import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
"""
Central loader for sentiment keyword configuration.

This is the defined interface for any tool or script that needs
keywords for X (Twitter) or Reddit sentiment fetching.

- Source of truth: config/sentiment_keywords.json
- Generated/updated by: scripts/optimize_sentiment_keywords.py
- Handles new pairs gracefully (falls back to ticker-based)
- Designed for monthly refresh + on-demand new-pair checks

Usage in other code:
    from phase6.core.sentiment_keywords import get_x_keyword, get_reddit_keywords, load_sentiment_keywords

    x_kw = get_x_keyword("XRP-USD")           # -> "XRP"
    reddit_kws = get_reddit_keywords("XRP-USD")  # -> ["XRP", "xrp"]
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.parent
KEYWORDS_FILE = BASE_DIR / "config" / "sentiment_keywords.json"
TRADING_CONFIG = BASE_DIR / "config" / "trading_config_phase6.json"


def load_sentiment_keywords() -> Dict:
    """Load the full sentiment keywords configuration."""
    if not KEYWORDS_FILE.exists():
        # Fallback to empty with sensible defaults
        return {"pairs": {}, "defaults": {"x_fallback": "ticker_upper", "reddit_fallback": ["ticker_lower"]}}

    with open(KEYWORDS_FILE) as f:
        return json.load(f)


def _get_ticker(pair: str) -> str:
    return pair.split("-")[0].upper()


def _get_ticker_lower(pair: str) -> str:
    return pair.split("-")[0].lower()


def get_x_keyword(pair: str) -> str:
    """
    Return the keyword string to use for X (Twitter) searches for this pair.
    Falls back to the upper ticker if not explicitly configured.
    """
    data = load_sentiment_keywords()
    pair_data = data.get("pairs", {}).get(pair, {})

    if "x" in pair_data:
        return pair_data["x"]

    # Fallback
    defaults = data.get("defaults", {})
    if defaults.get("x_fallback") == "ticker_upper":
        return _get_ticker(pair)
    return _get_ticker_lower(pair)


def get_reddit_keywords(pair: str) -> List[str]:
    """
    Return the list of keywords (in priority order) for Reddit searches.
    First item is the primary one used in most calls.
    Falls back to [lower ticker] if not configured.
    """
    data = load_sentiment_keywords()
    pair_data = data.get("pairs", {}).get(pair, {})

    if "reddit" in pair_data and isinstance(pair_data["reddit"], list):
        return pair_data["reddit"]

    defaults = data.get("defaults", {})
    if "reddit_fallback" in defaults:
        return defaults["reddit_fallback"]
    return [_get_ticker_lower(pair)]


def get_all_configured_pairs() -> List[str]:
    """Return pairs that have explicit keyword entries."""
    data = load_sentiment_keywords()
    return list(data.get("pairs", {}).keys())


def get_current_basket() -> List[str]:
    """Load the live trading basket from config."""
    try:
        with open(TRADING_CONFIG) as f:
            cfg = json.load(f)
        pairs = cfg.get("global_settings", {}).get("pairs") or \
                cfg.get("phase_6_specific", {}).get("opportunity_pool") or []
        return pairs
    except Exception:
        return []


def check_for_new_pairs() -> List[str]:
    """
    Compare current basket against configured keywords.
    Returns list of pairs that are in the basket but have no explicit entry.
    These should be optimized next.
    """
    basket = get_current_basket()
    configured = set(get_all_configured_pairs())
    new_pairs = [p for p in basket if p not in configured]
    return new_pairs


def get_keyword_summary() -> Dict:
    """Return a convenient summary for logging/debugging."""
    data = load_sentiment_keywords()
    return {
        "last_updated": data.get("last_updated"),
        "version": data.get("version"),
        "configured_pairs": len(data.get("pairs", {})),
        "new_pairs_needing_optimization": check_for_new_pairs()
    }


if __name__ == "__main__":
    # Quick self-test / inspection
    print("Sentiment Keywords Loader Self-Test")
    print("Basket:", get_current_basket())
    print("New pairs needing attention:", check_for_new_pairs())
    print("X for XRP-USD:", get_x_keyword("XRP-USD"))
    print("Reddit for XRP-USD:", get_reddit_keywords("XRP-USD"))
    print("X for BTC-USD:", get_x_keyword("BTC-USD"))
    print("Summary:", get_keyword_summary())