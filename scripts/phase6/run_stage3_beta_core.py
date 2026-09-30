#!/usr/bin/env python3
"""Stage 3 BTC/ETH beta core clip.

Default is dry-run. Money requires --go AND --live.

  .venv/bin/python scripts/phase6/run_stage3_beta_core.py
  .venv/bin/python scripts/phase6/run_stage3_beta_core.py --go --live --json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.beta_core import (  # noqa: E402
    CORE_LIMIT_FIRST_CFG,
    DEFAULT_CLIP_USD,
    plan_beta_core,
)
from phase6.core.paths import PROJECT_ROOT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("stage3_beta_core")

LIVE_STATE = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"
REGIME = PROJECT_ROOT / "data" / "state" / "regime_cash_status.json"
OUT = PROJECT_ROOT / "data" / "state" / "stage3_beta_core_latest.json"


def _load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _usd_usdc(live: Dict[str, Any]) -> tuple[float, float, float]:
    usd = float(live.get("cash_usd") or 0)
    usdc = 0.0
    for b in live.get("balances") or []:
        ccy = str(b.get("currency") or "").upper()
        if ccy == "USD":
            usd = float(b.get("available") or b.get("balance") or usd or 0)
        if ccy == "USDC":
            usdc = float(b.get("available") or b.get("balance") or 0)
    eq = float(live.get("total_usd") or 0) or (usd + usdc)
    return eq, usd, usdc


def _held(live: Dict[str, Any]) -> list:
    return [str(p.get("pair") or "") for p in (live.get("positions") or [])]


def _write(payload: Dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip-usd", type=float, default=DEFAULT_CLIP_USD)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    live = _load(LIVE_STATE)
    status = _load(REGIME)
    eq, usd, usdc = _usd_usdc(live)
    plan = plan_beta_core(
        equity=eq,
        usd=usd,
        usdc=usdc,
        status=status,
        clip_usd=float(args.clip_usd),
        held=_held(live),
    )
    money = bool(args.go) and bool(args.live)
    out: Dict[str, Any] = {
        "schema": "stage3_beta_core_v1",
        "go": bool(args.go),
        "live": bool(args.live),
        "money": money,
        "plan": plan.to_dict(),
        "unwind": None,
        "buys": [],
    }

    if plan.status != "planned":
        _write(out)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"blocked: {plan.reasons}")
        return 1

    if not money:
        out["note"] = "dry_run — would unwind then limit-buy BTC/ETH skip_sl"
        _write(out)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(
                f"dry plan clip=${plan.clip_usd:.0f} BTC=${plan.btc_usd:.0f} "
                f"ETH=${plan.eth_usd:.0f} unwind=${plan.unwind_usdc_usd:.0f} skip_sl={plan.skip_sl}"
            )
        return 0

    from phase6.core.tryout_scale_up_live import _build_executor
    from phase6.core.usdc_convert import convert_usdc_to_usd

    exor = _build_executor(shadow_mode=False)
    ex = exor.exchange
    if plan.unwind_usdc_usd >= 1.0:
        log.info("[STAGE3] unwind USDC→USD $%.2f", plan.unwind_usdc_usd)
        conv = convert_usdc_to_usd(ex, plan.unwind_usdc_usd)
        out["unwind"] = conv
        if not conv.get("success"):
            out["error"] = "unwind_failed"
            _write(out)
            if args.json:
                print(json.dumps(out, indent=2, default=str))
            return 2

    for leg in plan.legs:
        log.info("[STAGE3] buy %s $%.2f skip_sl", leg.pair, leg.usd)
        buy = exor.execute_buy(
            leg.pair,
            float(leg.usd),
            skip_sl=True,
            config_dict=CORE_LIMIT_FIRST_CFG,
            force_market=False,
        )
        out["buys"].append({"pair": leg.pair, "usd": leg.usd, "result": buy})
        log.info(
            "[STAGE3] %s ok=%s sl=%s oid=%s style=%s",
            leg.pair,
            buy.get("success"),
            buy.get("sl_attached"),
            buy.get("order_id"),
            buy.get("execution_style"),
        )

    filled = [b for b in out["buys"] if (b.get("result") or {}).get("success")]
    out["ok"] = bool(filled)
    out["any_sl_attached"] = any(
        (b.get("result") or {}).get("sl_attached") for b in out["buys"]
    )
    _write(out)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"ok={out['ok']} fills={len(filled)} sl_attached={out['any_sl_attached']}")
    return 0 if out["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
