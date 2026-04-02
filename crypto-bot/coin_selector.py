"""
coin_selector.py — Coin selection + allocation methodology engine (Phase 5)

Codifies the selection criteria and allocation logic from the strategy briefing:
- Volatility (40pts): 90d average swing
- Liquidity (25pts): daily trading volume
- Thematic fit (20pts): AI/infra/memecoin/payments tier score
- Market cap presence (15pts): not too micro-cap

Allocation method: tiered risk-bucket with inverse-vol adjustment within tiers.

No external dependencies. Coin data must be provided by caller (fetched via Coinbase or CoinGecko API).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Coin metadata model ──────────────────────────────────────────────────────

@dataclass
class CoinProfile:
    symbol: str
    avg_volatility_90d: float        # 0.0–1.0+ (annualized or 90d fractional swing)
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


# ── Selection scoring ────────────────────────────────────────────────────────

def score_coin(profile: CoinProfile) -> int:
    """Return a 0–100 score. Coins >= 70 are eligible for the portfolio."""
    score = 0

    # 1. Volatility (40 pts)
    if profile.avg_volatility_90d > 0.50:
        score += 40
    elif profile.avg_volatility_90d > 0.35:
        score += 30
    elif profile.avg_volatility_90d > 0.20:
        score += 18
    else:
        score += 5

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
    # else: 0

    # 3. Thematic fit (20 pts)
    score += THEMATIC_SCORES.get(profile.thematic_tier, 0)

    # 4. Market cap presence (15 pts) — lower rank = more liquid/stable
    rank = profile.market_cap_rank
    if rank <= 20:
        score += 15
    elif rank <= 50:
        score += 12
    elif rank <= 100:
        score += 8
    elif rank <= 200:
        score += 4
    # else: 0

    return min(score, 100)


def select_coins(profiles: List[CoinProfile], min_score: int = 70) -> List[CoinProfile]:
    """Filter to coins that pass the minimum score threshold AND are Coinbase-listed."""
    eligible = [p for p in profiles if p.coinbase_listed and score_coin(p) >= min_score]
    eligible.sort(key=lambda p: score_coin(p), reverse=True)
    return eligible


# ── Allocation methodology ───────────────────────────────────────────────────

# Risk-bucket caps: ensure no tier dominates the portfolio
TIER_CAPS: Dict[str, float] = {
    "memecoin":    0.30,   # Max 30% total in memecoins
    "ai_infra":    0.25,   # Max 25% in AI/infra
    "l1_infra":    0.25,   # Max 25% in L1 infrastructure
    "payments":    0.20,   # Max 20% in payments
    "speculative": 0.10,   # Max 10% in speculative/small-cap
}

PER_COIN_MIN = 0.04   # 4% floor (avoid dust positions)
PER_COIN_MAX = 0.15   # 15% ceiling (avoid concentration)


def compute_allocations(
    selected: List[CoinProfile],
    method: str = "inverse_vol",   # "inverse_vol" | "static_tier"
) -> Dict[str, float]:
    """
    Return per-coin target weights (fractions summing to 1.0).

    method="inverse_vol":
        Within each tier, allocate inversely proportional to volatility.
        Then scale each tier's total by its cap.
        Clip each coin to [PER_COIN_MIN, PER_COIN_MAX] and renormalize.

    method="static_tier":
        Divide tier budget equally among coins in that tier.
        Apply same clip + renormalize pass.
    """
    if not selected:
        return {}

    # Group by tier
    tiers: Dict[str, List[CoinProfile]] = {}
    for c in selected:
        tiers.setdefault(c.thematic_tier, []).append(c)

    # Compute budget for each tier (proportional to cap, normalized across present tiers)
    present_caps = {t: TIER_CAPS[t] for t in tiers if t in TIER_CAPS}
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
        else:  # static_tier: equal split within tier
            per_coin = budget / len(coins)
            for c in coins:
                raw_weights[c.symbol] = per_coin

    # Clip per-coin bounds
    clipped = {sym: max(PER_COIN_MIN, min(PER_COIN_MAX, w)) for sym, w in raw_weights.items()}

    # Renormalize to exactly 1.0
    total = sum(clipped.values())
    if total <= 0:
        return {}
    normalized = {sym: round(w / total, 4) for sym, w in clipped.items()}

    return normalized


def allocations_to_usd(weights: Dict[str, float], total_capital: float) -> Dict[str, float]:
    """Convert fractional weights to USD amounts."""
    return {sym: round(w * total_capital, 2) for sym, w in weights.items()}


def format_allocation_report(
    profiles: List[CoinProfile],
    weights: Dict[str, float],
    total_capital: float,
) -> str:
    """Return a human-readable allocation report."""
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


# ── Reference dataset: original 11-coin portfolio (Grok recommendation) ─────
# These represent the original selection that was used for modeling.
# Coins NOT on Coinbase Advanced Trade are flagged coinbase_listed=False.

REFERENCE_PORTFOLIO: List[CoinProfile] = [
    CoinProfile("XRP",  0.40, 3_000_000_000, 7,  "payments",    coinbase_listed=True),
    CoinProfile("DOGE", 0.75, 1_800_000_000, 9,  "memecoin",    coinbase_listed=True),
    CoinProfile("SHIB", 0.80,   700_000_000, 15, "memecoin",    coinbase_listed=True),
    CoinProfile("NEAR", 0.55,   300_000_000, 25, "l1_infra",    coinbase_listed=True),
    CoinProfile("RNDR", 0.65,   200_000_000, 38, "ai_infra",    coinbase_listed=True),  # rebranded RENDER
    CoinProfile("TAO",  0.70,   120_000_000, 45, "ai_infra",    coinbase_listed=False),  # not on CB
    CoinProfile("GRT",  0.55,   180_000_000, 55, "ai_infra",    coinbase_listed=True),
    CoinProfile("FIL",  0.50,   250_000_000, 30, "l1_infra",    coinbase_listed=True),
    CoinProfile("WIF",  0.85,   300_000_000, 40, "memecoin",    coinbase_listed=True),
    CoinProfile("AIOZ", 0.70,    15_000_000, 120,"speculative",  coinbase_listed=False), # not on CB
    CoinProfile("SOLX", 0.90,     5_000_000, 200,"speculative",  coinbase_listed=False), # not listed
]


if __name__ == "__main__":
    print("=== COIN SELECTION SCORES ===")
    for p in REFERENCE_PORTFOLIO:
        s = score_coin(p)
        cb = "✓" if p.coinbase_listed else "✗"
        print(f"  {p.symbol:<6} score={s:>3}  coinbase={cb}  tier={p.thematic_tier}")

    print()
    selected = select_coins(REFERENCE_PORTFOLIO)
    print(f"=== SELECTED ({len(selected)} coins, Coinbase-eligible, score≥70) ===")
    for p in selected:
        print(f"  {p.symbol}")

    print()
    weights = compute_allocations(selected, method="inverse_vol")
    print("=== ALLOCATION REPORT (inverse_vol, $10K reference) ===")
    print(format_allocation_report(selected, weights, 10_000))
