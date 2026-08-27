#!/usr/bin/env python3
"""
Operator one-shot: trim LINK → buy BTC to ~30% NAV.

Brad go 2026-08-24: option #2, 30% BTC.
Requires --confirm-live.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("op_trim")

TARGET_BTC_FRAC = 0.30
# leave a small cash buffer after buy
CASH_BUFFER_USD = 25.0
FEE_PAD = 1.01  # sell a touch more LINK so net covers buy+fees


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-live", action="store_true")
    ap.add_argument("--target-btc-frac", type=float, default=TARGET_BTC_FRAC)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.confirm_live and not args.dry_run:
        print("Refusing without --confirm-live (or --dry-run)")
        return 2

    from phase6.core.phase6_runner import Phase6Runner
    from phase6.core.trade_ledger import TradeLedger

    runner = Phase6Runner(config_path="config/trading_config_phase6.json", mode="live")
    ex = runner.exchange
    if not ex or not ex._ensure_live_client():
        print("FAIL: no live client")
        return 1

    # --- snapshot ---
    holdings = ex.get_holdings_verified() or {}
    # holdings shape may be {pair: amount} or nested
    if isinstance(holdings, dict) and "holdings" in holdings:
        hmap = holdings["holdings"]
    else:
        hmap = holdings

    def base_amt(pair: str) -> float:
        # try several shapes
        if pair in hmap:
            v = hmap[pair]
            if isinstance(v, dict):
                return _f(v.get("available") or v.get("amount") or v.get("size"))
            return _f(v)
        base = pair.split("-")[0]
        for k, v in (hmap or {}).items():
            if str(k).upper() in (pair, base, f"{base}-USD"):
                if isinstance(v, dict):
                    return _f(v.get("available") or v.get("amount") or v.get("size"))
                return _f(v)
        return 0.0

    link_amt = base_amt("LINK-USD")
    btc_amt = base_amt("BTC-USD")
    # available may be locked by stops — use total if available
    try:
        raw = ex.get_holdings() or {}
        if isinstance(raw, dict):
            link_amt = max(link_amt, _f(raw.get("LINK-USD") or raw.get("LINK")))
            btc_amt = max(btc_amt, _f(raw.get("BTC-USD") or raw.get("BTC")))
    except Exception as e:
        log.warning("get_holdings: %s", e)

    link_px = _f(ex.get_price("LINK-USD"))
    btc_px = _f(ex.get_price("BTC-USD"))
    cash = 0.0
    for ccy in ("USD", "USDC"):
        try:
            cash = max(cash, _f(ex.get_account_balance(ccy)))
        except Exception:
            pass

    link_usd = link_amt * link_px
    btc_usd = btc_amt * btc_px
    # other positions approx from live state
    other = 0.0
    try:
        live = json.loads(Path("data/state/phase6_live_state.json").read_text())
        for row in live.get("positions") or []:
            p = str(row.get("pair") or "")
            if p in ("LINK-USD", "BTC-USD"):
                continue
            other += _f(row.get("value_usd"))
        if cash < 1:
            cash = _f(live.get("cash_usd"), cash)
    except Exception:
        pass

    nav = link_usd + btc_usd + other + cash
    target_btc = args.target_btc_frac * nav
    need_usd = max(0.0, target_btc - btc_usd)
    # don't spend below buffer
    max_spend = max(0.0, cash + need_usd - CASH_BUFFER_USD)  # after sell cash rises
    # sell notional
    sell_usd = need_usd * FEE_PAD
    if sell_usd < 15 and need_usd > 0:
        sell_usd = max(need_usd, 15.0)
    sell_qty = sell_usd / link_px if link_px > 0 else 0.0
    if sell_qty > link_amt * 0.95:
        # leave dust room / never full dump unless needed
        sell_qty = link_amt * 0.95
        sell_usd = sell_qty * link_px
    buy_usd = min(need_usd, sell_usd / FEE_PAD + max(0.0, cash - CASH_BUFFER_USD))
    # after sell, cash ≈ cash + sell proceeds; buy target_btc - btc_usd
    buy_usd = need_usd  # intend full gap; cash after sell should cover

    plan = {
        "ts": _utcnow(),
        "nav": round(nav, 2),
        "link_amt": link_amt,
        "link_px": link_px,
        "link_usd": round(link_usd, 2),
        "btc_amt": btc_amt,
        "btc_px": btc_px,
        "btc_usd": round(btc_usd, 2),
        "cash": round(cash, 2),
        "other_usd": round(other, 2),
        "target_btc_frac": args.target_btc_frac,
        "target_btc_usd": round(target_btc, 2),
        "need_usd": round(need_usd, 2),
        "sell_link_qty": sell_qty,
        "sell_link_usd_est": round(sell_usd, 2),
        "buy_btc_usd": round(buy_usd, 2),
        "post_est_btc_pct": round((btc_usd + buy_usd) / nav * 100, 1) if nav else None,
        "post_est_link_usd": round(link_usd - sell_usd, 2),
    }
    print(json.dumps(plan, indent=2))
    outp = Path("data/state/operator_trim_link_btc_30_plan.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(plan, indent=2))

    if need_usd < 20:
        print("Already near target; nothing meaningful to do.")
        return 0
    if sell_qty <= 0 or link_amt < sell_qty:
        print("FAIL: insufficient LINK", link_amt, sell_qty)
        return 1
    if args.dry_run:
        print("DRY RUN — no orders")
        return 0

    results = {"plan": plan, "steps": []}
    coord = getattr(runner, "stop_loss_coordinator", None)

    # 1) Suspend LINK stops (one-pair-at-a-time for operator trim) so base is free
    #    protected_market_exit will handle cancel→poll→sell→reattach for LINK
    pairs = ["LINK-USD"]
    if coord:
        try:
            sus = coord.suspend_protective_orders(pairs)
            results["steps"].append({"suspend": sus})
            log.info("suspended stops: %s", sus)
            time.sleep(3)
        except Exception as e:
            log.warning("suspend failed: %s — trying cancel_open_stops", e)
            try:
                from phase6.core.sl_preflight import cancel_open_stops_for_pair

                for p in pairs:
                    cancel_open_stops_for_pair(ex, p)
                time.sleep(3)
            except Exception as e2:
                results["steps"].append({"suspend_error": str(e2)})
                print("FAIL: could not free stops", e2)
                return 1
    else:
        from phase6.core.sl_preflight import cancel_open_stops_for_pair

        for p in pairs:
            cancel_open_stops_for_pair(ex, p)
        time.sleep(3)

    # poll available LINK (protected will also resolve/poll inside)
    for _ in range(8):
        try:
            hv = ex.get_holdings_verified() or {}
            hm = hv.get("holdings", hv) if isinstance(hv, dict) else {}
            avail = base_amt("LINK-USD")
            # also check available field
            raw = ex.get_holdings() or {}
            link_amt = max(link_amt, _f(raw.get("LINK-USD") or raw.get("LINK")), avail)
        except Exception:
            pass
        if link_amt >= sell_qty * 0.99:
            break
        time.sleep(1.5)

    # re-quantize sell
    try:
        sell_qty_q = float(ex.quantize_size("LINK-USD", sell_qty))
    except Exception:
        sell_qty_q = round(sell_qty, 4)

    # Wire to protected_market_exit SSOT (cancel→sell→reattach). Isolation + real data.
    from phase6.core.protected_market_exit import protected_market_exit
    log.info("SELL LINK (protected) qty=%s (~$%.2f)", sell_qty_q, sell_qty_q * link_px)
    sell_res = protected_market_exit(
        ex,
        "LINK-USD",
        qty=sell_qty_q,
        qty_full_hint=max(link_amt, sell_qty_q),
        entry_price=0.0,  # operator has no per-lot entry; protected falls back to mark_price for SL anchor
        mark_price=link_px,
        reason="operator_trim_link_to_btc_30pct",
        signal_source="operator_trim",
        dry_run=False,
        ledger=False,  # keep custom operator ledger below (adds "operator", "usd", "notes")
        reattach_sl=True,
    )
    results["steps"].append({"sell_link": sell_res})
    print("SELL:", sell_res)
    if not sell_res.get("success"):
        # protected_market_exit already performed reattach on fail path (sl_reattach_after_fail)
        # still attempt coord reattach for any other pairs (BTC) / safety
        if coord:
            try:
                pos = runner.portfolio.get_enriched_positions() if runner.portfolio else {}
                coord.reattach_protective_orders(pos.get("positions", pos) if isinstance(pos, dict) else {})
            except Exception:
                pass
        print("FAIL sell")
        Path("data/state/operator_trim_link_btc_30_result.json").write_text(json.dumps(results, indent=2, default=str))
        return 1

    sell_oid = sell_res.get("order_id")
    time.sleep(2)
    sell_fill_px = _f(sell_res.get("exit_price"), link_px)
    sell_fill_qty = _f(sell_res.get("filled_qty"), sell_qty_q)
    if sell_oid:
        try:
            fd = ex.get_order_fill_details(sell_oid) or {}
            if _f(fd.get("average_filled_price")) > 0:
                sell_fill_px = _f(fd.get("average_filled_price"))
            if _f(fd.get("filled_size")) > 0:
                sell_fill_qty = _f(fd.get("filled_size"))
            results["steps"].append({"sell_fill": fd})
        except Exception as e:
            results["steps"].append({"sell_fill_err": str(e)})

    sell_proceeds = sell_fill_qty * sell_fill_px
    log.info("sell fill qty=%s px=%s proceeds~%s", sell_fill_qty, sell_fill_px, sell_proceeds)

    # ledger SELL
    try:
        ledger = TradeLedger(Path("trades/phase6_trades.jsonl"))
        ledger.log_trade(
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "qty": sell_fill_qty,
                "entry_price": sell_fill_px,  # fill px
                "exit_price": sell_fill_px,
                "order_id": sell_oid,
                "reason": "operator_trim_link_to_btc_30pct",
                "usd": sell_proceeds,
                "timestamp": _utcnow(),
                "operator": True,
                "notes": "Brad go: trim LINK → BTC 30% NAV",
            }
        )
    except Exception as e:
        # fallback append
        log.warning("ledger SELL via TradeLedger failed: %s", e)
        try:
            with open("trades/phase6_trades.jsonl", "a") as f:
                f.write(
                    json.dumps(
                        {
                            "pair": "LINK-USD",
                            "side": "SELL",
                            "qty": sell_fill_qty,
                            "entry_price": sell_fill_px,
                            "order_id": sell_oid,
                            "reason": "operator_trim_link_to_btc_30pct",
                            "usd": sell_proceeds,
                            "timestamp": _utcnow(),
                            "operator": True,
                        }
                    )
                    + "\n"
                )
        except Exception as e2:
            log.error("ledger append failed: %s", e2)

    # 2) refresh cash and buy BTC
    time.sleep(2)
    cash2 = 0.0
    for ccy in ("USD", "USDC"):
        try:
            cash2 = max(cash2, _f(ex.get_account_balance(ccy)))
        except Exception:
            pass
    btc_px2 = _f(ex.get_price("BTC-USD")) or btc_px
    # buy min(need, cash - buffer)
    buy_usd_live = min(need_usd, max(0.0, cash2 - CASH_BUFFER_USD))
    # if cash still low, use most of proceeds
    if buy_usd_live < need_usd * 0.85:
        buy_usd_live = min(need_usd, max(buy_usd_live, sell_proceeds * 0.98 - 5.0, cash2 - 10.0))
        buy_usd_live = max(0.0, min(buy_usd_live, cash2 - 5.0 if cash2 > 5 else buy_usd_live))

    # re-read cash once more
    time.sleep(1)
    for ccy in ("USD", "USDC"):
        try:
            cash2 = max(cash2, _f(ex.get_account_balance(ccy)))
        except Exception:
            pass
    buy_usd_live = min(need_usd, max(0.0, cash2 - CASH_BUFFER_USD))
    if buy_usd_live < 15:
        # spend down to $10 cash if needed to complete rotate
        buy_usd_live = max(0.0, cash2 - 10.0)

    log.info("BUY BTC usd=%s cash=%s", buy_usd_live, cash2)
    buy_res = ex.place_market_buy("BTC-USD", buy_usd_live)
    results["steps"].append({"buy_btc": buy_res, "buy_usd": buy_usd_live, "cash_before_buy": cash2})
    print("BUY:", buy_res)
    if not buy_res.get("success"):
        results["error"] = "buy failed after sell — cash is free, manual BTC buy may be needed"
        Path("data/state/operator_trim_link_btc_30_result.json").write_text(json.dumps(results, indent=2, default=str))
        # still reattach SL on remaining
    else:
        buy_oid = buy_res.get("order_id")
        time.sleep(8)  # settlement before SL
        buy_fill_px = btc_px2
        buy_fill_qty = buy_usd_live / btc_px2 if btc_px2 else 0.0
        if buy_oid:
            try:
                fd = ex.get_order_fill_details(buy_oid) or {}
                if _f(fd.get("average_filled_price")) > 0:
                    buy_fill_px = _f(fd.get("average_filled_price"))
                if _f(fd.get("filled_size")) > 0:
                    buy_fill_qty = _f(fd.get("filled_size"))
                results["steps"].append({"buy_fill": fd})
            except Exception as e:
                results["steps"].append({"buy_fill_err": str(e)})
        try:
            with open("trades/phase6_trades.jsonl", "a") as f:
                f.write(
                    json.dumps(
                        {
                            "pair": "BTC-USD",
                            "side": "BUY",
                            "qty": buy_fill_qty,
                            "entry_price": buy_fill_px,
                            "order_id": buy_oid,
                            "reason": "operator_trim_link_to_btc_30pct",
                            "usd": buy_usd_live,
                            "timestamp": _utcnow(),
                            "operator": True,
                            "entry_drivers": ["operator_rotate", "rsi_structure_btc"],
                            "notes": "Brad go: BTC to 30% NAV from LINK trim",
                        }
                    )
                    + "\n"
                )
        except Exception as e:
            log.error("ledger BTC buy: %s", e)

        # entry lot tag for BTC add
        try:
            from phase6.core.rsi_primary_deploy import record_entry_lot, EntryDrivers

            record_entry_lot(
                pair="BTC-USD",
                entry_price=buy_fill_px,
                usd=buy_usd_live,
                drivers=EntryDrivers(
                    pair="BTC-USD",
                    drivers=["operator_rotate"],
                    sentiment_only=False,
                    sentiment_led=False,
                    full_size_ok=True,
                    rsi=None,
                    sentiment=None,
                    reason="operator_trim_link_to_btc_30pct",
                ),
                qty=buy_fill_qty,
                order_id=str(buy_oid) if buy_oid else None,
            )
        except Exception as e:
            log.warning("entry lot: %s", e)

    # 3) Reattach SLs on remaining LINK + full BTC
    time.sleep(3)
    try:
        # refresh portfolio
        if runner.portfolio:
            try:
                runner.portfolio.update() if hasattr(runner.portfolio, "update") else None
            except Exception:
                pass
        positions = {}
        raw_h = ex.get_holdings() or {}
        for pair, px_pair in (("LINK-USD", "LINK"), ("BTC-USD", "BTC"), ("PAXG-USD", "PAXG")):
            amt = _f(raw_h.get(pair) or raw_h.get(px_pair))
            if amt > 0:
                px = _f(ex.get_price(pair))
                positions[pair] = {
                    "pair": pair,
                    "amount": amt,
                    "size": amt,
                    "value_usd": amt * px,
                    "current_price": px,
                }
        results["steps"].append({"positions_post": {k: v.get("value_usd") for k, v in positions.items()}})
        if coord:
            att = coord.reattach_protective_orders(positions)
            results["steps"].append({"reattach": att})
            print("REATTACH:", att)
        else:
            # manager path
            if getattr(runner, "stop_loss_manager", None):
                for pair, pos in positions.items():
                    if pair in ("LINK-USD", "BTC-USD"):
                        try:
                            r = runner.stop_loss_manager.place_or_update_stop(pair, pos)
                            results["steps"].append({f"sl_{pair}": r})
                        except Exception as e:
                            results["steps"].append({f"sl_{pair}_err": str(e)})
    except Exception as e:
        results["steps"].append({"reattach_error": str(e)})
        log.exception("reattach")

    # final snapshot
    time.sleep(2)
    try:
        link_px_f = _f(ex.get_price("LINK-USD"))
        btc_px_f = _f(ex.get_price("BTC-USD"))
        raw_h = ex.get_holdings() or {}
        la = _f(raw_h.get("LINK-USD") or raw_h.get("LINK"))
        ba = _f(raw_h.get("BTC-USD") or raw_h.get("BTC"))
        cash_f = 0.0
        for ccy in ("USD", "USDC"):
            try:
                cash_f = max(cash_f, _f(ex.get_account_balance(ccy)))
            except Exception:
                pass
        lu, bu = la * link_px_f, ba * btc_px_f
        nav_f = lu + bu + other + cash_f
        final = {
            "link_usd": round(lu, 2),
            "btc_usd": round(bu, 2),
            "cash": round(cash_f, 2),
            "nav_est": round(nav_f, 2),
            "btc_pct": round(100 * bu / nav_f, 1) if nav_f else None,
            "link_pct": round(100 * lu / nav_f, 1) if nav_f else None,
        }
        results["final"] = final
        print("FINAL:", json.dumps(final, indent=2))
    except Exception as e:
        results["final_err"] = str(e)

    results["ok"] = bool(sell_res.get("success")) and (
        (results.get("steps") and any("buy_btc" in str(s) and s.get("buy_btc", {}).get("success") for s in results["steps"] if isinstance(s, dict)))
    )
    Path("data/state/operator_trim_link_btc_30_result.json").write_text(json.dumps(results, indent=2, default=str))
    print("Wrote data/state/operator_trim_link_btc_30_result.json")
    return 0 if results.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
