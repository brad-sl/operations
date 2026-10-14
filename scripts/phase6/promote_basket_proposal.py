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
        action="append",
        default=[],
        help=(
            "Manual promote: remove this pair. Repeat flag or comma-separate for multi-remove. "
            "With no --manual-add = remove-only hygiene flush (no ADD seat)."
        ),
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
    ap.add_argument(
        "--override-missfire-probation",
        action="store_true",
        help="Allow promote of ADD pairs blocked by miss-fire probation (ledger dig/fast hole)",
    )
    ap.add_argument(
        "--override-novelty-class",
        action="store_true",
        help="Allow promote of ADD pairs blocked by novelty class gate (restricted/hard pin)",
    )
    args = ap.parse_args()

    def _norm_pair(raw: str) -> str:
        s = str(raw or "").strip().upper()
        if not s:
            return ""
        if s.endswith("-USD"):
            return s
        if "-" in s:
            return s
        return f"{s}-USD"

    def _parse_removes(raw_list: List[str]) -> List[str]:
        out: List[str] = []
        seen: set = set()
        for chunk in raw_list or []:
            for part in str(chunk).split(","):
                p = _norm_pair(part)
                if not p or p in seen:
                    continue
                seen.add(p)
                out.append(p)
        return out

    removes = _parse_removes(list(args.manual_remove or []))
    add_one = _norm_pair(args.manual_add) if args.manual_add else ""

    if not args.from_proposed and not args.refresh and not removes and not add_one:
        args.refresh = True  # default: honest holdings-aware refresh

    holdings = load_holdings_usd()
    print("Holdings snapshot:", {k: round(v, 2) for k, v in sorted(holdings.items(), key=lambda x: -x[1])[:12]})

    swaps: List[Dict[str, Any]] = []
    proposed_active: List[str] = []
    before: List[str] = []
    source = "pool_cycling"
    methodology: Dict[str, Any] = {}
    remove_only = False

    if removes and add_one:
        tcfg0 = _load_json(TRADING_CONFIG_PHASE6)
        before = list((tcfg0.get("global_settings") or {}).get("pairs") or [])
        if len(removes) != 1:
            print("REFUSE: swap mode needs exactly one --manual-remove with --manual-add")
            return 6
        rem = removes[0]
        add = add_one
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
    elif removes and not add_one:
        # Hygiene flush: drop dead seats, no ADD (Brad GO remove-only)
        tcfg0 = _load_json(TRADING_CONFIG_PHASE6)
        before = list((tcfg0.get("global_settings") or {}).get("pairs") or [])
        remove_only = True
        source = "manual_hygiene_remove"
        methodology = {
            "manual": True,
            "remove_only": True,
            "rationale": (
                "operator hygiene flush — free seat narrative / eligibility; "
                "no ADD; no orders; open inventory not liquidated"
            ),
        }
        missing = [r for r in removes if r not in before]
        if missing:
            print(f"REFUSE: not in live basket: {missing} (live={before})")
            return 6
        for rem in removes:
            held = float(holdings.get(rem, 0.0) or 0.0)
            swaps.append(
                {
                    "remove": rem,
                    "add": None,
                    "remove_score": None,
                    "add_score": None,
                    "delta": None,
                    "reason": f"hygiene remove-only {rem} (operator Brad GO)",
                    "remove_held_usd": held,
                    "remove_only": True,
                }
            )
        proposed_active = [p for p in before if p not in set(removes)]
        print("Manual remove-only prepared:", swaps)
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
    sticky = {"BTC-USD", "ETH-USD", "PAXG-USD"}
    for sw in swaps:
        rem = sw.get("remove")
        add = sw.get("add")
        is_remove_only = bool(sw.get("remove_only") or remove_only or not add)
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
        if is_remove_only:
            sw["remove_only"] = True
            sw["add"] = None
            # no ADD gates
            continue
        if not add:
            print("REFUSE: missing add pair")
            return 5
        # Miss-fire probation (launch → no explode → dig hole)
        try:
            from phase6.core.missfire_probation import evaluate_pair_missfire

            mf = evaluate_pair_missfire(str(add), enforce=True)
            sw["missfire_probation"] = mf.to_dict()
            if mf.blocked and not args.override_missfire_probation:
                print(
                    f"REFUSE: miss-fire probation blocks ADD {add} "
                    f"[{mf.class_}] {'; '.join(mf.reasons[:3])}. "
                    f"Pass --override-missfire-probation to force (Brad only)."
                )
                return 6
            if mf.blocked and args.override_missfire_probation:
                print(
                    f"WARN: overriding miss-fire probation for {add} "
                    f"[{mf.class_}] {'; '.join(mf.reasons[:3])}"
                )
        except Exception as e:  # noqa: BLE001
            print(f"NOTE: missfire_probation check skipped ({type(e).__name__}: {e})")

        # Novelty class gate (meme/narrative restricted until graduation; reversible)
        try:
            from phase6.core.novelty_class_gate import evaluate_pair_novelty

            nv = evaluate_pair_novelty(str(add), enforce=True, persist_first_seen=True)
            sw["novelty_class"] = nv.to_dict()
            if nv.blocked and not args.override_novelty_class:
                print(
                    f"REFUSE: novelty class blocks ADD {add} "
                    f"[{nv.class_}] {'; '.join(nv.reasons[:3])}. "
                    f"Pass --override-novelty-class to force (Brad only), "
                    f"or graduate via run_novelty_class_gate.py --promote."
                )
                return 7
            if nv.blocked and args.override_novelty_class:
                print(
                    f"WARN: overriding novelty class for {add} "
                    f"[{nv.class_}] {'; '.join(nv.reasons[:3])}"
                )
        except Exception as e:  # noqa: BLE001
            print(f"NOTE: novelty_class check skipped ({type(e).__name__}: {e})")

        # First-fill tag (membership only; live BUY will be tryout-sized)
        try:
            from phase6.core.first_fill_probation import tag_promote_add

            ff = tag_promote_add(str(add))
            sw["first_fill_probation"] = ff
            if ff.get("first_fill_probation"):
                print(
                    f"NOTE: ADD {add} starts under first-fill tryout "
                    f"({', '.join(ff.get('reasons') or [])}). "
                    f"Live BUY haircut via filter_trade_plan_first_fill."
                )
        except Exception as e:  # noqa: BLE001
            print(f"NOTE: first_fill_probation tag skipped ({type(e).__name__}: {e})")

    tcfg = _load_json(TRADING_CONFIG_PHASE6)
    live_before = list((tcfg.get("global_settings") or {}).get("pairs") or [])
    if before and live_before and list(before) != list(live_before):
        print("NOTE: proposal from_active != live pairs; applying swap onto LIVE pairs.")
        before = live_before

    # Apply swaps onto live before list
    after = list(before)
    for sw in swaps:
        rem, add = sw.get("remove"), sw.get("add")
        is_remove_only = bool(sw.get("remove_only") or not add)
        if is_remove_only:
            after = [p for p in after if p != rem]
            continue
        if rem in after:
            after = [add if p == rem else p for p in after]
        elif add and add not in after:
            after.append(str(add))
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
        if sw.get("remove_only") or not sw.get("add"):
            print(
                f"  REMOVE {sw.get('remove')} (no ADD) "
                f"held_live=${sw.get('remove_held_usd_live', 0):.2f}"
            )
        else:
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

    # Metrics — one record per swap (skip promote-seat mint on remove-only)
    hygiene_receipts: List[Dict[str, Any]] = []
    for sw in swaps:
        held = float(sw.get("remove_held_usd_live") or sw.get("remove_held_usd") or 0.0)
        if sw.get("remove_only") or not sw.get("add"):
            hygiene_receipts.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "action": "remove_only",
                    "remove_pair": sw.get("remove"),
                    "held_usd": held,
                    "reason": sw.get("reason"),
                    "source": source,
                    "basket_before": before,
                    "basket_after": after,
                    "config_backup": bak.name,
                    "no_orders": True,
                    "note": "hygiene flush — not a promote seat; not written to basket_pick_metrics",
                }
            )
            print(f"Hygiene receipt REMOVE {sw.get('remove')} held=${held:.2f} (no pick ledger mint)")
            continue
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
                "remove_only=false",
            ],
        )
        print(
            f"Metrics pick_id={rec.pick_id} add={rec.add_pair} "
            f"base_px={rec.baseline_add.get('price')} ok={rec.baseline_add.get('ok')}"
        )

    if hygiene_receipts:
        hpath = PROJECT_ROOT / "data" / "state" / "basket_hygiene_remove_receipts.jsonl"
        with hpath.open("a") as fh:
            for row in hygiene_receipts:
                fh.write(json.dumps(row, default=str) + "\n")
        print(f"Appended {len(hygiene_receipts)} hygiene receipts → {hpath.name}")

    # Sidecar promote receipt
    receipt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "before": before,
        "after": after,
        "swaps": swaps,
        "backup": str(bak),
        "holdings_at_promote": holdings,
        "remove_only": bool(remove_only),
        "no_orders": True,
        "brad_go": True,
        "source": source,
        "hygiene_receipts": hygiene_receipts,
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
