"""Load optional intel_strategic_brief.json before rebalance (ANALYST-002/004)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def load_strategic_brief() -> Optional[Dict[str, Any]]:
    try:
        from phase6.core.paths import INTEL_BRIEF

        if not INTEL_BRIEF.exists():
            return None
        with open(INTEL_BRIEF) as f:
            return json.load(f)
    except Exception as exc:
        logger.debug("[STRATEGIC-BRIEF] load skipped: %s", exc)
        return None


def log_brief_for_rebalance(brief: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Log soft context; returns brief dict (empty if missing)."""
    brief = brief if brief is not None else load_strategic_brief()
    if not brief:
        logger.info("[STRATEGIC-BRIEF] No intel_strategic_brief.json — proceeding without extra context")
        return {}
    logger.info(
        "[STRATEGIC-BRIEF] regime risk_on=%s high_sl_risk=%s coverage=%s proposals=%s",
        brief.get("risk_on_bias"),
        brief.get("high_sl_risk_pairs"),
        brief.get("coverage"),
        [p.get("id") for p in (brief.get("top_proposals") or [])],
    )
    return brief