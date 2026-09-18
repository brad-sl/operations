"""Port protocols for domain actions (implementations live in phase6/adapters)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from phase6.domain.types import ActionReceipt, BookLeg


@runtime_checkable
class IdempotencyPort(Protocol):
    def begin(self, tenant_id: str, key: str) -> Optional[ActionReceipt]:
        """Return prior receipt if key already completed; else None and mark in-flight."""
        ...

    def complete(self, tenant_id: str, key: str, receipt: ActionReceipt) -> None:
        ...


@runtime_checkable
class BookPort(Protocol):
    def current_held_pairs(self) -> List[str]:
        ...

    def load_raw_plan_legs(self) -> List[Dict[str, Any]]:
        """Optional pre-built plan legs from snapshot/coordinator (may be empty)."""
        ...


@runtime_checkable
class ClockPort(Protocol):
    def now_iso(self) -> str:
        ...
