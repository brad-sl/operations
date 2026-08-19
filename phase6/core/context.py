"""
AccountContext for SCALING-1000 multi-tenant support (T0-02).

Provides dataclass + injection primitives for per-account isolation.
Dual-path: when MULTI_TENANT_ENABLED=false (default), legacy single-account
(Brad via env api_key) path remains unchanged.

Usage (shadow / future):
    from phase6.core.context import AccountContext, get_current_context, with_account

    ctx = AccountContext(account_id="brad-001", tier="elite", config={...})
    with with_account(ctx):
        # code runs with context active
        ...

In runner/coordinators: accept optional context= or use get_current_context()
when flag enabled.

Do NOT enable flag until T1+ and full isolation proven.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, TypeVar, cast

logger = __import__("logging").getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)  # immutable for safety in contexts
class AccountContext:
    """
    Canonical per-account execution context.

    - account_id: stable uuid or slug for the trader (from registry or trader_accounts.json)
    - tier: starter | pro | elite (affects caps, pair limits, etc.)
    - auth_mode: "cdp_key" | "oauth" | "shadow"
    - portfolio_uuid: Coinbase portfolio id (post 2025 changes)
    - oauth_client: future OAuth-wrapped client (None for legacy)
    - config: per-account override snapshot (merged from trader_accounts + global)
    - flags: runtime flags (e.g. {"multi_tenant": True})
    - billing_status: active | paused | dunning | etc (from GHL later)
    """

    account_id: str
    tier: str = "starter"
    auth_mode: str = "cdp_key"  # or "oauth"
    portfolio_uuid: Optional[str] = None
    oauth_client: Optional[Any] = None
    config: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    billing_status: str = "active"

    # Convenience for legacy single-account path (Brad)
    legacy_api_key: Optional[str] = None
    legacy_api_secret: Optional[str] = None

    def is_multi_tenant(self) -> bool:
        return bool(self.flags.get("multi_tenant_enabled", False))

    def get_effective_config(self) -> Dict[str, Any]:
        """Return merged view (caller can overlay)."""
        return dict(self.config)

    def __repr__(self) -> str:
        return f"AccountContext(account_id={self.account_id!r}, tier={self.tier}, auth={self.auth_mode})"


# Context variable for implicit injection (safe across threads/async with contextvars)
_current_account: contextvars.ContextVar[Optional[AccountContext]] = contextvars.ContextVar(
    "current_account_context", default=None
)


def get_current_context() -> Optional[AccountContext]:
    """Return the active AccountContext or None (legacy mode)."""
    return _current_account.get()


def set_current_context(ctx: Optional[AccountContext]) -> contextvars.Token:
    """Low-level set (prefer with_account context manager). Returns token for reset."""
    return _current_account.set(ctx)


def reset_current_context(token: contextvars.Token) -> None:
    """Reset using token from set."""
    _current_account.reset(token)


@contextmanager
def with_account(ctx: AccountContext):
    """
    Context manager to run block under specific account.

    Example:
        with with_account(test_ctx):
            runner = Phase6Runner(...)
            # inside, get_current_context() returns test_ctx
    """
    if not isinstance(ctx, AccountContext):
        raise TypeError("with_account expects AccountContext")
    token = _current_account.set(ctx)
    try:
        logger.debug(f"[CONTEXT] entered account {ctx.account_id}")
        yield ctx
    finally:
        _current_account.reset(token)
        logger.debug(f"[CONTEXT] exited account {ctx.account_id}")


def with_account_decorator(ctx: AccountContext) -> Callable[[F], F]:
    """
    Decorator factory: @with_account_decorator(ctx) def foo(): ...
    """

    def decorator(func: F) -> F:
        def wrapper(*args, **kwargs):
            with with_account(ctx):
                return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def create_legacy_context(account_id: str = "brad-primary", **overrides) -> AccountContext:
    """
    Create a context for the legacy single-account path.
    Pulls keys from env when present (does not store secrets in context for safety,
    but keeps refs for dual-path compatibility).
    """
    api_key = overrides.pop("api_key", os.getenv("COINBASE_API_KEY"))
    api_secret = overrides.pop("api_secret", os.getenv("COINBASE_API_SECRET"))
    cfg = overrides.pop("config", {})
    flags = overrides.pop("flags", {"multi_tenant_enabled": False})
    ctx = AccountContext(
        account_id=account_id,
        tier=overrides.pop("tier", "elite"),
        auth_mode=overrides.pop("auth_mode", "cdp_key"),
        config=cfg,
        flags=flags,
        legacy_api_key=api_key,
        legacy_api_secret=api_secret,
        **overrides,
    )
    return ctx


def is_multi_tenant_enabled(default: bool = False) -> bool:
    """
    Central feature flag check.
    Priority: explicit in current context > env var MULTI_TENANT_ENABLED > config > default=False
    """
    ctx = get_current_context()
    if ctx and "multi_tenant_enabled" in ctx.flags:
        return bool(ctx.flags["multi_tenant_enabled"])
    env = os.getenv("MULTI_TENANT_ENABLED")
    if env is not None:
        return env.lower() in ("1", "true", "yes", "on")
    # Could later pull from loaded config global_settings
    return default


# Convenience factory for tests (mock 2 accounts)
def create_test_context(account_id: str, tier: str = "starter", **kw) -> AccountContext:
    flags = kw.pop("flags", {})
    flags.setdefault("multi_tenant_enabled", True)
    return AccountContext(
        account_id=account_id,
        tier=tier,
        auth_mode=kw.pop("auth_mode", "shadow"),
        config=kw.pop("config", {"test": True}),
        flags=flags,
        **kw,
    )


if __name__ == "__main__":
    # Self-test
    print("AccountContext module loaded")
    legacy = create_legacy_context()
    print("Legacy:", legacy)
    test1 = create_test_context("acct-001")
    test2 = create_test_context("acct-002", tier="pro")
    print("Test1:", test1)
    with with_account(test1):
        print("Inside1:", get_current_context())
    print("Outside:", get_current_context())
    assert get_current_context() is None
    print("Context primitives OK")
