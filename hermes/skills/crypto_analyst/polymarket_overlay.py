"""
Polymarket Overlay Skill for Crypto Analyst (enhanced P2).

Robust volume-weighted polarity-adjusted probability from high-volume
crypto/macro markets. Replaces crude count-based bias.

Integrated into the intelligence report as "Polymarket Regime Bias".
Used for regime context, proposal generation, and the strategic brief.

Real data via public gamma API. Cached 15min. Fallback 0.5.
"""

import json
import re
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import requests

CACHE_PATH = Path("/tmp/polymarket_regime_cache.json")
CACHE_TTL = 15 * 60  # 15 minutes

# Enhanced fetch: high-volume first, more results, active only
POLY_URL = (
    "https://gamma-api.polymarket.com/markets"
    "?closed=false&active=true&limit=200&order=volumeNum&ascending=false"
)


DEFAULT_POLY_CONFIG = {
    "bullish_threshold": 0.05,
    "bearish_threshold": -0.25,
    "min_vol": 5000,
    "clamp_min": 0.15,
    "clamp_max": 0.85,
    "neutral_default": 0.5,
    "use_vocab_boost": False,
    "vocab_path": None,
}



def _fetch_markets() -> list:
    """Fetch high-volume markets + supplement with crypto-relevant via search for better coverage.
    Addresses stagnation when sports/politics dominate volume-sorted top-N (e.g. World Cup billions vs crypto millions).
    """
    markets = []
    try:
        resp = requests.get(POLY_URL, timeout=15)
        if resp.status_code == 200:
            markets = resp.json() or []
    except Exception as e:
        print(f"[Polymarket] high-vol fetch error: {e}")

    # Supplement with crypto-specific search to catch relevant markets buried under sports volume leaders
    # Use public-search for targeted discovery of bitcoin/crypto/fed etc. events/markets.
    try:
        import urllib.parse
        for q in ["bitcoin", "btc", "crypto", "fed rate", "recession"]:
            s = urllib.parse.quote(q)
            sresp = requests.get(f"https://gamma-api.polymarket.com/public-search?q={s}", timeout=10)
            if sresp.status_code == 200:
                data = sresp.json() or {}
                for evt in data.get("events", [])[:3]:
                    for m in evt.get("markets", [])[:5]:
                        # Dedup by id or question text
                        if not any(
                            (mm.get("id") == m.get("id") or mm.get("question") == m.get("question"))
                            for mm in markets
                        ):
                            markets.append(m)
    except Exception as e:
        print(f"[Polymarket] crypto search supplement error (non-fatal): {e}")

    return markets


def _load_cache():
    try:
        if CACHE_PATH.exists():
            with open(CACHE_PATH) as f:
                data = json.load(f)
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return data.get("bias")
    except Exception:
        pass
    return None


def _save_cache(bias: dict):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump({"ts": time.time(), "bias": bias}, f)
    except Exception:
        pass


def _get_yes_probability(m: dict) -> float:
    """Safely extract the 'Yes' / first outcome price as float."""
    try:
        prices = m.get("outcomePrices") or m.get("outcome_prices") or []
        if isinstance(prices, list) and len(prices) > 0:
            p = prices[0]
            return float(p)
        # Fallbacks
        if "yes_price" in m:
            return float(m.get("yes_price", 0.5))
        return 0.5
    except Exception:
        return 0.5

# === Sentiment polarity (word-frequency based, drawn from project sentiment lists) ===
# Bullish/Bearish here are sentiment values based on term presence + strength.
# We are NOT computing directional vectors — just whether the question framing is
# positive or negative in sentiment tone.

