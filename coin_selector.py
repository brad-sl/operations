"""
coin_selector.py — Coin selection + allocation methodology engine (Phase 5 + Dynamic)

Codifies the selection criteria and allocation logic from the strategy briefing:
- Volatility (40pts): 90d average swing → proxy via 30d price change
- Liquidity (25pts): daily trading volume
- Thematic fit (20pts): AI/infra/memecoin/payments tier score
- Market cap presence (15pts): not too micro-cap

New: `fetch_live_profiles(top_n=50)` using CoinGecko API for live dynamic basket generation.

Allocation method: tiered risk-bucket with inverse-vol adjustment within tiers.

No external dependencies beyond requests for live fetch.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import requests
import json


# ── Coin metadata model ──────────────────────────────────────────────────────

@dataclass
class CoinProfile:
    symbol: str
    avg_volatility_90d: float        # 0.0–1.0+ (annualized or 90d fractional swing; proxy=abs(30d % change)/100)
    avg_daily_volume_usd: float      # USD
    market_cap_rank: int             # CoinGecko rank; lower = larger
    thematic_tier: str               # "memecoin" | "ai_infra" | "l1_infra" | "payments" | "speculative"
    coinbase_listed: bool = True     # Only Coinbase-listed coins are eligible Phase 5
    notes: str = ""


# ── Thematic tier scores (out of 20) ────────────────────────────────────────

THEMATIC_SCORES: Dict[str, int] = {
    "memecoin":    18,   # Highest volatility/swing, sentiment-driven
    "ai_infra":    17,   # Strong 2025–26 tailwinds, news-sensitive
    "l1_infra":    15,   # Real utility, moderate volatility
    "payments":    14,   # Regulatory catalysts (XRP), decent swing
    "speculative":  9,   # Small-cap, low liquidity, presale risk
}


# ── Coinbase-listed pairs (hardcoded common ones for Phase 6)
COINBASE_PAIRS = {
    'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA', 'LINK', 'LTC', 'BCH', 'AVAX', 
    'NEAR', 'SHIB', 'UNI', 'DOT', 'FIL', 'MATIC', 'GRT', 'RNDR'
}


def infer_tier(symbol: str, name: str) -> str:
    """Infer thematic tier from symbol/name (simple heuristic)."""
    name_lower = name.lower()
    symbol_lower = symbol.lower()
    
    memecoins = {'doge', 'shib', 'wif', 'pepe', 'bonk', 'floki'}
    if any(m in symbol_lower or m in name_lower for m in memecoins):
        return "memecoin"
    
    ai_keywords = {'ai', 'render', ' Bittensor', 'TAO', 'fetch', 'grt', 'ocean'}
    if any(k in name_lower for k in ai_keywords):
        return "ai_infra"
    
    l1_keywords = {'solana', 'sol', 'near', 'avax', 'sui', 'aptos', 'stark', 'sei'}
    if any(k in name_lower for k in l1_keywords):
        return "l1_infra"
    
    payments_keywords = {'ripple', 'xrp', 'stellar', 'xlm'}
    if any(k in name_lower for k in payments_keywords):
        return "payments"
    
    return "speculative"


def fetch_live_profiles(top_n: int = 50) -> List[CoinProfile]:
    """Fetch live top coins from CoinGecko API (free tier), filter Coinbase-listed, infer tiers."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': top_n,
        'page': 1,
        'sparkline': 'false',
        'price_change_percentage': '14d,30d'
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"❌ CoinGecko fetch failed: {e}")
        return []
    
    profiles = []
    for coin in data:
        sym = coin['symbol'].upper()
        if sym in COINBASE_PAIRS:
            # Volatility proxy: max recent % change (14d/30d) normalized to 0-1 range
            changes = [
                abs(coin.get('price_change_percentage_14d_in_currency', 0)),
                abs(coin.get('price_change_percentage_30d_in_currency', 0))
            ]
            vol_proxy = max(changes) / 100.0 if changes else 0.2  # default moderate vol
            
            profiles.append(CoinProfile(
                symbol=sym,
                avg_volatility_90d=vol_proxy,
                avg_daily_volume_usd=coin.get('total_volume', 0),
                market_cap_rank=coin['market_cap_rank'],
                thematic_tier=infer_tier(sym, coin['name']),
                coinbase_listed=True,
                notes=f"{coin['name']}"
            ))
    
    print(f"✅ Fetched {len(profiles)} Coinbase-listed profiles from top {top_n}")
    return profiles


# ── Selection scoring ────────────────────────────────────────────────────────

def score_coin(profile: CoinProfile) -> int:
    """Return a 0–100 score. Coins >= 70 are eligible for the portfolio.
    
    Note: when using live CoinGecko data (30d price change as volatility proxy),
    thresholds are adjusted: abs(30d%) > 15% = high vol, > 8% = med, > 3% = low.
    """
    score = 0

    # 1. Volatility (40 pts)
    # For live proxy: 30d% / 100 → typical range 0.05–0.60 for volatile coins
    vol = profile.avg_volatility_90d
    if vol > 0.35:      # >35% move in 30d → very high vol
        score += 40
    elif vol > 0.15:    # >15%
        score += 30
    elif vol > 0.08:    # >8%
        score += 20
    elif vol > 0.03:    # >3%
        score += 10
    else:
        score += 2

    # 2. Liquidity (25 pts)
    vol = profile.avg_daily_volume_usd
    if vol >= 500_000_000:
        score += 25
    elif vol >= 100_000_000:
        score += 20
    elif vol >= 10_000_000:
        score += 12
    elif vol >= 1_000_000:
        score += 5

    # 3. Thematic fit (20 pts)
    score += THEMATIC_SCORES.get(profile.thematic_tier, 0)

    # 4. Market cap presence (15 pts)
    rank = profile.market_cap_rank
    if rank <= 20:
        score += 15
    elif rank <= 50:
        score += 12
    elif rank <= 100:
        score += 8
    elif rank <= 200:
        score += 4

    return min(score, 100)


