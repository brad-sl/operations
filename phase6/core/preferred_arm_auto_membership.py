#!/usr/bin/env python3
"""Preferred-arm auto membership (Brad GO 2026-09-25/26 path A).

When CF cron sees a *new* preferred-arm write that already clears membership
potential (M0–M3), apply the seat swap automatically:

  - membership only (promote path) — **no orders**, no force rebalance
  - dual_agree is **never** auto-applied (still Brad GO / TG)
  - global `live_membership_swaps` stays false (this is a narrow gate, not free-for-all)

Gates before apply
------------------
1. Decision flag `preferred_arm_auto_membership.enabled` (default true after Brad GO A)
2. No kill file `data/state/preferred_arm_auto_membership_KILL`
3. Preferred arm matches decision-file preferred_arm
4. membership_potential_ok on the write
5. Preflight: REMOVE in basket, ADD not in basket, not sticky BTC/ETH,
   REMOVE held < protect_usd (dust-only default — not full tryout shells)
6. Miss-fire probation must clear (no auto override)
7. Novelty may be overridden for seat-only (same as dual_agree GO habit) —
   logged explicitly; not graduated
8. Daily cap: ≤ max_per_day successful applies (default 1, UTC day)

Honesty
-------
Post-seat buy filters still gate money. Auto-seat ≠ fill.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

STATE = PROJECT_ROOT / "data" / "state"
DECISION = STATE / "basket_swap_brad_decision.json"
KILL = STATE / "preferred_arm_auto_membership_KILL"
RECEIPT = STATE / "preferred_arm_auto_membership_latest.json"
CRUMBS = STATE / "preferred_arm_auto_membership_crumbs.jsonl"
TRADING_CFG = PROJECT_ROOT / "config" / "trading_config_phase6.json"
PROMOTE = PROJECT_ROOT / "scripts" / "phase6" / "promote_basket_proposal.py"
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python3"

# Dust-only eject bar (matches risk_management.dust_sweep_orphan_max_usd).
# Full $25 tryout seats must stay on roster until flat — auto-membership
# must not messily eject live tryouts. Manual GO path still uses promote
# default $40 if Brad wants a looser bar.
DEFAULT_PROTECT_USD = 5.0
DEFAULT_MAX_PER_DAY = 1
STICKY = frozenset({"BTC-USD", "ETH-USD"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_day(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%d")


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _norm_pair(raw: str) -> str:
    s = str(raw or "").strip().upper().replace("_", "-")
    if not s:
        raise ValueError("empty pair")
    if s.endswith("-USD"):
        return s
    if "-" in s:
        return s if s.endswith("USD") else f"{s}-USD"
    return f"{s}-USD"


def load_policy(brad: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw = brad if isinstance(brad, dict) else (_load_json(DECISION, {}) or {})
    d: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    block_raw = d.get("preferred_arm_auto_membership")
    block: Dict[str, Any] = dict(block_raw) if isinstance(block_raw, dict) else {}
    # Brad GO path A default: ON (preferred-arm only; dual_agree stays manual)
    enabled_default = True
    return {
        "enabled": bool(block.get("enabled", enabled_default)),
        "max_per_day": int(block.get("max_per_day", DEFAULT_MAX_PER_DAY) or DEFAULT_MAX_PER_DAY),
        "protect_usd": float(block.get("protect_usd", DEFAULT_PROTECT_USD) or DEFAULT_PROTECT_USD),
        "override_novelty": bool(block.get("override_novelty", True)),
        "override_missfire": bool(block.get("override_missfire", False)),
        "allow_residual_hold": bool(block.get("allow_residual_hold", False)),
        "preferred_arm_only": True,
        "dual_agree_auto": False,
        "kill_file": str(KILL),
        "note": block.get("note")
        or "Preferred-arm auto membership; dual_agree manual; live_membership_swaps stays false.",
    }


def kill_switch_on() -> bool:
    return KILL.exists()


def _pairs() -> List[str]:
    cfg = _load_json(TRADING_CFG, {}) or {}
    return list((cfg.get("global_settings") or {}).get("pairs") or [])


def _holdings() -> Dict[str, float]:
    try:
        from phase6.core.pool_cycling import load_holdings_usd

        return {str(k): float(v or 0.0) for k, v in (load_holdings_usd() or {}).items()}
    except Exception:
        return {}


def _count_applies_today(day: Optional[str] = None) -> int:
    day = day or _utc_day()
    n = 0
    if not CRUMBS.exists():
        return 0
    try:
        for line in CRUMBS.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("utc_day") != day:
                continue
            if row.get("status") in {"applied", "already"} and row.get("counted", True):
                n += 1
    except Exception:
        return n
    return n


def _append_crumb(row: Dict[str, Any]) -> None:
    try:
        CRUMBS.parent.mkdir(parents=True, exist_ok=True)
        with CRUMBS.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def _write_receipt(row: Dict[str, Any]) -> None:
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(row, indent=2, default=str) + "\n")
    except Exception:
        pass


def extract_preferred_ok_writes(
    bundle: Dict[str, Any],
    *,
    preferred: str,
) -> List[Dict[str, Any]]:
    """New preferred-arm membership-OK paper writes from this CF run."""
    preferred = (preferred or "").strip()
    written = list(((bundle.get("arms_prop") or {}).get("written") or []))
    out: List[Dict[str, Any]] = []
    for w in written:
        if not isinstance(w, dict):
            continue
        if (w.get("arm") or "") != preferred:
            continue
        mp = w.get("membership_potential") or {}
        ok = bool(w.get("membership_potential_ok")) or bool(mp.get("ok"))
        if not ok:
            continue
        rem = w.get("remove")
        add = w.get("add")
        if not rem or not add:
            continue
        out.append(w)
    return out


def preflight(
    rem: str,
    add: str,
    *,
    protect_usd: float,
) -> Dict[str, Any]:
    before = _pairs()
    held = _holdings()
    held_rem = float(held.get(rem, 0.0) or 0.0)
    blockers: List[str] = []
    notes: List[str] = []

    if rem not in before:
        blockers.append(f"remove_not_in_basket:{rem}")
    if add in before:
        blockers.append(f"add_already_in_basket:{add}")
    if rem in STICKY:
        blockers.append(f"sticky_refuse:{rem}")
    if held_rem >= protect_usd:
        blockers.append(f"remove_held_${held_rem:.2f}>={protect_usd:.0f}")

    # missfire — hard for auto (no override unless policy says so)
    try:
        from phase6.core.missfire_probation import evaluate_pair_missfire

        mf = evaluate_pair_missfire(add, enforce=True)
        if getattr(mf, "blocked", False):
            blockers.append(f"missfire_probation:{getattr(mf, 'reason', 'blocked')}")
    except Exception as e:  # noqa: BLE001
        notes.append(f"missfire_check_skipped:{type(e).__name__}")

    novelty_blocked = False
    try:
        from phase6.core.novelty_class_gate import evaluate_pair_novelty

        nv = evaluate_pair_novelty(add, enforce=True, persist_first_seen=False)
        novelty_blocked = bool(getattr(nv, "blocked", False))
        if novelty_blocked:
            notes.append(
                f"novelty_blocks:{getattr(nv, 'class_', '?')} "
                "(auto may override seat-only if policy.override_novelty)"
            )
    except Exception as e:  # noqa: BLE001
        notes.append(f"novelty_check_skipped:{type(e).__name__}")

    after = [add if p == rem else p for p in before] if rem in before else list(before)
    return {
        "remove": rem,
        "add": add,
        "before": before,
        "after": after,
        "remove_held_usd": round(held_rem, 2),
        "blockers": blockers,
        "notes": notes,
        "novelty_blocked": novelty_blocked,
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
    import os

    env = dict(os.environ)
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


def try_auto_from_bundle(
    bundle: Dict[str, Any],
    *,
    dry_run: bool = False,
    brad: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attempt preferred-arm auto seat from a CF `run_full` bundle.

    Returns a receipt dict always (status=skipped|refused|applied|already|error).
    """
    now = _utc_now()
    day = _utc_day(now)
    raw_brad = brad if isinstance(brad, dict) else (_load_json(DECISION, {}) or {})
    brad_d: Dict[str, Any] = dict(raw_brad) if isinstance(raw_brad, dict) else {}
    policy = load_policy(brad_d)
    preferred = (brad_d.get("preferred_arm") or "").strip() or "rel_btc_stable"

    base: Dict[str, Any] = {
        "schema": "preferred_arm_auto_membership_v1",
        "ts": now.isoformat(),
        "utc_day": day,
        "preferred_arm": preferred,
        "policy": policy,
        "dry_run": bool(dry_run),
        "status": "skipped",
        "reason": "",
        "remove": None,
        "add": None,
        "orders": False,
        "force_rebalance": False,
        "live_membership_swaps": False,
        "dual_agree_auto": False,
    }

    if kill_switch_on():
        base["status"] = "skipped"
        base["reason"] = "kill_switch_file"
        _write_receipt(base)
        return base

    if not policy.get("enabled", True):
        base["status"] = "skipped"
        base["reason"] = "policy_disabled"
        _write_receipt(base)
        return base

    writes = extract_preferred_ok_writes(bundle, preferred=preferred)
    if not writes:
        base["status"] = "skipped"
        base["reason"] = "no_preferred_membership_ok_write"
        _write_receipt(base)
        return base

    # One swap per run: first membership-OK preferred write
    w0 = writes[0]
    try:
        rem = _norm_pair(str(w0.get("remove")))
        add = _norm_pair(str(w0.get("add")))
    except ValueError as e:
        base["status"] = "refused"
        base["reason"] = f"bad_pair:{e}"
        _write_receipt(base)
        return base

    base["remove"] = rem
    base["add"] = add
    base["write"] = {
        "arm": w0.get("arm"),
        "add_score": w0.get("add_score"),
        "reason": (w0.get("reason") or "")[:240],
        "remove_held_usd": w0.get("remove_held_usd"),
    }

    # Daily cap (successful applies only)
    applied_today = _count_applies_today(day)
    base["applies_today_before"] = applied_today
    if applied_today >= int(policy["max_per_day"]):
        base["status"] = "skipped"
        base["reason"] = f"daily_cap:{applied_today}>={policy['max_per_day']}"
        _write_receipt(base)
        _append_crumb({**base, "counted": False})
        return base

    pf = preflight(rem, add, protect_usd=float(policy["protect_usd"]))
    base["preflight"] = pf

    # Already seated
    blockers = list(pf.get("blockers") or [])
    if (
        f"remove_not_in_basket:{rem}" in blockers
        and f"add_already_in_basket:{add}" in blockers
    ):
        base["status"] = "already"
        base["reason"] = "already_seated"
        base["counted"] = True
        _write_receipt(base)
        _append_crumb(base)
        return base

    hard = list(blockers)
    if policy.get("allow_residual_hold"):
        hard = [b for b in hard if not str(b).startswith("remove_held_")]
    if hard:
        base["status"] = "refused"
        base["reason"] = " | ".join(hard)
        _write_receipt(base)
        _append_crumb({**base, "counted": False})
        return base

    ov_nov = bool(policy.get("override_novelty")) and bool(pf.get("novelty_blocked"))
    # If novelty blocked and policy forbids override → refuse
    if pf.get("novelty_blocked") and not policy.get("override_novelty"):
        base["status"] = "refused"
        base["reason"] = "novelty_blocked_no_override"
        _write_receipt(base)
        _append_crumb({**base, "counted": False})
        return base

    rc, promote_out = _run_promote(
        rem,
        add,
        dry_run=bool(dry_run),
        override_novelty=bool(policy.get("override_novelty")),
        override_missfire=bool(policy.get("override_missfire")),
        allow_residual=bool(policy.get("allow_residual_hold")),
        protect_usd=float(policy["protect_usd"]),
    )
    base["promote_rc"] = rc
    base["promote_tail"] = "\n".join((promote_out or "").splitlines()[-12:])
    base["novelty_override_used"] = bool(policy.get("override_novelty")) and bool(
        pf.get("novelty_blocked")
    )

    if dry_run:
        base["status"] = "dry_would_apply" if rc == 0 else "dry_refused"
        base["reason"] = "dry_run"
        base["counted"] = False
        _write_receipt(base)
        _append_crumb(base)
        return base

    if rc == 0:
        base["status"] = "applied"
        base["reason"] = "preferred_arm_auto_membership"
        base["pairs_now"] = _pairs()
        base["counted"] = True
        # Stamp last auto on decision file (non-destructive)
        try:
            d = _load_json(DECISION, {}) or {}
            d["last_preferred_arm_auto_membership"] = {
                "at": now.isoformat(),
                "remove": rem,
                "add": add,
                "arm": preferred,
                "novelty_override": base["novelty_override_used"],
                "note": "membership only; live_membership_swaps still false; no orders",
            }
            # ensure policy block exists
            pam = d.get("preferred_arm_auto_membership")
            if not isinstance(pam, dict):
                pam = {}
            pam.setdefault("enabled", True)
            pam.setdefault("max_per_day", DEFAULT_MAX_PER_DAY)
            pam["last_apply_at"] = now.isoformat()
            d["preferred_arm_auto_membership"] = pam
            DECISION.write_text(json.dumps(d, indent=2, default=str) + "\n")
        except Exception as e:  # noqa: BLE001
            base["decision_stamp_error"] = f"{type(e).__name__}:{e}"
    else:
        base["status"] = "refused"
        base["reason"] = f"promote_rc={rc}"
        base["counted"] = False

    _write_receipt(base)
    _append_crumb(base)
    return base


