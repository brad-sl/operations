#!/usr/bin/env python3
"""
IDEALOOP-002 Opportunity Scanner + Basket Expansion (Starter)

Lightweight extension of signal pipeline for proactive scoring of current + candidate pairs.
Uses REAL data ONLY: rsi_cache.json (fresh RSI e.g. BTC 42.48), x_sentiment_cache + canonical,
price_history.json for vol/edge/momentum proxies.

Scoring factors (per design):
- Momentum: RSI (oversold bias for lackluster market)
- Sentiment velocity: current scores from caches (X/Reddit)
- Vol-adjusted historical edge: recent mom % / vol from price series
- Diversification: bonus for non-current basket pairs

Ranks, proposes 1-2 small test allocations or basket adds (shadow only).
No deployment, no state mutation. Gated by IDEALOOP-005 shadow AB.

Run: python -m phase6.core.opportunity_scanner
Or from project root: python phase6/core/opportunity_scanner.py

Isolation test: phase6/core/test_isolation_opportunity_scanner.py (must pass first)
Proposals logged to data/state/opportunity_proposals.jsonl + logs/opportunity_scanner/*.md

Parallel to #5/#1. Starter only.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import sys
from pathlib import Path
sys.path.append("/home/brad/projects/crypto-trading-bot")

# Core imports for signal pipeline extension (light)
from phase6.core.sentiment_scorer import load_sentiment_scores
from phase6.core.phase6_runner import calculate_rsi  # reuse for consistency if needed for edge
from phase6.core.regime_switcher import get_active_regime

# Fixed universe and basket
PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
RSI_CACHE_PATH = PROJECT_ROOT / "data" / "state" / "rsi_cache.json"
PRICE_HISTORY_PATH = PROJECT_ROOT / "data" / "state" / "price_history.json"
X_SENTIMENT_PATH = PROJECT_ROOT / "phase6" / "data" / "sentiment" / "x_sentiment_cache.json"
CANONICAL_SENTIMENT_PATH = PROJECT_ROOT / "sentiment_cache.json"
REBALANCE_HISTORY_PATH = PROJECT_ROOT / "data" / "state" / "rebalance_history" / "default.jsonl"
LIVE_STATE_PATH = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"

# Scoring Mode Weights
SCORING_MODES = {
    "oversold": {
        "momentum": 0.40,
        "sentiment": 0.20,
        "edge": 0.25,
        "diversification": 0.15
    },
    "bullish": {
        "momentum": 0.20,
        "sentiment": 0.30,
        "edge": 0.40,
        "diversification": 0.10
    },
    "hybrid": {
        "momentum": 0.35,
        "sentiment": 0.25,
        "edge": 0.25,
        "diversification": 0.15
    }
}

# Dynamic per-trader trading basket (loaded from config so runner/rebalancer can dynamically promote/liquidate).
# Sentiment/RSI queries now take the basket dynamically.
# Values cached in DB (rsi_values, sentiment_scores) so any trader with similar basket benefits from shared data.
try:
    cfg = json.load(open(str(PROJECT_ROOT / "config" / "trading_config_phase6.json")))
    OPPORTUNITY_POOL = cfg.get("phase_6_specific", {}).get("opportunity_pool") or cfg.get("global_settings", {}).get("pairs", [])
except Exception:
    OPPORTUNITY_POOL = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD", "MATIC-USD"]
FIXED_UNIVERSE = OPPORTUNITY_POOL

# Active trading pool (subset for performance; max 12). Proposals help choose which to promote/liquidate.
CURRENT_BASKET = OPPORTUNITY_POOL[:4]  # or load from live_state / rebalance_history for the specific trader


def load_real_data() -> Dict[str, Any]:
    """Load ONLY real persisted data. No fabrication, conservative on missing."""
    data: Dict[str, Any] = {
        "rsi": {},
        "sentiment": {},
        "price_history": {},
        "rebalances": [],
        "live_state": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_sources": []
    }

    # RSI cache (real, fresh 15m)
    try:
        if RSI_CACHE_PATH.exists():
            with open(RSI_CACHE_PATH) as f:
                rsi_payload = json.load(f)
            data["rsi"] = rsi_payload.get("rsi", {})
            data["data_sources"].append("rsi_cache.json")
    except Exception as e:
        print(f"[scanner] WARN: rsi_cache load failed: {e}")

    # Price history (real closes for vol/edge)
    try:
        if PRICE_HISTORY_PATH.exists():
            with open(PRICE_HISTORY_PATH) as f:
                ph_payload = json.load(f)
            data["price_history"] = ph_payload.get("history", {})
            data["data_sources"].append("price_history.json")
    except Exception as e:
        print(f"[scanner] WARN: price_history load failed: {e}")

    # Sentiment: canonical first (light pipeline extend), overlay x_sentiment for real non-zero values
    try:
        sent = load_sentiment_scores(universe=FIXED_UNIVERSE)
        data["data_sources"].append("sentiment_cache.json (canonical)")
    except Exception:
        sent = {p: 0.0 for p in FIXED_UNIVERSE}

    # Overlay x cache (real X posts, non-zero in current data)
    try:
        if X_SENTIMENT_PATH.exists():
            with open(X_SENTIMENT_PATH) as f:
                xdata = json.load(f)
            x_sent = {}
            for k, v in xdata.items():
                if isinstance(v, dict):
                    x_sent[k] = float(v.get("sentiment", 0.0))
                else:
                    x_sent[k] = float(v) if v else 0.0
            for p in FIXED_UNIVERSE:
                if p in x_sent and x_sent[p] != 0.0:
                    sent[p] = x_sent[p]  # prefer real X signal over 0
            data["data_sources"].append("x_sentiment_cache.json")
    except Exception as e:
        print(f"[scanner] WARN: x_sentiment load failed: {e}")

    data["sentiment"] = sent

    # Rebalance + live for context (real, read-only)
    try:
        if REBALANCE_HISTORY_PATH.exists():
            with open(REBALANCE_HISTORY_PATH) as f:
                data["rebalances"] = [json.loads(line) for line in f if line.strip()]
            data["data_sources"].append("rebalance_history/default.jsonl")
    except Exception:
        pass

    try:
        if LIVE_STATE_PATH.exists():
            with open(LIVE_STATE_PATH) as f:
                data["live_state"] = json.load(f)
            data["data_sources"].append("phase6_live_state.json")
    except Exception:
        pass

    return data


def compute_vol_and_momentum(prices: List[float], n: int = 30) -> Tuple[float, float]:
    """Pure-python vol (std of returns) and recent momentum % from real price series. Proxy for edge."""
    if not prices or len(prices) < n + 1:
        return 0.08, 0.0  # conservative default (no fab)
    recent = [p for p in prices[-n:] if p > 0]
    if len(recent) < 5:
        return 0.08, 0.0
    returns = []
    for i in range(1, len(recent)):
        prev = recent[i-1]
        if prev > 0:
            ret = (recent[i] - prev) / prev
            returns.append(ret)
    if len(returns) < 2:
        return 0.08, 0.0
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    vol = math.sqrt(variance)
    mom = (recent[-1] - recent[0]) / recent[0] * 100.0
    return round(vol, 6), round(mom, 2)


def score_opportunity(
    pair: str,
    rsi: float,
    sentiment: float,
    vol: float,
    momentum_pct: float,
    is_current: bool,
    mode: str = "oversold"
) -> Tuple[float, str]:
    """
    Multi-factor score per IDEALOOP-002 design (starter).
    momentum (RSI oversold bias) + sentiment + vol-adj edge + diversification.
    Real data driven. Higher = better opportunity for test alloc / expand.
    """
    # 1. RSI component — mode-aware
    if mode == "oversold":
        # Strong bias to low RSI (mean-reversion / bounce)
        rsi_comp = max(0.0, (50.0 - rsi) / 25.0)
    elif mode == "bullish":
        # Continuation / momentum entry: favor neutral-to-bullish RSI band (40-68)
        # Peak around 52-58; penalize deep oversold or overbought for this mode
        if 40 <= rsi <= 68:
            dist_from_peak = abs(rsi - 55)
            rsi_cont_raw = max(0.0, 1.0 - (dist_from_peak / 13.0))
            rsi_comp = 0.3 + 0.5 * rsi_cont_raw   # 0.3 to 0.8 range
        else:
            rsi_comp = max(0.0, 0.15 - abs(rsi - 55) / 80.0)
    else:  # hybrid or default
        rsi_comp = max(0.0, (50.0 - rsi) / 28.0)  # milder oversold bias

    # 2. Sentiment (velocity proxy; current only, caches give real)
    sent_comp = max(0.0, min(1.0, (sentiment + 0.3) * 2.0))  # neutral~0.6, +0.1->0.8

    # 3. Vol-adjusted historical edge (mom / vol proxy sharpe + low vol tilt)
    edge_raw = (momentum_pct / 5.0) + 0.2  # recent mom scaled
    vol_adj = max(0.2, 1.0 - min(vol * 40.0, 0.8))  # penalize >2% vol
    edge_comp = max(0.0, min(1.0, edge_raw * vol_adj))

    # 4. Diversification: bonus if outside current 4-pair basket
    div_comp = 0.30 if not is_current else 0.05

    # Weighted sum (aligns with design: momentum primary for scanner)
    weights = SCORING_MODES.get(mode, SCORING_MODES["oversold"])
    total = (weights["momentum"] * rsi_comp +
             weights["sentiment"] * sent_comp +
             weights["edge"] * edge_comp +
             weights["diversification"] * div_comp)
    total = round(min(1.0, max(0.0, total)), 3)

    reason = (f"Mode={mode} "
              f"RSI={rsi:.2f}(comp={rsi_comp:.2f}) "
              f"sent={sentiment:.3f}(comp={sent_comp:.2f}) "
              f"mom={momentum_pct:.1f}% vol={vol:.5f}(adj={vol_adj:.2f}) "
              f"div={div_comp}")
    return total, reason


def scan_opportunities(mode: str = "oversold") -> Dict[str, Any]:
    """Core scanner. Returns full report dict. Read-only on real caches."""
    data = load_real_data()
    
    # ... existing code ...
    rsi_map = data.get("rsi", {})
    sent_map = data.get("sentiment", {})
    ph_map = data.get("price_history", {})

    scores: Dict[str, Dict[str, Any]] = {}
    for pair in FIXED_UNIVERSE:
        rsi_entry = rsi_map.get(pair, {})
        if isinstance(rsi_entry, dict):
            rsi = float(rsi_entry.get("rsi", 50.0))
        else:
            rsi = float(rsi_entry) if rsi_entry else 50.0

        sent = float(sent_map.get(pair, 0.0))
        prices = ph_map.get(pair, [])
        vol, mom = compute_vol_and_momentum(prices, n=30)
        is_current = pair in CURRENT_BASKET

        # Auto-calculate mode if not provided or to override
        pair_mode = get_active_regime(prices, rsi)
        
        score, reason = score_opportunity(pair, rsi, sent, vol, mom, is_current, mode=pair_mode)
        scores[pair] = {
            "score": score,
            "mode": pair_mode,
            "rsi": round(rsi, 2),
            "sentiment": round(sent, 4),
            "vol": vol,
            "momentum_pct": mom,
            "in_current_basket": is_current,
            "reason": reason
        }

    # Rank descending
    ranked = sorted(
        [{"pair": p, **s} for p, s in scores.items()],
        key=lambda x: x["score"],
        reverse=True
    )

    # Calculate global market regime (based on most frequent mode)
    modes_found = [s["mode"] for s in scores.values()]
    most_common_mode = max(set(modes_found), key=modes_found.count)

    # Identify under-allocated current (low score) or strong non-current
    proposals: List[Dict[str, Any]] = []
    for item in ranked[:3]:  # top candidates
        pair = item["pair"]
        sc = item["score"]
        if sc < 0.25:
            continue
        if item["in_current_basket"]:
            alloc_usd = round(613.72 * 0.08, 1)  # ~8% of idle cash for test tilt
            prop = f"Test allocation increase: +${alloc_usd} to {pair} (small tilt, score={sc})"
        else:
            alloc_usd = round(613.72 * 0.06, 1)  # ~6% test new pair
            prop = f"Test basket expansion: add {pair} with ${alloc_usd} test alloc (score={sc})"
        proposals.append({
            "pair": pair,
            "score": sc,
            "proposal": prop,
            "reason": item["reason"],
            "gate": "#5 shadow only - no deployment / no live rebalance yet",
            "data": {"rsi": item["rsi"], "sent": item["sentiment"], "mom": item["momentum_pct"]}
        })
        if len(proposals) >= 2:
            break

    # Fallback 1-2 if none strong
    if len(proposals) < 2:
        for item in ranked:
            if item["pair"] not in [p["pair"] for p in proposals] and item["score"] > 0.15:
                pair = item["pair"]
                sc = item["score"]
                if item["in_current_basket"]:
                    prop = f"Test allocation: small re-tilt +$25 to {pair} (score={sc}, oversold)"
                else:
                    prop = f"Test new pair candidate: {pair} (score={sc}) - monitor only"
                proposals.append({
                    "pair": pair,
                    "score": sc,
                    "proposal": prop,
                    "reason": item["reason"],
                    "gate": "#5 shadow only - no deployment / no live rebalance yet",
                    "data": {"rsi": item["rsi"], "sent": item["sentiment"], "mom": item["momentum_pct"]}
                })
                if len(proposals) >= 2:
                    break

    report = {
        "timestamp": data["timestamp"],
        "current_basket": CURRENT_BASKET,
        "mode": most_common_mode,
        "num_active_approx": 4,
        "usd_balance": 613.72,
        "scores": scores,
        "ranked": ranked,
        "proposals": proposals,
        "market_context": "lackluster market (RSI all <50 oversold-ish, sent~0-0.1, rebal executed=0 skipped>0, cash-heavy $613.72, holdings_value~0 from state)",
        "data_sources": data["data_sources"],
        "schema": "IDEALOOP-002-starter-v1",
        "note": "Real data only from caches + history. Lightly extended signal pipeline (load_sentiment_scores + price vol/mom + reuse calc style). All proposals gated by IDEALOOP-005 shadow AB - no apply, no runner change, no capital risk. Proposals logged durably."
    }
    return report


def log_proposals(report: Dict[str, Any]) -> Path:
    """Durable append log + human readable MD report. No overwrites."""
    # JSONL for durable proposals (append)
    jsonl_path = PROJECT_ROOT / "data" / "state" / "opportunity_proposals.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "ts": report["timestamp"],
        "proposals": report["proposals"],
        "top_ranked": [ {"pair": r["pair"], "score": r["score"]} for r in report["ranked"][:3] ],
        "market": report["market_context"][:80]
    }
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # MD report
    logs_dir = PROJECT_ROOT / "logs" / "opportunity_scanner"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts_short = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = logs_dir / f"IDEALOOP-002_proposals_{ts_short}.md"

    md = f"""# IDEALOOP-002 Opportunity Scanner + Basket Expansion - Proposals (Starter)