BULLISH_KEYWORDS = {
    "pump": 0.9, "pumping": 0.85, "rally": 0.85, "breakout": 0.8,
    "strength": 0.7, "strong": 0.7, "bullish": 0.75, "bull": 0.6, "fomo": 0.8,
    "adoption": 0.75, "institutional": 0.7, "whale": 0.6, "accumulation": 0.75,
    "buy": 0.6, "gain": 0.7, "gains": 0.75, "moon": 0.85, "mooning": 0.85,
    "rocket": 0.85, "surging": 0.8, "surge": 0.75, "recovery": 0.7,
    "positive": 0.6, "upside": 0.6, "optimistic": 0.65,
    "above": 0.65, "higher": 0.6, "win": 0.55, "beat": 0.6, "exceed": 0.6,
    "hit": 0.55, "ath": 0.7, "all-time high": 0.75, "new high": 0.7,
    "target": 0.5, "high": 0.55, "up": 0.55, "rallying": 0.8,
}

BEARISH_KEYWORDS = {
    "crash": -1.0, "dump": -0.9, "rug": -0.95, "liquidation": -0.9,
    "weakness": -0.7, "weak": -0.6, "fear": -0.8, "sell off": -0.8,
    "decline": -0.6, "falling": -0.6, "bearish": -0.7, "bear": -0.6,
    "loss": -0.6, "losing": -0.6, "collapse": -0.9,
    "below": -0.65, "lower": -0.6, "lose": -0.55, "under": -0.5, "fail": -0.6,
    "dip": -0.75, "dips": -0.7, "hike": -0.65, "hikes": -0.6, "tightening": -0.65,
    "no cut": -0.5, "no cuts": -0.5, "hawkish": -0.7, "down": -0.55, "correction": -0.7,
}

def _compute_sentiment_polarity(q_lower: str, config: dict = None) -> str:
    """Return 'bullish', 'bearish' or 'neutral' using weighted term frequency.
    Tunable via config['bullish_threshold'] and config['bearish_threshold'].
    """
    config = config or DEFAULT_POLY_CONFIG
    bull_th = config.get("bullish_threshold", 0.2)
    bear_th = config.get("bearish_threshold", -0.2)

    bull_score = sum(w for t, w in BULLISH_KEYWORDS.items() if t in q_lower)
    bear_score = sum(abs(w) for t, w in BEARISH_KEYWORDS.items() if t in q_lower)
    net = bull_score - bear_score
    if net > bull_th:
        return "bullish"
    elif net < bear_th:
        return "bearish"
    return "neutral"

def _get_sentiment_p(q_lower: str, yes_p: float, config: dict = None) -> float:
    """Map yes_p to a sentiment value (positive/risk-on framing).
    Uses tunable thresholds from config.
    """
    config = config or DEFAULT_POLY_CONFIG
    polarity = _compute_sentiment_polarity(q_lower, config)
    neutral = config.get("neutral_default", 0.5)
    if polarity == "bullish":
        return yes_p
    elif polarity == "bearish":
        return 1.0 - yes_p
    else:
        return neutral





