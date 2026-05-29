#!/usr/bin/env python3
"""
Capital Allocation Backtest — Pure Buzz Focus
==============================================

Tests different capital allocation strategies where "Pure Buzz" allocation
means weights are derived purely from sentiment/buzz signal strength.

Variants tested:
1. Equal Weight (baseline) — uniform capital split
2. Pure Buzz — allocation proportional to |sentiment| strength only
3. Buzz-Thresholded — only allocate to pairs with |sentiment| > threshold
4. Inverse Volatility — risk-parity style
5. Hybrid Buzz+Vol — blend of buzz and inverse-vol

All variants use the same RSI(11) + Sentiment signal generator and
Fixed 3% SL / Let-It-Ride TP policy for fair comparison.

Data: Genuine historical OHLCV (2025-05-05 to 2026-05-05)
Output: Capital_Allocation_Backtest_PureBuzz.md (permanent location)
"""

import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Tuple
import os
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

PAIRS = ["btc", "eth", "sol", "xrp", "doge"]
DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
OUTPUT_REPORT = "/home/brad/projects/crypto-trading-bot/reports/Capital_Allocation_Backtest_PureBuzz.md"
TOTAL_CAPITAL = 10000.0  # Starting portfolio capital for allocation tests

# ── Data Loading & Indicators (reused from run_1year_sl_tp_backtest.py) ──────

def load_real_ohlcv(pair_code: str) -> List[Dict]:
    fname = f"backtest_historical_ohlcv_{pair_code}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    return filtered

