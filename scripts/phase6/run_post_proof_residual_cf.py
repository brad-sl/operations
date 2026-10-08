
# scripts/phase6/run_post_proof_residual_cf.py
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# --- Config and Paths ---
LEDGER_PATH = Path('trades/phase6_trades.jsonl')
PPD_STATE_PATH = Path('data/state/post_proof_dwell.json')
TRADING_CONFIG_PATH = Path('config/trading_config_phase6.json')
REGIME_CASH_POLICY_PATH = Path('config/regime_cash_policy.json')
TSU_CONFIG_PATH = Path('config/tryout_scale_up_shadow.json') # For kindling bars

REPORT_DIR = Path('reports')
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILENAME = REPORT_DIR / f'POST_PROOF_RESIDUAL_GROWTH_CF_{datetime.now(timezone.utc).strftime("%Y-%m-%d")}.md'

# --- Load Configs and States ---
def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"Error loading {path}: {e}")
            return {}
    return {}

TRADING_CONFIG = load_json(TRADING_CONFIG_PATH)
REGIME_CASH_POLICY = load_json(REGIME_CASH_POLICY_PATH)
PPD_STATE = load_json(PPD_STATE_PATH)
TSU_CONFIG = load_json(TSU_CONFIG_PATH)

ADD_RISK_SIZER_ENABLED = TRADING_CONFIG.get('risk_management', {}).get('add_risk_sizer_enabled', False)
ADD_RISK_CONFIG = REGIME_CASH_POLICY.get('add_risk', {})
TSU_LIVE_SIGNAL_PROFILE = TSU_CONFIG.get('profiles', {}).get('live_signal', {})

# --- Helper Functions ---
def get_regime_for_ts(timestamp):
    # This is a simplification. In real life, you'd need a regime history.
    # For backtesting, we'll assume a 'flat' regime for add_risk calculations
    # unless actual regime data is integrated.
    return 'flat' # Placeholder

def calculate_add_risk_size(current_position_usd, pair, regime='flat'):
    # Simplified add_risk_sizer logic for backtesting
    # This needs to align with the actual add_risk_sizer.py logic
    # Assume 1000 equity for this simulation to get a notion of add size
    EQUITY = 1000 # Placeholder for simulation
    
    regime_cfg = ADD_RISK_CONFIG.get('by_regime', {}).get(regime, {})
    if not regime_cfg.get('allow_pyramid', False):
        return 0 # No add risk allowed in this regime

    target_pair_weight = regime_cfg.get('target_pair_weight', 0)
    h_add = regime_cfg.get('h_add', 0)
    
    # Very simplified: target up to a certain % of equity based on regime
    # and a fixed dollar amount for demonstration
    max_add_usd = EQUITY * target_pair_weight - current_position_usd
    max_add_usd = min(max_add_usd, 50) # Cap each add for simplicity
    
    return max(0, max_add_usd)

def is_kindling_eligible(trade_entry, current_mark_price, kindling_config):
    # Simplified kindling eligibility based on TSU_LIVE_SIGNAL_PROFILE
    # This requires actual OHLCV and phase data which we don't have in ledger
    # Will make assumptions or use mocked data for demo
    
    # Placeholder: assume any tryout that ran for > 2h and is still green or flat is eligible
    # This is a HUGE simplification. Actual logic needs phase, structure, R-band.
    
    hold_hours = (datetime.now(timezone.utc) - trade_entry['timestamp_dt']).total_seconds() / 3600 # Assume current time is end of backtest period
    unrealized_r = (current_mark_price / trade_entry['entry_price']) - 1
    
    min_hold_hours = kindling_config.get('min_hold_hours', 2.0)
    min_unrealized_r = kindling_config.get('min_unrealized_r', 0.008)
    max_unrealized_r = kindling_config.get('max_unrealized_r', 0.035)

    if hold_hours >= min_hold_hours and min_unrealized_r <= unrealized_r <= max_unrealized_r:
        return True
    return False

def get_graduated_pairs():
    graduated = {}
    for pair, data in PPD_STATE.get('pairs', {}).items():
        if data.get('status') == 'graduated_hold':
            graduated[pair] = data
    return graduated

