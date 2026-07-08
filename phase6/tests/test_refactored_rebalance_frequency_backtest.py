#!/usr/bin/env python3
"""
Isolation Backtest: Optimal Rebalance Frequency under Refactored ARCH-4 Logic (Post-2026-06-15)

Tests the *current* refactored trading logic:
- evaluate_universe (ARCH-1 proposals from real SignalGenerator + sentiment/RSI)
- create_allocator("rotation") / RotationStrategy (catch-the-wave with churn controls)
- TradePlan execution simulation with fees

Re-uses the exact same real historical OHLCV data (2025-04-20 to 2026-04-20) as prior Phase 4/5/6 backtests.

Varies:
- Rebalance frequency (simulated by calling the allocator only every N days)
- "Let it ride" conservative mode (high min_score_delta + min_move_usd to reduce churn, mimicking "not taking profit")

Metrics:
- Total return %
- Number of trades / actions (direct fee proxy)
- Estimated fees paid (at 0.1% per side)
- Max drawdown
- Rebalance/decision count
- Final equity

Run standalone for Code Isolation Testing:
  PYTHONPATH=. python phase6/tests/test_refactored_rebalance_frequency_backtest.py

This directly re-tests the user's Phase 4 conclusion (weekly optimal + let-it-ride) under the new allocator + evaluation stack.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import math

# Ensure we can import the refactored modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.evaluation import evaluate_universe, Proposal
from phase6.core.allocator import create_allocator, AllocatorConfig, TradePlan

# Historical data location (same as all prior positive backtests)
DATA_DIR = PROJECT_ROOT / "backtests/data"
PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

FEE_RATE = 0.001  # 0.1% per trade side (conservative; Coinbase advanced is often lower)

def load_historical_closes() -> Dict[str, List[Dict]]:
    """Load real close prices. Returns {pair: list of {'timestamp': str, 'close': float} sorted}"""
    data = {}
    for pair in PAIRS:
        symbol = pair.split("-")[0].lower()
        f = DATA_DIR / f"backtest_historical_ohlcv_{symbol}_2025-04-20_to_2026-04-20.json"
        if not f.exists():
            print(f"WARNING: Missing data for {pair} at {f}")
            continue
        with open(f) as fh:
            raw = json.load(fh)
        cleaned = []
        for row in raw:
            ts = row.get("timestamp") or row.get("time") or row.get("date")
            close = float(row.get("close", 0))
            if close > 0:
                cleaned.append({"timestamp": ts, "close": close})
        data[pair] = sorted(cleaned, key=lambda x: x["timestamp"])
        print(f"  Loaded {pair}: {len(data[pair])} days")
    return data

def compute_rsi(prices: List[float], period: int = 14) -> float:
    """Pure Python Wilder RSI (same logic as runner)."""
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def get_proxy_sentiment_and_rsi(all_data: Dict[str, List[Dict]], pair: str, idx: int, window: int = 14) -> tuple[float, float]:
    """Momentum proxy for sentiment + actual RSI (consistent with prior isolation tests)."""
    prices = [p["close"] for p in all_data.get(pair, [])]
    if idx < window or len(prices) <= idx:
        return 0.0, 50.0
    recent = prices[max(0, idx-window):idx+1]
    if len(recent) < 2:
        return 0.0, 50.0
    mom = (recent[-1] - recent[0]) / recent[0]
    sent = max(min(mom * 3.0, 0.95), -0.95)  # slightly stronger proxy
    rsi = compute_rsi(recent[-window-1:] if len(recent) > window else recent)
    return sent, rsi

def simulate_apply_plan(plan: TradePlan, holdings: Dict[str, float], cash: float, prices: Dict[str, float], fee_rate: float) -> tuple[Dict[str, float], float, List[dict], float]:
    """Apply TradePlan actions to holdings/cash. Returns updated holdings, cash, trades list, fees paid this step."""
    trades = []
    fees_paid = 0.0
    current_allocs = {p: holdings.get(p, 0) * prices.get(p, 0) for p in holdings}

    for action in plan.actions:
        pair = action["pair"]
        act = str(action.get("action", "")).upper()
        usd = float(action.get("usd", action.get("usd_amount", 0)))
        if usd <= 0 or pair not in prices:
            continue
        price = prices[pair]
        fee = usd * fee_rate
        fees_paid += fee
        net_usd = usd - fee if act == "BUY" else usd + fee  # rough

        if act == "BUY":
            amt = net_usd / price
            holdings[pair] = holdings.get(pair, 0) + amt
            cash -= usd  # pay gross, fee already deducted in net calc for simplicity
            trades.append({"pair": pair, "action": "BUY", "usd": round(usd, 2), "reason": action.get("reason", "")})
        elif act in ("SELL", "ROTATE_OUT"):
            amt = min(usd / price, holdings.get(pair, 0))
            holdings[pair] = max(0, holdings.get(pair, 0) - amt)
            cash += usd * (1 - fee_rate)  # receive net
            trades.append({"pair": pair, "action": "SELL", "usd": round(usd, 2), "reason": action.get("reason", "")})

    return holdings, cash, trades, fees_paid

def run_frequency_backtest(frequency_days: int, conservative: bool = False, initial_capital: float = 10000.0, max_days: int = 120) -> Dict[str, Any]:
    """
    Run one backtest scenario using the *current refactored* evaluate_universe + Rotation allocator.
    frequency_days: call allocator only every N days (simulates rebalance frequency).
    conservative=True: high churn controls ("let it ride").
    """
    print(f"\n=== Running freq={frequency_days}d {'(conservative/let-it-ride)' if conservative else '(default rotation)'} ===")

    hist = load_historical_closes()
    if not hist:
        return {"error": "no data"}

    # Use last N days for focused test (matches prior isolation tests)
    btc = hist.get("BTC-USD", [])
    n = min(max_days, len(btc))
    test_indices = list(range(len(btc) - n, len(btc)))

    # Allocator config
    if conservative:
        # "Let it ride" — high bar for rotation, larger minimum moves
        alloc_cfg = {"min_move_usd": 150.0, "min_score_delta": 0.30, "stop_loss_pct": 0.12}
        strategy = "rotation"
    else:
        alloc_cfg = {"min_move_usd": 50.0, "min_score_delta": 0.15, "stop_loss_pct": 0.12}
        strategy = "rotation"

    allocator = create_allocator(strategy, **alloc_cfg)

    holdings: Dict[str, float] = {}
    cash = initial_capital
    equity_curve = [initial_capital]
    all_trades: List[dict] = []
    total_fees = 0.0
    decision_count = 0
    peak = initial_capital
    max_dd = 0.0

    # Initial equal allocation
    start_idx = test_indices[0]
    start_prices = {p: hist[p][start_idx]["close"] for p in PAIRS if p in hist and start_idx < len(hist[p])}
    per_pair = initial_capital / len(PAIRS)
    for pair in PAIRS:
        if pair in start_prices and start_prices[pair] > 0:
            amt = per_pair / start_prices[pair]
            holdings[pair] = amt
            cash -= per_pair

    for rel_i, abs_idx in enumerate(test_indices):
        # Current prices
        prices = {}
        for p in PAIRS:
            if p in hist and abs_idx < len(hist[p]):
                prices[p] = hist[p][abs_idx]["close"]

        # Mark to market
        portfolio_value = cash
        for pair, amt in list(holdings.items()):
            if pair in prices:
                portfolio_value += amt * prices[pair]
        equity_curve.append(portfolio_value)

        # Drawdown
        if portfolio_value > peak:
            peak = portfolio_value
        dd = (peak - portfolio_value) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

        # Decision point?
        is_decision_day = ((rel_i + 1) % frequency_days == 0)
        if not is_decision_day:
            continue

        decision_count += 1

        # Proxy signals for this day (real data driven)
        sentiment = {}
        rsi_vals = {}
        for pair in PAIRS:
            sent, rsi = get_proxy_sentiment_and_rsi(hist, pair, abs_idx)
            sentiment[pair] = sent
            rsi_vals[pair] = rsi

        # Refactored logic call
        proposals = evaluate_universe(
            basket=PAIRS,
            sentiment=sentiment,
            rsi_values=rsi_vals,
            mode="weighted",
            include_scanner=True
        )

        current_allocs_usd = {p: holdings.get(p, 0) * prices.get(p, 0) for p in PAIRS}
        total_cap = portfolio_value

        plan: TradePlan = allocator.allocate(
            proposals=proposals,
            current_allocs=current_allocs_usd,
            cash_usd=cash,
            total_capital=total_cap
        )

        # Simulate execution
        holdings, cash, step_trades, step_fees = simulate_apply_plan(
            plan, holdings, cash, prices, FEE_RATE
        )
        all_trades.extend(step_trades)
        total_fees += step_fees

    final_equity = equity_curve[-1]
    total_return = ((final_equity - initial_capital) / initial_capital) * 100

    result = {
        "frequency_days": frequency_days,
        "conservative_let_it_ride": conservative,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": len(all_trades),
        "estimated_fees_usd": round(total_fees, 2),
        "decision_count": decision_count,
        "initial_capital": initial_capital,
        "notes": "Used current evaluate_universe + RotationStrategy allocator. Proxy sentiment/RSI from real closes. Real historical data 2025-04-2026."
    }
    print(f"  Return: {total_return:.2f}% | Trades: {len(all_trades)} | Fees est: ${total_fees:.2f} | MaxDD: {max_dd:.2f}% | Decisions: {decision_count}")
    return result

def main():
    print("=" * 80)
    print("REF ACTORED ARCH-4 REBALANCE FREQUENCY BACKTEST")
    print("Re-testing Phase 4 conclusion (weekly optimal + 'let it ride' superior)")
    print("Using live post-2026-06-15 modules: evaluate_universe + Rotation allocator")
    print("Data: real backtest_historical_ohlcv_* 2025-04-20 → 2026-04-20 (last ~120 days)")
    print("=" * 80)

    frequencies = [1, 3, 7, 14, 30]
    results = []

    for freq in frequencies:
        res = run_frequency_backtest(freq, conservative=False)
        results.append(res)

    # Conservative "let it ride" variants for key frequencies
    for freq in [7, 14, 30]:
        res = run_frequency_backtest(freq, conservative=True)
        results.append(res)

    # Summary table
    print("\n" + "=" * 80)
    print("SUMMARY TABLE (sorted by return desc)")
    print("=" * 80)
    print(f"{'Freq':>5} | {'LetRide':>7} | {'Return%':>8} | {'Trades':>6} | {'Fees$':>7} | {'MaxDD%':>7} | {'Decisions':>9}")
    print("-" * 70)

    sorted_results = sorted(results, key=lambda x: x.get("total_return_pct", -999), reverse=True)
    for r in sorted_results:
        print(f"{r['frequency_days']:>5}d | {str(r['conservative_let_it_ride']):>7} | "
              f"{r['total_return_pct']:>8.2f} | {r['total_trades']:>6} | "
              f"{r['estimated_fees_usd']:>7.2f} | {r['max_drawdown_pct']:>7.2f} | {r['decision_count']:>9}")

    # Save evidence
    evidence = {
        "test_name": "refactored_arch4_rebalance_frequency_backtest",
        "date": datetime.utcnow().isoformat(),
        "logic": "evaluate_universe + RotationStrategy allocator (post June 2026 refactor)",
        "data_period": "2025-04-20 to 2026-04-20 (real OHLCV, last 120 days focused)",
        "fee_rate": FEE_RATE,
        "results": sorted_results,
        "conclusion_candidate": "See table. Compare to Phase 4 finding (weekly + no-TP/let-it-ride was best).",
        "old_phase4_finding": "Weekly optimal to minimize fees + maximize returns. 'Not taking profit (let it ride)' far more profitable."
    }

    out_path = Path("data/state/refactored_frequency_backtest_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(evidence, f, indent=2)

    print(f"\nEvidence saved to {out_path}")
    print("Test complete. Review table for optimal frequency under new logic.")

if __name__ == "__main__":
    main()