def telegram_notice(result: Dict[str, Any]) -> Optional[str]:
    """Short TG body for auto apply / refuse (None if skip silence)."""
    st = result.get("status")
    if st in {None, "skipped"} and result.get("reason") in {
        "no_preferred_membership_ok_write",
        "policy_disabled",
        "",
    }:
        return None
    if st == "skipped" and str(result.get("reason") or "").startswith("daily_cap"):
        # still notify so Brad knows a candidate was eaten by cap
        rem, add = result.get("remove"), result.get("add")
        if rem and add:
            return (
                "⏸️ Preferred-arm auto membership skipped (daily cap)\n"
                f"• would: {rem} → {add}\n"
                f"• reason: {result.get('reason')}\n"
                "• dual_agree still manual · live_swaps OFF · no orders"
            )
        return None
    if st == "skipped":
        if result.get("reason") == "kill_switch_file":
            return (
                "⏸️ Preferred-arm auto membership KILL switch on "
                f"({KILL.name}) — no seat apply"
            )
        return None

    rem = result.get("remove")
    add = result.get("add")
    arm = result.get("preferred_arm")
    if st == "applied":
        nov = " · novelty override (seat only)" if result.get("novelty_override_used") else ""
        return (
            "✅ AUTO membership (preferred arm — not dual_agree)\n"
            f"• {rem} → {add} via `{arm}`{nov}\n"
            "• seat only · no orders · live_membership_swaps OFF\n"
            "• buy still needs RSI/sent/seats/run-phase\n"
            f"• kill: touch {KILL}"
        )
    if st == "already":
        return (
            f"ℹ️ Preferred-arm auto: already seated {rem} → {add}\n"
            "· live_swaps OFF · no orders"
        )
    if st in {"refused", "dry_refused", "error"}:
        return (
            "⚠️ Preferred-arm auto membership REFUSED\n"
            f"• {rem} → {add}\n"
            f"• reason: {result.get('reason')}\n"
            "• dual_agree path unchanged (still needs GO if it fires)\n"
            "· live_swaps OFF · no orders"
        )
    if st == "dry_would_apply":
        return (
            f"DRY preferred-arm auto would apply {rem} → {add} "
            f"(arm={arm}) · no write"
        )
    return None


