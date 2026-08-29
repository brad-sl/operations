#!/usr/bin/env python3
"""Refresh phase6_live_state.json from exchange (no SQLite). Keeps dashboard current between runner cycles."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.paths import PHASE6_LIVE_STATE, PRICE_HISTORY, load_project_dotenv
from phase6.core.exchange_client import CoinbaseExchangeClient, _holding_parts
from phase6.core.trade_ledger import TradeLedger
from phase6.core.price_history_manager import PriceHistoryManager

load_project_dotenv()


def _avg_entries(ledger: TradeLedger) -> dict:
    totals: dict = {}
    for t in ledger.get_recent_trades(200):
        if (t.get("side") or "").upper() != "BUY":
            continue
        pair = t.get("pair")
        qty = float(t.get("qty") or 0)
        price = float(t.get("entry_price") or 0)
        if not pair or qty <= 0 or price <= 0:
            continue
        totals.setdefault(pair, {"qty": 0.0, "cost": 0.0})
        totals[pair]["qty"] += qty
        totals[pair]["cost"] += qty * price
    return {p: d["cost"] / d["qty"] for p, d in totals.items() if d["qty"] > 0}


def refresh() -> dict:
    ex = CoinbaseExchangeClient(mode="live")
    ledger = TradeLedger()
    entries = _avg_entries(ledger)
    price_mgr = PriceHistoryManager(persist_path=str(PRICE_HISTORY))

    # None = API failure (must not coerce to 0 — NAV cliff / −96% tiles)
    _usd_raw = ex.get_account_balance("USD")
    usd_unknown = _usd_raw is None
    usd = float(_usd_raw or 0) if not usd_unknown else 0.0
    try:
        _usdc_raw = ex.get_account_balance("USDC")
        usdc_unknown = _usdc_raw is None
        usdc = float(_usdc_raw or 0) if not usdc_unknown else 0.0
    except Exception:
        usdc = 0.0
        usdc_unknown = True

    holdings = {}
    if hasattr(ex, "get_holdings_verified"):
        h = ex.get_holdings_verified() or {}
        holdings = h.get("positions") or h.get("holdings") or {}
    if not holdings and hasattr(ex, "get_crypto_holdings"):
        holdings = ex.get_crypto_holdings() or {}

    positions = []
    total_holdings = 0.0
    for key, amt in (holdings or {}).items():
        if str(key).upper() in ("USD", "USDC"):
            continue
        pair = key if str(key).endswith("-USD") else f"{key}-USD"
        try:
            if isinstance(amt, dict):
                avail, hold_amt, amount = _holding_parts(amt)
            else:
                avail, hold_amt, amount = _holding_parts(amt)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        px = float(ex.get_price(pair) or 0)
        quote_ts = price_mgr.quote_timestamp(pair) if px > 0 else None
        if px > 0:
            price_mgr.add_price(pair, px)
            quote_ts = price_mgr.quote_timestamp(pair)
        value = amount * px
        entry = float(entries.get(pair, px) or px)
        pnl = ((px - entry) / entry) if entry > 0 else 0.0
        positions.append(
            {
                "pair": pair,
                "amount": amount,
                "qty": amount,
                "quantity": amount,
                "available": avail,
                "hold": hold_amt,
                "current_price": px,
                "price_as_of": quote_ts,
                "price_stale": False,
                "value_usd": value,
                "entry_price": entry,
                "unrealized_pnl_pct": round(pnl, 4),
                "side": "long",
            }
        )
        total_holdings += value

    try:
        from phase6.core.position_qty import normalize_positions_list

        positions = normalize_positions_list(positions)
    except Exception:
        pass

    prior = {}
    if PHASE6_LIVE_STATE.exists():
        try:
            prior = json.loads(PHASE6_LIVE_STATE.read_text())
        except Exception:
            prior = {}

    raw_total = usd + usdc + total_holdings
    try:
        from phase6.core.live_state_nav_guard import guard_live_nav

        total_usd, usd_safe, hold_safe, guard_meta = guard_live_nav(
            new_total=raw_total,
            new_cash=usd + usdc,
            new_holdings=total_holdings,
            prior_total=prior.get("total_usd") or prior.get("total_balance"),
            prior_cash=(prior.get("cash_usd") if prior.get("cash_usd") is not None else None),
        )
        if guard_meta.get("guarded"):
            # Restore cash from prior; keep freshly marked holdings when present
            cash_prior = float(prior.get("cash_usd") or 0) + float(
                next(
                    (
                        b.get("balance") or 0
                        for b in (prior.get("balances") or [])
                        if str(b.get("currency") or "").upper() == "USDC"
                    ),
                    0,
                )
                or 0
            )
            if cash_prior <= 0:
                cash_prior = float(prior.get("cash_usd") or usd_safe or 0)
            usd = float(prior.get("cash_usd") or usd_safe or usd)
            # Prefer split USD from prior balances
            for b in prior.get("balances") or []:
                if str(b.get("currency") or "").upper() == "USD":
                    usd = float(b.get("balance") or usd)
            usdc = 0.0
            for b in prior.get("balances") or []:
                if str(b.get("currency") or "").upper() == "USDC":
                    usdc = float(b.get("balance") or 0)
            if total_holdings <= 0 and hold_safe > 0:
                total_holdings = hold_safe
            total_usd = usd + usdc + total_holdings
            print(
                f"[DASH-REFRESH] NAV guard blocked cash/API cliff "
                f"raw_total=${raw_total:.2f} -> kept ${total_usd:.2f} ({guard_meta.get('reason')})"
            )
        else:
            total_usd = raw_total
    except Exception as _g_e:
        print(f"[DASH-REFRESH] nav guard skipped: {_g_e}")
        total_usd = raw_total

    state = {
        "balances": [
            {"currency": "USD", "balance": usd, "available": usd, "hold": 0},
            {"currency": "USDC", "balance": usdc, "available": usdc, "hold": 0},
        ],
        "positions": positions,
        "cash_positions": [],
        "trading_positions": positions,
        "active_positions": len(positions),
        "total_usd": total_usd,
        "total_balance": total_usd,
        "total_holdings_value": total_holdings,
        "cash_usd": usd,
        "last_updated": datetime.now().isoformat(),
        "source": "refresh_dashboard_live_state.py",
        "qty_ssot": {
            "schema": "position_qty_v1",
            "aliases": ["amount", "qty", "quantity"],
        },
    }

    for k in ("rsi", "performance_metrics", "arch4", "bought_indicators", "sold_indicators"):
        if k in prior:
            state[k] = prior[k]

    PHASE6_LIVE_STATE.parent.mkdir(parents=True, exist_ok=True)
    PHASE6_LIVE_STATE.write_text(json.dumps(state, indent=2))
    price_mgr.flush()
    print(f"[DASH-REFRESH] {len(positions)} positions total=${total_usd:.2f} -> {PHASE6_LIVE_STATE}")
    return state


if __name__ == "__main__":
    refresh()