def get_polymarket_regime_bias(config: dict = None) -> Dict[str, Any]:
    """
    Returns a richer regime signal:
    {
      "risk_on_bias": 0.62,          # volume-weighted polarity-adjusted prob (clamped 0.2-0.8)
      "source": "polymarket",
      "num_markets": 7,
      "total_vol": 12345678.9,
      "confidence": 0.78,
      "events": ["..."],
      "note": "Volume-weighted from 7 high-vol markets (total vol 12.3M)"
    }
    """
    config = {**DEFAULT_POLY_CONFIG, **(config or {})}

    cached = _load_cache()
    if cached:
        return cached

    markets = _fetch_markets()
    if not markets:
        result = {
            "risk_on_bias": 0.5,
            "source": "polymarket (fallback)",
            "num_markets": 0,
            "total_vol": 0.0,
            "confidence": 0.0,
            "events": [],
            "note": "API unavailable or no data; neutral bias"
        }
        _save_cache(result)
        return result

    # Keywords for crypto/macro relevance (expanded)
    # Core crypto + macro-economic keywords (tightened to reduce sports/politics noise)
    crypto_keywords = [
        "bitcoin", "btc", "eth", "ethereum", "sol", "solana", "crypto",
        "fed", "rate cut", "rate hike", "powell", "inflation", "cpi", "recession",
        "tariff", "tariffs", "interest rate", "fomc"
    ]

    weighted_sum = 0.0
    total_weight = 0.0
    num_markets = 0
    total_vol = 0.0
    events = []

    for m in markets:
        q = (m.get("question") or "").lower()
        # Robust keyword match (avoid substring false positives like "eth" in "Netherlands")
        def _matches_crypto_macro(text, keywords):
            t = " " + text + " "
            for k in keywords:
                if len(k) <= 3:
                    # short codes: require as whole "word" or with common separators
                    if re.search(r"[^a-z]" + re.escape(k) + r"[^a-z]", t):
                        return True
                else:
                    if k in text:
                        return True
            return False

        if not _matches_crypto_macro(q, crypto_keywords):
            continue

        vol = float(m.get("volumeNum") or m.get("volume_num") or m.get("volume", 0) or 0)
        min_vol = config.get("min_vol", 10000)
        if vol < min_vol:
            continue

        yes_p = _get_yes_probability(m)

        # Polarity adjustment using project sentiment terms (word frequency + strength)
        # sentiment_p represents positive/risk-on sentiment value (based on term presence), not a vector.
        sentiment_p = _get_sentiment_p(q, yes_p, config)

        weighted_sum += vol * sentiment_p
        total_weight += vol
        total_vol += vol
        num_markets += 1

        # Keep a few sample events
        if len(events) < 5:
            events.append(f"{m.get('question', '')[:65]}: yes={yes_p:.2f} sent_p={sentiment_p:.2f} vol={int(vol):,}")

    if total_weight <= 0 or num_markets == 0:
        bias = 0.5
        confidence = 0.0
        note = "No qualifying high-volume markets"
    else:
        score = weighted_sum / total_weight
        cmin = config.get("clamp_min", 0.2)
        cmax = config.get("clamp_max", 0.8)
        bias = max(cmin, min(cmax, score))  # tunable clamp
        # Confidence based on log of total volume (rough skin-in-game proxy)
        confidence = min(1.0, max(0.0, math.log10(total_vol + 1) / 6.0))

        note = f"Volume-weighted from {num_markets} high-vol markets (total vol {total_vol:,.0f})"

    result = {
        "risk_on_bias": round(bias, 3),
        "source": "polymarket",
        "num_markets": num_markets,
        "total_vol": round(total_vol, 1),
        "confidence": round(confidence, 3),
        "events": events[:3],
        "note": note
    }

    _save_cache(result)
    return result





