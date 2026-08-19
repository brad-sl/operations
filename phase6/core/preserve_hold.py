"""
Preserve Mode — Hold profile only (MVP).

Ballast sleeve: static PAXG target of cash+preserve equity, deep emergency stop E1 on
Coinbase (−32% from arm_vwap), soft adds_block at −12%. DeRisk multi-leg is NOT implemented.

Defaults: enabled=false, armed=false. No auto-arm. Crypto rebalance must not cancel E1.
"""
from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger("phase6.preserve_hold")

STATE_PATH = PROJECT_ROOT / "data/state/preserve_hold_state.json"
STATUS_PATH = PROJECT_ROOT / "data/state/preserve_hold_status.json"
CONFIG_KEY = "preserve_mode"
STABLE = frozenset({"USD", "USDC", "USDT", "DAI"})
DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "armed": False,
    "profile": "hold",
    "target_pct": 0.20,
    "asset": "PAXG-USD",
    "preserve_equity_base": "cash_plus_preserve_mtm",
    "allow_preserve_with_crypto_util": False,
    "min_ballast_usd": 500.0,
    "band_pct": 0.02,
    "attach_safety_ratio": 0.98,
    # Micro live: small fixed USD sleeve for logging / E1 path (not full 20%)
    "micro_live": False,
    "micro_usd": 75.0,
    "hold": {
        "e1_dd_pct": -0.32,
        "soft_adds_block_dd_pct": -0.12,
        "e1_limit_slip_pct": 0.006,
    },
    "derisk": {"enabled": False},
    "venue_probe_result": "A",
    "venue_probe_date": "2026-08-02",
    # Step1: re-place E1 when armed+inventory but stop missing
    "e1_auto_repair": True,
    # Step2: write park_ballast_decision_latest.json (no orders)
    "shadow_decision_log": True,
}

SLEEVE_LOG_PATH = PROJECT_ROOT / "data/state/preserve_sleeve_log.jsonl"
E1_ALERT_PATH = PROJECT_ROOT / "data/state/preserve_e1_alert.json"
DECISION_LATEST_PATH = PROJECT_ROOT / "data/state/park_ballast_decision_latest.json"
DECISION_HISTORY_PATH = PROJECT_ROOT / "data/state/park_ballast_decision_history.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_preserve_config(full_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = deepcopy(DEFAULTS)
    if full_config and isinstance(full_config.get(CONFIG_KEY), dict):
        user = full_config[CONFIG_KEY]
        for k, v in user.items():
            if k == "hold" and isinstance(v, dict):
                cfg["hold"] = {**cfg["hold"], **v}
            elif k == "derisk" and isinstance(v, dict):
                cfg["derisk"] = {**cfg["derisk"], **v}
            else:
                cfg[k] = v
    # Force hold-only product for MVP
    cfg["profile"] = "hold"
    if isinstance(cfg.get("derisk"), dict):
        cfg["derisk"]["enabled"] = False
    return cfg


def default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "armed": False,
        "profile": "hold",
        "asset": "PAXG-USD",
        "target_pct": 0.20,
        "arm_vwap": None,
        "arm_qty": None,
        "arm_ts": None,
        "e1_order_id": None,
        "e1_stop_price": None,
        "e1_qty": None,
        "adds_blocked": False,
        "last_error": None,
        "last_tick_ts": None,
        "last_action": None,
        "updated_at": None,
    }


def load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or STATE_PATH
    base = default_state()
    if not p.exists():
        return base
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            base.update(raw)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[PRESERVE] state load failed: %s", e)
    return base


def asset_base(pair: str) -> str:
    return pair.split("-")[0] if "-" in pair else pair


def is_preserve_order_id(order_id: Optional[str], state: Optional[Dict[str, Any]] = None) -> bool:
    if not order_id:
        return False
    st = state if state is not None else load_state()
    eid = st.get("e1_order_id")
    return bool(eid and str(order_id) == str(eid))


def is_preserve_pair(pair: Optional[str], cfg: Optional[Dict[str, Any]] = None) -> bool:
    if not pair:
        return False
    c = cfg or load_preserve_config()
    return str(pair).upper() == str(c.get("asset", "PAXG-USD")).upper()


