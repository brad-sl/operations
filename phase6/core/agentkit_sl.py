# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
AgentKit-based Stop-Loss PoC (separate path).

This is a proof-of-concept implementation to evaluate Coinbase AgentKit
as a mitigation for SL attach reliability issues (INSUFFICIENT_FUND,
preview failures, balance mismatches seen in live cutover).

Design:
- Run SEPARATELY from the current StopLossManager + CR-03 coordinator.
- Uses AgentKit (CDP wallet/action providers) for improved balance/fund
  visibility where possible.
- Delegates actual order placement to the provided exchange client
  (AgentKit is primarily on-chain/wallet focused; not a full drop-in
   for Coinbase Advanced Trade spot stop_limit yet).
- Provides attach_stop_loss with the same signature as production for easy comparison.

To run separately:
    PYTHONPATH=. python -c "
    from phase6.core.agentkit_sl import AgentKitStopLossManager
    from phase6.core.exchange_client import CoinbaseExchangeClient
    ...
    "

Compare results to phase6/core/stop_loss_manager.py:StopLossManager.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import os
    from coinbase_agentkit import AgentKit, AgentKitConfig
    from coinbase_agentkit.wallet_providers import CdpEvmWalletProvider, CdpEvmWalletProviderConfig
    from coinbase_agentkit.action_providers import CdpApiActionProvider, WalletActionProvider, wallet_action_provider
    AGENTKIT_AVAILABLE = True
except ImportError:
    AGENTKIT_AVAILABLE = False
    logger.warning("coinbase-agentkit not available; AgentKitSL will use fallback behavior.")