# --- Main Simulation Logic ---
def run_simulation(tp_sell_frac=None, simulate_kindling=False):
    results = defaultdict(lambda: {'baseline': [], 'partial_trail': [], 'kindling_first': []})
    
    trades = []
    with open(LEDGER_PATH, 'r') as f:
        for line in f:
            try:
                trade = json.loads(line)
                trade['timestamp_dt'] = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                trades.append(trade)
            except json.JSONDecodeError:
                continue

    # Sort trades by timestamp to process chronologically
    trades.sort(key=lambda x: x['timestamp_dt'])

    graduated_pairs = get_graduated_pairs()
    
    for i, trade in enumerate(trades):
        if trade.get('side') == 'SELL' and trade.get('exit_class') == 'CLOSED_TP_TRAIL':
            pair = trade['pair']
            entry_price = trade['entry_price']
            exit_price = trade['exit_price']
            qty = trade['qty']
            pnl_usd_baseline = trade['pnl_usd']
            pnl_pct_baseline = trade['pnl_pct']
            
            # --- Baseline (Current Full Shell Exit) ---
            results[pair]['baseline'].append({
                'trade_id': trade['order_id'],
                'type': 'full_exit_tp',
                'pnl_usd': pnl_usd_baseline,
                'pnl_pct': pnl_pct_baseline,
                'qty_sold': qty,
                'qty_retained': 0,
                'final_pnl_usd': pnl_usd_baseline,
                'note': 'Current behavior'
            })

            # --- Scenario 1: Partial Trail TP ---
            if tp_sell_frac is not None:
                qty_sold_partial = qty * tp_sell_frac
                qty_retained_partial = qty * (1 - tp_sell_frac)
                pnl_usd_partial_sell = (exit_price - entry_price) * qty_sold_partial
                
                # Simulate subsequent add_risk on residual
                # For simplicity, assume we add once and sell at end of period or fixed PnL target
                # This requires market data (OHLCV) and add_risk_sizer logic
                # MOCKED: Assume residual gains an additional 5% or gets a $25 add and sells at 0%
                residual_pnl_usd = 0 # Assume it breaks even if not actively managed for this demo
                
                if ADD_RISK_SIZER_ENABLED and qty_retained_partial > 0:
                    current_position_usd = qty_retained_partial * exit_price
                    # Need market price for add_risk_size calc which we don't have historically here
                    # For demo, assume we can add a fixed $25 value once
                    add_amount_usd = 25 # Fixed add for demo purposes
                    if add_amount_usd > 0:
                        # Assume it trades flat after add for this simple demo
                        residual_pnl_usd += add_amount_usd * 0 # No additional PnL after add

                final_pnl_usd_partial_trail = pnl_usd_partial_sell + residual_pnl_usd

                results[pair]['partial_trail'].append({
                    'trade_id': trade['order_id'],
                    'type': f'partial_trail_tp ({tp_sell_frac*100:.0f}% sold)',
                    'pnl_usd_initial_sell': pnl_usd_partial_sell,
                    'qty_sold': qty_sold_partial,
                    'qty_retained': qty_retained_partial,
                    'pnl_usd_residual': residual_pnl_usd,
                    'final_pnl_usd': final_pnl_usd_partial_trail,
                    'note': 'Simulated partial sale + add_risk (mocked residual PnL)'
                })

            # --- Scenario 2: Kindling First (Pre-TP) ---
            if simulate_kindling:
                # Find the corresponding BUY trade for this SELL
                buy_trade = next((t for t in trades if t.get('side') == 'BUY' and t.get('order_id') == trade.get('buy_order_id', '')), None)
                
                if buy_trade: # and pair not in graduated_pairs: # Kindling only on non-graduated or prior to graduation
                    # MOCKED: Check eligibility based on simple metrics (hold_hours, unrealized_r)
                    # Need to know the price when kindling would have occurred (e.g. at 2-hour mark)
                    # For simplicity, assume kindling would have added $25 if eligible at buy_trade time
                    kindling_add_usd = 0
                    kindling_qty_added = 0
                    kindling_add_price = 0 # Placeholder

                    # Assume kindling only happens once on a tryout
                    # If this shell proves eligible for kindling
                    mock_current_mark_price = (entry_price + exit_price) / 2 # Mid-point for kindling check
                    if is_kindling_eligible(buy_trade, mock_current_mark_price, TSU_LIVE_SIGNAL_PROFILE):
                        kindling_add_usd = 25 # Assuming a fixed $25 step
                        kindling_add_price = mock_current_mark_price # Price at kindling time
                        kindling_qty_added = kindling_add_usd / kindling_add_price
                        
                    total_qty_kindled = qty + kindling_qty_added
                    
                    # PnL with kindling: initial qty PnL + kindling qty PnL
                    # Assuming all sells at exit_price
                    pnl_usd_kindling = (exit_price - entry_price) * qty + \
                                       (exit_price - kindling_add_price) * kindling_qty_added
                    
                    results[pair]['kindling_first'].append({
                        'trade_id': trade['order_id'],
                        'type': 'kindling_first_tp',
                        'kindling_add_usd': kindling_add_usd,
                        'total_qty': total_qty_kindled,
                        'final_pnl_usd': pnl_usd_kindling,
                        'note': 'Simulated kindling step before TP (mocked eligibility)'
                    })
                else:
                    results[pair]['kindling_first'].append({
                        'trade_id': trade['order_id'],
                        'type': 'kindling_first_tp',
                        'note': 'No corresponding BUY trade or not eligible for kindling simulation'
                    })

    return results

