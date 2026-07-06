#!/usr/bin/env python3
"""Isolation: strategic brief loader."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.strategic_brief_loader import load_strategic_brief, log_brief_for_rebalance


def main():
    sample = {
        "risk_on_bias": 0.55,
        "high_sl_risk_pairs": ["SOL-USD"],
        "coverage": {"full": 9, "total": 11},
        "top_proposals": [{"id": "ANALYST-X", "title": "test"}],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "intel_strategic_brief.json"
        p.write_text(json.dumps(sample))
        import phase6.core.strategic_brief_loader as mod
        import phase6.core.paths as paths

        paths.INTEL_BRIEF = p
        mod.INTEL_BRIEF = p  # type: ignore
        assert load_strategic_brief()["risk_on_bias"] == 0.55
        log_brief_for_rebalance()
    print("[STRATEGIC-BRIEF ISOLATION] PASSED")


if __name__ == "__main__":
    main()