def serious_consider_with_auto(
    bundle: Dict[str, Any],
    *,
    auto_result: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Compose TG: dual_agree still asks GO; preferred arm reports auto outcome."""
    from phase6.core.basket_swap_shadow_cf import serious_consider_message

    auto_result = auto_result or {}
    auto_st = auto_result.get("status")

    # Build dual-only view if preferred was handled by auto (avoid double GO ask)
    bundle_for_msg = bundle
    if auto_st in {"applied", "already", "refused", "dry_would_apply", "dry_refused"} or (
        auto_st == "skipped" and str(auto_result.get("reason") or "").startswith("daily_cap")
    ):
        # Strip preferred writes so serious_consider only surfaces dual_agree
        try:
            import copy

            bundle_for_msg = copy.deepcopy(bundle)
            arms = bundle_for_msg.get("arms_prop") or {}
            preferred = (auto_result.get("preferred_arm") or "").strip()
            written = list(arms.get("written") or [])
            arms["written"] = [w for w in written if (w.get("arm") or "") != preferred]
            bundle_for_msg["arms_prop"] = arms
        except Exception:
            bundle_for_msg = bundle

    dual_msg = serious_consider_message(bundle_for_msg)
    auto_msg = telegram_notice(auto_result)

    parts = [p for p in (auto_msg, dual_msg) if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "\n\n——\n\n" + parts[1]
