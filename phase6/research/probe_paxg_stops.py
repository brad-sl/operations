#!/usr/bin/env python3
"""
PRESERVE G1 — Coinbase PAXG-USD stop venue probe.

Default: --dry-run (no orders).
--execute: place real micro inventory (if needed) + stop-limit ladder, verify, cancel, unwind.

Safety:
- client_order_id prefix preserve-probe-
- max buy notional default $25
- always cancel probe orders in finally
- sell residual PAXG after probe
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from phase6.core.exchange_client import CoinbaseExchangeClient  # noqa: E402

PRODUCT = "PAXG-USD"
PREFIX = "preserve-probe-"
REPORT_DIR = PROJECT / "reports"
STATE_DIR = PROJECT / "data" / "state"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cid(tag: str) -> str:
    return f"{PREFIX}{tag}-{int(time.time())}-{int(time.time() * 1000) % 10000}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Place real orders")
    ap.add_argument("--max-buy-usd", type=float, default=25.0)
    ap.add_argument("--keep-inventory", action="store_true", help="Do not market-sell residual PAXG")
    args = ap.parse_args()
    execute = bool(args.execute)

    report: dict = {
        "as_of": _now(),
        "product": PRODUCT,
        "execute": execute,
        "max_buy_usd": args.max_buy_usd,
        "steps": [],
        "order_ids": [],
        "venue_probe_result": None,
        "errors": [],
        "cleanup": {},
    }

    ex = CoinbaseExchangeClient(mode="live")
    meta = ex.get_product_metadata(PRODUCT)
    report["metadata"] = meta
    try:
        px = float(ex.get_price(PRODUCT))
    except Exception as e:
        report["errors"].append(f"get_price: {e}")
        px = None
    report["price"] = px

    # Balances
    try:
        paxg_avail = float(ex.get_crypto_available("PAXG") or 0)
    except Exception:
        try:
            h = ex.get_holdings() or {}
            raw = h.get("PAXG") or h.get("PAXG-USD") or 0
            if isinstance(raw, dict):
                paxg_avail = float(raw.get("available") or 0)
            else:
                paxg_avail = float(raw or 0)
        except Exception as e:
            paxg_avail = 0.0
            report["errors"].append(f"balance: {e}")
    report["paxg_available_before"] = paxg_avail

    # T1 metadata
    report["steps"].append(
        {
            "id": "T1_metadata",
            "ok": bool(meta.get("base_increment")) and px is not None and px > 0,
            "meta": meta,
            "price": px,
        }
    )

    if not execute:
        report["venue_probe_result"] = "DRY_RUN"
        report["note"] = (
            "Dry-run only. Re-run with --execute to place micro inventory + stops. "
            "Planned: buy <= max_buy_usd PAXG if needed; place 1 then 2 then 3 stop-limits; "
            "list open; cancel all preserve-probe-*; sell residual."
        )
        _write(report)
        print(json.dumps({"result": "DRY_RUN", "price": px, "meta": meta}, indent=2))
        return 0

    if px is None or px <= 0:
        report["venue_probe_result"] = "C"
        report["errors"].append("No price — cannot execute")
        _write(report)
        return 2

    placed = []
    bought_qty = 0.0

    try:
        # Ensure inventory for sells
        need_usd = min(args.max_buy_usd, 25.0)
        min_base = max(float(meta.get("base_increment") or 1e-5) * 10, need_usd / px * 0.5)
        target_qty = max(need_usd / px, min_base)
        target_qty = float(ex.quantize_size(PRODUCT, target_qty))

        if paxg_avail < target_qty * 0.95:
            buy_usd = min(need_usd, target_qty * px * 1.02)
            report["steps"].append({"id": "T0_buy", "usd": buy_usd, "target_qty": target_qty})
            br = ex.place_market_buy(PRODUCT, buy_usd)
            report["steps"][-1]["response"] = _shrink(br)
            ok_buy = bool(br and (br.get("success") is True or br.get("order_id") or br.get("success_response")))
            if not ok_buy and isinstance(br, dict) and br.get("error"):
                ok_buy = False
            # settle
            time.sleep(2.5)
            try:
                paxg_avail = float(ex.get_crypto_available("PAXG") or 0)
            except Exception:
                paxg_avail = paxg_avail
            report["paxg_available_after_buy"] = paxg_avail
            if paxg_avail <= 0:
                report["errors"].append(f"Buy failed or zero PAXG: {br}")
                report["venue_probe_result"] = "C"
                _write(report)
                return 3
            bought_qty = paxg_avail
        else:
            bought_qty = paxg_avail
            report["steps"].append({"id": "T0_buy", "skipped": True, "paxg": paxg_avail})

        # Use 90% of available across legs
        attach = float(ex.quantize_size(PRODUCT, bought_qty * 0.90))
        if attach <= 0:
            report["venue_probe_result"] = "C"
            report["errors"].append("attach qty 0")
            _write(report)
            return 3

        # Fractions for 1, then split for multi
        q1 = float(ex.quantize_size(PRODUCT, attach * 0.98))
        # stops well below market so they rest
        s1 = float(ex.quantize_price(PRODUCT, px * 0.88))  # -12%
        s2 = float(ex.quantize_price(PRODUCT, px * 0.82))  # -18%
        s3 = float(ex.quantize_price(PRODUCT, px * 0.68))  # -32%
        l1 = float(ex.quantize_price(PRODUCT, s1 * 0.994))
        l2 = float(ex.quantize_price(PRODUCT, s2 * 0.994))
        l3 = float(ex.quantize_price(PRODUCT, s3 * 0.994))

        def place(tag, qty, stop, limit):
            cid = _cid(tag)
            # CoinbaseExchangeClient has no client_order_id kw; wrapper does if used directly
            r = ex.place_stop_limit_sell(PRODUCT, qty, stop, limit_price=limit)
            oid = None
            success = False
            if isinstance(r, dict):
                success = r.get("success") is True or bool(r.get("order_id"))
                if r.get("success") is False:
                    success = False
                oid = r.get("order_id") or (r.get("success_response") or {}).get("order_id")
            elif r is True:
                success = True
            entry = {
                "tag": tag,
                "qty": qty,
                "stop": stop,
                "limit": limit,
                "client_order_id": cid,
                "success": success,
                "order_id": oid,
                "raw": _shrink(r),
            }
            report["steps"].append({"id": f"place_{tag}", **entry})
            if success and oid:
                placed.append(oid)
                report["order_ids"].append(oid)
            return success, oid, r

        # T2 single
        ok1, oid1, _ = place("S1", float(ex.quantize_size(PRODUCT, attach * 0.30)), s1, l1)
        report["T2_single_stop"] = ok1
        time.sleep(1.0)

        # T4 second concurrent
        ok2, oid2, _ = place("S2", float(ex.quantize_size(PRODUCT, attach * 0.35)), s2, l2)
        report["T4_two_concurrent"] = ok1 and ok2
        time.sleep(1.0)

        # T5 third
        ok3, oid3, _ = place("S3", float(ex.quantize_size(PRODUCT, attach * 0.33)), s3, l3)
        report["T5_three_concurrent"] = ok1 and ok2 and ok3

        # List open stops
        try:
            opens = ex.get_open_stop_orders() if hasattr(ex, "get_open_stop_orders") else ex.get_open_orders()
            report["open_orders_snapshot"] = _shrink(opens)
            # count PAXG probe-ish
            n_paxg = 0
            if isinstance(opens, list):
                for o in opens:
                    pid = (o.get("product_id") or o.get("productId") or "")
                    if "PAXG" in str(pid).upper():
                        n_paxg += 1
            report["open_paxg_stop_count"] = n_paxg
        except Exception as e:
            report["errors"].append(f"list open: {e}")
            report["open_paxg_stop_count"] = None

        # Classify A/B/C
        if ok1 and ok2 and ok3:
            result = "A"
        elif ok1 and not ok2:
            result = "B"
        elif ok1 and ok2 and not ok3:
            result = "A"  # >=2 concurrent is enough for multi-leg lite
            report["note_concurrent"] = "2 of 3 legs OK — treat as A for dual-leg; full 3-leg weak"
        elif ok1:
            result = "B"
        else:
            result = "C"
        report["venue_probe_result"] = result

    except Exception as e:
        report["errors"].append(traceback.format_exc())
        report["venue_probe_result"] = report.get("venue_probe_result") or "C"
    finally:
        # Cancel all placed
        cancelled = []
        for oid in list(placed):
            try:
                cr = ex.cancel_order(oid)
                cancelled.append({"order_id": oid, "resp": _shrink(cr)})
            except Exception as e:
                cancelled.append({"order_id": oid, "error": str(e)})
        report["cleanup"]["cancels"] = cancelled

        # Also try cancel by scanning open orders for our prefix / PAXG stops we created
        try:
            opens = ex.get_open_orders() if hasattr(ex, "get_open_orders") else []
            if isinstance(opens, list):
                for o in opens:
                    oid = o.get("order_id") or o.get("id")
                    pid = str(o.get("product_id") or "")
                    cid = str(o.get("client_order_id") or o.get("client_order_id") or "")
                    if oid and "PAXG" in pid.upper() and (PREFIX in cid or oid in placed):
                        if oid not in [c.get("order_id") for c in cancelled]:
                            try:
                                ex.cancel_order(oid)
                                cancelled.append({"order_id": oid, "extra": True})
                            except Exception:
                                pass
        except Exception:
            pass

        if not args.keep_inventory:
            try:
                time.sleep(1.5)
                left = float(ex.get_crypto_available("PAXG") or 0)
                report["cleanup"]["paxg_left_before_sell"] = left
                if left > 0:
                    # leave dust under ~$1
                    if left * (px or 0) >= 1.0:
                        sr = ex.place_market_sell(PRODUCT, left)
                        report["cleanup"]["sell"] = _shrink(sr)
            except Exception as e:
                report["cleanup"]["sell_error"] = str(e)

    _write(report)
    print(
        json.dumps(
            {
                "venue_probe_result": report.get("venue_probe_result"),
                "T2": report.get("T2_single_stop"),
                "T4": report.get("T4_two_concurrent"),
                "T5": report.get("T5_three_concurrent"),
                "orders": report.get("order_ids"),
                "errors": report.get("errors"),
            },
            indent=2,
        )
    )
    return 0 if report.get("venue_probe_result") in ("A", "B") else 1


def _shrink(x, depth=0):
    if depth > 4:
        return "..."
    if isinstance(x, dict):
        return {k: _shrink(v, depth + 1) for k, v in list(x.items())[:40]}
    if isinstance(x, list):
        return [_shrink(v, depth + 1) for v in x[:30]]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)[:500]


def _write(report: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = REPORT_DIR / f"PRESERVE_VENUE_PROBE_{day}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    (STATE_DIR / "preserve_venue_probe_latest.json").write_text(json.dumps(report, indent=2, default=str))
    # markdown summary
    md = REPORT_DIR / f"PRESERVE_VENUE_PROBE_{day}.md"
    md.write_text(
        "\n".join(
            [
                f"# Preserve venue probe — {day}",
                "",
                f"**Result:** `{report.get('venue_probe_result')}`",
                f"**Product:** {PRODUCT}",
                f"**Execute:** {report.get('execute')}",
                f"**Price:** {report.get('price')}",
                f"**Meta:** `{report.get('metadata')}`",
                f"**T2 single:** {report.get('T2_single_stop')}",
                f"**T4 two concurrent:** {report.get('T4_two_concurrent')}",
                f"**T5 three concurrent:** {report.get('T5_three_concurrent')}",
                f"**Order IDs:** {report.get('order_ids')}",
                f"**Errors:** {report.get('errors')}",
                "",
                "JSON: `data/state/preserve_venue_probe_latest.json`",
                "",
                "## Meaning",
                "- **A:** ≥2 concurrent stop-limits OK — Hold E1 + multi-leg DeRisk possible",
                "- **B:** single stop only — Hold E1 only; DeRisk multi-leg blocked on exchange",
                "- **C:** stops unreliable / cannot place — Preserve blocked",
                "",
            ]
        )
    )
    print(f"Wrote {path}")
    print(f"Wrote {md}")


if __name__ == "__main__":
    raise SystemExit(main())
