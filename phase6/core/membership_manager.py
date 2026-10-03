#!/usr/bin/env python3
"""Membership Manager — self-regulating bag seats (Brad GO 2026-10-03).

Product
-------
Find contenders, dismiss weak ones, cycle the best name into the active bag
in place of a deadbeat / underperformer. Brad is **not** on the happy path.
History (career ledger) lets cold names re-cycle when demand returns.

This is **membership only** (config pairs + reload flag). No orders, no force
rebalance, no free-for-all `live_membership_swaps`.

Sources (priority)
------------------
1. Preferred-arm CF membership-OK write (same bar as path A auto).
2. Else contender_vs_weak: promote-eligible discovery contender vs weakest
   flat non-sticky active (pool-cycler / quality scores + M-gates).

Gates (always)
--------------
- config enabled + live_apply
- no kill file (manager and optional preferred-arm kill)
- ≤ max_per_day successful applies (UTC day; shared crumb count)
- REMOVE in basket, ADD not in basket, not sticky
- REMOVE held < protect_usd (dust-only — never eject live tryout shells)
- missfire hard-block on ADD (no auto override by default)
- novelty may override seat-only (logged; not graduated)
- dual_agree never auto-applied here

Honesty
-------
Seat ≠ fill ≠ win. Buy still needs RSI/sent/seats/run-phase.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket
from phase6.core import preferred_arm_auto_membership as pam

STATE = PROJECT_ROOT / "data" / "state"
CFG_PATH = PROJECT_ROOT / "config" / "membership_manager.json"
KILL = STATE / "membership_manager_KILL"
RECEIPT = STATE / "membership_manager_latest.json"
CRUMBS = STATE / "membership_manager_crumbs.jsonl"
CAREER = STATE / "membership_career_ledger.json"
CONTENDERS = STATE / "pair_discovery_contenders.json"
POOL_LATEST = STATE / "pool_cycling_latest.json"
CF_LATEST = STATE / "basket_swap_shadow_counterfactual_latest.json"
IDLE_LATEST = STATE / "basket_seat_idle_latest.json"
DECISION = STATE / "basket_swap_brad_decision.json"

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "live_apply": True,
    "max_per_day": 1,
    "protect_usd": 5.0,
    "override_novelty": True,
    "override_missfire": False,
    "allow_residual_hold": False,
    "dual_agree_auto": False,
    "sources": {"preferred_arm_cf": True, "contender_vs_weak": True},
    "contender": {
        "min_quality": 0.55,
        "min_delta_vs_weak": 0.08,
        "require_promote_eligible": True,
        "skip_pump_names": True,
    },
    "sticky": ["BTC-USD", "ETH-USD"],
    "also_honor_preferred_arm_kill": True,
}


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


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def _norm_pair(raw: str) -> str:
    return pam._norm_pair(raw)


def load_config(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    disk = raw if isinstance(raw, dict) else (_load_json(CFG_PATH, {}) or {})
    if not isinstance(disk, dict):
        disk = {}
    out = dict(DEFAULTS)
    out.update({k: disk[k] for k in disk if k in DEFAULTS or k in (
        "enabled", "live_apply", "max_per_day", "protect_usd", "override_novelty",
        "override_missfire", "allow_residual_hold", "dual_agree_auto", "sources",
        "contender", "sticky", "also_honor_preferred_arm_kill", "note", "brad_go",
        "updated", "schema", "kill_file",
    )})
    src = dict(DEFAULTS["sources"])
    if isinstance(disk.get("sources"), dict):
        src.update(disk["sources"])
    out["sources"] = src
    cont = dict(DEFAULTS["contender"])
    if isinstance(disk.get("contender"), dict):
        cont.update(disk["contender"])
    out["contender"] = cont
    sticky = disk.get("sticky") or DEFAULTS["sticky"]
    out["sticky"] = [str(x) for x in sticky]
    return out


def kill_switch_on(cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    if KILL.exists():
        return True, f"kill_file:{KILL.name}"
    cfg = cfg or load_config()
    if cfg.get("also_honor_preferred_arm_kill") and pam.KILL.exists():
        return True, f"preferred_arm_kill:{pam.KILL.name}"
    return False, ""


def _append_crumb(row: Dict[str, Any]) -> None:
    try:
        CRUMBS.parent.mkdir(parents=True, exist_ok=True)
        with CRUMBS.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def _count_applies_today(day: Optional[str] = None) -> int:
    """Count manager + preferred-arm applies so caps stay global ≤1/day."""
    day = day or _utc_day()
    n = 0
    for path in (CRUMBS, pam.CRUMBS):
        if not path.exists():
            continue
        try:
            for line in path.read_text().splitlines():
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
            continue
    return n


# ---------------------------------------------------------------------------
# Career ledger — history so names can leave and return
# ---------------------------------------------------------------------------

def load_career() -> Dict[str, Any]:
    raw = _load_json(CAREER, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    pairs = raw.get("pairs") if isinstance(raw.get("pairs"), dict) else {}
    return {
        "schema": "membership_career_ledger_v1",
        "updated": raw.get("updated"),
        "pairs": dict(pairs),
    }


def _career_touch(
    career: Dict[str, Any],
    pair: str,
    *,
    event: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    pairs_raw = career.get("pairs")
    pairs: Dict[str, Any] = dict(pairs_raw) if isinstance(pairs_raw, dict) else {}
    row = dict(pairs.get(pair) or {})
    row["pair"] = pair
    hist_raw = row.get("events")
    hist: List[Dict[str, Any]] = list(hist_raw) if isinstance(hist_raw, list) else []
    ev: Dict[str, Any] = {"at": _utc_now().isoformat(), "event": event}
    if detail:
        ev.update(detail)
    hist.append(ev)
    # keep tail
    row["events"] = hist[-40:]
    if event == "seated":
        row["career"] = "active"
        row["last_seat_at"] = ev["at"]
        row["n_seats"] = int(row.get("n_seats") or 0) + 1
        row["last_add_source"] = (detail or {}).get("source")
    elif event == "ejected":
        row["career"] = "alumni"
        row["last_eject_at"] = ev["at"]
        row["n_ejects"] = int(row.get("n_ejects") or 0) + 1
        row["last_outcome"] = (detail or {}).get("outcome") or row.get("last_outcome")
    elif event == "contender_seen":
        if row.get("career") not in {"active", "blocked"}:
            row["career"] = "contender"
        row["last_contender_at"] = ev["at"]
        row["last_quality"] = (detail or {}).get("quality")
    elif event == "dismissed":
        if row.get("career") != "active":
            row["career"] = "dismissed"
        row["last_dismiss_at"] = ev["at"]
        row["last_dismiss_reason"] = (detail or {}).get("reason")
    elif event == "blocked":
        row["career"] = "blocked"
        row["last_block_reason"] = (detail or {}).get("reason")
    pairs[pair] = row
    career["pairs"] = pairs
    career["updated"] = _utc_now().isoformat()


def save_career(career: Dict[str, Any]) -> None:
    career = dict(career)
    career["schema"] = "membership_career_ledger_v1"
    career["updated"] = _utc_now().isoformat()
    _write_json(CAREER, career)


def sync_career_with_basket(career: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mark actives vs alumni from live basket without inventing seats."""
    career = career or load_career()
    basket = set(load_trading_basket() or [])
    pairs = career.setdefault("pairs", {})
    for p in basket:
        row = dict(pairs.get(p) or {"pair": p})
        if row.get("career") != "blocked":
            row["career"] = "active"
        row["in_basket"] = True
        pairs[p] = row
    for p, row in list(pairs.items()):
        if p not in basket and row.get("career") == "active":
            row = dict(row)
            row["career"] = "alumni"
            row["in_basket"] = False
            pairs[p] = row
        elif p not in basket:
            row = dict(row)
            row["in_basket"] = False
            pairs[p] = row
    career["pairs"] = pairs
    return career