def format_report(results, tp_sell_frac, simulate_kindling):
    report_content = []
    report_content.append("# Post-Proof Residual Growth - Backtest Report")
    report_content.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    report_content.append("## Objective:")
    report_content.append("Evaluate potential PnL improvements by retaining residual positions after partial TP and/or adding kindling before TP.")
    report_content.append("## Scenarios Simulated:")
    report_content.append(f"- **Baseline:** Current full shell exit at TP.")
    if tp_sell_frac:
        report_content.append(f"- **Partial Trail TP:** {tp_sell_frac*100:.0f}% of position sold at TP, remaining {((1-tp_sell_frac)*100):.0f}% retained for potential add-risk (mocked).")
    if simulate_kindling:
        report_content.append(f"- **Kindling First:** Simulate one $25 kindling step before TP if eligible (mocked eligibility and pricing).")
    report_content.append("\n## Summary of Results (by Pair):\n")

    total_pnl_baseline = 0
    total_pnl_partial_trail = 0
    total_pnl_kindling_first = 0
    
    for pair, data in results.items():
        report_content.append(f"### {pair}")
        
        # Baseline
        pnl_sum_b = sum(r['pnl_usd'] for r in data['baseline'] if isinstance(r['pnl_usd'], (int, float)))
        num_b = len(data['baseline'])
        avg_pnl_b = pnl_sum_b / num_b if num_b > 0 else 0
        report_content.append(f"- **Baseline (Full Exit TP):** {num_b} trades, Total PnL: ${pnl_sum_b:.2f}, Avg PnL: ${avg_pnl_b:.2f}")
        total_pnl_baseline += pnl_sum_b

        # Partial Trail
        if tp_sell_frac:
            pnl_sum_pt = sum(r['final_pnl_usd'] for r in data['partial_trail'] if isinstance(r['final_pnl_usd'], (int, float)))
            num_pt = len(data['partial_trail'])
            avg_pnl_pt = pnl_sum_pt / num_pt if num_pt > 0 else 0
            report_content.append(f"- **Partial Trail TP (Mocked Add-Risk):** {num_pt} trades, Total PnL: ${pnl_sum_pt:.2f}, Avg PnL: ${avg_pnl_pt:.2f}")
            total_pnl_partial_trail += pnl_sum_pt

        # Kindling First
        if simulate_kindling:
            pnl_sum_kf = sum(r['final_pnl_usd'] for r in data['kindling_first'] if isinstance(r['final_pnl_usd'], (int, float)))
            num_kf = len(data['kindling_first'])
            avg_pnl_kf = pnl_sum_kf / num_kf if num_kf > 0 else 0
            report_content.append(f"- **Kindling First (Mocked Eligibility):** {num_kf} trades, Total PnL: ${pnl_sum_kf:.2f}, Avg PnL: ${avg_pnl_kf:.2f}")
            total_pnl_kindling_first += pnl_sum_kf
        report_content.append("\n")

    report_content.append("## Overall Totals:")
    report_content.append(f"- **Baseline Total PnL:** ${total_pnl_baseline:.2f}")
    if tp_sell_frac:
        report_content.append(f"- **Partial Trail TP Total PnL:** ${total_pnl_partial_trail:.2f} (+${total_pnl_partial_trail - total_pnl_baseline:.2f} vs Baseline)")
    if simulate_kindling:
        report_content.append(f"- **Kindling First Total PnL:** ${total_pnl_kindling_first:.2f} (+${total_pnl_kindling_first - total_pnl_baseline:.2f} vs Baseline)")
    
    report_content.append("\n## Caveats and Limitations:")
    report_content.append("- **Mocked Logic:** `add_risk` and `kindling eligibility/pricing` are highly simplified placeholders. Actual backtesting requires integrating real market data (OHLCV) and the full logic of these components.")
    report_content.append("- **Regime Data:** Assumes 'flat' regime for `add_risk` demo. Full backtest needs historical regime data.")
    report_content.append("- **Residual PnL:** Simplified residual PnL assumption after partial sale.")
    report_content.append("- **Trade Selection:** Only processes 'CLOSED_TP_TRAIL' sells for now.")
    report_content.append("- **Fees:** Not included in PnL calculations for simplicity.")
    report_content.append("\n## Next Steps:")
    report_content.append("- Refine backtesting logic with real historical data and full component integrations (add-risk sizer, kindling bars).")
    report_content.append("- Expand to include max drawdown and win rate analysis.")
    report_content.append("- Test various `tp_sell_frac` values and kindling conditions.")

    return "\n".join(report_content)

