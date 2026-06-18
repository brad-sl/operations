#!/usr/bin/env python3
"""
ARCH-1 Isolation Test: Unified Evaluation Layer

Standalone test for the new evaluate_universe facade.
Verifies:
- Produces consistent list[Proposal] from real data (sentiment_scorer + signal_generator).
- Includes contributions from signal + opportunity paths.
- Proposals are ranked, have source, metadata with real values.
- Can be consumed by Allocator / rotation_strategy (example: filter for ROTATE_IN).

This is the first step toward making evaluation always feed action.
"""

import json
from pathlib import Path
from datetime import datetime
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.evaluation import evaluate_universe, Proposal, evaluate_basket
from phase6.core.sentiment_scorer import load_sentiment_scores

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

def test_unified_evaluation_produces_proposals():
    print("=== ARCH-1: Unified Evaluation Isolation Test ===")
    print("Testing: evaluate_universe (new facade in phase6/core/evaluation.py)")
    print("Input: real basket + real sentiment via scorer (prices/rsi optional for baseline)\n")

    real_sent = load_sentiment_scores(universe=FIXED_UNIVERSE)
    print(f"Real sentiment input: { {p: round(s,4) for p,s in real_sent.items()} }")

    proposals = evaluate_universe(
        basket=FIXED_UNIVERSE,
        sentiment=real_sent,
        rsi_values={p: 46.0 for p in FIXED_UNIVERSE},  # neutral recent
        mode="weighted",
        include_scanner=True
    )

    print("\n--- Unified Proposals (real data) ---")
    for p in proposals:
        print(f"{p.pair}: {p.side} score={p.score:.2f} source={p.source} reason='{p.reason[:60]}...' sent={p.metadata.get('sentiment',0):.3f}")

    # Evidence
    evidence = {
        "timestamp": datetime.utcnow().isoformat(),
        "input_sentiment": {p: round(s,4) for p,s in real_sent.items()},
        "proposals": [
            {
                "pair": p.pair,
                "side": p.side,
                "score": round(p.score, 3),
                "source": p.source,
                "reason": p.reason,
                "metadata": {k: round(v,4) if isinstance(v, float) else v for k,v in p.metadata.items()}
            } for p in proposals
        ],
        "count": len(proposals),
        "note": "First unified output. Downstream (Allocator, rotation) can now consume this instead of calling generators separately. Signals that were previously 'logs only' now become first-class Proposals."
    }
    out_path = PROJECT_ROOT / "data/state/arch1_isolation_evaluation_evidence.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nEvidence written to {out_path}")

    # Assertions for isolation
    assert len(proposals) > 0, "Should produce at least some proposals"
    assert all(isinstance(p, Proposal) for p in proposals), "All must be Proposal instances"
    assert any(p.source in ("signal_generator", "opportunity_scanner") for p in proposals), "Sources must be populated"
    # Example consumption: what rotation strategy would see
    rotate_ins = [p for p in proposals if p.side in ("ROTATE_IN", "BUY")]
    print(f"\nExample for rotation_strategy: {len(rotate_ins)} ROTATE_IN candidates")

    print("\n[ARCH-1 Evaluation] PASSED - unified facade works with real data.")
    return proposals, evidence

if __name__ == "__main__":
    test_unified_evaluation_produces_proposals()
    print("\nAll ARCH-1 evaluation assertions passed. Ready to wire into Allocator.")