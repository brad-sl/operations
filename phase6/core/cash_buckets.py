"""Cash / park / powder classification for dashboard + runner holdings.

USDC is park (capital-preserve A-leg), never a trading pair. USD is powder.
USDT is hop residual only (convert path). PAXG stays a preserve *asset* sleeve
elsewhere — this module only classifies cash-like balances so they are not
double-rendered as USDC-USD trade rows.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Base currencies that are cash, not trade seats.
CASH_CCY = frozenset(
    {
        "USD",
        "USDC",
        "USDT",
        "DAI",
        "EURC",
        "GUSD",
        "PYUSD",
        "USDP",
        "BUSD",
    }
)

# Explicit pair forms that still show up on Coinbase holdings / product maps.
CASH_PAIRS = frozenset(
    {
        "USDC-USD",
        "USD-USDC",
        "USDT-USD",
        "USD-USDT",
        "USDT-USDC",
        "USDC-USDT",
        "DAI-USD",
        "EURC-USD",
        "GUSD-USD",
        "PYUSD-USD",
        "USDP-USD",
        "BUSD-USD",
        "USD-USD",
    }
)

# Bucket designation for cash rows (UI badge). USDC = preserve (A-leg park).
BUCKET_POWDER = "powder"  # USD dry powder for buy waves
BUCKET_PRESERVE = "preserve"  # USDC park / yield stub (user-facing bucket)
BUCKET_HOP = "hop"  # USDT residual from convert hop
BUCKET_CASH = "cash"  # other stables


def _norm_pair(pair: Optional[str]) -> str:
    return str(pair or "").strip().upper()


def is_cash_like_pair(pair: Optional[str]) -> bool:
    """True for USD/USDC/USDT (and pair forms like USDC-USD) — not trade seats."""
    p = _norm_pair(pair)
    if not p:
        return False
    if p in CASH_CCY or p in CASH_PAIRS:
        return True
    if "-" not in p:
        return p in CASH_CCY
    base, _, quote = p.partition("-")
    if base in CASH_CCY and quote in CASH_CCY:
        return True
    if base in CASH_CCY and quote in ("USD", "USDC", "USDT"):
        return True
    return False


def cash_currency_from_pair(pair: Optional[str]) -> str:
    """Map USDC-USD → USDC, USD → USD, USDT-USDC → USDT (base), etc."""
    p = _norm_pair(pair)
    if not p:
        return ""
    if p in CASH_CCY:
        return p
    if "-" not in p:
        return p if p in CASH_CCY else ""
    base, _, quote = p.partition("-")
    # Prefer the non-USD leg as the held cash unit when one side is USD.
    if base == "USD" and quote in CASH_CCY:
        return quote
    if quote == "USD" and base in CASH_CCY:
        return base
    if base in CASH_CCY:
        return base
    if quote in CASH_CCY:
        return quote
    return base


def cash_bucket_for(pair_or_ccy: Optional[str]) -> str:
    """Bucket designation: powder (USD), preserve (USDC), hop (USDT), else cash."""
    ccy = cash_currency_from_pair(pair_or_ccy) or _norm_pair(pair_or_ccy)
    if ccy == "USD":
        return BUCKET_POWDER
    if ccy == "USDC":
        return BUCKET_PRESERVE
    if ccy == "USDT":
        return BUCKET_HOP
    if ccy in CASH_CCY or is_cash_like_pair(pair_or_ccy):
        return BUCKET_CASH
    return BUCKET_CASH


def split_cash_and_trading(
    positions: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split positions list into (cash_rows, trading_rows). Cash-like never trade."""
    cash: List[Dict[str, Any]] = []
    trading: List[Dict[str, Any]] = []
    for raw in positions or []:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        pair = p.get("pair") or p.get("currency") or ""
        if is_cash_like_pair(pair):
            ccy = cash_currency_from_pair(pair) or _norm_pair(pair)
            bucket = cash_bucket_for(ccy)
            p["pair"] = ccy
            p["currency"] = ccy
            p["sleeve"] = bucket
            p["bucket"] = bucket
            # Cash has no trade PnL
            p.setdefault("unrealized_pnl_pct", 0.0)
            p.setdefault("unrealized_pnl_usd", 0.0)
            cash.append(p)
        else:
            trading.append(p)
    return cash, trading


def merge_cash_rows(
    balance_rows: Sequence[Dict[str, Any]],
    extra_cash_from_positions: Sequence[Dict[str, Any]] = (),
    *,
    min_show_usd: float = 0.01,
) -> List[Dict[str, Any]]:
    """One row per cash currency. Prefer balances; fold USDC-USD position into USDC."""
    by_ccy: Dict[str, Dict[str, Any]] = {}

    def _upsert(ccy: str, amount: float, value: float, src: str) -> None:
        ccy = (ccy or "").upper()
        if not ccy or ccy not in CASH_CCY:
            return
        bucket = cash_bucket_for(ccy)
        prev = by_ccy.get(ccy)
        # Prefer larger non-zero amount (balances usually authoritative)
        if prev is None or float(amount or 0) >= float(prev.get("amount") or 0):
            by_ccy[ccy] = {
                "pair": ccy,
                "currency": ccy,
                "amount": float(amount or 0),
                "value_usd": float(value if value is not None else amount or 0),
                "current_price": 1.0,
                "entry_price": 1.0,
                "unrealized_pnl_pct": 0.0,
                "unrealized_pnl_usd": 0.0,
                "side": "cash",
                "sleeve": bucket,
                "bucket": bucket,
                "source": src,
            }

    for b in balance_rows or []:
        if not isinstance(b, dict):
            continue
        ccy = str(b.get("currency") or b.get("pair") or "").upper()
        amt = float(b.get("balance") or b.get("available") or b.get("amount") or 0)
        _upsert(ccy, amt, amt, "balances")

    for p in extra_cash_from_positions or []:
        if not isinstance(p, dict):
            continue
        pair = p.get("pair") or p.get("currency") or ""
        if not is_cash_like_pair(pair):
            continue
        ccy = cash_currency_from_pair(pair) or _norm_pair(pair)
        amt = float(p.get("amount") or p.get("balance") or p.get("available") or 0)
        val = float(p.get("value_usd") or amt or 0)
        existing = by_ccy.get(ccy)
        if existing is None:
            _upsert(ccy, amt, val, "positions")
        else:
            # Don't double-count: keep balance amount if already set
            if float(existing.get("amount") or 0) < min_show_usd and amt >= min_show_usd:
                _upsert(ccy, amt, val, "positions")

    # Stable display order: USD powder, USDC preserve, USDT hop, then alpha
    order = {"USD": 0, "USDC": 1, "USDT": 2}
    rows = [r for r in by_ccy.values() if float(r.get("value_usd") or 0) >= min_show_usd]
    rows.sort(key=lambda r: (order.get(str(r.get("pair")), 50), str(r.get("pair"))))
    return rows


def trading_holdings_usd(positions: Iterable[Dict[str, Any]]) -> float:
    """Sum value_usd for non-cash trading positions only."""
    total = 0.0
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        if is_cash_like_pair(p.get("pair") or p.get("currency")):
            continue
        total += float(p.get("value_usd") or 0)
    return total