if __name__ == "__main__":
    # --- Run Simulations ---
    # Scenario 1: Partial Trail TP (e.g., sell 50%, retain 50%)
    tp_sell_fraction = 0.5
    results_partial_trail = run_simulation(tp_sell_frac=tp_sell_fraction, simulate_kindling=False)
    report_content_partial_trail = format_report(results_partial_trail, tp_sell_frac=tp_sell_fraction, simulate_kindling=False)
    
    # Scenario 2: Kindling First (assuming all tryouts eligible before TP)
    # This will overwrite the previous results, so run one by one or combine
    results_kindling_first = run_simulation(tp_sell_frac=None, simulate_kindling=True)
    report_content_kindling_first = format_report(results_kindling_first, tp_sell_frac=None, simulate_kindling=True)

    # --- Combine and Write Report (simplified for demo) ---
    final_report_content = []
    final_report_content.append("# Consolidated Post-Proof Residual Growth Backtest Report")
    final_report_content.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    final_report_content.append("\n## Scenario: Partial Trail TP (50% sold, 50% retained)")
    final_report_content.append(report_content_partial_trail.split('## Overall Totals:')[0]) # Exclude overall totals for individual sections
    final_report_content.append("\n## Scenario: Kindling First (Mocked Eligibility)")
    final_report_content.append(report_content_kindling_first.split('## Overall Totals:')[0]) # Exclude overall totals for individual sections
    
    # Recalculate combined totals if needed, or stick to per-scenario
    # For now, just show individual totals in their sections.
    final_report_content.append("\n## Consolidated Overall Totals:")
    # This part would require careful merging of the 'results' dicts if we want accurate combined totals
    # For this iteration, refer to the individual scenario totals above.
    final_report_content.append("- See individual scenario summaries for their respective totals. A full combined total would require a more complex simulation integrating both paths.")

    with open(REPORT_FILENAME, 'w') as f:
        f.write("\n".join(final_report_content))

    print(f"Report written to {REPORT_FILENAME}")
