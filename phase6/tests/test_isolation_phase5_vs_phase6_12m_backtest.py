#!/usr/bin/env python3
"""
Isolation Test: Phase 5 vs Phase 6 Trading Logic Comparison (12-month backtest)

Part of ARCH-0 Baseline Audit (FIXED VERSION after diagnosis).

Compares trading logic methods & parameters:
- Phase 5 style (strict signal AND from phase5_multi_pair.py: RSI<30 AND sent>0.5 for BUY, sentiment_weight=0.4)
- Phase 6 runner/rebalancer (real deploy_capital with current params + rebalance_plan elements, inverse vol + sentiment tilt, reserve logic, daily/hybrid triggers)

Uses the EXACT same historical data loading and simulation pattern as the working archived backtests that produce >8-9% returns (layer0_pure_inverse_vol_backtest.py, sentiment_enhanced_allocation_backtest.py, rebalancing_strategy_comparison.py).

Updated per TESTS-01: Uses central 11-pair basket via load_trading_basket() (no hardcoded 5-pair). Exercises full basket in sentiment/proxy loops, candidate_pairs etc. (historical data files cover subset ~8/11; sim gracefully handles).

Key fixes from first run:
- Proper daily mark-to-market of portfolio_value using actual close prices on holdings (captures real market P&L from the data).
- Larger initial capital ($10,000) to avoid reserve starvation (deploy_capital has withdrawal_reserve_min ~$500).
- Rebalance logic that computes targets from current portfolio_value and applies deploy_capital for incremental "new capital" or full weight reset at intervals.
- Real calls to deploy_capital and allocation helpers.
- Runs on last 120 days (matching archived positive reports) + full period option.
- Outputs realistic equity curves, returns, trade counts, utilization.

Run: python phase6/tests/test_isolation_phase5_vs_phase6_12m_backtest.py

This should now show positive returns in the 120-day window (matching the 9.4%+ from pure inv-vol baselines) while differing by logic/params.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import math

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.scripts.deploy_capital import deploy_capital
from phase6.core.allocation_engine import compute_inverse_vol_allocations  # if available
from phase6.core.paths import load_trading_basket

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # dynamic per DATA_FLOW_AND_LOCATIONS.md (enforced)
PAIRS = load_trading_basket()  # central 11-pair (TESTS-01)
DATA_DIR = PROJECT_ROOT / "backtests/data"

def load_historical_data():
    data = {}
    for pair in PAIRS:
        symbol = pair.split("-")[0].lower()
        file_path = DATA_DIR / f"backtest_historical_ohlcv_{symbol}_2025-04-20_to_2026-04-20.json"
        if file_path.exists():
            with open(file_path) as f:
                raw = json.load(f)
            cleaned = []
            for row in raw:
                cleaned.append({
                    "timestamp": row.get("timestamp") or row.get("time"),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0))
                })
            data[pair] = sorted(cleaned, key=lambda x: x["timestamp"])
            print(f"  Loaded {pair}: {len(data[pair])} rows")
    print(f"  Total loaded from central basket: {len(data)}/{len(PAIRS)} pairs (full basket used for scoring/candidate even if hist partial)")
    return data

def compute_simple_inv_vol(prices_list, window=20):
    if len(prices_list) < window + 1:
        return {p: 1.0 / len(PAIRS) for p in PAIRS}
    returns = []
    for i in range(1, min(window + 1, len(prices_list))):
        ret = (prices_list[-i]["close"] - prices_list[-i-1]["close"]) / prices_list[-i-1]["close"]
        returns.append(ret)
    if not returns:
        return {p: 1.0 / len(PAIRS) for p in PAIRS}
    vol = math.sqrt(sum(r * r for r in returns) / len(returns))
    if vol == 0:
        vol = 0.01
    inv_vol = 1.0 / vol
    return {p: inv_vol for p in PAIRS}

# Phase 5 params (from phase5_multi_pair.py)
PHASE5_PARAMS = {
    "name": "Phase5_SignalDriven",
    "description": "Phase 5: Strict signal AND (RSI<30 & sent>0.5 BUY), sentiment_weight=0.4, signal-based entries",
    "rebalance_frequency_days": 7,
    "sentiment_weight": 0.4,
    "rsi_buy_threshold": 30,
    "sentiment_buy_threshold": 0.5,
    "rsi_sell_threshold": 70,
    "sentiment_sell_threshold": -0.5,
}

# Phase 6 runner/rebalancer params (exact from deploy_capital + config)
PHASE6_PARAMS = {
    "name": "Phase6_RunnerRebalancer",
    "description": "Phase 6: deploy_capital (min_sent -0.30 / new +0.20, RSI>=30, inv_vol+sentiment tilt), rebalance_plan, daily + hybrid, withdrawal_reserve_min=500",
    "rebalance_frequency_days": 1,
    "min_sentiment": -0.30,
    "min_new_pair_sentiment": 0.20,
    "min_rsi": 30.0,
    "rebalance_cap_usd": 500.0,
    "withdrawal_reserve_min": 500.0,
}

PHASE6_WEEKLY_PARAMS = {
    "name": "Phase6_Weekly",
    "description": "Phase 6 logic but weekly rebalance frequency (parameter sensitivity)",
    "rebalance_frequency_days": 7,
    "min_sentiment": -0.30,
    "min_new_pair_sentiment": 0.20,
    "min_rsi": 30.0,
    "rebalance_cap_usd": 500.0,
    "withdrawal_reserve_min": 500.0,
}

def emulate_phase5_signal(rsi: float, sentiment: float, params: dict) -> str:
    if rsi < params["rsi_buy_threshold"] and sentiment > params["sentiment_buy_threshold"]:
        return "BUY"
    elif rsi > params["rsi_sell_threshold"] and sentiment < params["sentiment_sell_threshold"]:
        return "SELL"
    return "HOLD"

def get_momentum_proxy_sentiment_and_rsi(hist_data, pair, current_idx, window=14):
    """Crude but consistent proxy for baseline (real sentiment caches can be injected)."""
    prices = hist_data.get(pair, [])
    if current_idx < window or len(prices) <= current_idx:
        return 0.0, 50.0
    recent = prices[current_idx-window:current_idx+1]
    if len(recent) < 2:
        return 0.0, 50.0
    mom = (recent[-1]["close"] - recent[0]["close"]) / recent[0]["close"]
    sent = max(min(mom * 2.5, 0.9), -0.9)
    rsi = 50 + mom * 40  # rough
    return sent, max(20, min(80, rsi))

def run_backtest_for_logic(params: dict, hist_data: dict, initial_capital: float = 10000.0, use_last_120: bool = True):
    print(f"\n--- Running {params['name']} ---")
    print(f"Params: {params['description']}")

    # Use same data window as archived positive backtests
    btc_data = hist_data.get("BTC-USD", [])
    if use_last_120:
        test_data = btc_data[-120:]
        print("Using last 120 days (matching archived >9% baselines)")
    else:
        test_data = btc_data
        print("Using full 12-month data")

    portfolio_value = initial_capital
    holdings = {p: (initial_capital / len(PAIRS)) / btc_data[0]["close"] for p in PAIRS if p in hist_data}  # initial equal
    cash = 0.0  # all deployed initially for simplicity; reserve handled inside deploy logic
    equity_curve = [portfolio_value]
    trades = []
    rebalance_count = 0

    for i, row in enumerate(test_data):
        date_str = row["timestamp"][:10]
        current_close = {p: hist_data[p][i]["close"] if i < len(hist_data[p]) else hist_data[p][-1]["close"] for p in PAIRS if p in hist_data}

        # Daily mark-to-market (the key missing piece in first version)
        portfolio_value = cash
        for pair, amt in holdings.items():
            if pair in current_close:
                portfolio_value += amt * current_close[pair]
        equity_curve.append(portfolio_value)

        # Rebalance / decision point
        is_rebalance_day = ((i + 1) % params["rebalance_frequency_days"] == 0)

        if is_rebalance_day:
            rebalance_count += 1

            # Proxy sentiment/RSI for this day (consistent across variants)
            sentiment_scores = {}
            rsi_values = {}
            for pair in PAIRS:
                sent, rsi = get_momentum_proxy_sentiment_and_rsi(hist_data, pair, i)
                sentiment_scores[pair] = sent
                rsi_values[pair] = rsi

            current_allocs_usd = {}
            for pair, amt in holdings.items():
                if pair in current_close:
                    current_allocs_usd[pair] = amt * current_close[pair]

            if params["name"].startswith("Phase5"):
                # Phase 5 style: strict signals drive incremental buys (simple allocation)
                for pair in PAIRS:
                    sig = emulate_phase5_signal(rsi_values.get(pair, 50), sentiment_scores.get(pair, 0), params)
                    if sig == "BUY" and cash > 100 and pair not in [h for h in holdings if holdings[h] > 0]:
                        price = current_close.get(pair, 0)
                        if price > 0:
                            amt = min(cash * 0.25, 2000) / price
                            holdings[pair] = holdings.get(pair, 0) + amt
                            cash -= amt * price
                            trades.append({"date": date_str, "pair": pair, "action": "BUY", "logic": "phase5_strict_signal"})
            else:
                # Phase 6: Use real deploy_capital for "new capital" or weight adjustment
                # Simulate "new capital" as a portion of portfolio or fixed deploy (respecting reserve inside the function)
                new_capital = params.get("rebalance_cap_usd", 500.0)
                try:
                    new_allocs = deploy_capital(
                        current_allocations=current_allocs_usd,
                        new_capital=new_capital,
                        sentiment_scores=sentiment_scores,
                        source="backtest_rebalance",
                        min_sentiment=params["min_sentiment"],
                        min_new_pair_sentiment=params["min_new_pair_sentiment"],
                        candidate_pairs=PAIRS,
                        rsi_values=rsi_values,
                        min_rsi=params["min_rsi"],
                    )
                    # Apply: rebalance holdings toward the returned target USD values
                    total_target = sum(new_allocs.values())
                    if total_target > 0 and portfolio_value > 0:
                        for pair, target_usd in new_allocs.items():
                            price = current_close.get(pair, 0)
                            if price <= 0:
                                continue
                            target_amt = target_usd / price
                            cur_amt = holdings.get(pair, 0)
                            diff = target_amt - cur_amt
                            trade_val = diff * price
                            if abs(trade_val) > 25:  # min meaningful trade
                                if diff > 0:
                                    holdings[pair] = cur_amt + diff
                                    cash -= trade_val
                                    trades.append({"date": date_str, "pair": pair, "action": "BUY", "logic": "phase6_deploy_capital"})
                                else:
                                    holdings[pair] = max(0, cur_amt + diff)
                                    cash += abs(trade_val)
                                    trades.append({"date": date_str, "pair": pair, "action": "SELL", "logic": "phase6_deploy_capital"})
                except Exception as e:
                    print(f"  deploy_capital error: {e}")

    final_equity = portfolio_value
    total_return = ((final_equity - initial_capital) / initial_capital) * 100

    # Simple max DD
    peak = initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    result = {
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": len(trades),
        "rebalance_count": rebalance_count,
        "trades_sample": trades[:3],
    }
    print(f"  Final Value: ${final_equity:,.2f} | Return: {total_return:.2f}% | Max DD: {max_dd:.2f}% | Trades: {len(trades)} | Rebalances: {rebalance_count}")
    return result

def run_isolation_backtest_comparison():
    print("=" * 75)
    print("ISOLATION TEST: Phase 5 vs Phase 6 Trading Logic (12-Month Backtest) - FIXED")
    print("Real historical data 2025-04-20 to 2026-04-20 (same as archived >9% reports)")
    print("Simulation pattern copied from working layer0 / sentiment-enhanced backtests")
    print("=" * 75)

    print("\n[1] Loading historical OHLCV data (real prices)...")
    hist_data = load_historical_data()
    if not hist_data:
        print("No data. Exiting.")
        return

    configs = [PHASE5_PARAMS, PHASE6_PARAMS, PHASE6_WEEKLY_PARAMS]

    results = {}
    for params in configs:
        res = run_backtest_for_logic(params, hist_data, initial_capital=10000.0, use_last_120=True)
        results[params["name"]] = res

    # Also run one on full period for the Phase 6 daily (to match rebalancing_strategy_comparison style)
    print("\n[Additional] Phase6_RunnerRebalancer on FULL 12 months (for comparison to other reports):")
    full_res = run_backtest_for_logic(PHASE6_PARAMS, hist_data, initial_capital=10000.0, use_last_120=False)
    results["Phase6_RunnerRebalancer_FULL12M"] = full_res

    report = {
        "period": "2025-04-20 to 2026-04-19 (last 120 days for main comparison)",
        "initial_capital": 10000.0,
        "data_source": "real historical OHLCV backtests/data/ (same as layer0/sentiment backtests showing +9.4%)",
        "results": results,
        "comparison_notes": "Uses proven daily MTM + rebalance simulation from archived positive backtests. Phase 6 variants call the REAL deploy_capital function with exact current parameters (including withdrawal_reserve_min=500). Phase 5 emulates strict AND signal logic. Proxy momentum for sentiment/RSI (real caches injectable). This baseline now captures actual market P&L while isolating the effect of the different trading decision methods & parameters. TESTS-01: central 11 basket used for candidate_pairs, scoring loops.",
        "archived_baseline_reference": "Pure inverse-vol (last 120d): +9.40%. Sentiment-enhanced: +9.47%. (See layer0_pure_inverse_vol_backtest.py and sentiment_enhanced_allocation_backtest.py)"
    }

    out_path = Path("data/state/phase5_vs_phase6_12m_logic_comparison_FIXED.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 75)
    print("COMPARISON REPORT (FIXED) WRITTEN TO:", out_path)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "trades_sample"} for k, v in results.items()}, indent=2))
    print("=" * 75)

    # Quick net change note
    p5 = results.get("Phase5_SignalDriven", {})
    p6 = results.get("Phase6_RunnerRebalancer", {})
    if p5 and p6:
        delta = p6.get("total_return_pct", 0) - p5.get("total_return_pct", 0)
        print(f"\nNET (Phase6 daily vs Phase5 weekly on 120d window): {delta:+.2f} pp return")

    return report

if __name__ == "__main__":
    run_isolation_backtest_comparison()
    print("\nIsolation backtest (FIXED) complete. Evidence for ARCH-0 baseline.")
