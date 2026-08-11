#!/usr/bin/env python3
"""
Promote a pool-cycling shadow proposal into live global_settings.pairs.

Safety:
  - Never eject sticky BTC/ETH
  - Block eject if live held USD >= protect threshold (unless --allow-residual-hold)
  - Backup config before write
  - Record basket pick metrics baseline
  - Does NOT place orders
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.basket_pick_metrics import record_promotion  # noqa: E402
from phase6.core.pool_cycling import (  # noqa: E402
    PROPOSED_PAIRS_JSON,
    TRADING_CONFIG_PHASE6,
    load_holdings_usd,
    run_pool_cycling,
    PoolCyclingConfig,
)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from-proposed",
        action="store_true",
        help="Use data/state/pool_cycling_proposed_pairs.json as-is",
    )
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run pool cycler (holdings-aware) and promote its swap",
    )
    ap.add_argument(
        "--manual-add",
        type=str,
        default="",
        help="Manual promote: add this pair (use with --manual-remove)",
    )
    ap.add_argument(
        "--manual-remove",
        type=str,
        default="",
        help="Manual promote: remove this pair",
    )
    ap.add_argument(
        "--allow-residual-hold",
        action="store_true",
        help="Allow removing a pair that still has live held USD >= protect threshold",
    )
    ap.add_argument(
        "--protect-usd",
        type=float,
        default=40.0,
        help="Block eject when held >= this unless --allow-residual-hold (default 40)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.from_proposed and not args.refresh and not (args.manual_add and args.manual_remove):
        args.refresh = True  # default: honest holdings-aware refresh

    holdings = load_holdings_usd()
    print("Holdings snapshot:", {k: round(v, 2) for k, v in sorted(holdings.items(), key=lambda x: -x[1])[:12]})

    swaps: List[Dict[str, Any]] = []
    proposed_active: List[str] = []
    before: List[str] = []
    source = "pool_cycling"
    methodology: Dict[str, Any] = {}

    if args.manual_add and args.manual_remove:
        tcfg0 = _load_json(TRADING_CONFIG_PHASE6)
        before = list((tcfg0.get("global_settings") or {}).get("pairs") or [])
        rem = args.manual_remove.strip().upper()
        if not rem.endswith("-USD"):
            rem = rem + "-USD" if "-" not in rem else rem
        add = args.manual_add.strip().upper()
        if not add.endswith("-USD"):
            add = add + "-USD" if "-" not in add else add
        # normalize common form
        if not rem.endswith("-USD"):
            rem = f"{rem}-USD"
        if not add.endswith("-USD"):
            add = f"{add}-USD"
        # softer normalize: keep as given if already *-USD
        rem = args.manual_remove if "-USD" in args.manual_remove.upper() else rem
        add = args.manual_add if "-USD" in args.manual_add.upper() else add
        rem = rem.upper() if rem.endswith("-USD") else args.manual_remove
        add = add.upper() if add.endswith("-USD") else args.manual_add
        # Final clean
        rem = str(args.manual_remove).strip()
        add = str(args.manual_add).strip()
        if rem not in before:
            print(f"REFUSE: {rem} not in live basket {before}")
            return 6
        if add in before:
            print(f"REFUSE: {add} already in basket")
            return 7
        held = float(holdings.get(rem, 0.0) or 0.0)
        swaps = [
            {
                "remove": rem,
                "add": add,
                "remove_score": None,
                "add_score": None,
                "delta": None,
                "reason": f"manual promote {rem} -> {add} (operator)",
                "remove_held_usd": held,
            }
        ]
        proposed_active = [add if p == rem else p for p in before]
        source = "manual_operator"
        methodology = {
            "manual": True,
            "rationale": "operator promote; discovery/cycle may have blocked held ejects",
        }
        # Enrich scores from latest cycler/discovery if present
        try:
            if PROPOSED_PAIRS_JSON.exists():
                methodology["last_proposed"] = _load_json(PROPOSED_PAIRS_JSON)
        except Exception:
            pass
        try:
            cpath = PROJECT_ROOT / "data" / "state" / "pair_discovery_contenders.json"
            if cpath.exists():
                methodology["contenders"] = _load_json(cpath)
        except Exception:
            pass
        print("Manual swap prepared:", swaps)
    elif args.refresh:
        report = run_pool_cycling(
            cfg=PoolCyclingConfig(),
            write_log=True,
            write_proposed=True,
            apply_config=False,
        )
        before = list(report.active_pool)
        proposed_active = list(report.proposed_active)
        swaps = list(report.swaps)
        source = "pool_cycling_refresh"
        methodology = {
            "gates": report.gates,
            "note": report.note,
            "top_scores": [
                {"pair": s.get("pair"), "score": s.get("score"), "held_usd": s.get("held_usd")}
                for s in (report.scores or [])[:8]
            ],
        }
        print(report.note)
        print("Refresh swaps:", json.dumps(swaps, indent=2))
    else:
        if not PROPOSED_PAIRS_JSON.exists():
            print("No proposed file", PROPOSED_PAIRS_JSON)
            return 2
        prop = _load_json(PROPOSED_PAIRS_JSON)
        before = list(prop.get("from_active") or [])
        proposed_active = list(prop.get("proposed_active") or [])
        swaps = list(prop.get("swaps") or [])
        source = "pool_cycling_proposed_file"
        methodology = {"proposed_ts": prop.get("ts"), "gate": prop.get("gate")}
        print("Loaded proposed ts", prop.get("ts"))

    if not swaps:
        print("No swaps to promote.")
        return 1

    # Safety gates on each swap
    sticky = {"BTC-USD", "ETH-USD"}
    for sw in swaps:
        rem = sw.get("remove")
        add = sw.get("add")
        if rem in sticky:
            print(f"REFUSE: cannot remove sticky {rem}")
            return 3
        held = float(holdings.get(rem, 0.0) or 0.0)
        # prefer live holdings over stale proposal field
        sw["remove_held_usd_live"] = held
        if held >= args.protect_usd and not args.allow_residual_hold:
            print(
                f"REFUSE: {rem} still held ${held:.2f} (>= ${args.protect_usd:.0f}). "
                f"Use --allow-residual-hold to eject membership while position remains, "
                f"or wait for flat/exit. (Proposal claimed held=${sw.get('remove_held_usd')})"
            )
            return 4
        if not add:
            print("REFUSE: missing add pair")
            return 5

    tcfg = _load_json(TRADING_CONFIG_PHASE6)
    live_before = list((tcfg.get("global_settings") or {}).get("pairs") or [])
    if before and live_before and list(before) != list(live_before):
        print("NOTE: proposal from_active != live pairs; applying swap onto LIVE pairs.")
        before = live_before

    # Apply swaps onto live before list
    after = list(before)
    for sw in swaps:
        rem, add = sw["remove"], sw["add"]
        if rem in after:
            after = [add if p == rem else p for p in after]
        elif add not in after:
            after.append(add)
    # dedupe
    seen = set()
    after_u: List[str] = []
    for p in after:
        if p not in seen:
            seen.add(p)
            after_u.append(p)
    after = after_u

    print("BEFORE:", before)
    print("AFTER: ", after)
    for sw in swaps:
        print(
            f"  {sw.get('remove')} -> {sw.get('add')} "
            f"Δ={sw.get('delta')} held_live=${sw.get('remove_held_usd_live', 0):.2f}"
        )

    if args.dry_run:
        print("DRY RUN — config not written, metrics not recorded.")
        return 0

    # Backup + write
    bak = TRADING_CONFIG_PHASE6.with_suffix(
        TRADING_CONFIG_PHASE6.suffix + f".bak_promote_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(TRADING_CONFIG_PHASE6, bak)
    new_cfg = deepcopy(tcfg)
    new_cfg.setdefault("global_settings", {})["pairs"] = after
    opp = list((new_cfg.get("phase_6_specific") or {}).get("opportunity_pool") or [])
    for p in after:
        if p not in opp:
            opp.append(p)
    # keep removed name in opportunity for possible re-entry research
    for sw in swaps:
        if sw.get("remove") and sw["remove"] not in opp:
            opp.append(sw["remove"])
        if sw.get("add") and sw["add"] not in opp:
            opp.append(sw["add"])
    new_cfg.setdefault("phase_6_specific", {})["opportunity_pool"] = opp
    TRADING_CONFIG_PHASE6.write_text(json.dumps(new_cfg, indent=2) + "\n")
    print(f"Wrote {TRADING_CONFIG_PHASE6} backup={bak.name}")

    # Metrics — one record per swap
    for sw in swaps:
        held = float(sw.get("remove_held_usd_live") or sw.get("remove_held_usd") or 0.0)
        rec = record_promotion(
            add_pair=str(sw["add"]),
            remove_pair=str(sw.get("remove")) if sw.get("remove") else None,
            basket_before=before,
            basket_after=after,
            source=source,
            add_score=sw.get("add_score"),
            remove_score=sw.get("remove_score"),
            delta=sw.get("delta"),
            reason=str(sw.get("reason") or ""),
            remove_held_usd=held,
            residual_hold_allowed=bool(held >= args.protect_usd and args.allow_residual_hold),
            methodology=methodology,
            notes=[
                f"config_backup={bak.name}",
                f"promoted_at={datetime.now(timezone.utc).isoformat()}",
            ],
        )
        print(
            f"Metrics pick_id={rec.pick_id} add={rec.add_pair} "
            f"base_px={rec.baseline_add.get('price')} ok={rec.baseline_add.get('ok')}"
        )

    # Sidecar promote receipt
    receipt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "before": before,
        "after": after,
        "swaps": swaps,
        "backup": str(bak),
        "holdings_at_promote": holdings,
    }
    (PROJECT_ROOT / "data" / "state" / "basket_promote_latest.json").write_text(
        json.dumps(receipt, indent=2, default=str) + "\n"
    )
    # Signal live runner to pick up pairs without process restart
    try:
        flag = PROJECT_ROOT / "data" / "state" / "basket_reload.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(datetime.now(timezone.utc).isoformat() + "\n")
        print(f"Touched {flag.name} — live runner should log [BASKET-RELOAD] within ~60s (no restart).")
    except Exception as e:
        print(f"NOTE: could not write basket_reload.flag: {e}")
    print(
        "Promote complete. No orders placed — membership only. "
        "Hot-reload within ~60s if runner has basket_hot_reload; "
        "restart only if log lacks [BASKET-RELOAD]."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
