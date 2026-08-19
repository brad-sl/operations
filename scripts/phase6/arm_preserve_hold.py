#!/usr/bin/env python3
"""
Operator tool: arm / disarm / status Preserve Hold.

Defaults refuse live arm unless --i-understand and config preserve_mode.enabled=true
(or --set-enabled which flips enabled in config — still requires --i-understand for live).

Examples:
  PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py status
  PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --dry-run
  PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --i-understand
  PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py disarm --i-understand
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from phase6.core.exchange_client import CoinbaseExchangeClient  # noqa: E402
from phase6.core.preserve_hold import (  # noqa: E402
    arm_preserve_hold,
    disarm_preserve_hold,
    load_preserve_config,
    maybe_preserve_hold_tick,
    status_snapshot,
)


def load_cfg() -> dict:
    p = PROJECT / "config" / "trading_config_phase6.json"
    return json.loads(p.read_text(encoding="utf-8"))


def save_cfg(cfg: dict) -> None:
    p = PROJECT / "config" / "trading_config_phase6.json"
    p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "arm", "disarm", "tick"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--i-understand", action="store_true", help="Allow live buy/stop/sell")
    ap.add_argument("--set-enabled", action="store_true", help="Set preserve_mode.enabled=true in config before arm")
    ap.add_argument("--force", action="store_true", help="Bypass crypto-parked / enabled checks")
    ap.add_argument(
        "--micro",
        action="store_true",
        help="Arm small fixed USD sleeve (preserve_mode.micro_usd, default $75) for logging — not full 20%",
    )
    ap.add_argument("--micro-usd", type=float, default=None, help="Override micro USD size")
    args = ap.parse_args()

    cfg = load_cfg()
    if args.cmd == "status":
        # Prefer live exchange so e1_open is truthful (falls back to disk state)
        try:
            ex = CoinbaseExchangeClient(mode="live")
            print(json.dumps(status_snapshot(cfg, exchange=ex), indent=2, default=str))
        except Exception:
            print(json.dumps(status_snapshot(cfg), indent=2, default=str))
        return 0

    if args.cmd == "tick":
        ex = CoinbaseExchangeClient(mode="live")
        print(json.dumps(maybe_preserve_hold_tick(exchange=ex, full_config=cfg), indent=2, default=str))
        return 0

    if args.cmd == "arm":
        if args.set_enabled:
            cfg.setdefault("preserve_mode", {})["enabled"] = True
        if args.micro:
            cfg.setdefault("preserve_mode", {})["micro_live"] = True
            if args.micro_usd is not None:
                cfg["preserve_mode"]["micro_usd"] = float(args.micro_usd)
            cfg["preserve_mode"]["enabled"] = True
            save_cfg(cfg)
            print(
                "Micro live:",
                cfg["preserve_mode"].get("micro_usd"),
                "enabled=true",
            )
        elif args.set_enabled:
            save_cfg(cfg)
            print("Set preserve_mode.enabled=true")
        if not args.dry_run and not args.i_understand:
            print("Refusing live arm without --i-understand (use --dry-run to preview)")
            return 2
        ex = CoinbaseExchangeClient(mode="live")
        max_buy = None
        if args.micro or (cfg.get("preserve_mode") or {}).get("micro_live"):
            max_buy = float(
                args.micro_usd
                if args.micro_usd is not None
                else (cfg.get("preserve_mode") or {}).get("micro_usd")
                or 75.0
            )
        r = arm_preserve_hold(
            ex,
            cfg,
            force=args.force,
            dry_run=args.dry_run,
            max_buy_usd=max_buy,
        )
        print(json.dumps(r, indent=2, default=str))
        return 0 if r.get("ok") else 1

    if args.cmd == "disarm":
        if not args.i_understand:
            print("Refusing disarm without --i-understand")
            return 2
        ex = CoinbaseExchangeClient(mode="live")
        r = disarm_preserve_hold(ex, cfg, sell=True)
        print(json.dumps(r, indent=2, default=str))
        return 0 if r.get("ok") else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