def select_coins(profiles: List[CoinProfile], min_score: int = 70, max_coins: int = 8) -> List[CoinProfile]:
    """Filter to coins that pass the minimum score threshold AND are Coinbase-listed."""
    eligible = [p for p in profiles if p.coinbase_listed and score_coin(p) >= min_score]
    eligible.sort(key=lambda p: score_coin(p), reverse=True)
    return eligible[:max_coins]


# ── Allocation methodology ───────────────────────────────────────────────────

TIER_CAPS: Dict[str, float] = {
    "memecoin":    0.30,
    "ai_infra":    0.25,
    "l1_infra":    0.25,
    "payments":    0.20,
    "speculative": 0.10,
}

PER_COIN_MIN = 0.04
PER_COIN_MAX = 0.15


def compute_allocations(
    selected: List[CoinProfile],
    method: str = "inverse_vol",
) -> Dict[str, float]:
    if not selected:
        return {}

    tiers: Dict[str, List[CoinProfile]] = {}
    for c in selected:
        tiers.setdefault(c.thematic_tier, []).append(c)

    present_caps = {t: TIER_CAPS.get(t, 0.10) for t in tiers}
    total_cap = sum(present_caps.values())
    tier_budgets = {t: (cap / total_cap) for t, cap in present_caps.items()}

    raw_weights: Dict[str, float] = {}

    for tier, coins in tiers.items():
        budget = tier_budgets.get(tier, 0.10)
        if method == "inverse_vol":
            inv_vols = [1.0 / max(c.avg_volatility_90d, 1e-9) for c in coins]
            total_inv = sum(inv_vols)
            for c, iv in zip(coins, inv_vols):
                raw_weights[c.symbol] = budget * (iv / total_inv)
        else:  # static_tier
            per_coin = budget / len(coins)
            for c in coins:
                raw_weights[c.symbol] = per_coin

    clipped = {sym: max(PER_COIN_MIN, min(PER_COIN_MAX, w)) for sym, w in raw_weights.items()}
    total = sum(clipped.values())
    normalized = {sym: round(w / total, 4) for sym, w in clipped.items() if total > 0}

    return normalized


def allocations_to_usd(weights: Dict[str, float], total_capital: float) -> Dict[str, float]:
    return {sym: round(w * total_capital, 2) for sym, w in weights.items()}


def format_allocation_report(
    profiles: List[CoinProfile],
    weights: Dict[str, float],
    total_capital: float,
) -> str:
    lines = [f"{'Coin':<8} {'Tier':<12} {'Score':>5} {'Vol90d':>7} {'Weight':>7} {'USD':>10}"]
    lines.append("-" * 54)
    usd = allocations_to_usd(weights, total_capital)
    for p in sorted(profiles, key=lambda x: weights.get(x.symbol, 0), reverse=True):
        sym = p.symbol
        if sym not in weights:
            continue
        lines.append(
            f"{sym:<8} {p.thematic_tier:<12} {score_coin(p):>5} "
            f"{p.avg_volatility_90d:>6.0%}  {weights[sym]:>6.1%}  {usd[sym]:>9.2f}"
        )
    lines.append("-" * 54)
    lines.append(f"{'TOTAL':<8} {'':<12} {'':>5} {'':>7} {sum(weights.values()):>6.1%}  {sum(usd.values()):>9.2f}")
    return "\n".join(lines)


# ── Reference dataset (original fixed basket fallback)
REFERENCE_PORTFOLIO: List[CoinProfile] = [
    CoinProfile("XRP",  0.40, 3_000_000_000, 7,  "payments",    coinbase_listed=True),
    CoinProfile("DOGE", 0.75, 1_800_000_000, 9,  "memecoin",    coinbase_listed=True),
    CoinProfile("SHIB", 0.80,   700_000_000, 15, "memecoin",    coinbase_listed=True),
    CoinProfile("NEAR", 0.55,   300_000_000, 25, "l1_infra",    coinbase_listed=True),
    CoinProfile("RNDR", 0.65,   200_000_000, 38, "ai_infra",    coinbase_listed=True),
    CoinProfile("GRT",  0.55,   180_000_000, 55, "ai_infra",    coinbase_listed=True),
    CoinProfile("FIL",  0.50,   250_000_000, 30, "l1_infra",    coinbase_listed=True),
    CoinProfile("WIF",  0.85,   300_000_000, 40, "memecoin",    coinbase_listed=True),
]


if __name__ == "__main__":
    print("=== LIVE DYNAMIC BASKET TEST ===")
    profiles = fetch_live_profiles(50)
    if profiles:
        selected = select_coins(profiles)
        print(f"=== SELECTED ({len(selected)} coins, score≥70) ===")
        for p in selected:
            print(f"  {p.symbol} (score={score_coin(p)}, tier={p.thematic_tier})")
        
        weights = compute_allocations(selected)
        print("\n=== ALLOCATION REPORT ($10K reference) ===")
        print(format_allocation_report(selected, weights, 10000))
    else:
        print("Fallback to reference portfolio")
        selected = select_coins(REFERENCE_PORTFOLIO)
        weights = compute_allocations(selected)
        print(format_allocation_report(selected, weights, 10000))