class AgentKitStopLossManager:
    """
    Separate PoC SL manager using AgentKit primitives for pre-flight.

    Intended to be invoked independently (e.g. via dedicated script or
    config flag) and compared to the production StopLossManager.
    """

    def __init__(
        self,
        exchange_client: Any,
        config: dict,
        mode: str = "shadow",
        agentkit_config: Optional[dict] = None
    ):
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.shadow_mode = (mode == "shadow")
        self.default_sl_pct = config.get("risk_management", {}).get("stop_loss_pct", 0.03)

        self.agentkit = None
        self._init_agentkit(agentkit_config)

        logger.info(f"[AGENTKIT-SL PoC] Initialized | mode={mode} | agentkit_available={bool(self.agentkit)}")

    def _init_agentkit(self, ak_config: Optional[dict]):
        if not AGENTKIT_AVAILABLE:
            return
        try:
            # Re-broadened for real CdpEvmWalletProvider + WalletAction.get_balance (P0 t_7ddd3f2d)
            # CDP keys (CDP_API_KEY_ID/SECRET/WALLET_SECRET) now supported via env or ak_config.
            # See .env.example and re_broaden_agentkit_poc.py for setup + live views.
            wallet_provider = None
            if ak_config and ak_config.get("api_key_id") and ak_config.get("api_key_secret") and ak_config.get("wallet_secret"):
                wallet_provider = CdpEvmWalletProvider(
                    CdpEvmWalletProviderConfig(
                        api_key_id=ak_config["api_key_id"],
                        api_key_secret=ak_config["api_key_secret"],
                        wallet_secret=ak_config["wallet_secret"],
                        network_id=ak_config.get("network_id", "base-sepolia"),
                    )
                )
            else:
                # Standard: load from env (set in project .env after obtaining from CDP portal)
                api_id = os.getenv("CDP_API_KEY_ID")
                api_sec = os.getenv("CDP_API_KEY_SECRET")
                w_sec = os.getenv("CDP_WALLET_SECRET")
                if api_id and api_sec and w_sec and not str(api_id).startswith("your-"):
                    wallet_provider = CdpEvmWalletProvider(
                        CdpEvmWalletProviderConfig(
                            api_key_id=api_id,
                            api_key_secret=api_sec,
                            wallet_secret=w_sec,
                            network_id=os.getenv("NETWORK_ID", "base-sepolia"),
                        )
                    )
                    logger.info("[AGENTKIT-SL PoC] Real CdpEvmWalletProvider initialized from CDP_* env keys.")
            action_providers = [CdpApiActionProvider(), WalletActionProvider()] if wallet_provider else []
            config = AgentKitConfig(
                wallet_provider=wallet_provider,
                action_providers=action_providers,
            ) if (wallet_provider or action_providers) else AgentKitConfig()
            self.agentkit = AgentKit(config=config)
            self.wallet_provider = wallet_provider  # for direct balance/action access
            logger.info("[AGENTKIT-SL PoC] AgentKit client ready (CDP-backed + WalletAction.get_balance available).")
        except Exception as e:
            logger.warning(f"[AGENTKIT-SL PoC] AgentKit init failed (expected without real CDP keys): {e}")
            self.agentkit = None
            self.wallet_provider = None

    def _agentkit_balance_view(self, asset: str) -> Dict[str, float]:
        """
        Use AgentKit/CDP + real WalletActionProvider.get_balance for live balance views.
        Falls back to exchange client's methods when CDP not available or for CEX-specific assets.
        """
        wallet_prov = getattr(self, "wallet_provider", None) or (getattr(self.agentkit, "wallet_provider", None) if self.agentkit else None)

        if not wallet_prov:
            # Fallback to exchange (original behavior)
            avail = 0.0
            total = 0.0
            try:
                if hasattr(self.exchange, "get_crypto_available"):
                    avail = float(self.exchange.get_crypto_available(asset) or 0.0)
                if hasattr(self.exchange, "get_holdings_verified"):
                    h = self.exchange.get_holdings_verified() or {}
                    total = float((h.get("positions") or {}).get(asset, 0.0))
            except Exception:
                pass
            return {"available": avail, "total": total, "source": "exchange_fallback"}

        # Real CDP + WalletAction path for live views (broadened PoC)
        try:
            start = time.time()  # for latency in logs
            native_bal = wallet_prov.get_balance()
            # Use WalletActionProvider explicitly (per task)
            try:
                wa = WalletActionProvider()
                wa_details = wa.get_wallet_details(wallet_prov, {})
                wa_bal = wa.get_balance(wallet_prov, {})
                logger.info(f"[AGENTKIT-SL] WalletAction views: details={str(wa_details)[:80]} bal={str(wa_bal)[:80]}")
            except Exception as wa_e:
                logger.debug(f"WalletAction direct call note: {wa_e}")

            # For CEX asset matching, we still pull from exchange but credit the CDP source
            # (on-chain native vs CEX spot are different; this PoC surfaces both)
            avail = 0.0
            total = 0.0
            try:
                if hasattr(self.exchange, "get_crypto_available"):
                    avail = float(self.exchange.get_crypto_available(asset) or 0.0)
                if hasattr(self.exchange, "get_holdings_verified"):
                    h = self.exchange.get_holdings_verified() or {}
                    total = float((h.get("positions") or {}).get(asset, 0.0))
            except Exception:
                pass

            latency = int((time.time() - start) * 1000)
            logger.info(f"[AGENTKIT-SL] Real CDP balance view (native): {native_bal} | latency={latency}ms | asset={asset} exchange_total={total}")
            return {
                "available": avail,
                "total": total,
                "cdp_native_balance": float(Decimal(native_bal) / Decimal(10**18)),
                "source": "cdp_evm_walletaction",
                "latency_ms": latency,
            }
        except Exception as e:
            logger.warning(f"[AGENTKIT-SL] CDP/WalletAction balance view failed for {asset}: {e}")
            # fall through to exchange numbers
            avail = 0.0
            total = 0.0
            try:
                if hasattr(self.exchange, "get_crypto_available"):
                    avail = float(self.exchange.get_crypto_available(asset) or 0.0)
                if hasattr(self.exchange, "get_holdings_verified"):
                    h = self.exchange.get_holdings_verified() or {}
                    total = float((h.get("positions") or {}).get(asset, 0.0))
            except Exception:
                pass
            return {"available": avail, "total": total, "source": "agentkit_error_fallback"}

    def attach_stop_loss(
        self,
        pair: str,
        entry_price: float,
        size: float,
        sl_pct: float = None
    ) -> bool:
        """
        Attach SL using AgentKit-informed pre-flight + delegate to exchange for order.

        This is the SEPARATE implementation. Call this from an isolated script/mode
        to compare against the production StopLossManager.attach_stop_loss.
        """
        pct = sl_pct if sl_pct is not None else self.default_sl_pct
        asset = pair.split("-")[0] if "-" in pair else pair

        # === AgentKit-enhanced balance view (core of the PoC mitigation) ===
        bal = self._agentkit_balance_view(asset)
        avail = bal.get("available", 0.0)
        total = bal.get("total", 0.0)
        source = bal.get("source", "unknown")

        logger.info(f"[AGENTKIT-SL] Balance view for {pair} (source={source}): avail={avail:.8f} total={total:.8f}")

        # Replicate hardened sizing logic from production, but using the AgentKit-sourced numbers
        effective_size = size
        if not self.shadow_mode:
            use_total = False
            if avail <= 0 and total > 0:
                use_total = True
            elif total > 0 and avail < total * 0.2:  # avail << total (common Coinbase reporting when SL open or settlement lag)
                use_total = True
            if use_total:
                logger.info(f"[AGENTKIT-SL PROD-02] avail={avail:.4f} << total {total:.4f} via {source}; using total for recovery")
                avail = total
                if size > total:
                    size = total
            if size > avail * 0.95:
                safe = max(0.0, avail * 0.95)
                logger.warning(f"[AGENTKIT-SL] Capping size {size:.6f} -> {safe:.6f} (95% of avail via {source})")
                effective_size = safe
            if effective_size < 1e-8:
                logger.warning(f"[AGENTKIT-SL] Effective size too small for {pair}; skipping")
                return False

        # Quantize (reuse exchange helpers)
        meta = self.exchange.get_product_metadata(pair)
        stop_price = entry_price * (1 - pct)
        limit_price = stop_price * 0.995

        stop_price_str = self.exchange.quantize_price(pair, stop_price)
        stop_price = float(stop_price_str)
        limit_price_str = self.exchange.quantize_price(pair, limit_price)
        limit_price = float(limit_price_str)

        size_str = self.exchange.quantize_size(pair, effective_size)
        effective_size = float(size_str)

        if self.shadow_mode:
            print(f"[AGENTKIT-SL SHADOW] Would attach SL for {pair}")
            print(f"  Entry: ${entry_price:.2f} | Stop: ${stop_price:.4f} | Limit: ${limit_price:.4f} | size: {effective_size}")
            print(f"  Balance source: {source} (AgentKit view if available)")
            return True

        # Delegate the actual placement to the existing (production) exchange client.
        # This keeps the PoC focused on the mitigation (better pre-flight via AgentKit)
        # while still exercising the real order path for comparison.
        try:
            result = self.exchange.place_stop_limit_sell(
                product_id=pair,
                qty=effective_size,
                stop_price=stop_price,
                limit_price=limit_price
            )
            if result:
                logger.info(f"[AGENTKIT-SL] Stop-loss attached via AgentKit-informed path for {pair}")
                return True
            logger.warning(f"[AGENTKIT-SL] place_stop_limit_sell returned falsy for {pair}")
            return False
        except Exception as e:
            logger.error(f"[AGENTKIT-SL] attach failed for {pair}: {e}")
            return False

    # Minimal stubs for compatibility with coordinator-style usage in isolated PoC runs
    def detect_active_protective_orders(self, basket=None):
        # Delegate to exchange or return empty for pure PoC runs
        if hasattr(self.exchange, "get_open_orders"):
            try:
                return self.exchange.get_open_orders() or []
            except Exception:
                pass
        return []

    def suspend_active_protective_orders(self, active_stops):
        return {}

    def verify_reconciliation(self, *args, **kwargs):
        return {"success": True, "details": "AgentKit PoC reconciliation stub (see comparison script)"}
