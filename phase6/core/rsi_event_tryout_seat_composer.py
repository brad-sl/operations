#!/usr/bin/env python3
"""RSI-event → optional paid X probe → TryoutSeatBuyAction composer.

Not a full rebalance. Flow:

  1. Universe = production tryout-eligible doors under current regime
  2. RSI door = quality_tryout max_rsi (regime), not a tighter shadow-only band
  3. Optional paid X probe (budget-capped) on wash+stale doors
  4. Pick best dual-clear candidate (gate-grade eng + latch)
  5. Dispatch tryout_seat_buy (default dry_run; money only with --go-buy --live)

Hard fences
-----------
- place_orders / money off unless go_buy=True AND dry_run=False
- Max one seat attempt per run
- Free/tee cannot unlock buys (probe writes paid X / latch only)
- Does not call book_rebalance / force_rebalance
- Cron post-RSI path: spend_x under budget OK; money always OFF

Artifacts
---------
  data/state/rsi_event_tryout_seat_composer_latest.json
  data/state/rsi_event_tryout_seat_composer_events.jsonl
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import STATE_DIR
from phase6.domain.actions.tryout_seat_buy import (
    TryoutSeatBuyAction,
    handler_from_action,
)
from phase6.domain.dispatcher import ActionDispatcher
from phase6.domain.types import ActionRequest

logger = logging.getLogger("phase6.core.rsi_event_tryout_seat_composer")

SCHEMA = "rsi_event_tryout_seat_composer_v1"
LATEST = STATE_DIR / "rsi_event_tryout_seat_composer_latest.json"
EVENTS = STATE_DIR / "rsi_event_tryout_seat_composer_events.jsonl"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def resolve_regime_tryout_defaults() -> Dict[str, Any]:
    """Pull floor / max_rsi / abs_cap / eligible doors from live quality_tryout policy."""
    out: Dict[str, Any] = {
        "floor": 0.30,
        "rsi_max": 55.0,
        "abs_cap_usd": 25.0,
        "max_new_seats_per_day": 4,
        "eligible_pairs": [],
        "strategy_mode": None,
        "allow_new_buys": None,
        "regime": None,
    }
    try:
        from phase6.core.regime_cash_policy import (
            _recovery_rec,
            load_policy,
            recovery_quality_tryout_cfg,
            resolve_regime_cash,
        )
        from phase6.core.rsi_event_x_tryout_shadow import production_tryout_eligible_sources

        snap = resolve_regime_cash()
        out["strategy_mode"] = getattr(snap, "strategy_mode", None)
        out["allow_new_buys"] = getattr(snap, "allow_new_buys", None)
        out["regime"] = getattr(snap, "regime", None)
        pol = load_policy()
        rec = _recovery_rec(pol)
        qt = recovery_quality_tryout_cfg(rec) if rec else {}
        if qt:
            out["floor"] = float(qt.get("min_sentiment") or out["floor"])
            out["rsi_max"] = float(qt.get("max_rsi") or out["rsi_max"])
            out["abs_cap_usd"] = float(qt.get("abs_cap_usd") or out["abs_cap_usd"])
            out["max_new_seats_per_day"] = int(qt.get("max_new_seats_per_day") or 4)
        src = production_tryout_eligible_sources()
        uni = list(src.get("universe") or src.get("policy_effective_eligible") or [])
        out["eligible_pairs"] = sorted({_norm_pair(p) for p in uni if p})
        out["universe_source"] = src.get("source")
    except Exception as e:
        out["resolve_err"] = f"{type(e).__name__}:{e}"
    return out


@dataclass
class ComposerConfig:
    # top_k=0 → auto = all regime-eligible doors
    top_k: int = 0
    floor: float = 0.0  # 0 → resolve from quality_tryout
    rsi_max: float = 0.0  # 0 → resolve from quality_tryout max_rsi
    max_shell_usd: float = 75.0
    # X spend
    spend_x: bool = False  # paid probe
    dry_run_x: bool = True  # probe dry unless spend_x
    # Seat buy
    go_buy: bool = False
    dry_run_buy: bool = True  # money only if go_buy and not dry_run_buy
    tenant_id: str = "default"
    actor: str = "composer"
    pair_override: str = ""  # force one pair (still must clear gates)
    max_rsi_day: int = 4  # allow full small tryout set under daily budget
    max_day: int = 8
    cooldown_h: float = 6.0
    # Post-RSI cron: never money
    post_rsi: bool = False


def _load_latch_score(pair: str) -> Optional[Tuple[float, Dict[str, Any]]]:
    try:
        from phase6.core.tryout_sent_latch import active_latch_for_pair

        lat = active_latch_for_pair(_norm_pair(pair))
        if not isinstance(lat, dict):
            return None
        score = lat.get("cleared_sent")
        if score is None:
            score = lat.get("score") or lat.get("sentiment") or lat.get("eng") or lat.get("x_raw")
        if score is None:
            return None
        return float(score), lat
    except Exception:
        return None


def _candidate_eng_from_probe_row(row: Dict[str, Any], floor: float) -> Optional[Dict[str, Any]]:
    """Extract gate-grade eng after probe/shadow row."""
    pair = _norm_pair(row.get("pair") or "")
    if not pair:
        return None
    # Prefer fresh paid fetch
    fetched = row.get("fetched_raw")
    if fetched is None:
        fetched = row.get("x_raw_after") or row.get("x_raw")
    age = row.get("x_age_min_after")
    if age is None:
        age = row.get("x_age_min")
    source = str(row.get("eng_source") or row.get("x_source") or "probe")

    eng = None
    if fetched is not None:
        try:
            eng = float(fetched)
            source = source if "x" in source.lower() or source == "probe" else "paid_x"
        except (TypeError, ValueError):
            eng = None

    # Latch fallback (A2) — still gate-grade if latch was set from paid X
    latch = _load_latch_score(pair)
    if latch is not None:
        lat_score, lat_meta = latch
        if eng is None or lat_score >= (eng or -1):
            # use latch if eng missing or latch is the clearing path
            if eng is None or eng < floor <= lat_score:
                eng = lat_score
                source = "tryout_sent_latch"
                row = dict(row)
                row["latch"] = {k: lat_meta.get(k) for k in list(lat_meta)[:12]}

    if eng is None:
        # last resort: eng_sent on board if marked fresh enough (rare mid-cycle)
        es = row.get("eng_sent")
        if es is not None and _f(es) >= floor and _f(row.get("eng_age_min"), 999) < 20:
            eng = _f(es)
            source = str(row.get("eng_source") or "eng_cache_fresh")

    if eng is None:
        return None
    return {
        "pair": pair,
        "eng": float(eng),
        "eng_source": source,
        "rsi": row.get("rsi"),
        "clears_floor": float(eng) >= float(floor),
        "row": row,
    }


def select_buy_candidate(
    rows: Sequence[Dict[str, Any]],
    *,
    floor: float = 0.30,
    pair_override: str = "",
    rsi_max: float = 55.0,
) -> Optional[Dict[str, Any]]:
    """Pick best dual-clear row: eng>=floor AND RSI<=rsi_max (regime door). Prefer deeper wash."""
    override = _norm_pair(pair_override)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        c = _candidate_eng_from_probe_row(raw, floor)
        if not c or not c.get("clears_floor"):
            continue
        pair = c["pair"]
        if override and pair != override:
            continue
        rsi = c.get("rsi")
        try:
            rsi_f = float(rsi) if rsi is not None else None
        except (TypeError, ValueError):
            rsi_f = None
        # Must sit in regime RSI door unless explicit override forces the pair
        if not override:
            if rsi_f is None or rsi_f > float(rsi_max):
                continue
        else:
            if rsi_f is None:
                rsi_f = 50.0
        # deeper wash + higher eng
        rank = (float(rsi_max) - float(rsi_f)) * 2.0 + float(c["eng"]) * 10.0
        scored.append((rank, c))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]["pair"]))
    return scored[0][1]


def run_composer(cfg: Optional[ComposerConfig] = None, **kwargs: Any) -> Dict[str, Any]:
    """Run shadow → optional probe → optional tryout_seat_buy.

    kwargs override ComposerConfig fields.
    Universe = all production tryout-eligible doors for current regime.
    RSI door defaults to quality_tryout max_rsi (not shadow-only 40).
    """
    base = cfg or ComposerConfig()
    for k, v in kwargs.items():
        if hasattr(base, k):
            setattr(base, k, v)
    cfg = base

    # Policy ladder: approval (default) vs autonomous after N Brad GOs
    from phase6.core.rsi_event_tryout_seat_policy import (
        autonomous_money_allowed,
        kill_switch_on,
        load_policy,
        record_manual_go,
    )

    pol = load_policy()
    auto_ok = autonomous_money_allowed(pol) and (not kill_switch_on())

    # Post-RSI: money OFF unless autonomous fully armed; approval mode never money here
    if cfg.post_rsi:
        if auto_ok:
            cfg.go_buy = True
            cfg.dry_run_buy = False
            cfg.actor = cfg.actor or "post_rsi_auto"
        else:
            cfg.go_buy = False
            cfg.dry_run_buy = True

    if kill_switch_on():
        cfg.go_buy = False
        cfg.dry_run_buy = True

    regime = resolve_regime_tryout_defaults()
    if not cfg.floor or cfg.floor <= 0:
        cfg.floor = float(regime.get("floor") or 0.30)
    if not cfg.rsi_max or cfg.rsi_max <= 0:
        cfg.rsi_max = float(regime.get("rsi_max") or 55.0)
    elig = list(regime.get("eligible_pairs") or [])
    if not cfg.top_k or cfg.top_k <= 0:
        cfg.top_k = max(len(elig), 2)

    from phase6.core.rsi_event_x_probe import run_probe
    from phase6.core.rsi_event_x_tryout_shadow import ShadowConfig, build_shadow_board
    from phase6.core.x_query_budget import BudgetConfig

    bcfg = BudgetConfig(
        max_pair_queries_per_day=int(cfg.max_day),
        max_rsi_pair_queries_per_day=int(cfg.max_rsi_day),
        per_pair_cooldown_hours=float(cfg.cooldown_h),
    )

    # Full eligible board at regime RSI door (for inventory + dual-clear without X)
    board_full = build_shadow_board(
        ShadowConfig(
            rsi_wash_max=float(cfg.rsi_max),
            top_k=int(cfg.top_k),
            tryout_floor=float(cfg.floor),
            place_orders=False,
            mutate_config=False,
            spend_x=False,
        )
    )

    # Probe path: spends X only if spend_x and not dry_run_x (budget-capped)
    spend = bool(cfg.spend_x) and (not cfg.dry_run_x)
    probe = run_probe(
        dry_run=not spend,
        spend_x=spend,
        top_k=int(cfg.top_k),
        floor=float(cfg.floor),
        rsi_max=float(cfg.rsi_max),
        budget_cfg=bcfg,
    )

    # Collect candidate rows from full regime board + probe
    # board_full.candidates = ALL production tryout-eligible doors
    # selected_pre = wash doors ranked for X; x_scores = post-paid map
    rows: List[Dict[str, Any]] = []
    elig_set = {_norm_pair(p) for p in elig} if elig else set()

    def _extend_rows(block: Any) -> None:
        if isinstance(block, list):
            rows.extend([r for r in block if isinstance(r, dict)])

    if isinstance(board_full, dict):
        for key in ("candidates", "selected", "trigger_pool", "all"):
            _extend_rows(board_full.get(key))

    if isinstance(probe, dict):
        for key in ("selected_pre", "fetched_rows", "selected", "candidates", "results"):
            _extend_rows(probe.get(key))
        for nest_key in ("board", "board_post", "shadow_board_snip"):
            board = probe.get(nest_key)
            if isinstance(board, dict):
                for key in ("selected", "candidates", "trigger_pool"):
                    _extend_rows(board.get(key))
        # Merge paid x_scores into pair rows
        x_scores = probe.get("x_scores") if isinstance(probe.get("x_scores"), dict) else {}
        latch_writes = probe.get("latch_writes") if isinstance(probe.get("latch_writes"), dict) else {}
        score_rows: List[Dict[str, Any]] = []
        for p, row in x_scores.items():
            if not isinstance(row, dict):
                continue
            pn = _norm_pair(p)
            lat = latch_writes.get(pn) or latch_writes.get(p) or {}
            score_rows.append(
                {
                    "pair": pn,
                    "fetched_raw": row.get("sentiment"),
                    "x_raw": row.get("sentiment"),
                    "x_posts": row.get("post_count"),
                    "eng_source": "paid_x_probe",
                    "latch_meta": lat,
                    "rsi": None,  # filled from selected_pre if present
                }
            )
        rows.extend(score_rows)

    # de-dupe by pair keeping last; backfill rsi; regime-eligible filter
    by_pair: Dict[str, Dict[str, Any]] = {}
    rsi_map: Dict[str, Any] = {}
    for r in rows:
        p = _norm_pair(r.get("pair") or "")
        if not p:
            continue
        if elig_set and p not in elig_set and not cfg.pair_override:
            continue
        if r.get("rsi") is not None:
            rsi_map[p] = r.get("rsi")
        prev = by_pair.get(p) or {}
        merged = dict(prev)
        merged.update({k: v for k, v in r.items() if v is not None})
        if merged.get("rsi") is None and p in rsi_map:
            merged["rsi"] = rsi_map[p]
        by_pair[p] = merged
    rows = list(by_pair.values())

    # Inventory: every eligible door with RSI vs regime door
    universe_scan: List[Dict[str, Any]] = []
    for p in sorted(elig_set or {_norm_pair(r.get("pair") or "") for r in rows}):
        r = by_pair.get(p) or {}
        rsi_v = r.get("rsi")
        try:
            rsi_f = float(rsi_v) if rsi_v is not None else None
        except (TypeError, ValueError):
            rsi_f = None
        universe_scan.append(
            {
                "pair": p,
                "rsi": rsi_f,
                "in_rsi_door": (rsi_f is not None and rsi_f <= float(cfg.rsi_max)),
                "eng_sent": r.get("eng_sent"),
                "trigger_rsi_wash": bool(r.get("trigger_rsi_wash")),
                "trigger_eng_stale": bool(r.get("trigger_eng_stale")),
                "tryout_eligible": bool(r.get("tryout_eligible", True)),
            }
        )

    cand = select_buy_candidate(
        rows,
        floor=cfg.floor,
        pair_override=cfg.pair_override,
        rsi_max=float(cfg.rsi_max),
    )

    seat_receipt = None
    seat_skipped_reason = None
    if cand is None:
        seat_skipped_reason = "no_dual_clear_candidate"
    else:
        money = bool(cfg.go_buy) and (not cfg.dry_run_buy)
        key = (
            f"rsi-event-seat-{cand['pair']}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        req = ActionRequest(
            action="tryout_seat_buy",
            tenant_id=cfg.tenant_id,
            idempotency_key=key,
            params={
                "pair": cand["pair"],
                "sentiment": cand["eng"],
                "rsi": cand.get("rsi"),
                "eng_source": cand.get("eng_source") or "composer",
                "max_shell_usd": cfg.max_shell_usd,
                "dry_run": not money,
                "go": bool(cfg.go_buy),
            },
            actor=cfg.actor,
        )
        d = ActionDispatcher()
        d.register("tryout_seat_buy", handler_from_action(TryoutSeatBuyAction()))
        seat_receipt = d.dispatch(req).to_dict()
        # Ladder: count real fills toward autonomous (manual or auto)
        try:
            arts = (seat_receipt or {}).get("artifacts") or {}
            plan = arts.get("plan") if isinstance(arts.get("plan"), dict) else {}
            cand_pair = str((cand or {}).get("pair") or "")
            if str(plan.get("status") or "") == "filled" and money:
                record_manual_go(
                    pair=cand_pair,
                    shell_usd=float(plan.get("shell_usd") or 0),
                    receipt_id=str(
                        (seat_receipt or {}).get("idempotency_key")
                        or (seat_receipt or {}).get("receipt_id")
                        or key
                    ),
                    note="composer_fill",
                    source="auto_fill" if auto_ok and cfg.post_rsi else "manual_or_cli_fill",
                )
                pol = load_policy()
        except Exception as e:
            logger.warning("record_manual_go failed: %s", e)

    plain_bits = [
        f"probe dry={probe.get('dry_run') if isinstance(probe, dict) else None} "
        f"spend_exec={probe.get('spend_x_executed') if isinstance(probe, dict) else None}",
    ]
    if cand:
        plain_bits.append(
            f"candidate {cand['pair']} eng={cand['eng']:.3f} src={cand.get('eng_source')} "
            f"rsi={cand.get('rsi')}"
        )
    else:
        plain_bits.append("no dual-clear candidate")
    if seat_receipt:
        plain_bits.append(
            f"seat status={seat_receipt.get('status')} ok={seat_receipt.get('ok')} "
            f"reasons={list(seat_receipt.get('reasons') or [])[:2]}"
        )
    elif seat_skipped_reason:
        plain_bits.append(seat_skipped_reason)

    n_in_door = sum(1 for u in universe_scan if u.get("in_rsi_door"))
    plain_bits.insert(
        0,
        f"regime doors={len(universe_scan)} rsi_door≤{cfg.rsi_max:g} in_door={n_in_door} "
        f"mode={regime.get('strategy_mode')}",
    )

    from phase6.core.rsi_event_tryout_seat_policy import (
        approval_telegram_card,
        manual_go_count,
        policy_status_plain,
        ready_to_arm_autonomous,
    )

    money_flag = bool(cfg.go_buy) and (not cfg.dry_run_buy)
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "config": {
            "top_k": cfg.top_k,
            "floor": cfg.floor,
            "rsi_max": cfg.rsi_max,
            "max_shell_usd": cfg.max_shell_usd,
            "spend_x": cfg.spend_x,
            "dry_run_x": cfg.dry_run_x,
            "go_buy": cfg.go_buy,
            "dry_run_buy": cfg.dry_run_buy,
            "money": money_flag,
            "pair_override": cfg.pair_override or None,
            "post_rsi": bool(cfg.post_rsi),
            "auto_ok": bool(auto_ok),
        },
        "policy": {
            "mode": pol.get("mode"),
            "auto_armed": pol.get("auto_armed"),
            "manual_gos": manual_go_count(pol),
            "required_manual_gos": pol.get("required_manual_gos"),
            "ready_to_arm": ready_to_arm_autonomous(pol),
            "autonomous_money": autonomous_money_allowed(pol),
            "kill": kill_switch_on(),
            "plain": policy_status_plain(),
        },
        "regime": {
            k: regime.get(k)
            for k in (
                "strategy_mode",
                "allow_new_buys",
                "regime",
                "floor",
                "rsi_max",
                "abs_cap_usd",
                "max_new_seats_per_day",
                "eligible_pairs",
                "universe_source",
                "resolve_err",
            )
        },
        "universe_scan": universe_scan,
        "n_universe": len(universe_scan),
        "n_in_rsi_door": n_in_door,
        "board_full": {
            k: (board_full or {}).get(k)
            for k in (
                "n_universe",
                "n_trigger_pool",
                "n_selected_top_k",
                "plain_english",
            )
        }
        if isinstance(board_full, dict)
        else None,
        "probe": {
            k: (probe or {}).get(k)
            for k in (
                "schema",
                "dry_run",
                "spend_x_executed",
                "fetched",
                "n_selected",
                "n_trigger_pool",
                "plain_english",
                "budget",
            )
        }
        if isinstance(probe, dict)
        else {"raw_type": type(probe).__name__},
        "n_candidate_rows": len(rows),
        "candidate": {k: cand.get(k) for k in ("pair", "eng", "eng_source", "rsi", "clears_floor")}
        if cand
        else None,
        "seat_skipped_reason": seat_skipped_reason,
        "seat_receipt": seat_receipt,
        "plain_english": " | ".join(plain_bits),
        "note": (
            "Composer only. Scans all regime tryout-eligible doors. "
            "Approval ladder: first N Brad GOs via TG; then --arm-auto for 24×7. "
            "Not book_rebalance."
        ),
    }
    # Quiet approval card (empty when no dual-clear / deduped / already autonomous)
    try:
        card = approval_telegram_card(payload, force=False, mark_sent=True)
    except Exception as e:
        logger.warning("approval card failed: %s", e)
        card = ""
    payload["approval_card"] = card or None
    payload["approval_pending"] = bool(card)

    # keep fuller probe on disk only in events crumb size-safe: store path ref
    try:
        _write_json(LATEST, payload)
        if card:
            _write_json(
                STATE_DIR / "rsi_event_tryout_seat_approval_pending.json",
                {
                    "ts": _utc_iso(),
                    "card": card,
                    "candidate": payload.get("candidate"),
                    "policy": payload.get("policy"),
                },
            )
        _append_jsonl(
            EVENTS,
            {
                "ts": _utc_iso(),
                "candidate": payload.get("candidate"),
                "seat_status": (seat_receipt or {}).get("status"),
                "money": payload["config"]["money"],
                "approval_pending": bool(card),
                "spend_x_executed": (payload.get("probe") or {}).get("spend_x_executed"),
                "plain": payload.get("plain_english"),
            },
        )
    except Exception as e:
        logger.warning("composer persist failed: %s", e)
        payload["persist_error"] = str(e)
    return payload


def telegram_summary(payload: Dict[str, Any]) -> str:
    """Prefer quiet approval card; else short status (always non-empty for --telegram)."""
    card = payload.get("approval_card")
    if card:
        return str(card)
    try:
        from phase6.core.rsi_event_tryout_seat_policy import approval_telegram_card

        card2 = approval_telegram_card(payload, force=True, mark_sent=False)
        if card2:
            return card2
    except Exception:
        pass
    c = payload.get("candidate") or {}
    seat = payload.get("seat_receipt") or {}
    cfg = payload.get("config") or {}
    pol = payload.get("policy") or {}
    lines = [
        "RSI-event → tryout seat composer",
        payload.get("plain_english") or "",
        f"money={cfg.get('money')} auto_ok={cfg.get('auto_ok')} "
        f"policy={pol.get('mode')} gos={pol.get('manual_gos')}/{pol.get('required_manual_gos')}",
    ]
    if c:
        lines.append(f"cand {c.get('pair')} eng={c.get('eng')} rsi={c.get('rsi')}")
    if seat:
        arts = seat.get("artifacts") or {}
        plan = arts.get("plan") or {}
        lines.append(
            f"seat {seat.get('status')} shell=${(plan.get('shell_usd') or 0):.0f} "
            f"applied={arts.get('applied')}"
        )
    return "\n".join(lines)


def approval_stdout(payload: Dict[str, Any], *, force: bool = False) -> str:
    """Cron quiet contract: card body or empty string."""
    if payload.get("approval_card") and not force:
        return str(payload.get("approval_card") or "")
    try:
        from phase6.core.rsi_event_tryout_seat_policy import approval_telegram_card

        return approval_telegram_card(payload, force=force, mark_sent=not force)
    except Exception:
        return ""