# ---------------------------------------------------------------------------
# Proposal builders
# ---------------------------------------------------------------------------

def _scores_from_pool() -> Dict[str, float]:
    raw = _load_json(POOL_LATEST, {}) or {}
    scores = raw.get("scores") or {}
    out: Dict[str, float] = {}
    if isinstance(scores, dict):
        for k, v in scores.items():
            try:
                if isinstance(v, dict):
                    out[str(k)] = float(v.get("score") or v.get("opportunity") or 0.0)
                else:
                    out[str(k)] = float(v or 0.0)
            except (TypeError, ValueError):
                continue
    return out


def _holdings() -> Dict[str, float]:
    out: Dict[str, float] = {}
    try:
        from phase6.core.pool_cycling import load_holdings_usd

        for k, v in (load_holdings_usd() or {}).items():
            try:
                out[str(k)] = float(v or 0.0)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    # Enrich from tryout open lots / seat ledger when exchange map is thin
    try:
        from phase6.core.tryout_seat_ledger import load_held_usd_map

        for k, v in (load_held_usd_map() or {}).items():
            try:
                fv = float(v or 0.0)
            except (TypeError, ValueError):
                continue
            if fv > float(out.get(str(k), 0.0) or 0.0):
                out[str(k)] = fv
    except Exception:
        pass
    try:
        lots = _load_json(STATE / "tryout_scale_up_open_lots.json", {}) or {}
        for lot in (lots.get("lots") or lots.get("open") or []) if isinstance(lots, dict) else []:
            if not isinstance(lot, dict):
                continue
            if str(lot.get("status") or "open").lower() not in {"open", "tryout_open", ""}:
                continue
            pid = lot.get("pair") or lot.get("product_id")
            if not pid:
                continue
            try:
                usd = float(lot.get("held_usd") or lot.get("notional_usd") or lot.get("cost_usd") or 0.0)
            except (TypeError, ValueError):
                usd = 0.0
            if usd > float(out.get(str(pid), 0.0) or 0.0):
                out[str(pid)] = usd
    except Exception:
        pass
    return out


