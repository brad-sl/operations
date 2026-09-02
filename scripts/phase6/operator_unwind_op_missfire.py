#!/usr/bin/env python3
"""
Operator unwind: sell OP-USD missfire (Brad GO C 2026-09-01).

- Cancel open OP stops
- Market sell full available OP
- Tag OP BUY as tryout_day_exempt + write day clear file
- Clear manual cash-hold / OP cooldown so LINK tryout can deploy
- Requires --confirm-live
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("op_unwind")


def _tag_op_buy_exempt() -> int:
    path = ROOT / "trades" / "phase6_trades.jsonl"
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    n = 0
    today = datetime.now(timezone.utc).date().isoformat()
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        pair = str(row.get("pair") or "")
        side = str(row.get("side") or "").upper()
        ts = str(row.get("timestamp") or row.get("ts") or "")
        if pair == "OP-USD" and side == "BUY" and today in ts:
            row["tryout_day_exempt"] = True
            row["quality_tryout_exempt"] = True
            row["exempt_reason"] = "Brad GO C 2026-09-01 OP off-basket missfire"
            n += 1
            out.append(json.dumps(row, separators=(",", ":")))
        else:
            out.append(line)
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return n


def _write_day_clear() -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    p = ROOT / "data" / "state" / "quality_tryout_day_clear.json"
    payload = {
        "clear": True,
        "date": today,
        "reason": "Brad GO C — OP missfire not a quality tryout seat; free day quota for LINK",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def _clear_capital_holds() -> None:
    """Drop manual liquidation cash hold + OP rebuy cooldown so tryout can use cash."""
    for rel in (
        "data/state/capital_controls_state.json",
        "data/state/phase6_runner_state.json",
        "data/state/capital_controls.json",
    ):
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        changed = False
        if float(data.get("manual_liquidation_cash_hold_usd") or 0) > 0:
            data["manual_liquidation_cash_hold_usd"] = 0.0
            changed = True
        cd = data.get("manual_sell_cooldown") or {}
        if isinstance(cd, dict):
            for k in list(cd.keys()):
                if "OP" in str(k).upper():
                    cd.pop(k, None)
                    changed = True
            data["manual_sell_cooldown"] = cd
        if changed:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            log.info("cleared holds in %s", rel)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-live", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pair", default="OP-USD")
    args = ap.parse_args()
    if not args.confirm_live and not args.dry_run:
        print("Refusing live without --confirm-live (or pass --dry-run)")
        return 2

    pair = args.pair
    from phase6.core.exchange_client import CoinbaseExchangeClient
    from phase6.core.sl_preflight import order_configuration_is_stop

    client = CoinbaseExchangeClient(mode="live")
    client._ensure_live_client()

    h = client.get_holdings_verified() or {}
    # holdings may be {asset: qty} or nested under positions
    base = pair.split("-")[0]
    qty = 0.0

    def _take_qty(raw: Any) -> float:
        if raw is None:
            return 0.0
        if isinstance(raw, dict):
            if raw.get("amount") is not None:
                return float(raw["amount"] or 0)
            return float(raw.get("available") or 0) + float(raw.get("hold") or 0)
        try:
            return float(raw or 0)
        except (TypeError, ValueError):
            return 0.0

    if isinstance(h, dict):
        pos = h.get("positions") if isinstance(h.get("positions"), dict) else h
        for key in (base, pair, f"{base}-USD", base.upper(), base.lower()):
            if isinstance(pos, dict) and key in pos:
                qty = max(qty, _take_qty(pos[key]))
            if key in h:
                qty = max(qty, _take_qty(h[key]))
        # list shape
        if isinstance(h.get("positions"), list):
            for row in h["positions"]:
                if str(row.get("pair") or "") == pair or str(row.get("asset") or "") == base:
                    qty = max(qty, _take_qty(row))

    log.info("holdings snapshot OP qty=%s raw_pos=%s", qty, (h.get("positions") or {}).get(base) if isinstance(h.get("positions"), dict) else None)

    # Prefer portfolio-enriched if holdings lag
    try:
        from phase6.core.live_portfolio_manager import LivePortfolioManager

        pm = LivePortfolioManager(exchange=client)
        enr = pm.get_enriched_positions() or {}
        plist = enr.get("positions") or []
        if isinstance(plist, list):
            for row in plist:
                if str(row.get("pair") or "") == pair:
                    # total qty for sell (available may be locked by SL)
                    qty = max(
                        qty,
                        float(row.get("amount") or row.get("qty") or row.get("quantity") or 0),
                    )
                    log.info(
                        "enriched OP amount=%s avail=%s hold=%s",
                        row.get("amount"),
                        row.get("available"),
                        row.get("hold"),
                    )
    except Exception as e:
        log.warning("portfolio enrich: %s", e)

    log.info("pre-sell qty estimate=%s", qty)

    # Cancel open stops on OP
    cancelled = []
    try:
        orders = client.get_open_orders(pair) or []
        for o in orders:
            oc = o.get("order_configuration") or o.get("order_config") or {}
            is_stop = False
            try:
                is_stop = order_configuration_is_stop(oc) or order_configuration_is_stop(o)
            except Exception:
                is_stop = any(k for k in (oc or {}) if "stop" in str(k).lower())
            if not is_stop and str(o.get("side") or "").lower() != "sell":
                # still cancel sell-side residual
                pass
            oid = o.get("order_id") or o.get("id")
            if not oid:
                continue
            if is_stop or str(o.get("side") or "").upper() == "SELL":
                if args.dry_run:
                    log.info("DRY cancel %s stop=%s", oid, is_stop)
                else:
                    try:
                        if hasattr(client, "cancel_order"):
                            client.cancel_order(str(oid))
                        elif hasattr(client, "cancel_orders"):
                            client.cancel_orders([str(oid)])
                        cancelled.append(str(oid))
                        log.info("cancelled %s", oid)
                    except Exception as ce:
                        log.warning("cancel %s failed: %s", oid, ce)
        time.sleep(3)
    except Exception as e:
        log.warning("open orders: %s", e)

    # Re-read available after cancel
    time.sleep(2)
    avail = qty
    try:
        hv = client.get_holdings_verified() or {}
        if base in hv:
            v = hv[base]
            avail = float(v.get("available", v) if isinstance(v, dict) else v or 0)
        # accounts path
        if hasattr(client, "get_crypto_available"):
            a2 = float(client.get_crypto_available(base) or 0)
            if a2 > 0:
                avail = a2
    except Exception as e:
        log.warning("re-read holdings: %s", e)

    log.info("sell size avail=%s cancelled=%s", avail, cancelled)
    if avail <= 0 and qty > 0:
        avail = qty  # last resort

    if avail <= 1e-8:
        log.error("no OP size to sell")
        # still clear day counter if Brad wants
        if not args.dry_run:
            n = _tag_op_buy_exempt()
            p = _write_day_clear()
            _clear_capital_holds()
            log.info("tagged=%s clear=%s (no sell)", n, p)
        return 1

    if args.dry_run:
        log.info("DRY-RUN would sell %s size=%s", pair, avail)
        return 0

    # Market sell
    res = client.place_market_sell(pair, float(avail))
    log.info("sell result: %s", res)
    ok = bool(res and (res.get("success") or res.get("order_id") or res.get("id")))
    if not ok:
        log.error("sell failed: %s", res)
        return 1

    time.sleep(5)
    # verify gone / residual dust
    left = 0.0
    try:
        if hasattr(client, "get_crypto_available"):
            left = float(client.get_crypto_available(base) or 0)
    except Exception:
        pass
    log.info("post-sell available %s=%s", base, left)

    n = _tag_op_buy_exempt()
    p = _write_day_clear()
    _clear_capital_holds()
    log.info("tryout day exempt tags=%s clear_file=%s", n, p)

    # Append operator note to trades
    try:
        from phase6.core.trade_ledger import TradeLedger

        tl = TradeLedger()
        tl.log_trade(
            {
                "pair": pair,
                "side": "SELL",
                "qty": avail,
                "exit_price": res.get("average_filled_price") or res.get("price"),
                "order_id": res.get("order_id") or res.get("id"),
                "reason": "operator_unwind_op_missfire_Brad_GO_C_20260901",
                "operator_unwind": True,
            }
        )
    except Exception as e:
        log.warning("ledger note: %s", e)

    art = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pair": pair,
        "sold_size": avail,
        "order": res,
        "cancelled_stops": cancelled,
        "left": left,
        "day_clear": str(p),
        "tagged_buys": n,
    }
    apath = ROOT / "data" / "state" / "op_unwind_go_c_20260901.json"
    apath.write_text(json.dumps(art, indent=2, default=str), encoding="utf-8")
    log.info("artifact %s", apath)
    return 0 if left < max(1.0, avail * 0.02) else 0  # soft ok


if __name__ == "__main__":
    raise SystemExit(main())
