#!/usr/bin/env python3
"""One-call Brad-GO basket membership swap (no orders).

Default: dry-run the latest dual_agree REMOVE→ADD.
Apply only with --go. live_membership_swaps stays OFF. No force rebalance.

Examples (simple tool call):
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/basket_swap.py
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/basket_swap.py --go
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/basket_swap.py --go --override-novelty
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/basket_swap.py NEAR HYPE --go
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/basket_swap.py --remove NEAR-USD --add HYPE-USD --go
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DUAL_AGREE_LATEST = PROJECT_ROOT / "data" / "state" / "basket_dual_agree_latest.json"
DUAL_AGREE_ARM = (
    PROJECT_ROOT / "data" / "state" / "basket_select_arms" / "dual_agree" / "latest.json"
)
DECISION = PROJECT_ROOT / "data" / "state" / "basket_swap_brad_decision.json"
TRADING_CFG = PROJECT_ROOT / "config" / "trading_config_phase6.json"
PROMOTE = PROJECT_ROOT / "scripts" / "phase6" / "promote_basket_proposal.py"
RECEIPT = PROJECT_ROOT / "data" / "state" / "basket_swap_simple_latest.json"
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python3"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _norm_pair(raw: str) -> str:
    s = str(raw or "").strip().upper().replace("_", "-")
    if not s:
        raise ValueError("empty pair")
    if s.endswith("-USD"):
        return s
    if "-" in s:
        return s if s.endswith("USD") else f"{s}-USD"
    return f"{s}-USD"


def _pairs() -> List[str]:
    cfg = _load(TRADING_CFG)
    return list((cfg.get("global_settings") or {}).get("pairs") or [])


def _holdings() -> Dict[str, float]:
    try:
        from phase6.core.pool_cycling import load_holdings_usd

        return {str(k): float(v or 0.0) for k, v in (load_holdings_usd() or {}).items()}
    except Exception:
        return {}


def _decision_live_swaps() -> bool:
    try:
        d = _load(DECISION)
        return bool(d.get("live_membership_swaps"))
    except Exception:
        return False


def _dual_agree_swap() -> Optional[Tuple[str, str, Dict[str, Any]]]:
    for path in (DUAL_AGREE_LATEST, DUAL_AGREE_ARM):
        if not path.exists():
            continue
        try:
            d = _load(path)
        except Exception:
            continue
        run = d.get("this_run") or {}
        rem = run.get("remove")
        add = run.get("add")
        if rem and add and run.get("agreed", True):
            meta = {
                "source": "dual_agree.this_run",
                "path": str(path),
                "ts": d.get("ts"),
                "agree_arms": d.get("agree_arms"),
                "reason": (d.get("new_agreements") or [{}])[0].get("reason"),
            }
            return str(rem), str(add), meta
        news = d.get("new_agreements") or []
        if news:
            n0 = news[0] or {}
            if n0.get("remove") and n0.get("add"):
                meta = {
                    "source": "dual_agree.new_agreements[0]",
                    "path": str(path),
                    "ts": n0.get("ts") or d.get("ts"),
                    "agree_arms": n0.get("agree_arms") or d.get("agree_arms"),
                    "reason": n0.get("reason"),
                    "proposal_id": n0.get("proposal_id"),
                }
                return str(n0["remove"]), str(n0["add"]), meta
    return None


def _preflight(rem: str, add: str, protect_usd: float) -> Dict[str, Any]:
    before = _pairs()
    held = _holdings()
    held_rem = float(held.get(rem, 0.0) or 0.0)
    blockers: List[str] = []
    notes: List[str] = []

    if rem not in before:
        blockers.append(f"remove_not_in_basket:{rem}")
    if add in before:
        blockers.append(f"add_already_in_basket:{add}")
    if rem in {"BTC-USD", "ETH-USD"}:
        blockers.append(f"sticky_refuse:{rem}")
    if held_rem >= protect_usd:
        blockers.append(f"remove_held_${held_rem:.2f}>={protect_usd:.0f}")
    if _decision_live_swaps():
        notes.append("WARN: decision live_membership_swaps=true (script will not flip it)")

    # Lightweight novelty peek (same gate promote uses)
    novelty: Dict[str, Any] = {}
    try:
        from phase6.core.novelty_class_gate import evaluate_pair_novelty

        nv = evaluate_pair_novelty(add, enforce=True, persist_first_seen=False)
        novelty = nv.to_dict() if hasattr(nv, "to_dict") else {"blocked": bool(getattr(nv, "blocked", False))}
        if getattr(nv, "blocked", False):
            notes.append(
                f"novelty_blocks:{getattr(nv, 'class_', '?')} "
                f"(need --override-novelty with --go)"
            )
    except Exception as e:  # noqa: BLE001
        notes.append(f"novelty_check_skipped:{type(e).__name__}")

    after = [add if p == rem else p for p in before] if rem in before else list(before)
    if add not in after and rem in before:
        after = [add if p == rem else p for p in before]

    return {
        "remove": rem,
        "add": add,
        "before": before,
        "after": after,
        "remove_held_usd": round(held_rem, 2),
        "blockers": blockers,
        "notes": notes,
        "novelty": novelty,
        "live_membership_swaps": _decision_live_swaps(),
        "ok": not blockers,
    }


def _run_promote(
    rem: str,
    add: str,
    *,
    dry_run: bool,
    override_novelty: bool,
    override_missfire: bool,
    allow_residual: bool,
    protect_usd: float,
) -> Tuple[int, str]:
    py = str(VENV_PY if VENV_PY.exists() else sys.executable)
    cmd = [
        py,
        str(PROMOTE),
        "--manual-add",
        add,
        "--manual-remove",
        rem,
        "--protect-usd",
        str(protect_usd),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if override_novelty:
        cmd.append("--override-novelty-class")
    if override_missfire:
        cmd.append("--override-missfire-probation")
    if allow_residual:
        cmd.append("--allow-residual-hold")
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return int(p.returncode), out.strip()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Simple Brad-GO basket swap (membership only, dry-run default)."
    )
    ap.add_argument(
        "positional",
        nargs="*",
        help="Optional REMOVE ADD (symbols or *-USD). Default: dual_agree latest.",
    )
    ap.add_argument("--remove", default="", help="REMOVE pair (overrides positional/dual_agree)")
    ap.add_argument("--add", default="", help="ADD pair (overrides positional/dual_agree)")
    ap.add_argument(
        "--go",
        action="store_true",
        help="Apply membership write (default is dry-run). No orders.",
    )
    ap.add_argument(
        "--override-novelty",
        action="store_true",
        help="Brad-only: pass novelty class block on ADD (seat, not graduated).",
    )
    ap.add_argument(
        "--override-missfire",
        action="store_true",
        help="Brad-only: pass miss-fire probation on ADD.",
    )
    ap.add_argument(
        "--allow-residual-hold",
        action="store_true",
        help="Allow REMOVE while still held >= protect threshold.",
    )
    ap.add_argument("--protect-usd", type=float, default=40.0)
    ap.add_argument("--json", action="store_true", help="Machine-readable receipt on stdout")
    args = ap.parse_args(argv)

    meta: Dict[str, Any] = {"source": "explicit"}
    rem = add = ""

    if args.remove and args.add:
        rem, add = args.remove, args.add
        meta = {"source": "flags"}
    elif len(args.positional) >= 2:
        rem, add = args.positional[0], args.positional[1]
        meta = {"source": "positional"}
    elif len(args.positional) == 1:
        print("REFUSE: need REMOVE and ADD (or omit both for dual_agree).")
        return 2
    else:
        got = _dual_agree_swap()
        if not got:
            print("REFUSE: no dual_agree proposal and no REMOVE/ADD given.")
            return 3
        rem, add, meta = got

    try:
        rem_n = _norm_pair(rem)
        add_n = _norm_pair(add)
    except ValueError as e:
        print(f"REFUSE: bad pair ({e})")
        return 2

    pf = _preflight(rem_n, add_n, float(args.protect_usd))
    dry = not bool(args.go)

    # Already seated (common after dual_agree Brad GO + cron still pointing at same pair)
    blockers = list(pf.get("blockers") or [])
    if (
        f"remove_not_in_basket:{rem_n}" in blockers
        and f"add_already_in_basket:{add_n}" in blockers
    ):
        msg = f"ALREADY: {rem_n} → {add_n} seated (nothing to do)"
        print(msg)
        if args.json:
            print(
                json.dumps(
                    {"ok": True, "already": True, "preflight": pf, "meta": meta},
                    indent=2,
                    default=str,
                )
            )
        return 0

    # Novelty: apply needs flag if blocked; dry-run still shows the promote path
    nov_blocked = bool((pf.get("novelty") or {}).get("blocked"))
    if args.go and nov_blocked and not args.override_novelty:
        print(
            f"REFUSE: novelty blocks {add_n}. "
            f"Re-run with --go --override-novelty (Brad only; seat not graduated)."
        )
        if args.json:
            print(json.dumps({"ok": False, "preflight": pf, "meta": meta}, indent=2, default=str))
        return 7

    if blockers and not (
        args.allow_residual_hold
        and len(blockers) == 1
        and blockers[0].startswith("remove_held_")
    ):
        # residual hold can be overridden; other blockers hard-stop before promote
        hard = [
            b
            for b in blockers
            if not (args.allow_residual_hold and str(b).startswith("remove_held_"))
        ]
        if hard:
            print(f"REFUSE: {' | '.join(hard)}")
            print(f"would: {rem_n} → {add_n}  held_remove=${pf['remove_held_usd']:.2f}")
            if args.json:
                print(json.dumps({"ok": False, "preflight": pf, "meta": meta}, indent=2, default=str))
            return 4

    rc, promote_out = _run_promote(
        rem_n,
        add_n,
        dry_run=dry,
        override_novelty=bool(args.override_novelty),
        override_missfire=bool(args.override_missfire),
        allow_residual=bool(args.allow_residual_hold),
        protect_usd=float(args.protect_usd),
    )

    # Re-read pairs after apply
    after_live = _pairs()
    live_swaps = _decision_live_swaps()
    receipt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.go else "dry_run",
        "ok": rc == 0,
        "exit_code": rc,
        "remove": rem_n,
        "add": add_n,
        "meta": meta,
        "preflight": pf,
        "pairs_now": after_live,
        "live_membership_swaps": live_swaps,
        "orders": False,
        "force_rebalance": False,
        "promote_tail": "\n".join((promote_out or "").splitlines()[-12:]),
    }
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    except Exception:
        pass

    # Short human board (default)
    if not args.json:
        tag = "DRY-RUN" if dry else ("APPLIED" if rc == 0 else "FAILED")
        print(f"basket_swap {tag}: {rem_n} → {add_n}")
        print(f"  source: {meta.get('source')}  held_remove=${pf['remove_held_usd']:.2f}")
        if meta.get("reason"):
            print(f"  reason: {meta.get('reason')}")
        for n in pf.get("notes") or []:
            print(f"  note: {n}")
        if dry:
            print(f"  before: {pf['before']}")
            print(f"  after:  {pf['after']}")
            print("  live_membership_swaps stays OFF · no orders · pass --go to apply")
        else:
            print(f"  pairs: {after_live}")
            print(
                f"  live_membership_swaps={live_swaps} · no orders · "
                f"hot-reload via basket_reload.flag"
            )
        if rc != 0:
            print("--- promote ---")
            print(promote_out)
        elif dry and promote_out:
            # keep dry noise short: last useful lines only if refuse buried
            if "REFUSE" in promote_out or "WARN" in promote_out:
                for line in promote_out.splitlines():
                    if line.startswith(("REFUSE", "WARN", "NOTE", "BEFORE", "AFTER", "Manual")):
                        print(f"  {line}")
    else:
        print(json.dumps(receipt, indent=2, default=str))

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