def _idle_flags() -> Dict[str, Any]:
    raw = _load_json(IDLE_LATEST, {}) or {}
    by = {}
    rows = raw.get("seats") or raw.get("rows") or raw.get("pairs") or []
    if isinstance(rows, dict):
        return rows
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("pair"):
                by[str(r["pair"])] = r
    return by


_MEME_BLOCK_TOKENS = (
    "PUMP", "WIF", "FART", "USELESS", "MOG", "BOME", "MEW", "POPCAT", "PNUT", "GOAT",
)


def _is_meme_pair(pair: str) -> bool:
    u = str(pair or "").upper()
    base = u.split("-")[0] if u else ""
    return any(tok in base for tok in _MEME_BLOCK_TOKENS)


def preferred_arm_candidate(
    *,
    preferred: str,
    bundle: Optional[Dict[str, Any]] = None,
    skip_pump_names: bool = True,
) -> Optional[Dict[str, Any]]:
    """First preferred-arm membership-OK write from CF bundle or latest arm crumbs.

    Strict: only `membership_potential_ok` writes (same bar as path A). No loose fallback.
    """
    preferred = (preferred or "").strip()
    if bundle is None:
        written: List[Dict[str, Any]] = []
        arm_path = STATE / "basket_select_arms" / preferred / "latest.json"
        arm = _load_json(arm_path, {}) or {}
        for key in ("last_write", "proposal", "latest_proposal"):
            w = arm.get(key)
            if isinstance(w, dict) and w.get("remove") and w.get("add"):
                written.append({**w, "arm": w.get("arm") or preferred})
        # proposals jsonl — newest first, keep several for OK scan
        pj = STATE / "basket_select_arms" / preferred / "proposals.jsonl"
        if pj.exists():
            try:
                lines = [ln for ln in pj.read_text().splitlines() if ln.strip()]
                for ln in reversed(lines[-12:]):
                    try:
                        last = json.loads(ln)
                    except Exception:
                        continue
                    if last.get("remove") and last.get("add"):
                        written.append({**last, "arm": last.get("arm") or preferred})
            except Exception:
                pass
        cf = _load_json(CF_LATEST, {}) or {}
        arms_prop = cf.get("arms_prop") if isinstance(cf, dict) else None
        if isinstance(arms_prop, dict):
            for w in arms_prop.get("written") or []:
                if isinstance(w, dict):
                    written.append(w)
        bundle = {"arms_prop": {"written": written}}

    writes = pam.extract_preferred_ok_writes(bundle, preferred=preferred)
    if not writes:
        return None
    for w0 in writes:
        try:
            rem = _norm_pair(str(w0.get("remove")))
            add = _norm_pair(str(w0.get("add")))
        except ValueError:
            continue
        if skip_pump_names and _is_meme_pair(add):
            continue
        ok = bool(w0.get("membership_potential_ok")) or bool(
            (w0.get("membership_potential") or {}).get("ok")
        )
        if not ok:
            continue
        return {
            "source": "preferred_arm_cf",
            "arm": preferred,
            "remove": rem,
            "add": add,
            "add_score": w0.get("add_score") or w0.get("score"),
            "remove_score": w0.get("remove_score"),
            "reason": (w0.get("reason") or "preferred_arm_membership_ok")[:240],
            "membership_potential_ok": True,
            "raw": {
                k: w0.get(k)
                for k in ("add_score", "remove_held_usd", "membership_potential")
            },
        }
    return None


