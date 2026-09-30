"""NEEDLE-08: ignition scores → tryout ranking (basket-only).

Does NOT mutate opportunity_pool, universe, or live membership.
PC-08: dual_agree ≠ promote. Ranking artifact only.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

RANK_PATH = STATE_DIR / "needle08_ignition_rank.json"


def rank_from_scout_board(
    board: Optional[Dict[str, Any]] = None,
    *,
    universe: Optional[Sequence[str]] = None,
    write: bool = True,
) -> Dict[str, Any]:
    if board is None:
        p = PROJECT_ROOT / "data" / "state" / "ignition_scout_board.json"
        if p.exists():
            try:
                board = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                board = {}
        else:
            board = {}
    scored = list((board or {}).get("all_scored") or [])
    top = list((board or {}).get("top") or [])
    uni = {str(x).upper() for x in (universe or [])}
    ranked: List[Dict[str, Any]] = []
    for row in scored:
        pair = str((row or {}).get("pair") or "").upper()
        if uni and pair not in uni:
            continue
        ranked.append(
            {
                "pair": pair,
                "ignition_score": (row or {}).get("score"),
                "phase": (row or {}).get("phase"),
                "rsi": (row or {}).get("rsi"),
                "structure_ok": (row or {}).get("structure_ok"),
            }
        )
    ranked.sort(key=lambda r: float(r.get("ignition_score") or 0.0), reverse=True)
    out = {
        "schema": "needle08_ignition_rank_v1",
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "ranking_only",
        "mutates_membership": False,
        "n": len(ranked),
        "ranked": ranked[:20],
        "scout_top_snip": [
            {"pair": t.get("pair"), "score": t.get("score")} for t in top[:5] if isinstance(t, dict)
        ],
        "note": "Basket ranking only. dual_agree ≠ promote. No live membership swap.",
    }
    if write:
        RANK_PATH.parent.mkdir(parents=True, exist_ok=True)
        RANK_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        logger.info("[NEEDLE-08] wrote ignition rank n=%s", out["n"])
    return out