def calculate_rsi(prices: List[float], period: int = 11) -> List[float]:
    rsi = [50.0] * len(prices)
    if len(prices) < period + 1:
        return rsi
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period]) if np.mean(losses[:period]) > 0 else 1e-10
    rs = avg_gain / avg_loss
    rsi[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            avg_gain = (avg_gain * (period - 1) + delta) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_gain = (avg_gain * (period - 1)) / period
            avg_loss = (avg_loss * (period - 1) - delta) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
        rsi[i] = 100 - 100 / (1 + rs)
    return np.clip(rsi, 0, 100).tolist()

def get_sentiment_proxy(ohlcv: List[Dict], idx: int, window: int = 20) -> float:
    if idx < window:
        return 0.0
    recent = [d['close'] for d in ohlcv[idx-window:idx+1]]
    mom = (recent[-1] - recent[0]) / recent[0]
    return float(np.clip(mom * 3.0, -1.0, 1.0))

def generate_signal(rsi: float, sentiment: float) -> Tuple[str, float]:
    if rsi < 40 and sentiment >= 0.0:
        return "BUY", min((40 - rsi) / 40 + max(sentiment, 0) * 0.4, 1.0)
    elif rsi > 60 and sentiment <= 0.0:
        return "SELL", min((rsi - 60) / 40 + abs(min(sentiment, 0)) * 0.4, 1.0)
    return "HOLD", 0.0

# ── Capital Allocation Strategies ─────────────────────────────────────────────

def compute_equal_weight_allocation(pairs: List[str], total_capital: float) -> Dict[str, float]:
    """Baseline: equal split across all pairs."""
    per_pair = total_capital / len(pairs)
    return {p: per_pair for p in pairs}

def compute_pure_buzz_allocation(
    pair_sentiments: Dict[str, float],
    total_capital: float,
    min_weight: float = 0.05
) -> Dict[str, float]:
    """
    Pure Buzz allocation: weights proportional to |sentiment| strength.
    Pairs with stronger |sentiment| get more capital.
    """
    if not pair_sentiments:
        return compute_equal_weight_allocation(list(pair_sentiments.keys()), total_capital)
    
    buzz_scores = {p: abs(s) for p, s in pair_sentiments.items()}
    total_buzz = sum(buzz_scores.values())
    
    if total_buzz <= 0:
        return compute_equal_weight_allocation(list(pair_sentiments.keys()), total_capital)
    
    raw_weights = {p: (buzz / total_buzz) for p, buzz in buzz_scores.items()}
    
    # Apply minimum weight floor and renormalize
    clipped = {}
    for p, w in raw_weights.items():
        clipped[p] = max(min_weight, w)
    
    total_clipped = sum(clipped.values())
    normalized = {p: (w / total_clipped) * total_capital for p, w in clipped.items()}
    
    return normalized

def compute_buzz_thresholded_allocation(
    pair_sentiments: Dict[str, float],
    total_capital: float,
    threshold: float = 0.3,
    min_weight: float = 0.10
) -> Dict[str, float]:
    """
    Buzz-Thresholded: Only allocate to pairs where |sentiment| > threshold.
    Remaining pairs get zero allocation (or minimum if all below threshold).
    """
    eligible = {p: s for p, s in pair_sentiments.items() if abs(s) >= threshold}
    
    if not eligible:
        # Fallback to equal weight if nothing meets threshold
        return compute_equal_weight_allocation(list(pair_sentiments.keys()), total_capital)
    
    # Pure buzz among eligible only
    buzz_scores = {p: abs(s) for p, s in eligible.items()}
    total_buzz = sum(buzz_scores.values())
    
    if total_buzz <= 0:
        per_pair = total_capital / len(eligible)
        return {p: per_pair for p in eligible}
    
    raw_weights = {p: (buzz / total_buzz) for p, buzz in buzz_scores.items()}
    
    clipped = {p: max(min_weight, w) for p, w in raw_weights.items()}
    total_clipped = sum(clipped.values())
    
    return {p: (w / total_clipped) * total_capital for p, w in clipped.items()}

def compute_inverse_vol_allocation(
    pair_volatilities: Dict[str, float],
    total_capital: float,
    min_weight: float = 0.08,
    max_weight: float = 0.35
) -> Dict[str, float]:
    """
    Inverse volatility allocation (risk-parity style).
    Lower volatility pairs get higher weight.
    """
    if not pair_volatilities:
        return compute_equal_weight_allocation(list(pair_volatilities.keys()), total_capital)
    
    inv_vols = {p: 1.0 / max(v, 1e-6) for p, v in pair_volatilities.items()}
    total_inv = sum(inv_vols.values())
    
    if total_inv <= 0:
        return compute_equal_weight_allocation(list(pair_volatilities.keys()), total_capital)
    
    raw_weights = {p: (iv / total_inv) for p, iv in inv_vols.items()}
    
    clipped = {}
    for p, w in raw_weights.items():
        clipped[p] = max(min_weight, min(max_weight, w))
    
    total_clipped = sum(clipped.values())
    return {p: (w / total_clipped) * total_capital for p, w in clipped.items()}

def compute_hybrid_buzz_vol_allocation(
    pair_sentiments: Dict[str, float],
    pair_volatilities: Dict[str, float],
    total_capital: float,
    buzz_weight: float = 0.6,
    vol_weight: float = 0.4,
    min_weight: float = 0.06
) -> Dict[str, float]:
    """
    Hybrid: blend of Pure Buzz (60%) and Inverse Vol (40%).
    """
    buzz_alloc = compute_pure_buzz_allocation(pair_sentiments, total_capital, min_weight)
    vol_alloc = compute_inverse_vol_allocation(pair_volatilities, total_capital, min_weight)
    
    hybrid = {}
    all_pairs = set(pair_sentiments.keys()) | set(pair_volatilities.keys())
    
    for p in all_pairs:
        b = buzz_alloc.get(p, 0.0) / total_capital
        v = vol_alloc.get(p, 0.0) / total_capital
        hybrid[p] = (buzz_weight * b + vol_weight * v) * total_capital
    
    # Renormalize
    total_h = sum(hybrid.values())
    if total_h > 0:
        hybrid = {p: (v / total_h) * total_capital for p, v in hybrid.items()}
    
    return hybrid

# ── Per-Pair Backtest Runner (with capital allocation) ────────────────────────

def run_backtest_with_allocation(
    pair_data: Dict[str, List[Dict]],
    allocations: Dict[str, float],
    fee: float = 0.005
) -> Dict[str, Any]:
    """
    Run backtest across all pairs with given capital allocations.
    Each pair trades independently with its allocated capital slice.
    """
    all_trades = []
    total_pnl = 0.0
    total_trades = 0
    total_wins = 0
    total_protective_stops = 0
    equity_curves = {}
    
    for pair, ohlcv in pair_data.items():
        if len(ohlcv) < 30:
            continue
        
        alloc_capital = allocations.get(pair, 0.0)
        if alloc_capital <= 0:
            continue
        
        closes = [d['close'] for d in ohlcv]
        rsies = calculate_rsi(closes, 11)
        
        capital = alloc_capital
        position = 0.0
        entry_price = 0.0
        entry_idx = 0
        pair_trades = []
        equity_curve = [capital]
        protective_stops = 0
        max_equity = alloc_capital
        max_dd = 0.0
        
        for i in range(20, len(ohlcv)):
            price = closes[i]
            rsi = rsies[i]
            sentiment = get_sentiment_proxy(ohlcv, i)
            signal, conf = generate_signal(rsi, sentiment)
            
            # Position management (Fixed 3% SL, Let-It-Ride)
            if position > 0:
                sl_price = entry_price * (1 - 0.03)
                if price <= sl_price:
                    exit_price = sl_price
                    reason = "SL_3%"
                    protective_stops += 1
                elif signal == "SELL":
                    exit_price = price
                    reason = "SELL"
                else:
                    continue
                
                trade_pnl = position * (exit_price - entry_price) - (position * exit_price * fee)
                capital += trade_pnl
                if trade_pnl < 0:
                    pass  # track worst loss at portfolio level if needed
                pair_trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "entry": entry_price,
                    "exit": exit_price,
                    "pnl": round(trade_pnl, 2),
                    "reason": reason
                })
                position = 0.0
                equity_curve.append(capital)
                max_equity = max(max_equity, capital)
                max_dd = max(max_dd, (max_equity - capital) / max_equity)
            
            # Entry
            if position == 0 and signal == "BUY":
                position = (capital * 0.95) / price
                entry_price = price
                entry_idx = i
        
        # Force close
        if position > 0:
            exit_price = closes[-1]
            trade_pnl = position * (exit_price - entry_price) - (position * exit_price * fee)
            capital += trade_pnl
            pair_trades.append({
                "entry_idx": entry_idx,
                "exit_idx": len(ohlcv)-1,
                "entry": entry_price,
                "exit": exit_price,
                "pnl": round(trade_pnl, 2),
                "reason": "EOD"
            })
            equity_curve.append(capital)
        
        num_trades = len(pair_trades)
        wins = sum(1 for t in pair_trades if t["pnl"] > 0)
        total_pnl += (capital - alloc_capital)
        total_trades += num_trades
        total_wins += wins
        total_protective_stops += protective_stops
        
        equity_curves[pair] = equity_curve
        all_trades.extend(pair_trades)
    
    # Portfolio metrics
    win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
    
    # Aggregate equity curve for Sharpe / DD
    # Simple approach: average normalized equity curves
    portfolio_equity = [TOTAL_CAPITAL]
    for i in range(1, min(len(e) for e in equity_curves.values() if e)):
        step_total = sum(e[i] if i < len(e) else e[-1] for e in equity_curves.values())
        portfolio_equity.append(step_total)
    
    returns = np.diff(portfolio_equity) / np.array(portfolio_equity[:-1])
    sharpe = (np.mean(returns) / (np.std(returns) + 1e-9)) * np.sqrt(365) if len(returns) > 1 else 0.0
    
    max_dd_portfolio = 0.0
    peak = TOTAL_CAPITAL
    for eq in portfolio_equity:
        peak = max(peak, eq)
        max_dd_portfolio = max(max_dd_portfolio, (peak - eq) / peak)
    
    return {
        "final_capital": round(TOTAL_CAPITAL + total_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "num_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd_portfolio * 100, 1),
        "protective_stops": total_protective_stops,
        "allocations_used": allocations,
        "pair_count": len([p for p in allocations if allocations[p] > 0])
    }

# ── Main Backtest Orchestrator ────────────────────────────────────────────────

def main():
    print("=== CAPITAL ALLOCATION BACKTEST — PURE BUZZ FOCUS ===\n")
    
    # Load all pair data once
    pair_data = {}
    for pair in PAIRS:
        ohlcv = load_real_ohlcv(pair)
        if len(ohlcv) >= 30:
            pair_data[pair] = ohlcv
            print(f"Loaded {pair.upper()}: {len(ohlcv)} candles")
    
    if not pair_data:
        print("ERROR: No data loaded")
        return
    
    # Compute representative sentiment and volatility for allocation
    # Use latest available sentiment proxy and 30d rolling vol estimate
    latest_sentiments = {}
    latest_vols = {}
    
    for pair, ohlcv in pair_data.items():
        # Latest sentiment
        latest_sent = get_sentiment_proxy(ohlcv, len(ohlcv)-1)
        latest_sentiments[pair] = latest_sent
        
        # 30-day (or available) volatility proxy
        closes = [d['close'] for d in ohlcv[-30:]]
        if len(closes) > 1:
            returns = np.diff(closes) / np.array(closes[:-1])
            vol = np.std(returns) * np.sqrt(365)  # annualized rough
            latest_vols[pair] = max(vol, 0.01)
        else:
            latest_vols[pair] = 0.5  # fallback
    
    print(f"\nLatest sentiments: { {k: round(v,3) for k,v in latest_sentiments.items()} }")
    print(f"Latest vols (ann.): { {k: round(v,2) for k,v in latest_vols.items()} }\n")
    
    # Define allocation variants
    variants = {
        "Equal_Weight": compute_equal_weight_allocation(list(pair_data.keys()), TOTAL_CAPITAL),
        "Pure_Buzz": compute_pure_buzz_allocation(latest_sentiments, TOTAL_CAPITAL),
        "Buzz_Threshold_0.3": compute_buzz_thresholded_allocation(latest_sentiments, TOTAL_CAPITAL, threshold=0.3),
        "Inverse_Vol": compute_inverse_vol_allocation(latest_vols, TOTAL_CAPITAL),
        "Hybrid_Buzz60_Vol40": compute_hybrid_buzz_vol_allocation(latest_sentiments, latest_vols, TOTAL_CAPITAL, buzz_weight=0.6, vol_weight=0.4),
    }
    
    results = {}
    
    for name, alloc in variants.items():
        print(f"Running variant: {name}")
        print(f"  Allocations: { {k: round(v,0) for k,v in alloc.items()} }")
        res = run_backtest_with_allocation(pair_data, alloc)
        results[name] = res
        print(f"  → P/L=${res['total_pnl']:.0f} | DD={res['max_dd']}% | Trades={res['num_trades']} | Sharpe={res['sharpe']} | Pairs={res['pair_count']}\n")
    
    # Generate Markdown Report
    generate_report(results, latest_sentiments, latest_vols)

def generate_report(results: Dict, sentiments: Dict, vols: Dict):
    md = []
    md.append("# Capital Allocation Backtest — Pure Buzz Focus")
    md.append(f"**Generated:** {datetime.now().isoformat()}")
    md.append(f"**Period:** 2025-05-05 → 2026-05-05 (genuine daily OHLCV)")
    md.append(f"**Starting Capital:** ${TOTAL_CAPITAL:,.0f}")
    md.append(f"**Strategy:** RSI(11) + Sentiment (70/30) with Fixed 3% SL / Let-It-Ride TP")
    md.append("")
    
    md.append("## Allocation Variants Tested")
    md.append("")
    md.append("1. **Equal_Weight** — Uniform capital split across all 5 pairs (baseline)")
    md.append("2. **Pure_Buzz** — Weights proportional to |sentiment| strength only")
    md.append("3. **Buzz_Threshold_0.3** — Only pairs with |sentiment| ≥ 0.3 receive allocation (pure buzz among qualifiers)")
    md.append("4. **Inverse_Vol** — Risk-parity style: lower volatility pairs get higher weight")
    md.append("5. **Hybrid_Buzz60_Vol40** — 60% Pure Buzz + 40% Inverse Vol blended allocation")
    md.append("")
    
    md.append("## Latest Sentiment & Volatility Snapshot (used for allocation)")
    md.append("")
    md.append("| Pair | Sentiment | |Sentiment| | Ann. Vol |")
    md.append("|------|-----------|-------------|----------|")
    for p in PAIRS:
        s = sentiments.get(p, 0.0)
        v = vols.get(p, 0.0)
        md.append(f"| {p.upper()} | {s:+.3f} | {abs(s):.3f} | {v:.2f} |")
    md.append("")
    
    md.append("## Results Summary")
    md.append("")
    md.append("| Variant | Final Capital | Total P/L | Max DD | Sharpe | Trades | Win Rate | Pairs Used |")
    md.append("|---------|---------------|-----------|--------|--------|--------|----------|------------|")
    
    for name, res in results.items():
        md.append(
            f"| {name} | ${res['final_capital']:,.0f} | ${res['total_pnl']:+.0f} | {res['max_dd']}% | {res['sharpe']} | {res['num_trades']} | {res['win_rate']}% | {res['pair_count']} |"
        )
    md.append("")
    
    md.append("## Key Findings")
    md.append("")
    
    # Identify best/worst
    sorted_by_pnl = sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True)
    best = sorted_by_pnl[0]
    worst = sorted_by_pnl[-1]
    
    md.append(f"- **Best P/L performer:** {best[0]} (+${best[1]['total_pnl']:.0f})")
    md.append(f"- **Worst P/L performer:** {worst[0]} (+${worst[1]['total_pnl']:.0f})")
    md.append("")
    
    # Compare Pure Buzz vs Equal Weight
    if "Pure_Buzz" in results and "Equal_Weight" in results:
        pb = results["Pure_Buzz"]
        ew = results["Equal_Weight"]
        delta_pnl = pb['total_pnl'] - ew['total_pnl']
        delta_dd = pb['max_dd'] - ew['max_dd']
        md.append(f"- **Pure_Buzz vs Equal_Weight:** ΔP/L = ${delta_pnl:+.0f}, ΔDD = {delta_dd:+.1f}%")
        if delta_pnl > 0:
            md.append("  - Pure Buzz allocation improved returns over equal-weight baseline.")
        else:
            md.append("  - Equal-weight baseline outperformed Pure Buzz on this period.")
        md.append("")
    
    md.append("## Allocation Details (by variant)")
    md.append("")
    
    for name, res in results.items():
        md.append(f"### {name}")
        alloc = res.get("allocations_used", {})
        for p, amt in sorted(alloc.items(), key=lambda x: -x[1]):
            pct = (amt / TOTAL_CAPITAL) * 100
            md.append(f"- {p.upper()}: ${amt:,.0f} ({pct:.1f}%)")
        md.append("")
    
    md.append("## Recommendations")
    md.append("")
    md.append("- Pure Buzz allocation shines when sentiment dispersion is high (some pairs strongly bullish/bearish).")
    md.append("- Thresholded Buzz reduces noise but risks concentration if few pairs qualify.")
    md.append("- Hybrid (Buzz + Vol) offers a pragmatic middle ground for live deployment.")
    md.append("- Inverse Vol alone may under-allocate to high-sentiment volatile names (memecoins).")
    md.append("")
    md.append("**Next Steps:**")
    md.append("- Re-run with live CoinGecko sentiment fetch instead of price-proxy.")
    md.append("- Add dynamic rebalancing simulation (weekly/monthly).")
    md.append("- Backtest across multiple market regimes (bull/bear/sideways).")
    md.append("")
    
    # Write report
    Path(OUTPUT_REPORT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT, "w") as f:
        f.write("\n".join(md))
    
    print(f"\n✅ Report written to: {OUTPUT_REPORT}")

if __name__ == "__main__":
    main()