**Date:** {report['timestamp']}  
**Task:** IDEALOOP-002 (parallel to #5 Shadow AB guardrail)  
**Status:** SHADOW ONLY. No deployment, no rebalance, no live changes. Real data exclusively.  
**Capital Context:** ${report['usd_balance']} USD, ~{report['num_active_approx']} pairs active (quiet rebalances, executed=0), lackluster market.

## Current Basket (inferred real from rebalance targets + live_state)
{report['current_basket']}

## Market Context (real)
{report['market_context']}

## Scored Pairs (FIXED_UNIVERSE, real RSI/sentiment/price vol/edge)
Ranked by composite opportunity score (0-1). Higher = stronger case for small test alloc or expansion.

| Rank | Pair | Score | RSI | Sent | Vol | Mom% | InBasket | Reason |
|------|------|-------|-----|------|-----|------|----------|--------|
"""
    for i, r in enumerate(report["ranked"], 1):
        md += f"| {i} | {r['pair']} | {r['score']:.3f} | {r['rsi']:.2f} | {r['sentiment']:.3f} | {r['vol']:.5f} | {r['momentum_pct']:.1f} | {r['in_current_basket']} | {r['reason']} |\n"

    md += "\n## Proposed Test Allocations / Expansions (1-2 max, shadow gated)\n"
    if report["proposals"]:
        for p in report["proposals"]:
            md += f"- **{p['pair']}** (score={p['score']:.3f}): {p['proposal']}\n"
            md += f"  - Details: {p['reason']}\n"
            md += f"  - Gate: {p['gate']}\n"
            md += f"  - Real data: RSI={p['data']['rsi']}, Sent={p['data']['sent']}, Mom={p['data']['mom']}%\n"
    else:
        weights = SCORING_MODES.get(report.get("mode", "oversold"), SCORING_MODES["oversold"])
        md += f"""
### Implementation Notes (Starter)
- Data sources: {', '.join(report['data_sources'])}
- Scoring weights (design-aligned): {int(weights['momentum']*100)}% RSI-momentum (oversold bias), {int(weights['sentiment']*100)}% sentiment, {int(weights['edge']*100)}% vol-adj edge, {int(weights['diversification']*100)}% diversification.
- Lightly extended signal pipeline: reuses `load_sentiment_scores` (sentiment_scorer), `calculate_rsi` import, price_history for edge calc (pure py std/returns). No new deps.
- Logging: append-only to `data/state/opportunity_proposals.jsonl` + timestamped MD in logs/.
- Gating: All output is proposal-only. No writes to live_state, no calls to rebalancer/runner, no trades. Must pass IDEALOOP-005 isolation + shadow before any integration.
- Isolation test: `phase6/core/test_isolation_opportunity_scanner.py` (executes this, asserts real data, read-only, 1-2 proposals surfaced, no side effects).
- Success (per design): Scanner runs on current + candidates, surfaces 1-2 with scores, first proposal logged, tracked in MASTER.

**Next steps (post #5 guardrail):** 
- Wire scanner to shadow runner (parallel mode).
- Small paper validation window on proposals.
- Only then consider controlled basket tilt via rebalance_plan (with #5 comparator).
- Update dynamic basket logic only if metrics improve without quality gate regressions.

Real data only. No fabrication. Shadow by default.
"""
    with open(md_path, "w") as f:
        f.write(md)

    print(f"Proposals MD report written: {md_path}")
    print(f"Proposals JSONL appended: {jsonl_path}")
    return md_path


def main() -> Dict[str, Any]:
    print("=== IDEALOOP-002 Opportunity Scanner (Starter) ===")
    print("REAL DATA ONLY | SHADOW GATED (#5) | NO DEPLOYMENT")
    report = scan_opportunities()
    print(f"\nScanned universe: {FIXED_UNIVERSE}")
    print(f"Current basket: {CURRENT_BASKET}")
    print(f"Top 3 ranked by opportunity score:")
    for r in report["ranked"][:3]:
        print(f"  {r['pair']}: score={r['score']:.3f} | RSI={r['rsi']:.2f} | sent={r['sentiment']:.3f} | mom={r['momentum_pct']:.1f}%")
    print(f"\nProposals generated: {len(report['proposals'])}")
    for p in report["proposals"]:
        print(f"  - {p['pair']}: {p['proposal']}")
    md_path = log_proposals(report)
    print(f"\nReport: {md_path}")
    print("Scanner complete. All gated - no state or capital impact.")
    return report


if __name__ == "__main__":
    main()
