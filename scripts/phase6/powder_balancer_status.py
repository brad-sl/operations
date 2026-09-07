#!/usr/bin/env python3
"""Powder balancer status / dry-run CLI.

  python scripts/phase6/powder_balancer_status.py
  python scripts/phase6/powder_balancer_status.py --plan-only
  python scripts/phase6/powder_balancer_status.py --dry-run   # shadow execute path
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Powder balancer monitor")
    ap.add_argument("--account", default=None, help="portfolio uuid / account id")
    ap.add_argument("--plan-only", action="store_true", help="plan from live balances, no trade path")
    ap.add_argument("--dry-run", action="store_true", help="run execute path in dry_run")
    ap.add_argument("--json", action="store_true", help="raw JSON only")
    args = ap.parse_args()

    from phase6.core.param_audit import resolve_account_id_from_exchange
    from phase6.core.powder_balancer import (
        monitor_powder_snapshot,
        execute_powder_balance,
        STATUS_PATH,
    )
    from phase6.core.trader_account_config import live_usdc_park_settings

    # Prefer live balances via exchange if available
    usd = usdc = crypto = 0.0
    account_id = args.account or "default"
    config_dict = {}
    try:
        from phase6.core.exchange_client import ExchangeClient

        ex = ExchangeClient()
        from phase6.core.param_audit import resolve_account_id_from_exchange

        account_id = args.account or resolve_account_id_from_exchange(ex) or account_id
        usd = float(ex.get_account_balance("USD") or 0.0)
        usdc = float(ex.get_account_balance("USDC") or 0.0)
    except Exception as e:
        # fall back to live_state
        ls = ROOT / "data/state/phase6_live_state.json"
        try:
            raw = json.loads(ls.read_text())
            bals = raw.get("balances") or []
            if isinstance(bals, list):
                for row in bals:
                    if not isinstance(row, dict):
                        continue
                    cur = str(row.get("currency") or "").upper()
                    bal = float(row.get("balance") or row.get("available") or 0)
                    if cur == "USD":
                        usd = bal
                    elif cur == "USDC":
                        usdc = bal
            elif isinstance(bals, dict):
                usd = float(bals.get("USD") or bals.get("usd") or 0)
                usdc = float(bals.get("USDC") or bals.get("usdc") or 0)
            if not usd:
                usd = float(raw.get("cash_usd") or 0)
            pos = raw.get("positions") or raw.get("trading_positions") or []
            if isinstance(pos, list):
                for row in pos:
                    if not isinstance(row, dict):
                        continue
                    pair = str(row.get("pair") or "")
                    if pair.upper().startswith("USD"):
                        continue
                    crypto += float(row.get("value_usd") or 0)
            elif isinstance(pos, dict):
                for k, v in pos.items():
                    if str(k).upper() in ("USD", "USDC"):
                        continue
                    if isinstance(v, dict):
                        crypto += float(v.get("value_usd") or v.get("usd_value") or 0)
                    else:
                        crypto += float(v or 0)
            print(f"(balances from live_state; exchange err: {type(e).__name__}: {e})", file=sys.stderr)
        except Exception as e2:
            print(f"balance read failed: {e} / {e2}", file=sys.stderr)
            return 1

    # Load trading config for wave need
    try:
        tc = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
        config_dict = tc
        rcp = json.loads((ROOT / "config/regime_cash_policy.json").read_text())
        config_dict = {
            **tc,
            "regime_cash_policy": rcp,
            "operator_override": rcp.get("operator_override"),
            "global_settings": tc.get("global_settings") or {},
        }
        # merge live rebalance cap from regime status if present
        rs = ROOT / "data/state/regime_cash_status.json"
        if rs.exists():
            st = json.loads(rs.read_text())
            cap = (st.get("snapshot") or st).get("rebalance_cap_usd")
            if cap is not None:
                config_dict.setdefault("global_settings", {})["rebalance_cap_usd"] = cap
            sm = (st.get("snapshot") or st).get("strategy_mode")
            if sm:
                config_dict.setdefault("global_settings", {})["strategy_mode"] = sm
    except Exception:
        pass

    park = live_usdc_park_settings(account_id)
    mon = monitor_powder_snapshot(
        usd=usd,
        usdc=usdc,
        crypto_usd=crypto,
        park_cfg=park,
        config_dict=config_dict,
        park_master_enabled=bool(park.get("enabled")),
    )

    if args.dry_run:
        from unittest.mock import MagicMock

        runner = MagicMock()
        runner.mode = "shadow"
        runner.config_dict = config_dict
        runner.account_id = account_id
        runner.exchange = MagicMock()
        runner.exchange.get_account_balance = lambda c: {
            "USD": usd,
            "USDC": usdc,
        }.get(c, 0)
        runner.portfolio = MagicMock()
        runner.portfolio.get_enriched_positions.return_value = {"positions": {}}
        runner.portfolio.refresh = MagicMock()
        runner.FIXED_UNIVERSE = []
        runner.order_executor = MagicMock()
        out = execute_powder_balance(runner, park, account_id=account_id, dry_run=True)
        payload = {"monitor": mon, "dry_run": out, "status_path": str(STATUS_PATH)}
    else:
        payload = {"monitor": mon, "account_id": account_id, "status_path": str(STATUS_PATH)}
        # always refresh status file from monitor
        from phase6.core.powder_balancer import write_powder_status

        write_powder_status(
            {
                "ok": True,
                "source": "cli_monitor",
                "account_id": account_id,
                "action": mon.get("action"),
                "reason": mon.get("reason"),
                "plan": mon,
                "target_usd_reserve": mon.get("target_usd_reserve"),
                "structural_stub_usd": mon.get("structural_stub_usd"),
                "snap_before": {"usd": usd, "usdc": usdc, "crypto_usd": crypto},
            }
        )

    if args.json or args.plan_only:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    m = mon
    print("=== Powder balancer ===")
    print(f"account: {account_id}")
    print(f"USD ${usd:.2f}  USDC ${usdc:.2f}  crypto ~${crypto:.2f}")
    print(f"target USD reserve: ${m.get('target_usd_reserve', 0):.2f}")
    print(f"structural stub:    ${m.get('structural_stub_usd', 0):.2f}")
    print(f"wave: {m.get('wave')}")
    print(f"action: {m.get('action')}  reason: {m.get('reason')}")
    if m.get("convert_usd"):
        print(f"  would park USD→USDC: ${m['convert_usd']:.2f}")
    if m.get("unwind_usd"):
        print(f"  would top-up USDC→USD: ${m['unwind_usd']:.2f}")
    print(f"availability_ok: {m.get('availability_ok')}")
    print(f"enabled: master={park.get('enabled')} powder={park.get('powder_balancer', {}).get('enabled')}")
    print(f"status: {STATUS_PATH}")
    print()
    print(m.get("crypto_in_play_note", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