def contender_vs_weak_candidate(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best promote-eligible contender vs weakest flat non-sticky active."""
    cont_cfg = cfg.get("contender") or {}
    min_q = float(cont_cfg.get("min_quality") or 0.55)
    min_delta = float(cont_cfg.get("min_delta_vs_weak") or 0.08)
    require_pe = bool(cont_cfg.get("require_promote_eligible", True))
    skip_pump = bool(cont_cfg.get("skip_pump_names", True))
    sticky = set(cfg.get("sticky") or DEFAULTS["sticky"])
    protect = float(cfg.get("protect_usd") or 5.0)

    basket = list(load_trading_basket() or [])
    held = _holdings()
    scores = _scores_from_pool()
    idle = _idle_flags()

    # Weak eject candidates: non-sticky, held under protect (flat/dust)
    weak_rows: List[Tuple[float, str, Dict[str, Any]]] = []
    for p in basket:
        if p in sticky:
            continue
        h = float(held.get(p, 0.0) or 0.0)
        if h >= protect:
            continue
        sc = float(scores.get(p, 0.0) or 0.0)
        # idle flag boosts weakness (lower effective score)
        meta = idle.get(p) or {}
        if isinstance(meta, dict) and (
            meta.get("idle_cycle_flag") or meta.get("soft_idle") or meta.get("idle")
        ):
            sc = sc - 0.05
        weak_rows.append((sc, p, {"held": h, "score": sc}))
    if not weak_rows:
        return None
    weak_rows.sort(key=lambda t: (t[0], t[1]))
    weak_score, weak_pair, weak_meta = weak_rows[0]

    cdata = _load_json(CONTENDERS, {}) or {}
    contenders = list(cdata.get("contenders") or [])
    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for c in contenders:
        if not isinstance(c, dict):
            continue
        pid = str(c.get("product_id") or c.get("pair") or "")
        if not pid:
            continue
        try:
            pid = _norm_pair(pid)
        except ValueError:
            continue
        if pid in basket or pid in sticky:
            continue
        if require_pe and not c.get("promote_eligible", True):
            continue
        if skip_pump and _is_meme_pair(pid):
            continue
        q = c.get("quality_score")
        try:
            qf = float(q) if q is not None else float(c.get("prequal_energy") or 0.0)
        except (TypeError, ValueError):
            qf = 0.0
        if qf < min_q:
            continue
        # pool score if any
        add_sc = float(scores.get(pid, qf) or qf)
        ranked.append((add_sc, {**c, "product_id": pid, "quality_score": qf, "add_score": add_sc}))

    if not ranked:
        return None
    ranked.sort(key=lambda t: (-t[0], t[1]["product_id"]))
    best_sc, best = ranked[0]
    delta = float(best_sc) - float(weak_score)
    if delta < min_delta:
        return None

    # M-gate
    try:
        from phase6.core.membership_potential_gate import evaluate_membership_swap

        verdict = evaluate_membership_swap(
            add=best["product_id"],
            remove=weak_pair,
            active=basket,
            inbound_potential=float(best.get("quality_score") or best_sc),
            outbound_potential=float(weak_score),
            quote_vol_24h=best.get("volume_quote_usd"),
            ret_24h=best.get("ret_24h"),
            mom_3d=best.get("mom_3d"),
            mom_7d=best.get("mom_7d"),
            held_usd_remove=float(weak_meta.get("held") or 0.0),
        )
        if hasattr(verdict, "to_dict"):
            vdict = verdict.to_dict()
        else:
            vdict = {"ok": bool(getattr(verdict, "ok", False))}
        if not vdict.get("ok"):
            reasons = vdict.get("reasons") or []
            if not isinstance(reasons, list):
                reasons = [str(reasons)]
            return {
                "source": "contender_vs_weak",
                "remove": weak_pair,
                "add": best["product_id"],
                "add_score": best_sc,
                "remove_score": weak_score,
                "delta": round(delta, 4),
                "reason": (
                    f"m_gate_fail:{vdict.get('layer_failed')}:"
                    f"{','.join(str(x) for x in reasons)}"
                )[:240],
                "membership_potential_ok": False,
                "m_gate": vdict,
                "refused_pre": True,
            }
        m_ok = True
        m_gate = vdict
    except TypeError:
        # signature drift — try minimal
        try:
            from phase6.core.membership_potential_gate import evaluate_membership_swap

            verdict = evaluate_membership_swap(
                add=best["product_id"],
                remove=weak_pair,
                active=basket,
            )
            if hasattr(verdict, "to_dict"):
                vdict = verdict.to_dict()
            else:
                vdict = {"ok": bool(getattr(verdict, "ok", True))}
            if not vdict.get("ok", True):
                return None
            m_ok = True
            m_gate = vdict
        except Exception as e:  # noqa: BLE001
            m_ok = True
            m_gate = {"ok": True, "note": f"m_gate_skipped:{type(e).__name__}"}
    except Exception as e:  # noqa: BLE001
        m_ok = True
        m_gate = {"ok": True, "note": f"m_gate_skipped:{type(e).__name__}"}

    return {
        "source": "contender_vs_weak",
        "remove": weak_pair,
        "add": best["product_id"],
        "add_score": best_sc,
        "remove_score": weak_score,
        "delta": round(delta, 4),
        "reason": (
            f"contender {best['product_id']} q={best.get('quality_score')} "
            f"replaces weak flat {weak_pair} sc={weak_score:.3f} Δ={delta:.3f}"
        )[:240],
        "membership_potential_ok": bool(m_ok),
        "m_gate": m_gate,
        "contender": {
            "quality_score": best.get("quality_score"),
            "prequal_energy": best.get("prequal_energy"),
            "promote_eligible": best.get("promote_eligible"),
        },
    }


def choose_candidate(
    cfg: Dict[str, Any],
    *,
    preferred: str,
    bundle: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return best candidate + dismissed/skipped notes."""
    notes: List[Dict[str, Any]] = []
    src = cfg.get("sources") or {}
    skip_pump = bool((cfg.get("contender") or {}).get("skip_pump_names", True))
    cand = None
    if src.get("preferred_arm_cf", True):
        cand = preferred_arm_candidate(
            preferred=preferred, bundle=bundle, skip_pump_names=skip_pump
        )
        if cand:
            notes.append({"kept": "preferred_arm_cf", "add": cand.get("add"), "remove": cand.get("remove")})
        else:
            notes.append({"dismissed_source": "preferred_arm_cf", "reason": "no_ok_write"})
    if cand is None and src.get("contender_vs_weak", True):
        c2 = contender_vs_weak_candidate(cfg)
        if c2 and c2.get("refused_pre"):
            notes.append({"dismissed": c2})
            # Surface as refused candidate (not silent no_candidate)
            cand = c2
        elif c2:
            cand = c2
            notes.append({"kept": "contender_vs_weak", "add": cand.get("add"), "remove": cand.get("remove")})
        else:
            notes.append({"dismissed_source": "contender_vs_weak", "reason": "no_delta_or_flat"})
    return cand, notes


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def run_membership_manager(
    *,
    dry_run: bool = False,
    bundle: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    apply: Optional[bool] = None,
) -> Dict[str, Any]:
    """One manager tick: propose and optionally apply ≤1 seat swap."""
    now = _utc_now()
    day = _utc_day(now)
    cfg = cfg or load_config()
    brad = _load_json(DECISION, {}) or {}
    preferred = str((brad.get("preferred_arm") if isinstance(brad, dict) else None) or "rel_btc_stable")

    live_apply = bool(cfg.get("live_apply", True)) if apply is None else bool(apply)
    if dry_run:
        live_apply = False

    base: Dict[str, Any] = {
        "schema": "membership_manager_v1",
        "ts": now.isoformat(),
        "utc_day": day,
        "preferred_arm": preferred,
        "config": {
            "enabled": cfg.get("enabled"),
            "live_apply": cfg.get("live_apply"),
            "max_per_day": cfg.get("max_per_day"),
            "protect_usd": cfg.get("protect_usd"),
            "sources": cfg.get("sources"),
            "dual_agree_auto": False,
        },
        "dry_run": bool(dry_run),
        "live_apply_effective": live_apply,
        "status": "skipped",
        "reason": "",
        "remove": None,
        "add": None,
        "source": None,
        "orders": False,
        "force_rebalance": False,
        "live_membership_swaps": False,
        "brad_in_path": False,
        "plain_english": "",
    }

    killed, kill_why = kill_switch_on(cfg)
    if killed:
        base["status"] = "skipped"
        base["reason"] = kill_why
        base["plain_english"] = f"Membership manager killed ({kill_why})."
        _write_json(RECEIPT, base)
        return base

    if not cfg.get("enabled", True):
        base["status"] = "skipped"
        base["reason"] = "policy_disabled"
        base["plain_english"] = "Membership manager disabled in config."
        _write_json(RECEIPT, base)
        return base

    career = sync_career_with_basket(load_career())

    # Dismiss / note contenders for career (measure)
    cdata = _load_json(CONTENDERS, {}) or {}
    for c in cdata.get("contenders") or []:
        if not isinstance(c, dict):
            continue
        pid = c.get("product_id") or c.get("pair")
        if not pid:
            continue
        try:
            pid = _norm_pair(str(pid))
        except ValueError:
            continue
        if c.get("promote_eligible"):
            _career_touch(
                career,
                pid,
                event="contender_seen",
                detail={"quality": c.get("quality_score"), "energy": c.get("prequal_energy")},
            )
        else:
            _career_touch(
                career,
                pid,
                event="dismissed",
                detail={"reason": ",".join(c.get("reasons") or [])[:160] or "not_promote_eligible"},
            )

    cand, notes = choose_candidate(cfg, preferred=preferred, bundle=bundle)
    base["selection_notes"] = notes

    if not cand:
        base["status"] = "skipped"
        base["reason"] = "no_candidate"
        base["plain_english"] = (
            "No membership swap: preferred-arm had no OK write and no contender beat a flat weak seat."
        )
        save_career(career)
        _write_json(RECEIPT, base)
        return base

    if cand.get("refused_pre") or cand.get("membership_potential_ok") is False and cand.get("source") == "contender_vs_weak" and cand.get("m_gate") and not (cand.get("m_gate") or {}).get("ok", True):
        base["status"] = "refused"
        base["reason"] = cand.get("reason") or "pre_gate"
        base["remove"] = cand.get("remove")
        base["add"] = cand.get("add")
        base["source"] = cand.get("source")
        base["plain_english"] = f"Refused {cand.get('remove')}→{cand.get('add')}: {base['reason']}"
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    rem = str(cand["remove"])
    add = str(cand["add"])
    base["remove"] = rem
    base["add"] = add
    base["source"] = cand.get("source")
    base["candidate"] = {k: cand.get(k) for k in (
        "source", "arm", "add_score", "remove_score", "delta", "reason", "membership_potential_ok"
    )}

    # Hard refuse meme adds even if a bad CF write slipped through
    if _is_meme_pair(add) and bool((cfg.get("contender") or {}).get("skip_pump_names", True)):
        base["status"] = "refused"
        base["reason"] = f"meme_add_blocked:{add}"
        base["plain_english"] = f"Refused meme seat {rem}→{add}"
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    # Dust-only REMOVE: use enriched holdings (exchange + tryout lots)
    protect = float(cfg.get("protect_usd") or 5.0)
    held_map = _holdings()
    held_rem = float(held_map.get(rem, 0.0) or 0.0)
    base["remove_held_usd"] = held_rem
    if held_rem >= protect and not cfg.get("allow_residual_hold"):
        base["status"] = "refused"
        base["reason"] = f"remove_held_{held_rem:.2f}>=protect_{protect}"
        base["plain_english"] = (
            f"Refused {rem}→{add}: held ${held_rem:.2f} ≥ protect ${protect} "
            f"(dust-only eject; live shell stays)"
        )
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    applied_today = _count_applies_today(day)
    base["applies_today_before"] = applied_today
    if applied_today >= int(cfg.get("max_per_day") or 1):
        base["status"] = "skipped"
        base["reason"] = f"daily_cap:{applied_today}>={cfg.get('max_per_day')}"
        base["plain_english"] = f"Daily cap hit — would be {rem}→{add} via {cand.get('source')}."
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    pf = pam.preflight(rem, add, protect_usd=float(cfg.get("protect_usd") or 5.0))
    base["preflight"] = pf
    blockers = list(pf.get("blockers") or [])

    if (
        f"remove_not_in_basket:{rem}" in blockers
        and f"add_already_in_basket:{add}" in blockers
    ):
        base["status"] = "already"
        base["reason"] = "already_seated"
        base["counted"] = True
        base["plain_english"] = f"Already seated {rem}→{add}."
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb(base)
        return base

    hard = list(blockers)
    if cfg.get("allow_residual_hold"):
        hard = [b for b in hard if not str(b).startswith("remove_held_")]
    if hard:
        base["status"] = "refused"
        base["reason"] = " | ".join(hard)
        base["plain_english"] = f"Refused {rem}→{add}: {base['reason']}"
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    if pf.get("novelty_blocked") and not cfg.get("override_novelty", True):
        base["status"] = "refused"
        base["reason"] = "novelty_blocked_no_override"
        base["plain_english"] = f"Novelty blocked {add}; override off."
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    # Preferred-arm path still requires membership_potential_ok
    if cand.get("membership_potential_ok") is False:
        base["status"] = "refused"
        base["reason"] = "membership_potential_not_ok"
        base["plain_english"] = f"Refused {rem}→{add}: membership potential not OK"
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb({**base, "counted": False})
        return base

    if not live_apply:
        base["status"] = "dry_would_apply"
        base["reason"] = "dry_run_or_live_apply_false"
        base["counted"] = False
        base["novelty_override_used"] = bool(cfg.get("override_novelty")) and bool(pf.get("novelty_blocked"))
        base["plain_english"] = (
            f"DRY would seat {rem}→{add} via {cand.get('source')} "
            f"(protect=${cfg.get('protect_usd')}, no orders)."
        )
        save_career(career)
        _write_json(RECEIPT, base)
        _append_crumb(base)
        return base

    rc, promote_out = pam._run_promote(
        rem,
        add,
        dry_run=False,
        override_novelty=bool(cfg.get("override_novelty", True)),
        override_missfire=bool(cfg.get("override_missfire", False)),
        allow_residual=bool(cfg.get("allow_residual_hold", False)),
        protect_usd=float(cfg.get("protect_usd") or 5.0),
    )
    base["promote_rc"] = rc
    base["promote_tail"] = "\n".join((promote_out or "").splitlines()[-12:])
    base["novelty_override_used"] = bool(cfg.get("override_novelty")) and bool(pf.get("novelty_blocked"))

    if rc == 0:
        base["status"] = "applied"
        base["reason"] = f"membership_manager:{cand.get('source')}"
        base["pairs_now"] = list(load_trading_basket() or [])
        base["counted"] = True
        base["plain_english"] = (
            f"AUTO seat {rem}→{add} via {cand.get('source')} · no orders · "
            f"Brad not in path · kill {KILL.name}"
        )
        _career_touch(
            career,
            rem,
            event="ejected",
            detail={"outcome": "replaced", "add": add, "source": cand.get("source")},
        )
        _career_touch(
            career,
            add,
            event="seated",
            detail={"source": cand.get("source"), "remove": rem, "reason": cand.get("reason")},
        )
        # stamp decision file
        try:
            d_raw = _load_json(DECISION, {}) or {}
            d: Dict[str, Any] = dict(d_raw) if isinstance(d_raw, dict) else {}
            d["last_membership_manager"] = {
                "at": now.isoformat(),
                "remove": rem,
                "add": add,
                "source": cand.get("source"),
                "preferred_arm": preferred,
                "note": "self-regulating membership; no orders; dual_agree still manual",
            }
            # doctrine: Brad out of preferred-arm / manager path
            mm_raw = d.get("membership_manager")
            mm: Dict[str, Any] = dict(mm_raw) if isinstance(mm_raw, dict) else {}
            mm.update({
                "enabled": True,
                "live_apply": True,
                "brad_in_path": False,
                "dual_agree_auto": False,
                "last_apply_at": now.isoformat(),
                "note": "Brad GO 2026-10-03 self-regulating; dual_agree still manual GO",
            })
            d["membership_manager"] = mm
            # keep preferred_arm_auto enabled as subordinate source
            pam_raw = d.get("preferred_arm_auto_membership")
            pam_block: Dict[str, Any] = dict(pam_raw) if isinstance(pam_raw, dict) else {}
            pam_block.setdefault("enabled", True)
            pam_block["subordinate_to"] = "membership_manager"
            d["preferred_arm_auto_membership"] = pam_block
            _write_json(DECISION, d)
        except Exception as e:  # noqa: BLE001
            base["decision_stamp_error"] = f"{type(e).__name__}:{e}"
    else:
        base["status"] = "refused"
        base["reason"] = f"promote_rc={rc}"
        base["counted"] = False
        base["plain_english"] = f"Promote refused {rem}→{add} rc={rc}"

    save_career(career)
    _write_json(RECEIPT, base)
    _append_crumb(base)
    return base


def telegram_notice(result: Dict[str, Any]) -> Optional[str]:
    st = result.get("status")
    if st == "skipped" and result.get("reason") in {
        "no_candidate",
        "policy_disabled",
        "",
    }:
        return None
    rem, add = result.get("remove"), result.get("add")
    src = result.get("source") or "?"
    if st == "applied":
        nov = " · novelty override (seat only)" if result.get("novelty_override_used") else ""
        return (
            "✅ Membership Manager AUTO seat (self-regulating)\\n"
            f"• {rem} → {add} via `{src}`{nov}\\n"
            "• eligibility only · no orders · Brad not in path\\n"
            "• buy still needs RSI/sent/seats/run-phase\\n"
            f"• kill: touch {KILL}"
        )
    if st == "already":
        return f"ℹ️ Membership Manager: already seated {rem} → {add}"
    if st == "dry_would_apply":
        return f"DRY Membership Manager would seat {rem} → {add} ({src})"
    if st in {"refused", "error"}:
        return (
            "⚠️ Membership Manager REFUSED\\n"
            f"• {rem} → {add} ({src})\\n"
            f"• reason: {result.get('reason')}"
        )
    if st == "skipped" and str(result.get("reason") or "").startswith("daily_cap"):
        return (
            f"⏸️ Membership Manager daily cap — would {rem}→{add} ({src})"
        )
    if st == "skipped" and "kill" in str(result.get("reason") or ""):
        return f"⏸️ Membership Manager KILL on — {result.get('reason')}"
    return None


def dashboard_payload() -> Dict[str, Any]:
    """Thin API blob for Promote / Membership pane."""
    cfg = load_config()
    receipt = _load_json(RECEIPT, {}) or {}
    career = load_career()
    pairs = career.get("pairs") or {}
    by_career: Dict[str, int] = {}
    for row in pairs.values():
        if not isinstance(row, dict):
            continue
        c = str(row.get("career") or "unknown")
        by_career[c] = by_career.get(c, 0) + 1
    killed, kill_why = kill_switch_on(cfg)
    return {
        "schema": "membership_manager_dashboard_v1",
        "as_of": _utc_now().isoformat(),
        "enabled": bool(cfg.get("enabled")),
        "live_apply": bool(cfg.get("live_apply")),
        "kill": killed,
        "kill_why": kill_why or None,
        "brad_in_path": False,
        "dual_agree_auto": False,
        "max_per_day": cfg.get("max_per_day"),
        "protect_usd": cfg.get("protect_usd"),
        "sources": cfg.get("sources"),
        "last": {
            "status": receipt.get("status"),
            "reason": receipt.get("reason"),
            "remove": receipt.get("remove"),
            "add": receipt.get("add"),
            "source": receipt.get("source"),
            "ts": receipt.get("ts"),
            "plain_english": receipt.get("plain_english"),
        },
        "career_counts": by_career,
        "applies_today": _count_applies_today(),
        "plain_english": (
            receipt.get("plain_english")
            or "Membership manager armed — self-regulating seats, Brad out of path."
        ),
    }
