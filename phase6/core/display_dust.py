"""UX helpers: hide sub-threshold positions from dashboard tables (not from exchange)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

DEFAULT_DUST_HIDE_USD = 5.0


def split_dust_positions(
    positions: List[Dict[str, Any]],
    hide_below_usd: float = DEFAULT_DUST_HIDE_USD,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Return (display_positions, hidden_dust).
    If every line is dust, show all so the table is not empty.
    """
    if not positions:
        return [], []
    dust = []
    core = []
    for p in positions:
        val = float(p.get("value_usd") or 0)
        if val < hide_below_usd:
            dust.append(p)
        else:
            core.append(p)
    if core:
        return core, dust
    return positions, []