def extract_polymarket_vocabulary(n_markets: int = 500, min_vol: int = 1000, crypto_only: bool = True,
                                   bull_cut: float = 0.55, bear_cut: float = 0.45) -> dict:
    """
    Extract terms that trend with bullish vs bearish crowd sentiment on Polymarket.

    Strategy (easy for LLM analysis too):
    - Pull high-volume active markets.
    - For crypto/macro relevant questions:
      - If crowd yes_p > bull_cut (default 0.55) → terms in that question trend "bullish"
      - If crowd yes_p < bear_cut (default 0.45) → terms trend "bearish"
    - Simple word frequency (3+ letter tokens).

    Tunable cutoffs make it easy to do parameter testing / sensitivity analysis.

    Returns top terms + counts. You (or an LLM) can then promote high-frequency
    strong terms into the BULLISH_KEYWORDS / BEARISH_KEYWORDS dicts with appropriate weights.

    Note: When markets are mostly around 0.5 (flat regime), output will be sparse.
    Re-run during volatile periods or lower bull_cut/bear_cut for more signal.
    """
    from collections import Counter
    import re as _re

    markets = _fetch_markets()
    if not markets:
        return {"bullish_terms": {}, "bearish_terms": {}, "total_analyzed": 0, "note": "No markets"}

    crypto_keywords = [
        "bitcoin", "btc", "eth", "ethereum", "sol", "solana", "crypto",
        "fed", "rate cut", "rate hike", "powell", "inflation", "cpi", "recession",
        "tariff", "tariffs", "interest rate", "fomc"
    ]

    def _matches(text):
        t = " " + text.lower() + " "
        for k in crypto_keywords:
            if len(k) <= 3:
                if _re.search(r"[^a-z]" + _re.escape(k) + r"[^a-z]", t): return True
            elif k in text.lower(): return True
        return False

    b_counter = Counter()
    be_counter = Counter()
    analyzed = 0

    for m in markets[:n_markets]:
        q = (m.get("question") or "").strip()
        if not q: continue
        vol = float(m.get("volumeNum") or 0)
        if vol < min_vol: continue
        if crypto_only and not _matches(q): continue

        try:
            yes_p = float((m.get("outcomePrices") or [0.5])[0])
        except:
            yes_p = 0.5

        words = _re.findall(r"[a-z]{3,}", q.lower())

        if yes_p > bull_cut:
            for w in words: b_counter[w] += 1
            analyzed += 1
        elif yes_p < bear_cut:
            for w in words: be_counter[w] += 1
            analyzed += 1

    return {
        "bullish_terms": dict(b_counter.most_common(60)),
        "bearish_terms": dict(be_counter.most_common(60)),
        "total_analyzed": analyzed,
        "note": f"Analyzed {analyzed} markets (vol>{min_vol}, cuts {bull_cut}/{bear_cut}). Tunable cutoffs for optimization runs."
    }


def get_polymarket_influence(
    data: dict = None,
    age_hours: float = 0.0,
    half_life_hours: float = 8.0,   # Proposed slower regime persistence (vs 1h for per-pair sentiment)
    vol_weight: bool = True
) -> dict:
    """Model Polymarket's position in the trade influence stack.
    
    Returns effective influence strength (0-1) after time decay + confidence.
    Polymarket is treated as a slower, higher-conviction regime signal
    (global tilt / filter) rather than high-frequency per-pair trigger.
    
    Proposed stack positioning:
    - X sentiment: fast tactical (peak 0-15min, HL ~60min)
    - Reddit: confirmatory medium (peak ~30min)
    - Polymarket: strategic regime (slower decay, high skin-in-game when vol high)
    """
    if data is None:
        data = get_polymarket_regime_bias()
    
    bias = float(data.get("risk_on_bias", 0.5))
    conf = float(data.get("confidence", 0.5))
    total_vol = float(data.get("total_vol", 0))
    num_m = int(data.get("num_markets", 0))
    
    # Base directional strength (distance from neutral * confidence)
    directional = abs(bias - 0.5) * 2 * conf
    
    # Volume boost (skin in the game)
    vol_boost = 1.0
    if vol_weight and total_vol > 0:
        vol_boost = min(1.5, 1.0 + (total_vol / 50_000_000))  # + up to 50% for very high vol
    
    strength = min(1.0, directional * vol_boost)
    
    # Time decay (much slower than social sentiment)
    if age_hours > 0:
        decay = 2 ** (-age_hours / half_life_hours)
        strength *= decay
    
    effective = max(0.0, min(1.0, strength))
    
    return {
        "effective_influence": round(effective, 4),
        "base_directional": round(directional, 4),
        "vol_boost": round(vol_boost, 3),
        "decay_factor": round(2 ** (-age_hours / half_life_hours), 4) if age_hours > 0 else 1.0,
        "bias": bias,
        "confidence": conf,
        "num_markets": num_m,
        "total_vol": total_vol,
        "half_life_hours": half_life_hours,
        "note": "Regime-level (global tilt/filter). Slower than X/Reddit social."
    }


if __name__ == "__main__":
    print(get_polymarket_regime_bias())
