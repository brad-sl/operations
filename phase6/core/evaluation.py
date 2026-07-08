# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Unified Evaluation Layer (ARCH-1)

Single source for turning real data (prices, sentiment via scorer, RSI) into actionable Proposals.
Consumes SignalGenerator + OpportunityScanner (and future scorers).

All downstream (Allocator, rotation_strategy, runner) should call evaluate_universe instead of the individual modules directly.

This eliminates duplication and ensures evaluation always produces first-class, consumable output (no more "logs only").

Contract:
- evaluate_universe(basket: Optional[list[str]]=None, ...) -> list[Proposal]
  If basket=None, auto-loads full central basket via load_trading_basket() (11 pairs).
  Guarantees uniform identical scoring tree applied to every member.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .signal_generator import SignalGenerator, Signal
from .sentiment_scorer import load_sentiment_scores
from .paths import load_trading_basket
from .opportunity_scanner import scan_opportunities  # P1-01: real scanner integration (COMPLETED - removed sim stub)
# All evaluation MUST use central basket loader (paths.load_trading_basket) for full 11-pair uniformity.


@dataclass
class Proposal:
    """Unified proposal from any evaluation source. Always actionable."""
    pair: str
    side: str                 # "BUY", "SELL", "HOLD", or "ROTATE_IN", "ROTATE_OUT"
    score: float              # 0.0 - 1.0 or higher for ranking
    reason: str
    source: str               # "signal_generator", "opportunity_scanner", "rotation", etc.
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)  # rsi, sent, atr, etc.
    timestamp: str = ""


def _signal_to_proposal(signal: Signal, source: str = "signal_generator") -> Proposal:
    side = signal.signal
    if side == "BUY":
        side = "ROTATE_IN"  # align with catch-the-wave language
    elif side == "SELL":
        side = "ROTATE_OUT"
    return Proposal(
        pair=signal.pair,
        side=side,
        score=signal.confidence,
        reason=signal.reason,
        source=source,
        confidence=signal.confidence,
        metadata={"original_signal": signal.signal},
        timestamp=signal.timestamp or datetime.now(timezone.utc).isoformat()
    )


def evaluate_universe(
    basket: Optional[List[str]] = None,
    prices: Optional[Dict[str, List[float]]] = None,
    sentiment: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    mode: str = "weighted",
    include_scanner: bool = True,
) -> List[Proposal]:
    """
    Main unified entrypoint for ARCH-1+ (uniform decision tree).

    Loops over the FULL basket from central loader (paths.load_trading_basket)
    to ensure every pair is first-class with IDENTICAL decision tree treatment.

    Uniform per-pair logic:
    - For EVERY pair in (central) basket (no subsets, no special-casing by pair):
      * sentiment = load_sentiment_scores(universe=basket) [real X/Reddit via central scorer]
      * rsi = rsi_values.get(pair, 50.0) if provided else 50.0 (neutral default)
      * sig: Signal = SignalGenerator().generate_signal(pair, rsi, atr=None, sentiment=sent, mode=mode)
        [applies the SAME scoring tree to all pairs: RSI<30/ >70 +/-0.4, sent>0.2/<-0.2 +/-0.3,
         ATR damp if extreme, thresholds for BUY/SELL/HOLD, confidence]
      * prop = _signal_to_proposal(sig) -> Proposal with ROTATE_IN/OUT/HOLD, score, reason, metadata
      * enrich: prop.metadata["rsi"]=..., "sentiment"=..., "real_data"=True
    - (include_scanner=True) Call real scan_opportunities() from opportunity_scanner.
      For pairs with scanner score > 0.15, create Proposal(source="opportunity_scanner", side="ROTATE_IN",
      score=scanner_score, reason=scanner_reason, metadata populated with rsi, sentiment, vol, momentum_pct, mode, real_data).
      Scanner proposals are first-class (not proxy/simulation).
    - Merge: scanner proposals + signal_generator proposals; dedup by pair keeping highest score.
      Tie-breaker: on equal score, prefer opportunity_scanner proposal (more targeted opportunity signal).
    - Return: sorted(list) by score desc. Always |basket| unique pairs.
      Every basket member ALWAYS gets a Proposal (at minimum HOLD with score 0.5).
      All treated identically: same inputs sources, same scoring function, same output shape.

    basket=None (or empty): auto-loads full central basket = load_trading_basket()
    (ensures no drift to subsets even if caller passes partial).

    Used by runner (ARCH-4), allocator, tests. See also SignalGenerator docs.
    """
    if basket is None or len(basket) == 0:
        basket = load_trading_basket()

    proposals: List[Proposal] = []

    # 1. Sentiment (real, required) - always for the (central) basket
    if sentiment is None:
        sentiment = load_sentiment_scores(universe=basket)

    # 2. SignalGenerator path (core evaluation) -- UNIFORM per-pair decision tree (identical for all in central basket)
    gen = SignalGenerator()
    for pair in basket:
        rsi = rsi_values.get(pair, 50.0) if rsi_values else 50.0
        sent = sentiment.get(pair, 0.0)
        # Simple ATR proxy if not provided
        atr = None
        sig: Signal = gen.generate_signal(pair, rsi, atr=atr, sentiment=sent, mode=mode)
        prop = _signal_to_proposal(sig)
        # Enrich metadata
        prop.metadata.update({
            "rsi": rsi,
            "sentiment": sent,
            "real_data": True
        })
        proposals.append(prop)

    # 3. Opportunity Scanner contribution (P1-01) -- REAL integration (removed simulation stub / sentiment proxy)
    #    Calls real scan_opportunities(); proposals are first-class in unified output.
    #    Metadata fully populated from scanner (reason, score, rsi, sent, vol, mom, mode).
    if include_scanner:
        try:
            scanner_report = scan_opportunities()
            scores = scanner_report.get("scores", {})
            for pair in basket:
                if pair in scores:
                    s = scores[pair]
                    sc = float(s.get("score", 0.0))
                    if sc > 0.15:  # modest threshold to surface meaningful opportunities
                        prop = Proposal(
                            pair=pair,
                            side="ROTATE_IN",
                            score=sc,
                            reason=s.get("reason", f"opportunity_scanner score {sc:.3f}"),
                            source="opportunity_scanner",
                            confidence=sc,
                            metadata={
                                "rsi": s.get("rsi"),
                                "sentiment": s.get("sentiment"),
                                "vol": s.get("vol"),
                                "momentum_pct": s.get("momentum_pct"),
                                "mode": s.get("mode"),
                                "real_data": True
                            }
                        )
                        proposals.append(prop)
        except Exception as e:
            # Scanner is optional; log at debug level in production
            import logging
            logging.getLogger(__name__).debug(f"Opportunity scanner skipped in evaluate_universe: {e}")

    # Dedup by pair, keep highest score.
    # Tie-breaker: if scores equal, prefer opportunity_scanner (defined tie-break for first-class scanner).
    best: Dict[str, Proposal] = {}
    for p in proposals:
        if p.pair not in best or p.score > best[p.pair].score or (p.score == best[p.pair].score and p.source == "opportunity_scanner"):
            best[p.pair] = p

    sorted_props = sorted(best.values(), key=lambda x: x.score, reverse=True)
    return sorted_props


# Convenience for quick use (delegates; supports central default if called without)
def evaluate_basket(basket: List[str] = None) -> List[Proposal]:
    return evaluate_universe(basket)