def should_protect_preserve_sleeve(
    *,
    pair: Optional[str] = None,
    order_id: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    """True if this pair/order must not be cancelled by crypto rebalance/dust."""
    st = state if state is not None else load_state()
    c = cfg or load_preserve_config()
    if not st.get("armed") and not c.get("armed"):
        # still protect known E1 id if present (bot mid-disarm)
        if order_id and is_preserve_order_id(order_id, st):
            return True
        return False
    if order_id and is_preserve_order_id(order_id, st):
        return True
    if pair and is_preserve_pair(pair, c):
        return True
    return False


def _holding_qty(exchange: Any, asset: str) -> Tuple[float, float]:
    """Return (available, total)."""
    avail = 0.0
    total = 0.0
    try:
        if hasattr(exchange, "get_crypto_available"):
            avail = float(exchange.get_crypto_available(asset) or 0)
            total = avail
    except Exception:
        pass
    try:
        h = exchange.get_holdings() or {}
        raw = h.get(asset) or h.get(f"{asset}-USD") or 0
        if isinstance(raw, dict):
            a = float(raw.get("available") or 0)
            hold = float(raw.get("hold") or 0)
            tot = float(raw.get("amount")) if raw.get("amount") is not None else a + hold
            avail = a if a else avail
            total = tot if tot else total
        else:
            total = max(total, float(raw or 0))
            if avail <= 0:
                avail = total
    except Exception:
        pass
    return avail, total


def crypto_util_pct(exchange: Any, preserve_asset: str = "PAXG") -> float:
    """Share of non-stable non-preserve holdings / (cash + those + preserve). 0 = parked."""
    try:
        holdings = exchange.get_holdings() or {}
    except Exception:
        return 0.0
    cash = 0.0
    preserve_mtm = 0.0
    crypto_mtm = 0.0
    prices: Dict[str, float] = {}

    def px(sym: str) -> float:
        if sym in prices:
            return prices[sym]
        pair = f"{sym}-USD" if "-" not in sym else sym
        try:
            p = float(exchange.get_price(pair) or 0)
        except Exception:
            p = 0.0
        prices[sym] = p
        return p

    for k, raw in holdings.items():
        base = asset_base(str(k)).upper()
        if isinstance(raw, dict):
            qty = float(raw.get("amount") if raw.get("amount") is not None else (float(raw.get("available") or 0) + float(raw.get("hold") or 0)))
        else:
            try:
                qty = float(raw or 0)
            except (TypeError, ValueError):
                qty = 0.0
        if qty <= 0:
            continue
        if base in STABLE or base in ("USD",):
            cash += qty
            continue
        p = px(base if base != preserve_asset else preserve_asset)
        mtm = qty * p
        if base == preserve_asset.upper():
            preserve_mtm += mtm
        else:
            crypto_mtm += mtm
    # also try get_account_balance style
    try:
        if hasattr(exchange, "get_account_balance"):
            for sk in ("USD", "USDC", "USDT"):
                try:
                    v = float(exchange.get_account_balance(sk) or 0)
                except TypeError:
                    # dict-style get_account_balance()
                    bal = exchange.get_account_balance() or {}
                    v = float((bal or {}).get(sk) or 0)
                except Exception:
                    v = 0.0
                if v > cash:
                    cash = v
    except Exception:
        pass
    denom = cash + preserve_mtm + crypto_mtm
    if denom <= 0:
        return 0.0
    return float(crypto_mtm / denom)


def cash_plus_preserve_mtm(exchange: Any, asset_pair: str) -> Dict[str, float]:
    base = asset_base(asset_pair)
    avail, total = _holding_qty(exchange, base)
    try:
        price = float(exchange.get_price(asset_pair) or 0)
    except Exception:
        price = 0.0
    preserve_mtm = total * price
    cash = 0.0
    try:
        holdings = exchange.get_holdings() or {}
        for k, raw in holdings.items():
            b = asset_base(str(k)).upper()
            if b not in STABLE and b not in ("USD",):
                continue
            if isinstance(raw, dict):
                q = float(raw.get("amount") if raw.get("amount") is not None else float(raw.get("available") or 0))
            else:
                q = float(raw or 0)
            cash += q
    except Exception:
        pass
    try:
        if hasattr(exchange, "get_account_balance"):
            for sk in ("USD", "USDC", "USDT"):
                try:
                    v = float(exchange.get_account_balance(sk) or 0)
                except TypeError:
                    bal = exchange.get_account_balance() or {}
                    v = float((bal or {}).get(sk) or 0)
                except Exception:
                    v = 0.0
                if v > 0:
                    cash = max(cash, v)
                    break
    except Exception:
        pass
    return {
        "cash": cash,
        "preserve_qty": total,
        "preserve_avail": avail,
        "price": price,
        "preserve_mtm": preserve_mtm,
        "equity_base": cash + preserve_mtm,
    }


def compute_e1_prices(arm_vwap: float, e1_dd: float, slip: float) -> Tuple[float, float]:
    """Return (stop_price, limit_price). e1_dd is negative e.g. -0.32."""
    stop = float(arm_vwap) * (1.0 + float(e1_dd))
    limit = stop * (1.0 - abs(float(slip)))
    return stop, limit


def place_e1_stop(
    exchange: Any,
    *,
    pair: str,
    qty: float,
    stop_price: float,
    limit_price: float,
    arm_vwap: float,
    mode: str = "live",
) -> Dict[str, Any]:
    """Place stop-limit E1; register sleeve=preserve."""
    out: Dict[str, Any] = {"success": False, "order_id": None, "error": None}
    if qty <= 0 or stop_price <= 0:
        out["error"] = "bad_qty_or_stop"
        return out
    try:
        if hasattr(exchange, "quantize_size"):
            qty = float(exchange.quantize_size(pair, qty))
        if hasattr(exchange, "quantize_price"):
            stop_price = float(exchange.quantize_price(pair, stop_price))
            limit_price = float(exchange.quantize_price(pair, limit_price))
    except Exception:
        pass
    try:
        resp = exchange.place_stop_limit_sell(pair, qty, stop_price, limit_price=limit_price)
    except Exception as e:
        out["error"] = str(e)
        return out
    oid = None
    ok = False
    if isinstance(resp, dict):
        if resp.get("success") is False:
            out["error"] = resp.get("error") or resp.get("raw")
            out["raw"] = resp
            return out
        ok = bool(resp.get("success")) or bool(resp.get("order_id"))
        oid = resp.get("order_id") or (resp.get("success_response") or {}).get("order_id")
    elif resp is True:
        ok = True
    out["success"] = ok
    out["order_id"] = oid
    out["raw"] = resp
    if ok and oid:
        try:
            from phase6.core.protective_orders_registry import register_protective_order

            register_protective_order(
                pair=pair,
                sl_order_id=str(oid),
                entry_price=float(arm_vwap),
                qty=float(qty),
                stop_price=float(stop_price),
                limit_price=float(limit_price),
                mode=mode,
                sleeve="preserve",
                reason="preserve_e1",
            )
        except TypeError:
            # older signature without sleeve — still register basics
            try:
                from phase6.core.protective_orders_registry import register_protective_order

                register_protective_order(
                    pair=pair,
                    sl_order_id=str(oid),
                    entry_price=float(arm_vwap),
                    qty=float(qty),
                    stop_price=float(stop_price),
                    limit_price=float(limit_price),
                    mode=mode,
                )
            except Exception as e:
                logger.warning("[PRESERVE] registry write failed: %s", e)
        except Exception as e:
            logger.warning("[PRESERVE] registry write failed: %s", e)
    return out


def cancel_e1(exchange: Any, order_id: Optional[str]) -> bool:
    if not order_id:
        return True
    try:
        r = exchange.cancel_order(order_id)
        return bool(r) if not isinstance(r, dict) else bool(r.get("success", True))
    except Exception as e:
        logger.warning("[PRESERVE] cancel E1 %s failed: %s", order_id, e)
        return False


def arm_preserve_hold(
    exchange: Any,
    full_config: Dict[str, Any],
    *,
    force: bool = False,
    dry_run: bool = False,
    max_buy_usd: Optional[float] = None,
    skip_target_topup: bool = False,
) -> Dict[str, Any]:
    """
    Buy up to target_pct of cash+preserve, place E1, persist armed state.
    Requires config enabled (or force) and crypto util ~0 unless allowed.

    max_buy_usd: cap buy size (soak / micro arm).
    skip_target_topup: if True and already have any PAXG, don't buy more — just attach E1.
    """
    cfg = load_preserve_config(full_config)
    result: Dict[str, Any] = {"ok": False, "action": "arm", "steps": []}
    if not cfg.get("enabled") and not force:
        result["error"] = "preserve_mode.enabled is false"
        return result
    if str(cfg.get("profile", "hold")).lower() != "hold":
        result["error"] = "only hold profile supported"
        return result

    pair = str(cfg.get("asset") or "PAXG-USD")
    base = asset_base(pair)
    util = crypto_util_pct(exchange, base)
    result["crypto_util_pct"] = util
    if not cfg.get("allow_preserve_with_crypto_util") and util > 0.02 and not force:
        result["error"] = f"crypto_not_parked util={util:.4f}"
        return result

    snap = cash_plus_preserve_mtm(exchange, pair)
    equity = float(snap["equity_base"])
    target_pct = float(cfg.get("target_pct") or 0.20)
    target_usd = equity * target_pct
    if max_buy_usd is not None:
        # soak: treat target as min(current+max_buy, max_buy) style micro
        target_usd = min(target_usd, float(max_buy_usd) + float(snap["preserve_mtm"]))
        if float(snap["preserve_mtm"]) <= 0:
            target_usd = float(max_buy_usd)
    band = float(cfg.get("band_pct") or 0.02)
    result["equity_base"] = equity
    result["target_usd"] = target_usd
    result["snap"] = snap

    if equity <= 0 and max_buy_usd is None:
        result["error"] = "zero_equity_base"
        return result

    price = float(snap["price"] or 0)
    if price <= 0:
        result["error"] = "no_price"
        return result

    current_mtm = float(snap["preserve_mtm"])
    need_usd = target_usd - current_mtm
    buy_usd = 0.0
    if skip_target_topup and current_mtm > 5:
        buy_usd = 0.0
    elif need_usd > max(target_usd * band, 5.0) if max_buy_usd is None else need_usd > 5.0:
        buy_usd = need_usd
        buy_usd = min(buy_usd, max(0.0, float(snap["cash"]) - 10.0))
        if max_buy_usd is not None:
            buy_usd = min(buy_usd, float(max_buy_usd))

    if dry_run:
        result["ok"] = True
        result["dry_run"] = True
        result["buy_usd"] = buy_usd
        return result

    if buy_usd >= 5.0:
        try:
            br = exchange.place_market_buy(pair, buy_usd)
            result["steps"].append({"buy": buy_usd, "resp": str(br)[:400]})
            if isinstance(br, dict) and br.get("success") is False:
                result["error"] = f"buy_failed:{br.get('error')}"
                return result
            # Coinbase consumer balances can lag fill by several seconds
            for _ in range(12):
                time.sleep(1.0)
                snap_w = cash_plus_preserve_mtm(exchange, pair)
                if float(snap_w.get("preserve_qty") or 0) > 0:
                    break
            else:
                time.sleep(2.0)
            # Ledger with honest reason (not rebalance)
            try:
                from phase6.core.trade_ledger import TradeLedger

                oid = (br or {}).get("order_id") if isinstance(br, dict) else None
                TradeLedger().log_trade(
                    {
                        "pair": pair,
                        "side": "BUY",
                        "qty": None,
                        "entry_price": None,
                        "exit_price": None,
                        "pnl": 0.0,
                        "order_id": oid,
                        "reason": "preserve_arm" if not cfg.get("soak_micro") else "preserve_arm_micro",
                        "signal_source": "preserve_hold.arm",
                        "mode": "live",
                        "sleeve": "preserve",
                        "usd_notional_request": buy_usd,
                    },
                    exchange=exchange,
                )
            except Exception as le:
                logger.warning("preserve arm ledger log failed: %s", le)
        except Exception as e:
            result["error"] = f"buy_failed:{e}"
            return result

    snap2 = cash_plus_preserve_mtm(exchange, pair)
    avail, total = snap2["preserve_avail"], snap2["preserve_qty"]
    price2 = float(snap2["price"] or price)
    if total <= 0:
        result["error"] = "no_paxg_after_buy"
        return result

    # arm_vwap: approximate with current price if no fill detail
    arm_vwap = price2
    safety = float(cfg.get("attach_safety_ratio") or 0.98)
    e1_qty = float(avail if avail > 0 else total) * safety
    try:
        if hasattr(exchange, "quantize_size"):
            e1_qty = float(exchange.quantize_size(pair, e1_qty))
    except Exception:
        pass

    hold = cfg.get("hold") or {}
    e1_dd = float(hold.get("e1_dd_pct", -0.32))
    slip = float(hold.get("e1_limit_slip_pct", 0.006))
    stop_px, limit_px = compute_e1_prices(arm_vwap, e1_dd, slip)

    # cancel any previous e1 first
    st = load_state()
    if st.get("e1_order_id"):
        cancel_e1(exchange, st.get("e1_order_id"))

    placed = place_e1_stop(
        exchange,
        pair=pair,
        qty=e1_qty,
        stop_price=stop_px,
        limit_price=limit_px,
        arm_vwap=arm_vwap,
        mode="live" if not getattr(exchange, "shadow_mode", False) else "shadow",
    )
    result["steps"].append({"e1": placed})
    if not placed.get("success") or not placed.get("order_id"):
        result["error"] = f"e1_place_failed:{placed.get('error')}"
        result["naked_arm_forbidden"] = True
        return result

    new_state = default_state()
    new_state.update(
        {
            "armed": True,
            "profile": "hold",
            "asset": pair,
            "target_pct": target_pct if max_buy_usd is None else None,
            "soak_micro": max_buy_usd is not None,
            "arm_vwap": arm_vwap,
            "arm_qty": total,
            "arm_ts": _now(),
            "e1_order_id": placed.get("order_id"),
            "e1_stop_price": stop_px,
            "e1_qty": e1_qty,
            "adds_blocked": False,
            "last_error": None,
            "last_action": "arm_soak" if max_buy_usd is not None else "arm",
            "last_tick_ts": _now(),
        }
    )
    save_state(new_state)
    try:
        persist_status(full_config, exchange=exchange)
    except Exception:
        pass
    result["ok"] = True
    result["state"] = new_state
    return result


def disarm_preserve_hold(
    exchange: Any,
    full_config: Optional[Dict[str, Any]] = None,
    *,
    sell: bool = True,
) -> Dict[str, Any]:
    """Cancel E1 (and any other PAXG stop-limits) then optionally market-sell PAXG."""
    cfg = load_preserve_config(full_config)
    pair = str(cfg.get("asset") or "PAXG-USD")
    st = load_state()
    out: Dict[str, Any] = {"ok": False, "steps": []}
    oid = st.get("e1_order_id")
    if oid:
        out["steps"].append({"cancel": oid, "ok": cancel_e1(exchange, oid)})
    # Cancel any remaining open stop-limits on the preserve pair (repair race / stale legs)
    try:
        if hasattr(exchange, "get_open_stop_orders"):
            stops = exchange.get_open_stop_orders(pair) or []
        else:
            stops = []
        for o in stops:
            ooid = o.get("order_id") or o.get("id")
            if not ooid:
                continue
            try:
                ok = bool(exchange.cancel_order(str(ooid)))
            except Exception as e:
                ok = False
                out["steps"].append({"cancel_extra_err": str(ooid), "err": str(e)})
            out["steps"].append({"cancel_extra": str(ooid), "ok": ok})
    except Exception as e:
        out["steps"].append({"list_stops_err": str(e)})
    time.sleep(1.5)
    if sell:
        base = asset_base(pair)
        for attempt in range(4):
            avail, total = _holding_qty(exchange, base)
            qty = avail if avail > 0 else total
            if qty <= 0:
                break
            try:
                if hasattr(exchange, "quantize_size"):
                    qty = float(exchange.quantize_size(pair, qty))
                if qty <= 0:
                    break
                sr = exchange.place_market_sell(pair, qty)
                out["steps"].append({"sell": qty, "attempt": attempt, "resp": str(sr)[:300]})
                if isinstance(sr, dict) and sr.get("success") is False:
                    time.sleep(1.5)
                    continue
                try:
                    from phase6.core.trade_ledger import TradeLedger

                    oid = (sr or {}).get("order_id") if isinstance(sr, dict) else None
                    TradeLedger().log_trade(
                        {
                            "pair": pair,
                            "side": "SELL",
                            "qty": qty,
                            "entry_price": None,
                            "exit_price": None,
                            "pnl": None,
                            "order_id": oid,
                            "reason": "preserve_disarm",
                            "exit_reason": "preserve_disarm",
                            "signal_source": "preserve_hold.disarm",
                            "mode": "live",
                            "sleeve": "preserve",
                        },
                        exchange=exchange,
                    )
                except Exception as le:
                    logger.warning("preserve disarm ledger log failed: %s", le)
                time.sleep(1.5)
            except Exception as e:
                out["steps"].append({"sell_error": str(e), "attempt": attempt})
                time.sleep(1.5)
    cleared = default_state()
    cleared["last_action"] = "disarm"
    cleared["last_tick_ts"] = _now()
    save_state(cleared)
    try:
        persist_status(full_config, exchange=exchange)
    except Exception:
        pass
    out["ok"] = True
    out["state"] = cleared
    return out


def _list_pair_stops(exchange: Any, pair: str) -> List[Dict[str, Any]]:
    try:
        if hasattr(exchange, "get_open_stop_orders"):
            stops = exchange.get_open_stop_orders(pair) or []
        else:
            stops = exchange.get_open_orders() or []
        out = []
        for o in stops:
            if not isinstance(o, dict):
                continue
            pid = o.get("product_id") or o.get("pair") or pair
            if pid and str(pid).upper() not in (str(pair).upper(), str(pair).split("-")[0].upper()):
                # keep if get_open_stop_orders already filtered
                if hasattr(exchange, "get_open_stop_orders"):
                    out.append(o)
                continue
            out.append(o)
        return out if out else list(stops or [])
    except Exception:
        raise


def inspect_e1_health(
    exchange: Any,
    cfg: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Truthful E1 presence for armed Preserve sleeves.

    e1_open: any open stop on the preserve pair OR exact e1_order_id match.
    naked: armed + inventory > 0 + no open stop.
    """
    pair = str(state.get("asset") or cfg.get("asset") or "PAXG-USD")
    oid = state.get("e1_order_id")
    health: Dict[str, Any] = {
        "pair": pair,
        "tracked_order_id": oid,
        "e1_open": False,
        "matched_order_id": None,
        "match_mode": None,
        "open_stop_count": 0,
        "qty_total": 0.0,
        "qty_avail": 0.0,
        "naked": False,
        "flat": False,
        "list_ok": True,
        "list_error": None,
        "as_of": _now(),
    }
    if not state.get("armed"):
        health["reason"] = "not_armed"
        return health

    try:
        stops = _list_pair_stops(exchange, pair)
        health["open_stop_count"] = len(stops)
        exact = False
        any_pair = False
        matched = None
        for o in stops:
            ooid = o.get("order_id") or o.get("id")
            if oid and str(ooid) == str(oid):
                exact = True
                matched = ooid
                break
            # any stop on preserve pair counts as protection present
            if is_preserve_pair(o.get("product_id") or o.get("pair") or pair, cfg):
                any_pair = True
                matched = ooid
        if exact:
            health["e1_open"] = True
            health["matched_order_id"] = matched
            health["match_mode"] = "exact_id"
        elif any_pair or (stops and not oid):
            health["e1_open"] = True
            health["matched_order_id"] = matched or (
                (stops[0].get("order_id") or stops[0].get("id")) if stops else None
            )
            health["match_mode"] = "pair_stop" if any_pair else "any_listed_stop"
            if oid and health["matched_order_id"] and str(health["matched_order_id"]) != str(oid):
                health["id_drift"] = True
        elif stops:
            # listed stops on pair endpoint — trust presence
            health["e1_open"] = True
            health["matched_order_id"] = stops[0].get("order_id") or stops[0].get("id")
            health["match_mode"] = "pair_endpoint"
            # sync tracked id if drifted
            if health["matched_order_id"] and str(health["matched_order_id"]) != str(oid or ""):
                health["id_drift"] = True
    except Exception as e:
        health["list_ok"] = False
        health["list_error"] = str(e)[:200]
        health["reason"] = f"list_failed:{e}"
        return health

    try:
        avail, total = _holding_qty(exchange, asset_base(pair))
        health["qty_avail"] = float(avail or 0)
        health["qty_total"] = float(total or 0)
    except Exception as e:
        health["qty_error"] = str(e)[:120]

    if health["qty_total"] <= 1e-12:
        health["flat"] = True
        health["naked"] = False
        health["reason"] = "flat"
    elif health["e1_open"]:
        health["naked"] = False
        health["reason"] = "e1_present"
    else:
        health["naked"] = True
        health["reason"] = "naked_armed_inventory"
    return health


def write_e1_alert(health: Dict[str, Any], repair: Optional[Dict[str, Any]] = None) -> None:
    """Persist naked-E1 alert for dash/ops (cleared when healthy)."""
    try:
        if health.get("naked"):
            payload = {
                "alert": "PRESERVE_E1_NAKED",
                "severity": "critical",
                "as_of": _now(),
                "message": (
                    "Preserve armed with PAXG inventory but no open E1 stop on exchange. "
                    "Kill-bot protection may be missing."
                ),
                "health": health,
                "repair": repair or {},
            }
            E1_ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
            E1_ALERT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        elif E1_ALERT_PATH.exists() and health.get("e1_open"):
            # clear stale alert
            E1_ALERT_PATH.unlink(missing_ok=True)
    except Exception as e:
        logger.debug("[PRESERVE] e1 alert write failed: %s", e)


def repair_e1_if_missing(exchange: Any, cfg: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """If armed but E1 gone (and still have inventory), re-place once."""
    out: Dict[str, Any] = {"repaired": False, "reason": None, "health_before": None}
    if not state.get("armed"):
        out["reason"] = "not_armed"
        return out

    health = inspect_e1_health(exchange, cfg, state)
    out["health_before"] = {k: health.get(k) for k in (
        "e1_open", "naked", "flat", "match_mode", "tracked_order_id", "matched_order_id", "qty_total", "list_ok"
    )}

    if not health.get("list_ok"):
        out["reason"] = health.get("reason") or "list_failed"
        return out

    # Sync drifted stop id into state when a pair stop exists
    if health.get("e1_open") and health.get("id_drift") and health.get("matched_order_id"):
        state["e1_order_id"] = health["matched_order_id"]
        state["last_action"] = "e1_id_sync"
        save_state(state)
        out["reason"] = "e1_present_id_synced"
        out["order_id"] = health["matched_order_id"]
        write_e1_alert(health)
        return out

    if health.get("e1_open"):
        out["reason"] = "e1_present"
        write_e1_alert(health)
        return out

    if health.get("flat"):
        state["armed"] = False
        state["e1_order_id"] = None
        state["last_action"] = "e1_filled_or_flat"
        state["last_error"] = None
        save_state(state)
        out["reason"] = "flat_cleared"
        write_e1_alert({**health, "naked": False, "e1_open": False})
        return out

    if not cfg.get("e1_auto_repair", True):
        out["reason"] = "auto_repair_disabled"
        write_e1_alert(health, out)
        return out

    pair = str(state.get("asset") or cfg.get("asset") or "PAXG-USD")
    arm_vwap = float(state.get("arm_vwap") or 0)
    if arm_vwap <= 0:
        try:
            arm_vwap = float(exchange.get_price(pair) or 0)
        except Exception:
            arm_vwap = 0.0
    if arm_vwap <= 0:
        out["reason"] = "no_vwap"
        write_e1_alert(health, out)
        return out

    hold = cfg.get("hold") or {}
    safety = float(cfg.get("attach_safety_ratio") or 0.98)
    avail = float(health.get("qty_avail") or 0)
    total = float(health.get("qty_total") or 0)
    e1_qty = (avail if avail > 0 else total) * safety
    try:
        if hasattr(exchange, "quantize_size"):
            e1_qty = float(exchange.quantize_size(pair, e1_qty))
    except Exception:
        pass
    stop_px, limit_px = compute_e1_prices(
        arm_vwap, float(hold.get("e1_dd_pct", -0.32)), float(hold.get("e1_limit_slip_pct", 0.006))
    )
    placed = place_e1_stop(
        exchange,
        pair=pair,
        qty=e1_qty,
        stop_price=stop_px,
        limit_price=limit_px,
        arm_vwap=arm_vwap,
        mode="shadow" if getattr(exchange, "shadow_mode", False) else "live",
    )
    if placed.get("success") and placed.get("order_id"):
        state["e1_order_id"] = placed["order_id"]
        state["e1_stop_price"] = stop_px
        state["e1_qty"] = e1_qty
        state["last_action"] = "repair_e1"
        state["last_error"] = None
        save_state(state)
        out["repaired"] = True
        out["order_id"] = placed["order_id"]
        out["reason"] = "repaired"
        # verify
        health2 = inspect_e1_health(exchange, cfg, load_state())
        out["health_after"] = {k: health2.get(k) for k in ("e1_open", "naked", "match_mode")}
        write_e1_alert(health2, out)
        logger.warning("[PRESERVE] E1 repaired order_id=%s stop=%.4f", placed["order_id"], stop_px)
    else:
        out["reason"] = f"place_failed:{placed.get('error')}"
        state["last_error"] = out["reason"]
        state["last_action"] = "repair_e1_failed"
        save_state(state)
        write_e1_alert(health, out)
        logger.error("[PRESERVE] E1 NAKED — repair failed: %s", out["reason"])
    return out


def update_adds_blocked(exchange: Any, cfg: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """Set adds_blocked if MTM from arm_vwap <= soft threshold. Never auto-clears without re-arm."""
    if not state.get("armed"):
        return False
    if state.get("adds_blocked"):
        return True
    arm_vwap = float(state.get("arm_vwap") or 0)
    if arm_vwap <= 0:
        return False
    pair = str(state.get("asset") or cfg.get("asset") or "PAXG-USD")
    try:
        px = float(exchange.get_price(pair) or 0)
    except Exception:
        return False
    if px <= 0:
        return False
    thr = float((cfg.get("hold") or {}).get("soft_adds_block_dd_pct", -0.12))
    dd = px / arm_vwap - 1.0
    if dd <= thr:
        state["adds_blocked"] = True
        state["last_action"] = f"adds_blocked_dd={dd:.4f}"
        save_state(state)
        logger.info("[PRESERVE] adds_blocked latched dd=%.4f thr=%.4f", dd, thr)
        return True
    return False


def maybe_preserve_hold_tick(
    runner: Any = None,
    *,
    exchange: Any = None,
    full_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Per-cycle maintenance. No-op unless preserve_mode.enabled.
    Does NOT auto-arm. If state.armed: repair E1 + latch adds_block.
    """
    out: Dict[str, Any] = {"ran": False, "skipped": True, "reason": None}
    cfg_full = full_config
    if cfg_full is None and runner is not None:
        cfg_full = getattr(runner, "config_dict", None) or {}
    cfg_full = cfg_full or {}
    cfg = load_preserve_config(cfg_full)
    if not cfg.get("enabled"):
        out["reason"] = "disabled"
        return out

    ex = exchange
    if ex is None and runner is not None:
        ex = getattr(runner, "exchange", None)
    if ex is None:
        out["reason"] = "no_exchange"
        return out

    out["skipped"] = False
    out["ran"] = True
    state = load_state()
    # config.armed is operator intent to stay armed; state.armed is runtime
    if not state.get("armed"):
        out["reason"] = "not_armed"
        out["note"] = "enable+arm via arm_preserve_hold / scripts; no auto-arm"
        return out

    ab = update_adds_blocked(ex, cfg, state)
    repair = repair_e1_if_missing(ex, cfg, load_state())
    state = load_state()
    state["last_tick_ts"] = _now()
    # cache last e1 health on state for status without re-list if needed
    try:
        health = inspect_e1_health(ex, cfg, state)
        state["e1_open"] = bool(health.get("e1_open"))
        state["e1_naked"] = bool(health.get("naked"))
        state["e1_health_reason"] = health.get("reason")
        if health.get("matched_order_id") and health.get("e1_open"):
            # keep status in sync without forcing save thrash when unchanged
            if str(state.get("e1_order_id") or "") != str(health.get("matched_order_id")):
                state["e1_order_id"] = health["matched_order_id"]
    except Exception as e:
        health = {"e1_open": None, "naked": None, "error": str(e)[:120]}
    save_state(state)
    log_row = log_sleeve_snapshot(ex, cfg, state, health=health)
    out["adds_blocked"] = state.get("adds_blocked") or ab
    out["repair"] = repair
    out["e1_order_id"] = state.get("e1_order_id")
    out["e1_open"] = health.get("e1_open")
    out["e1_naked"] = health.get("naked")
    out["sleeve_log"] = {k: log_row.get(k) for k in ("preserve_usd", "ret_vs_arm", "e1_open", "badge")}
    try:
        persist_status(cfg_full, exchange=ex, e1_health=health)
    except Exception:
        pass
    # Step 2 — shadow decision matrix (no orders)
    if cfg.get("shadow_decision_log", True):
        try:
            from phase6.core.park_ballast_shadow import write_park_ballast_decision

            dec = write_park_ballast_decision(
                exchange=ex,
                full_config=cfg_full,
                preserve_cfg=cfg,
                state=state,
                e1_health=health,
                sleeve_row=log_row,
            )
            out["shadow_decision"] = {
                "action": dec.get("recommended_action"),
                "path": str(DECISION_LATEST_PATH),
            }
        except Exception as e:
            out["shadow_decision_error"] = str(e)[:160]
            logger.debug("[PRESERVE] shadow decision failed: %s", e)
    return out


def log_sleeve_snapshot(
    exchange: Any,
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    health: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one JSONL row for sleeve MTM / E1 presence / simple returns."""
    pair = str(state.get("asset") or cfg.get("asset") or "PAXG-USD")
    arm_vwap = state.get("arm_vwap")
    row: Dict[str, Any] = {
        "ts": _now(),
        "armed": bool(state.get("armed")),
        "micro": bool(state.get("soak_micro") or cfg.get("micro_live")),
        "asset": pair,
        "arm_vwap": arm_vwap,
        "e1_order_id": state.get("e1_order_id"),
        "e1_stop_price": state.get("e1_stop_price"),
        "adds_blocked": bool(state.get("adds_blocked")),
    }
    try:
        px = float(exchange.get_price(pair) or 0)
        avail, total = _holding_qty(exchange, asset_base(pair))
        usd = round(total * px, 4) if px else 0.0
        row["price"] = px
        row["qty"] = total
        row["preserve_usd"] = usd
        if arm_vwap and float(arm_vwap) > 0 and px > 0:
            row["ret_vs_arm"] = round(px / float(arm_vwap) - 1.0, 6)
        # cost basis approx: arm_vwap * arm_qty at arm; use arm_qty if set
        aq = state.get("arm_qty")
        if aq and arm_vwap:
            cost = float(aq) * float(arm_vwap)
            row["arm_cost_usd"] = round(cost, 4)
            row["pnl_usd"] = round(usd - cost, 4)
            if cost > 0:
                row["ret_usd"] = round((usd - cost) / cost, 6)
        if health is None:
            health = inspect_e1_health(exchange, cfg, state)
        e1_open = bool(health.get("e1_open"))
        row["e1_open"] = e1_open
        row["e1_naked"] = bool(health.get("naked"))
        row["e1_match_mode"] = health.get("match_mode")
        micro = bool(state.get("soak_micro") or cfg.get("micro_live"))
        if state.get("armed") and health.get("naked"):
            row["badge"] = "NAKED"
        elif state.get("armed") and micro:
            row["badge"] = "MICRO"
        elif state.get("armed"):
            row["badge"] = "ARMED"
        else:
            row["badge"] = "OFF"
        if state.get("adds_blocked") and row["badge"] in ("MICRO", "ARMED"):
            row["badge"] = row["badge"] + "·NO-ADD"
    except Exception as e:
        row["error"] = str(e)[:200]
    try:
        SLEEVE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SLEEVE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:
        logger.debug("[PRESERVE] sleeve log write failed: %s", e)
    return row


def status_snapshot(
    full_config: Optional[Dict[str, Any]] = None,
    *,
    exchange: Any = None,
    e1_health: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = load_preserve_config(full_config)
    st = load_state()
    badge = "OFF"
    detail = "disabled"
    health = e1_health
    if exchange is not None and st.get("armed") and health is None:
        try:
            health = inspect_e1_health(exchange, cfg, st)
        except Exception:
            health = None
    if not cfg.get("enabled"):
        badge = "OFF"
        detail = "code ready · not enabled"
    elif not st.get("armed"):
        badge = "STANDBY"
        detail = "enabled · not armed"
    else:
        micro = bool(st.get("soak_micro") or cfg.get("micro_live"))
        naked = bool((health or {}).get("naked") or st.get("e1_naked"))
        e1_open = (health or {}).get("e1_open")
        if e1_open is None:
            e1_open = st.get("e1_open")
        if naked:
            badge = "NAKED"
            detail = "E1 missing — inventory unprotected"
        elif micro:
            badge = "MICRO"
            detail = f"Hold micro ~${float(cfg.get('micro_usd') or 75):.0f}"
        else:
            badge = "ARMED"
            detail = "Hold E1"
        if st.get("adds_blocked") and badge not in ("NAKED",):
            badge = badge + "·NO-ADD"
            detail = "adds blocked"
        if e1_open is False and not naked and st.get("armed"):
            detail = (detail + " · E1 unknown").strip(" ·")
    e1_px = st.get("e1_stop_price")
    arm_vwap = st.get("arm_vwap")
    mtm_dd = None
    preserve_usd = None
    if exchange is not None and st.get("armed"):
        try:
            pair = str(st.get("asset") or cfg.get("asset") or "PAXG-USD")
            px = float(exchange.get_price(pair) or 0)
            if arm_vwap and px > 0:
                mtm_dd = round(px / float(arm_vwap) - 1.0, 4)
            avail, total = _holding_qty(exchange, asset_base(pair))
            preserve_usd = round(total * px, 2) if px else None
        except Exception:
            pass
    e1_open_val = None
    e1_naked_val = None
    if health is not None:
        e1_open_val = health.get("e1_open")
        e1_naked_val = health.get("naked")
    elif st.get("e1_open") is not None:
        e1_open_val = st.get("e1_open")
        e1_naked_val = st.get("e1_naked")
    snap = {
        "as_of": _now(),
        "badge": badge,
        "detail": detail,
        "config_enabled": bool(cfg.get("enabled")),
        "config_armed_flag": bool(cfg.get("armed")),
        "profile": cfg.get("profile"),
        "derisk_enabled": bool((cfg.get("derisk") or {}).get("enabled")),
        "state_armed": bool(st.get("armed")),
        "asset": st.get("asset") or cfg.get("asset"),
        "target_pct": st.get("target_pct") or cfg.get("target_pct"),
        "arm_vwap": arm_vwap,
        "e1_order_id": st.get("e1_order_id"),
        "e1_stop_price": e1_px,
        "e1_qty": st.get("e1_qty"),
        "e1_open": e1_open_val,
        "e1_naked": e1_naked_val,
        "e1_match_mode": (health or {}).get("match_mode"),
        "e1_health_reason": (health or {}).get("reason") or st.get("e1_health_reason"),
        "e1_alert_path": str(E1_ALERT_PATH) if e1_naked_val else None,
        "adds_blocked": bool(st.get("adds_blocked")),
        "mtm_dd_from_arm": mtm_dd,
        "preserve_usd": preserve_usd,
        "last_action": st.get("last_action"),
        "last_error": st.get("last_error"),
        "last_tick_ts": st.get("last_tick_ts"),
        "venue_probe_result": cfg.get("venue_probe_result"),
        "decision_matrix": "docs/research/PARK_BALLAST_DECISION_MATRIX.md",
        "shadow_decision_path": str(DECISION_LATEST_PATH),
        # honest label — never "safe" / "risk-free"
        "label_ui": f"Preserve {badge}",
        "tooltip": (
            "Ballast sleeve (Hold): small PAXG target of cash+gold. "
            "E1 is a deep Coinbase emergency stop (~−32% from arm), not a 3% crypto SL. "
            "Not risk-free; gold can drop ~20–28% path DD. "
            f"E1 open={e1_open_val}."
        ),
    }
    return snap


def persist_status(
    full_config: Optional[Dict[str, Any]] = None,
    *,
    exchange: Any = None,
    path: Optional[Path] = None,
    e1_health: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    snap = status_snapshot(full_config, exchange=exchange, e1_health=e1_health)
    p = path or STATUS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    return snap


def save_state(state: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = _now()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    try:
        persist_status()
    except Exception:
        pass
