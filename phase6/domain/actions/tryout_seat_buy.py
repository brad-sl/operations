#!/usr/bin/env python3
"""TryoutSeatBuyAction — narrow one-pair $shell tryout open (not full rebalance).

Doctrine
--------
BookRebalanceAction owns held-book hygiene and **refuses** new tryout seats.
This action is the complementary money path for a *single* quality-tryout seat:

  RSI-event / latch / dual-clear → evaluate_buy_entry → $abs_cap shell BUY

Hard fences
-----------
- Default dry_run. Money only when go=True AND dry_run=False.
- Max one pair per invocation (no basket spray).
- Shell size = quality_tryout abs_cap_usd (policy), never > max_shell_usd param.
- evaluate_buy_entry is SSOT for doors (regime, blocks, seats/day, missfire, RSI/sent).
- Never force full rebalance / never mutate basket roster.
- Free/tee sentiment cannot unlock buys — caller must pass gate-grade eng (paid X / latch).

Artifacts
---------
  data/state/action_receipts/<tenant>/tryout_seat_buy_latest.json
  data/state/tryout_seat_buy_latest.json
  data/state/tryout_seat_buy_events.jsonl
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from phase6.core.paths import STATE_DIR
from phase6.domain.types import ActionReceipt, ActionRequest

logger = logging.getLogger("phase6.domain.tryout_seat_buy")

SCHEMA = "tryout_seat_buy_v1"
DEFAULT_RECEIPT_DIR = STATE_DIR / "action_receipts"
LATEST_PATH = STATE_DIR / "tryout_seat_buy_latest.json"
EVENTS_PATH = STATE_DIR / "tryout_seat_buy_events.jsonl"
LIVE_STATE_DEFAULT = STATE_DIR / "phase6_live_state.json"

DEFAULT_MAX_SHELL_USD = 75.0


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def held_pairs_from_live_state(live: Dict[str, Any]) -> Set[str]:
    """Non-stable held pairs from live state snapshot."""
    held: Set[str] = set()
    stables = {"USDT-USD", "USDC-USD", "USD-USD", "USDT-USDC", "USDC-USDT"}
    positions = live.get("positions") if isinstance(live, dict) else None
    if isinstance(positions, list):
        for row in positions:
            if not isinstance(row, dict):
                continue
            pair = _norm_pair(row.get("pair") or row.get("product_id") or "")
            if not pair or pair in stables:
                continue
            qty = _f(row.get("qty") or row.get("size") or row.get("quantity"))
            usd = _f(row.get("usd_value") or row.get("market_value") or row.get("notional_usd"))
            if qty > 1e-12 or usd > 1.0:
                held.add(pair)
    if isinstance(positions, dict):
        for k, v in positions.items():
            pair = _norm_pair(k if not isinstance(v, dict) else (v.get("pair") or k))
            if pair in stables:
                continue
            if isinstance(v, dict):
                qty = _f(v.get("qty") or v.get("size"))
                usd = _f(v.get("usd_value") or v.get("market_value"))
                if qty > 1e-12 or usd > 1.0:
                    held.add(pair)
            elif _f(v) > 1e-12:
                held.add(pair)
    ap = live.get("active_positions") if isinstance(live, dict) else None
    if isinstance(ap, list):
        for item in ap:
            if isinstance(item, str):
                p = _norm_pair(item)
                if p and p not in stables:
                    held.add(p)
            elif isinstance(item, dict):
                p = _norm_pair(item.get("pair") or item.get("product_id") or "")
                if p and p not in stables:
                    held.add(p)
    return held


def kill_switch_on() -> bool:
    try:
        from phase6.core.tryout_scale_up_live import kill_switch_on as _ks

        return bool(_ks())
    except Exception:
        return (STATE_DIR / "kill_switch.flag").exists()


def resolve_shell_usd(
    *,
    abs_cap_usd: float,
    max_shell_usd: float = DEFAULT_MAX_SHELL_USD,
    override_usd: Optional[float] = None,
) -> float:
    """Shell = min(policy abs_cap, max_shell, optional override)."""
    cap = max(0.0, _f(abs_cap_usd))
    hard = max(0.0, _f(max_shell_usd, DEFAULT_MAX_SHELL_USD))
    shell = cap if cap > 0 else hard
    if override_usd is not None:
        shell = min(shell, max(0.0, _f(override_usd)))
    shell = min(shell, hard) if hard > 0 else shell
    return round(max(shell, 0.0), 2)


@dataclass
class SeatPlan:
    pair: str
    shell_usd: float
    status: str  # planned | blocked | skipped_held | dry_would_buy | filled | error
    reasons: List[str] = field(default_factory=list)
    sentiment: Optional[float] = None
    rsi: Optional[float] = None
    eng_source: Optional[str] = None
    order_id: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def plan_tryout_seat(
    pair: str,
    *,
    sentiment: Optional[float],
    rsi: Optional[float],
    eng_source: str = "caller",
    held_pairs: Optional[Set[str]] = None,
    shell_usd: Optional[float] = None,
    max_shell_usd: float = DEFAULT_MAX_SHELL_USD,
    snap: Any = None,
    policy: Optional[Dict[str, Any]] = None,
    require_not_held: bool = True,
    isolation_skip_process_tax: bool = False,
) -> SeatPlan:
    """Plan one seat via evaluate_buy_entry + held/shell fences. No orders."""
    from phase6.core.regime_cash_policy import (
        _recovery_rec,
        evaluate_buy_entry,
        load_policy,
        recovery_quality_tryout_cfg,
        resolve_regime_cash,
    )

    p = _norm_pair(pair)
    held = set(held_pairs or set())

    if not p or "-USD" not in p:
        return SeatPlan(pair=p or str(pair), shell_usd=0.0, status="blocked", reasons=["bad_pair"])

    if require_not_held and p in held:
        return SeatPlan(
            pair=p,
            shell_usd=0.0,
            status="skipped_held",
            reasons=["already_held"],
            sentiment=sentiment,
            rsi=rsi,
            eng_source=eng_source,
        )

    pol = policy if isinstance(policy, dict) else load_policy()
    if isolation_skip_process_tax and isinstance(pol, dict):
        pol = dict(pol)
        pol["_isolation_skip_process_tax"] = True

    snap_l = snap if snap is not None else resolve_regime_cash()
    rec = _recovery_rec(pol if isinstance(pol, dict) else {})
    qt = recovery_quality_tryout_cfg(rec) if rec else {}
    abs_cap = _f((qt or {}).get("abs_cap_usd"), 25.0)
    shell = resolve_shell_usd(
        abs_cap_usd=abs_cap,
        max_shell_usd=max_shell_usd,
        override_usd=shell_usd,
    )
    if shell < 5.0 - 1e-9:
        return SeatPlan(
            pair=p,
            shell_usd=shell,
            status="blocked",
            reasons=[f"shell_usd={shell:.2f}<5"],
            sentiment=sentiment,
            rsi=rsi,
            eng_source=eng_source,
            detail={"abs_cap_usd": abs_cap, "qt": qt},
        )

    if kill_switch_on():
        return SeatPlan(
            pair=p,
            shell_usd=shell,
            status="blocked",
            reasons=["kill_switch"],
            sentiment=sentiment,
            rsi=rsi,
            eng_source=eng_source,
        )

    dec = evaluate_buy_entry(
        p,
        snap_l,
        sentiment=sentiment,
        rsi=rsi,
        is_new_pair=True,
        policy=pol if isinstance(pol, dict) else None,
    )
    if not bool(getattr(dec, "allowed", False)):
        return SeatPlan(
            pair=p,
            shell_usd=shell,
            status="blocked",
            reasons=list(getattr(dec, "reasons", None) or ["entry_blocked"]),
            sentiment=sentiment,
            rsi=rsi,
            eng_source=eng_source,
            detail={
                "abs_cap_usd": abs_cap,
                "entry_allowed": False,
                "strategy_mode": getattr(snap_l, "strategy_mode", None),
            },
        )

    return SeatPlan(
        pair=p,
        shell_usd=shell,
        status="planned",
        reasons=["ready_for_apply_when_go", "evaluate_buy_entry_ok", f"shell=${shell:.2f}"],
        sentiment=sentiment,
        rsi=rsi,
        eng_source=eng_source,
        detail={
            "abs_cap_usd": abs_cap,
            "entry_allowed": True,
            "strategy_mode": getattr(snap_l, "strategy_mode", None),
            "qt_max_rsi": (qt or {}).get("max_rsi"),
            "qt_min_sent": (qt or {}).get("min_sentiment"),
        },
    )


def _build_executor(shadow_mode: bool = True):
    from phase6.core.tryout_scale_up_live import _build_executor as _be

    return _be(shadow_mode=shadow_mode)


@dataclass
class TryoutSeatBuyAction:
    """Domain action: open at most one quality-tryout seat at $shell."""

    live_state_path: Path = field(default_factory=lambda: LIVE_STATE_DEFAULT)
    receipt_dir: Path = field(default_factory=lambda: DEFAULT_RECEIPT_DIR)
    latest_path: Path = field(default_factory=lambda: LATEST_PATH)
    events_path: Path = field(default_factory=lambda: EVENTS_PATH)
    write_receipt: bool = True
    executor_factory: Optional[Callable[[bool], Any]] = None

    def run(self, request: ActionRequest) -> ActionReceipt:
        t0 = time.perf_counter()
        params = dict(request.params or {})
        dry_run = bool(params.get("dry_run", True))
        go = bool(params.get("go", False))
        money = bool(go) and (not dry_run)

        pair = _norm_pair(params.get("pair") or "")
        sentiment = params.get("sentiment")
        if sentiment is not None:
            try:
                sentiment = float(sentiment)
            except (TypeError, ValueError):
                sentiment = None
        rsi = params.get("rsi")
        if rsi is not None:
            try:
                rsi = float(rsi)
            except (TypeError, ValueError):
                rsi = None
        eng_source = str(params.get("eng_source") or "caller")
        max_shell = _f(params.get("max_shell_usd"), DEFAULT_MAX_SHELL_USD)
        shell_override = params.get("shell_usd")
        if shell_override is not None:
            shell_override = _f(shell_override)
        require_not_held = bool(params.get("require_not_held", True))
        isolation_skip_tax = bool(params.get("_isolation_skip_process_tax", False))
        executor = params.get("executor")

        live_path = (
            Path(params["live_state_path"]) if params.get("live_state_path") else self.live_state_path
        )
        live = _read_json(live_path) if live_path else None
        held = held_pairs_from_live_state(live if isinstance(live, dict) else {})

        effects: List[str] = []
        if dry_run:
            effects.append("dry_run")
        if go:
            effects.append("go_intent")
        effects.append("no_full_rebalance")
        effects.append("single_pair_max")

        if not pair:
            receipt = ActionReceipt(
                action="tryout_seat_buy",
                tenant_id=request.tenant_id,
                idempotency_key=request.idempotency_key,
                ok=False,
                status="error",
                reasons=("pair_required",),
                effects=tuple(effects),
                artifacts={"schema": SCHEMA, "held_pairs": sorted(held)},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            self._persist(request, receipt)
            return receipt

        plan = plan_tryout_seat(
            pair,
            sentiment=sentiment,
            rsi=rsi,
            eng_source=eng_source,
            held_pairs=held,
            shell_usd=shell_override,
            max_shell_usd=max_shell,
            require_not_held=require_not_held,
            isolation_skip_process_tax=isolation_skip_tax,
            policy=params.get("policy") if isinstance(params.get("policy"), dict) else None,
            snap=params.get("snap"),
        )

        applied = False
        order_id = None
        mode = "dry_run"
        if plan.status == "planned" and not money:
            plan.status = "dry_would_buy"
            plan.reasons = list(plan.reasons) + ["dry_run_no_order"]
            mode = "dry_run_go" if go else "dry_run"
            effects.append(f"would_buy:{plan.pair}:${plan.shell_usd:.2f}")
        elif plan.status == "planned" and money:
            mode = "live"
            try:
                if executor is not None:
                    ex = executor
                else:
                    factory = self.executor_factory or _build_executor
                    ex = factory(False)
                if getattr(ex, "shadow_mode", False):
                    plan.status = "error"
                    plan.reasons = list(plan.reasons) + ["executor_shadow_mode_refused_for_live"]
                    effects.append("executor_shadow_refused")
                else:
                    buy = ex.execute_buy(plan.pair, plan.shell_usd)
                    ok_buy = bool(buy.get("success")) if isinstance(buy, dict) else False
                    order_id = (buy or {}).get("order_id") if isinstance(buy, dict) else None
                    plan.order_id = order_id
                    plan.detail["buy_result"] = (
                        {
                            k: (buy or {}).get(k)
                            for k in (
                                "success",
                                "order_id",
                                "entry_price",
                                "size",
                                "sl_attached",
                                "execution_style",
                                "fill_status",
                                "error",
                            )
                        }
                        if isinstance(buy, dict)
                        else {}
                    )
                    if ok_buy:
                        applied = True
                        plan.status = "filled"
                        plan.reasons = list(plan.reasons) + ["order_filled"]
                        effects.append(f"filled:{plan.pair}:{order_id or 'no_id'}")
                        # R5 bridge: register open tryout lot for scale-up ladder
                        try:
                            from phase6.core.tryout_scale_up_shadow import (
                                register_tryout_open_lot,
                            )

                            entry_px = None
                            if isinstance(buy, dict):
                                entry_px = buy.get("entry_price")
                            reg = register_tryout_open_lot(
                                plan.pair,
                                shell_usd=float(plan.shell_usd or 0),
                                entry_price=float(entry_px) if entry_px is not None else None,
                                order_id=str(order_id or "") or None,
                                source="tryout_seat_buy",
                            )
                            plan.detail["scale_up_lot"] = reg
                            effects.append(f"scale_up_lot_registered:{plan.pair}")
                        except Exception as e:
                            effects.append(f"scale_up_lot_register_failed:{type(e).__name__}")
                            logger.warning("register_tryout_open_lot failed: %s", e)
                    else:
                        plan.status = "error"
                        err = str((buy or {}).get("error") or "execute_buy_failed")
                        plan.reasons = list(plan.reasons) + [err]
                        effects.append(f"buy_failed:{err}")
            except Exception as e:
                plan.status = "error"
                plan.reasons = list(plan.reasons) + [f"execute_exception:{e}"]
                effects.append(f"execute_exception:{type(e).__name__}")
                logger.exception("tryout_seat_buy execute failed for %s", plan.pair)
        elif plan.status == "skipped_held":
            effects.append(f"skip_held:{plan.pair}")
        elif plan.status == "blocked":
            effects.append(f"blocked:{plan.pair}")

        # Map plan status → receipt status
        if plan.status in ("dry_would_buy",) or (plan.status == "planned" and dry_run):
            status: str = "dry_run"
            ok = True
        elif plan.status == "filled":
            status = "ok"
            ok = True
        elif plan.status == "skipped_held":
            status = "noop"
            ok = True
        elif plan.status == "blocked":
            status = "blocked"
            ok = True  # gate refuse is successful evaluation
        elif plan.status == "error":
            status = "error"
            ok = False
        else:
            status = "ok" if not dry_run else "dry_run"
            ok = True

        artifacts: Dict[str, Any] = {
            "schema": SCHEMA,
            "mode": mode,
            "go": go,
            "money": money,
            "dry_run": dry_run,
            "plan": plan.to_dict(),
            "held_pairs": sorted(held),
            "applied": applied,
            "order_id": order_id,
            "live_state_path": str(live_path),
            "note": (
                "Narrow tryout seat only — not book_rebalance. "
                "Money requires go=True AND dry_run=False."
            ),
            "ts": _utc_iso(),
        }

        receipt = ActionReceipt(
            action="tryout_seat_buy",
            tenant_id=request.tenant_id,
            idempotency_key=request.idempotency_key,
            ok=ok,
            status=status,  # type: ignore[arg-type]
            reasons=tuple(plan.reasons),
            effects=tuple(effects),
            artifacts=artifacts,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        self._persist(request, receipt)
        return receipt

    def _persist(self, request: ActionRequest, receipt: ActionReceipt) -> None:
        try:
            if self.write_receipt:
                d = self.receipt_dir / request.tenant_id
                d.mkdir(parents=True, exist_ok=True)
                (d / "tryout_seat_buy_latest.json").write_text(
                    json.dumps(receipt.to_dict(), indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
                with (d / "tryout_seat_buy_crumbs.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(receipt.to_dict(), default=str) + "\n")
            payload = {
                "schema": SCHEMA,
                "as_of": _utc_iso(),
                "receipt": receipt.to_dict(),
            }
            _write_json(self.latest_path, payload)
            _append_jsonl(
                self.events_path,
                {
                    "ts": _utc_iso(),
                    "idempotency_key": request.idempotency_key,
                    "status": receipt.status,
                    "ok": receipt.ok,
                    "pair": ((receipt.artifacts or {}).get("plan") or {}).get("pair"),
                    "applied": (receipt.artifacts or {}).get("applied"),
                    "reasons": list(receipt.reasons)[:5],
                },
            )
        except Exception as e:
            logger.warning("tryout_seat_buy persist failed: %s", e)


def run_tryout_seat_buy(req: ActionRequest, **kwargs: Any) -> ActionReceipt:
    return TryoutSeatBuyAction(**kwargs).run(req)


def handler_from_action(action: Optional[TryoutSeatBuyAction] = None):
    act = action or TryoutSeatBuyAction()

    def _h(req: ActionRequest) -> ActionReceipt:
        return act.run(req)

    return _h
