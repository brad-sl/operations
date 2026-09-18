#!/usr/bin/env python3
"""Rebalance-path X universe: held ∪ plan-delta only — never full opportunity pool.

Part of docs/plans/2026-09-16-rebalance-book-vs-rsi-buy-x-split.md (Task 1).
"""
from __future__ import annotations

from typing import Iterable, Optional, Set


def _norm(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if s and "-" not in s:
        s = f"{s}-USD"
    return s


# Cash/stable path — not buy-decision social fuel
_STABLE_BASES = frozenset({"USD", "USDC", "USDT", "DAI", "EUR", "GBP"})


def is_stable_pair(pair: str) -> bool:
    p = _norm(pair)
    if not p or "-" not in p:
        return False
    a, b = p.split("-", 1)
    return a in _STABLE_BASES and b in _STABLE_BASES


def rebalance_x_candidates(
    *,
    held_pairs: Iterable[str],
    plan_pairs: Iterable[str] = (),
    pool: Optional[Iterable[str]] = None,
    exclude_stables: bool = True,
    exclude_ballast: Iterable[str] = ("PAXG-USD", "PAXG-USDC", "BTC-USD", "BTC-USDC"),
) -> Set[str]:
    """Return pairs that may receive paid X on a rebalance slot.

    Rules:
    - Union of held and plan-delta pairs only.
    - If ``pool`` is given, intersect for safety (never expand beyond pool).
    - Never expand to full opportunity pool just because it exists.
    - Stables / optional ballast excluded from social X by default.
    """
    held = {_norm(p) for p in (held_pairs or []) if _norm(p)}
    plan = {_norm(p) for p in (plan_pairs or []) if _norm(p)}
    out = held | plan
    if pool is not None:
        pool_n = {_norm(p) for p in pool if _norm(p)}
        out &= pool_n
    if exclude_stables:
        out = {p for p in out if not is_stable_pair(p)}
    ball = {_norm(p) for p in (exclude_ballast or []) if _norm(p)}
    if ball:
        out -= ball
    return out


def estimate_full_book_calls(n_pairs: int, *, batch_size: int = 6) -> int:
    """Rough /search/recent call count for full-book batching (lower bound)."""
    n = max(0, int(n_pairs))
    if n == 0:
        return 0
    bs = max(1, int(batch_size))
    return (n + bs - 1) // bs


def estimate_candidate_calls(n_candidates: int, *, single_when_le: int = 4) -> int:
    """Candidate-only path: small N often 1 call; empty → 0."""
    n = max(0, int(n_candidates))
    if n == 0:
        return 0
    if n <= single_when_le:
        return 1
    return estimate_full_book_calls(n)
