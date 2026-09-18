"""ActionDispatcher — route ActionRequest → handler → ActionReceipt + idempotency."""
from __future__ import annotations

import time
import uuid
from typing import Callable, Dict, Optional

from phase6.domain.types import ActionName, ActionReceipt, ActionRequest

Handler = Callable[[ActionRequest], ActionReceipt]


class InMemoryIdempotency:
    """Process-local idempotency (tests + single-process dry_run)."""

    def __init__(self) -> None:
        self._done: Dict[str, ActionReceipt] = {}

    def _k(self, tenant_id: str, key: str) -> str:
        return f"{tenant_id}::{key}"

    def begin(self, tenant_id: str, key: str) -> Optional[ActionReceipt]:
        return self._done.get(self._k(tenant_id, key))

    def complete(self, tenant_id: str, key: str, receipt: ActionReceipt) -> None:
        self._done[self._k(tenant_id, key)] = receipt


class ActionDispatcher:
    def __init__(
        self,
        handlers: Optional[Dict[ActionName, Handler]] = None,
        idempotency: Optional[InMemoryIdempotency] = None,
    ) -> None:
        self._handlers: Dict[str, Handler] = {str(k): v for k, v in (handlers or {}).items()}
        self._idem = idempotency or InMemoryIdempotency()

    def register(self, action: ActionName, handler: Handler) -> None:
        self._handlers[str(action)] = handler

    def dispatch(self, req: ActionRequest) -> ActionReceipt:
        prior = self._idem.begin(req.tenant_id, req.idempotency_key)
        if prior is not None:
            # Return frozen copy marked replayed
            return ActionReceipt(
                action=prior.action,
                tenant_id=prior.tenant_id,
                idempotency_key=prior.idempotency_key,
                ok=prior.ok,
                status=prior.status,
                reasons=prior.reasons,
                effects=prior.effects,
                artifacts=dict(prior.artifacts),
                duration_ms=prior.duration_ms,
                correlation_id=prior.correlation_id,
                replayed=True,
            )

        handler = self._handlers.get(str(req.action))
        t0 = time.perf_counter()
        corr = str(uuid.uuid4())
        if handler is None:
            receipt = ActionReceipt(
                action=req.action,
                tenant_id=req.tenant_id,
                idempotency_key=req.idempotency_key,
                ok=False,
                status="error",
                reasons=(f"no_handler:{req.action}",),
                duration_ms=int((time.perf_counter() - t0) * 1000),
                correlation_id=corr,
            )
            self._idem.complete(req.tenant_id, req.idempotency_key, receipt)
            return receipt

        try:
            receipt = handler(req)
        except Exception as exc:  # noqa: BLE001 — receipt must always return
            receipt = ActionReceipt(
                action=req.action,
                tenant_id=req.tenant_id,
                idempotency_key=req.idempotency_key,
                ok=False,
                status="error",
                reasons=(f"handler_exception:{type(exc).__name__}:{exc}",),
                duration_ms=int((time.perf_counter() - t0) * 1000),
                correlation_id=corr,
            )
            self._idem.complete(req.tenant_id, req.idempotency_key, receipt)
            return receipt

        # Ensure duration/correlation filled if handler omitted
        if not receipt.correlation_id or receipt.duration_ms == 0:
            receipt = ActionReceipt(
                action=receipt.action,
                tenant_id=receipt.tenant_id,
                idempotency_key=receipt.idempotency_key,
                ok=receipt.ok,
                status=receipt.status,
                reasons=receipt.reasons,
                effects=receipt.effects,
                artifacts=dict(receipt.artifacts),
                duration_ms=receipt.duration_ms
                or int((time.perf_counter() - t0) * 1000),
                correlation_id=receipt.correlation_id or corr,
                replayed=False,
            )
        self._idem.complete(req.tenant_id, req.idempotency_key, receipt)
        return receipt


def make_noop_handler() -> Handler:
    def _noop(req: ActionRequest) -> ActionReceipt:
        return ActionReceipt(
            action=req.action,
            tenant_id=req.tenant_id,
            idempotency_key=req.idempotency_key,
            ok=True,
            status="noop",
            reasons=("noop",),
            effects=(),
        )

    return _noop
