"""Core action contracts: ActionRequest → ActionReceipt.

See docs/plans/2026-09-18-streamlined-action-architecture.md
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

TenantId = str  # "default" today

ActionName = Literal[
    "book_rebalance",
    "rsi_event_probe",
    "tryout_seat_buy",
    "x_refresh_candidates",
    "protective_reconcile",
    "status_plain",
    "funnel_why",
    "noop",
]

ReceiptStatus = Literal["ok", "noop", "blocked", "error", "dry_run"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ActionRequest:
    action: ActionName
    tenant_id: TenantId
    idempotency_key: str
    requested_at: datetime = field(default_factory=_utc_now)
    params: Dict[str, Any] = field(default_factory=dict)
    actor: str = "system"  # cron | brad | api:user | agent | cli

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["requested_at"] = self.requested_at.isoformat()
        return d


@dataclass(frozen=True)
class ActionReceipt:
    action: ActionName
    tenant_id: TenantId
    idempotency_key: str
    ok: bool
    status: ReceiptStatus
    reasons: Tuple[str, ...] = ()
    effects: Tuple[str, ...] = ()
    artifacts: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    correlation_id: str = ""
    replayed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "tenant_id": self.tenant_id,
            "idempotency_key": self.idempotency_key,
            "ok": self.ok,
            "status": self.status,
            "reasons": list(self.reasons),
            "effects": list(self.effects),
            "artifacts": dict(self.artifacts),
            "duration_ms": self.duration_ms,
            "correlation_id": self.correlation_id,
            "replayed": self.replayed,
        }


# --- Book plan legs (pure classification for BookRebalance) ---

LegKind = Literal[
    "trim",
    "weight_fix",
    "cash_path",
    "protective",
    "new_tryout_seat",
    "opportunity_entry",
    "unknown",
]


@dataclass(frozen=True)
class BookLeg:
    """One proposed book mutation before refuse filter."""

    pair: str
    side: str  # BUY / SELL / HOLD / REATTACH_SL / ...
    usd: float = 0.0
    kind: LegKind = "unknown"
    reason: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair,
            "side": self.side,
            "usd": self.usd,
            "kind": self.kind,
            "reason": self.reason,
            "meta": dict(self.meta),
        }


def classify_leg(raw: Dict[str, Any], *, held_pairs: Optional[set] = None) -> BookLeg:
    """Classify a TradePlan-like action dict into a BookLeg.

    Rules (conservative — when in doubt, new seat if BUY on non-held):
    - Explicit tags win: kind / leg_kind / seat_kind / quality_tryout / is_tryout
    - SELL / TRIM / reduce → trim
    - REATTACH / SL / protective → protective
    - stable cash path BUY (USDT/USDC) → cash_path
    - BUY on already-held → weight_fix
    - BUY on not-held with tryout markers or small seat size → new_tryout_seat
    - BUY on not-held opportunity / rotate_in → opportunity_entry
    """
    held = {str(p).upper() for p in (held_pairs or set())}
    pair = str(raw.get("pair") or raw.get("product_id") or "").strip().upper()
    if pair and "-" not in pair:
        pair = f"{pair}-USD"
    side = str(raw.get("action") or raw.get("side") or "").strip().upper()
    try:
        usd = float(raw.get("usd") or raw.get("notional") or raw.get("size_usd") or 0.0)
    except (TypeError, ValueError):
        usd = 0.0
    reason = str(raw.get("reason") or raw.get("note") or "")
    meta = {k: v for k, v in raw.items() if k not in ("pair", "product_id", "action", "side", "usd")}

    explicit = (
        str(raw.get("kind") or raw.get("leg_kind") or raw.get("seat_kind") or "")
        .strip()
        .lower()
    )
    if explicit in (
        "trim",
        "weight_fix",
        "cash_path",
        "protective",
        "new_tryout_seat",
        "opportunity_entry",
    ):
        return BookLeg(pair=pair, side=side or "?", usd=usd, kind=explicit, reason=reason, meta=meta)  # type: ignore[arg-type]

    # Boolean / tag markers for tryout
    tryout_markers = (
        bool(raw.get("quality_tryout"))
        or bool(raw.get("is_tryout"))
        or bool(raw.get("tryout_seat"))
        or "tryout" in reason.lower()
        or "quality_tryout" in reason.lower()
        or str(raw.get("sleeve") or "").lower() == "tryout"
    )
    opportunity_markers = (
        bool(raw.get("opportunity_entry"))
        or "opportunity" in reason.lower()
        or "rotate_in" in reason.lower()
        or str(raw.get("proposal_side") or "").upper() in ("ROTATE_IN", "BUY_NEW")
    )

    if side in ("SELL", "TRIM", "REDUCE", "ROTATE_OUT"):
        return BookLeg(pair=pair, side=side, usd=usd, kind="trim", reason=reason, meta=meta)
    if side in ("REATTACH_SL", "ATTACH_SL", "PROTECTIVE", "RECONCILE_SL") or "protective" in reason.lower():
        return BookLeg(pair=pair, side=side or "PROTECTIVE", usd=usd, kind="protective", reason=reason, meta=meta)

    base = pair.split("-")[0] if pair else ""
    if side == "BUY" and base in ("USDT", "USDC", "USD", "DAI"):
        return BookLeg(pair=pair, side=side, usd=usd, kind="cash_path", reason=reason, meta=meta)

    if side == "BUY":
        if tryout_markers:
            return BookLeg(pair=pair, side=side, usd=usd, kind="new_tryout_seat", reason=reason, meta=meta)
        if pair not in held:
            if opportunity_markers:
                return BookLeg(
                    pair=pair, side=side, usd=usd, kind="opportunity_entry", reason=reason, meta=meta
                )
            # Non-held BUY without explicit book tag → refuse as new seat (fail closed)
            return BookLeg(
                pair=pair,
                side=side,
                usd=usd,
                kind="new_tryout_seat",
                reason=reason or "non_held_buy_default_tryout",
                meta=meta,
            )
        return BookLeg(pair=pair, side=side, usd=usd, kind="weight_fix", reason=reason, meta=meta)

    return BookLeg(pair=pair, side=side or "?", usd=usd, kind="unknown", reason=reason, meta=meta)


def filter_book_legs(
    legs: List[BookLeg],
    *,
    allow_new_tryout_seats: bool = False,
    allow_opportunity_entries: bool = False,
) -> Tuple[List[BookLeg], List[BookLeg], Tuple[str, ...]]:
    """Split keep vs refused. Default: refuse new seats and opportunity entries."""
    keep: List[BookLeg] = []
    refused: List[BookLeg] = []
    reasons: List[str] = []
    for leg in legs:
        if leg.kind == "new_tryout_seat" and not allow_new_tryout_seats:
            refused.append(leg)
            reasons.append(f"book_rebalance_refuses_new_seats:{leg.pair}")
            continue
        if leg.kind == "opportunity_entry" and not allow_opportunity_entries:
            refused.append(leg)
            reasons.append(f"book_rebalance_refuses_opportunity_entry:{leg.pair}")
            continue
        keep.append(leg)
    return keep, refused, tuple(reasons)
