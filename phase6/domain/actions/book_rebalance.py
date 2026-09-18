"""BookRebalanceAction — maintain held book; never open new tryout seats.

docs/plans/2026-09-18-streamlined-action-architecture.md §5.1 / Task 6
docs/plans/2026-09-16-rebalance-book-vs-rsi-buy-x-split.md Task 3

Default: dry_run. No orders. No membership swaps. No full-pool X.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.rebalance_x_candidates import rebalance_x_candidates
from phase6.domain.types import (
    ActionReceipt,
    ActionRequest,
    BookLeg,
    classify_leg,
    filter_book_legs,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE = ROOT / "data" / "state" / "phase6_live_state.json"
DEFAULT_RECEIPT_DIR = ROOT / "data" / "state" / "action_receipts"


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if s and "-" not in s:
        s = f"{s}-USD"
    return s


def held_pairs_from_live_state(live: Dict[str, Any]) -> List[str]:
    """Extract held non-zero pairs from phase6_live_state-like dict."""
    out: List[str] = []
    seen = set()

    def _add(pair: str, qty_or_usd: float) -> None:
        p = _norm_pair(pair)
        if not p or p in seen:
            return
        if qty_or_usd and float(qty_or_usd) > 0:
            seen.add(p)
            out.append(p)

    # positions: list of dicts or map
    positions = live.get("positions") or live.get("trading_positions") or []
    if isinstance(positions, dict):
        for k, v in positions.items():
            if isinstance(v, dict):
                q = v.get("qty") or v.get("quantity") or v.get("usd") or v.get("value") or 0
                _add(str(v.get("pair") or v.get("product_id") or k), float(q or 0))
            else:
                try:
                    _add(str(k), float(v or 0))
                except (TypeError, ValueError):
                    pass
    elif isinstance(positions, list):
        for row in positions:
            if not isinstance(row, dict):
                continue
            q = row.get("qty") or row.get("quantity") or row.get("usd_value") or row.get("value_usd") or 0
            try:
                qf = float(q or 0)
            except (TypeError, ValueError):
                qf = 0.0
            _add(str(row.get("pair") or row.get("product_id") or ""), qf)

    # active_positions sometimes list of pair strings
    ap = live.get("active_positions")
    if isinstance(ap, list):
        for item in ap:
            if isinstance(item, str):
                _add(item, 1.0)
            elif isinstance(item, dict):
                q = item.get("qty") or item.get("usd") or 1
                _add(str(item.get("pair") or item.get("product_id") or ""), float(q or 0))

    return out


def load_live_state(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_LIVE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@dataclass
class BookRebalanceAction:
    """Pure-ish book maintenance planner + refuse filter.

    Does not place orders. Optional write of receipt JSON under tenant namespace.
    """

    live_state_path: Path = field(default_factory=lambda: DEFAULT_LIVE)
    receipt_dir: Path = field(default_factory=lambda: DEFAULT_RECEIPT_DIR)
    write_receipt: bool = True

    def run(self, req: ActionRequest) -> ActionReceipt:
        t0 = time.perf_counter()
        params = dict(req.params or {})
        dry_run = bool(params.get("dry_run", True))
        allow_new = bool(params.get("allow_new_tryout_seats", False))
        allow_opp = bool(params.get("allow_opportunity_entries", False))
        spend_x = bool(params.get("spend_x_for_candidates", False))  # never true by default
        reattach = bool(params.get("reattach_protectives", True))
        raw_legs_in: Sequence[Dict[str, Any]] = params.get("plan_legs") or []

        live_path = Path(params["live_state_path"]) if params.get("live_state_path") else self.live_state_path
        live = load_live_state(live_path)
        held = held_pairs_from_live_state(live)
        held_set = set(held)

        # Classify legs (from params for tests; empty → noop plan)
        legs: List[BookLeg] = [classify_leg(dict(r), held_pairs=held_set) for r in raw_legs_in]
        keep, refused, refuse_reasons = filter_book_legs(
            legs,
            allow_new_tryout_seats=allow_new,
            allow_opportunity_entries=allow_opp,
        )

        x_cands = sorted(
            rebalance_x_candidates(
                held_pairs=held,
                plan_pairs=[lg.pair for lg in keep],
            )
        )

        effects: List[str] = []
        for lg in keep:
            effects.append(f"keep:{lg.kind}:{lg.pair}")
        for lg in refused:
            effects.append(f"refuse:{lg.kind}:{lg.pair}")
        if reattach:
            effects.append("would_reattach_protectives")
        if spend_x:
            effects.append("spend_x_requested_but_disabled_in_v1")
        # v1 never spends X or places orders
        effects.append("no_orders")
        if dry_run:
            effects.append("dry_run")

        reasons = list(refuse_reasons)
        if not legs and not held:
            reasons.append("empty_book_and_plan")
        elif not legs:
            reasons.append("no_plan_legs_maintenance_noop")

        status = "dry_run" if dry_run else "ok"
        if not keep and refused:
            # refused everything that mattered
            status = "dry_run" if dry_run else "blocked"
        if not legs and held:
            status = "noop" if not dry_run else "dry_run"

        artifacts: Dict[str, Any] = {
            "held_pairs": held,
            "x_candidates": x_cands,
            "legs_in": [lg.to_dict() for lg in legs],
            "legs_keep": [lg.to_dict() for lg in keep],
            "legs_refused": [lg.to_dict() for lg in refused],
            "dry_run": dry_run,
            "allow_new_tryout_seats": allow_new,
            "spend_x_for_candidates": False,  # forced off in v1
            "reattach_protectives": reattach,
            "live_state_path": str(live_path),
            "book_rebalance_refuses_new_seats": not allow_new,
            "orders": [],
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        receipt = ActionReceipt(
            action="book_rebalance",
            tenant_id=req.tenant_id,
            idempotency_key=req.idempotency_key,
            ok=True,
            status=status,  # type: ignore[arg-type]
            reasons=tuple(reasons),
            effects=tuple(effects),
            artifacts=artifacts,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        if self.write_receipt:
            self._persist(req.tenant_id, receipt)

        return receipt

    def _persist(self, tenant_id: str, receipt: ActionReceipt) -> None:
        try:
            d = self.receipt_dir / tenant_id
            d.mkdir(parents=True, exist_ok=True)
            latest = d / "book_rebalance_latest.json"
            latest.write_text(json.dumps(receipt.to_dict(), indent=2), encoding="utf-8")
            # crumb
            crumb = d / "book_rebalance_crumbs.jsonl"
            with crumb.open("a", encoding="utf-8") as f:
                f.write(json.dumps(receipt.to_dict(), separators=(",", ":")) + "\n")
        except OSError:
            pass


def run_book_rebalance(req: ActionRequest, **kwargs: Any) -> ActionReceipt:
    return BookRebalanceAction(**kwargs).run(req)


def handler_from_action(action: Optional[BookRebalanceAction] = None):
    act = action or BookRebalanceAction()

    def _h(req: ActionRequest) -> ActionReceipt:
        return act.run(req)

    return _h
