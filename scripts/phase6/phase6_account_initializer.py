import logging
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum

from phase6_config_loader import Scenario, load_scenario_config, ScenarioConfig
from phase6_user_prompts import (
    get_user_currency_preference,
    confirm_entry_price,
    approve_liquidation,
    confirm_sl_tp
)
# Assume these exist
# from coinbase_client import CoinbaseClient
# from order_executor import place_sl_tp_order, place_limit_sell
# from state_manager import StateManager  # Global state

logger = logging.getLogger(__name__)

TRADING_PAIRS = ['BTC-USD', 'ETH-USD', 'SOL-USD']  # Extend as needed
FIAT_CURRENCIES = ['USD', 'USDC']

class Phase6Initializer:
    def __init__(self, coinbase_client, order_executor, state_manager):
        self.cb_client = coinbase_client
        self.order_exec = order_executor
        self.state = state_manager

    def get_balances(self) -> Dict[str, float]:
        """Get balances for fiat and crypto."""
        accounts = self.cb_client.get_accounts()
        balances = {}
        for acc in accounts:
            currency = acc['currency']
            balance = float(acc['balance'])
            if balance > 0.001:  # Threshold
                balances[currency] = balance
        logger.info(f"Detected balances: {balances}")
        return balances

    def detect_scenario(self, balances: Dict[str, float]) -> Scenario:
        """Detect account scenario."""
        usd = balances.get('USD', 0.0)
        usdc = balances.get('USDC', 0.0)
        fiat_total = usd + usdc
        crypto_total = sum(balances.get(pair.split('-')[0], 0.0) for pair in TRADING_PAIRS)

        has_fiat = fiat_total > 100.0
        has_crypto = crypto_total > 0.001

        if fiat_total < 1.0 and not has_crypto:
            return Scenario.READY_TO_START
        elif not has_fiat and has_crypto:
            return Scenario.TAKEOVER_2
        elif has_fiat and not has_crypto:
            return Scenario.FRESH_START
        elif has_fiat and has_crypto:
            # Check for Bank Your Wins: significant USDC + USD + crypto
            if usdc > usd * 2 and usd > 500 and has_crypto:
                return Scenario.BANK_YOUR_WINS
            return Scenario.TAKEOVER_1
        raise ValueError("Unable to detect scenario")

    def get_trading_fiat_balance(self, trading_fiat: str, balances: Dict[str, float]) -> float:
        """Get balance for chosen trading fiat."""
        return balances.get(trading_fiat, 0.0)

    def get_crypto_holdings(self, balances: Dict[str, float]) -> Dict[str, float]:
        """Get qty for trading pairs."""
        holdings = {}
        for pair in TRADING_PAIRS:
            base = pair.split('-')[0]
            qty = balances.get(base, 0.0)
            if qty > 0.001:
                holdings[pair] = qty
        return holdings

    def estimate_entry_prices(self, holdings: Dict[str, float], cb_client) -> Dict[str, float]:
        """Try to get avg entry from history, else current price."""
        prices = {}
        for pair, qty in holdings.items():
            # Mock: try history
            history = cb_client.get_account_history(pair)  # Assume returns txs
            entry_price = self._calc_avg_entry(history)  # Implement logic
            if entry_price is None:
                # Fallback to current price
                current_price = cb_client.get_current_price(pair)
                entry_price = current_price
            prices[pair] = entry_price
        return prices

    def _calc_avg_entry(self, history: List[Dict]) -> Optional[float]:
        """Calculate avg buy price from history. Mock impl."""
        buys = [tx for tx in history if tx['side'] == 'buy']
        if not buys:
            return None
        total_cost = sum(tx['total'] for tx in buys)
        total_qty = sum(tx['size'] for tx in buys)
        return total_cost / total_qty if total_qty > 0 else None

    def initialize(self) -> Dict[str, Any]:
        """Main initialization logic."""
        balances = self.get_balances()
        scenario = self.detect_scenario(balances)
        config = load_scenario_config(scenario)

        # Currency preference
        trading_fiat = get_user_currency_preference()
        trading_balance = self.get_trading_fiat_balance(trading_fiat, balances)
        yield_fiat = 'USDC' if trading_fiat == 'USD' else 'USD'
        yield_balance = balances.get(yield_fiat, 0.0)

        holdings = self.get_crypto_holdings(balances)
        portfolio_value = trading_balance + yield_balance + sum(holdings.values()) * 100  # Rough approx (avg $100/coin)

        if scenario == Scenario.READY_TO_START:
            self.state.update({'status': 'AWAITING_FUNDING', 'scenario': scenario.value})
            logger.warning("READY_TO_START: Trading blocked until funded.")
            return {'status': 'awaiting_funding'}

        reserve_usd = max(config.min_reserve_usd, trading_balance * config.reserve_pct) if trading_balance > 0 else 0
        deploy_budget = max(0, trading_balance - reserve_usd) if trading_balance > 0 else 0

        if scenario == Scenario.TAKEOVER_2:
            usd_needed = portfolio_value * config.self_fund_pct
            if trading_balance < usd_needed:
                # Self-fund
                pair_to_sell = max(holdings, key=lambda p: holdings[p])  # Simplistic
                qty_to_sell = usd_needed / self.cb_client.get_current_price(pair_to_sell)
                if approve_liquidation(pair_to_sell, qty_to_sell, usd_needed, "Self-fund reserve"):
                    # self.order_exec.place_limit_sell(pair_to_sell, qty_to_sell)
                    logger.info("Liquidation executed (mock).")
                    trading_balance += usd_needed  # Simulate
                    holdings[pair_to_sell] -= qty_to_sell
                reserve_usd = usd_needed
                deploy_budget = trading_balance * config.deploy_pct

        # Handle takeovers: entry prices, SL/TP
        if holdings:
            entry_prices = self.estimate_entry_prices(holdings, self.cb_client)
            for pair, qty in holdings.items():
                entry_price = confirm_entry_price(pair, entry_prices[pair])
                current_price = self.cb_client.get_current_price(pair)
                sl_price = entry_price * (1 + config.sl_pct)
                tp_price = entry_price * (1 + config.tp_pct)
                if confirm_sl_tp(pair, sl_price, tp_price):
                    # self.order_exec.place_sl_tp(pair, qty, sl_price, tp_price)
                    logger.info(f"SL/TP placed for {pair} (mock)")

        # Update state
        self.state.update({
            'scenario': scenario.value,
            'trading_fiat': trading_fiat,
            'trading_balance': trading_balance,
            'reserve_usd': reserve_usd,
            'deploy_budget': deploy_budget,
            'yield_balance': yield_balance,
            'holdings': holdings,
            'status': 'READY_TO_TRADE'
        })

        logger.info(f"Phase 6 initialized: {scenario.value}, deploy=${deploy_budget:.2f}")
        return self.state.get_state()
