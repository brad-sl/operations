# Handoff: GAP-002 – SignalGenerator Abstraction

**Task ID**: GAP-002  
**Priority**: High  
**Created**: 2026-06-04  
**Status**: Ready for implementation

---

## Goal

Create a clean, extensible `SignalGenerator` in `phase6/core/signal_generator.py` that consolidates signal logic previously scattered or missing in Phase 6.

This replaces the inline/primitive logic from Phase 5.1 and provides a single place to evolve trading signals.

---

## Background

Phase 5 had `signal_generator.py` with a `Signal` dataclass and `SignalGenerator` class. Phase 6 currently lacks a centralized signal abstraction, making it harder to maintain and extend (especially with the new ATR module).

---

## Requirements

### Core Components

1. **Signal Dataclass**
   - `pair`, `signal` ("BUY", "SELL", "HOLD"), `confidence`, `reason`, `timestamp`

2. **SignalGenerator Class**
   - Accepts RSI, ATR, Sentiment as inputs
   - Supports multiple modes:
     - `weighted` (default)
     - `conservative` (AND-gate style)
     - `rsi_primary`

### Public API

```python
@dataclass
class Signal:
    pair: str
    signal: str
    confidence: float
    reason: str

class SignalGenerator:
    def generate_signal(self, pair: str, rsi: float, atr: float, sentiment: float, mode: str = "weighted") -> Signal:
        ...

    def generate_signals(self, data: dict, mode: str = "weighted") -> list[Signal]:
        ...
```

---

## Must Do

1. Create `phase6/core/signal_generator.py`
2. Implement `Signal` dataclass and `SignalGenerator`
3. Support at least the three modes above
4. Add clear documentation and examples
5. Make it importable from `phase6/core/`

---

## Must Not Do

- Do not tightly couple to the runner (keep it as a pure logic module)
- Do not hardcode thresholds — make them configurable

---

## Integration Points

- Consume `ATRCalculator` (GAP-001)
- Will be used by `phase6_runner.py` and future regime logic (GAP-003)
- Can replace or augment logic in `hybrid_rebalancer.py`

---

## Success Criteria

- `SignalGenerator` produces consistent, explainable signals
- Supports the three defined modes
- Ready for integration into the runner

---

## References

- `signal_generator.py` (Phase 5 original)
- `phase5_multi_pair.py` → `_determine_trade_signal`
- `indicators/dynamic_rsi_strategy.py`

---

**Next Step**: After this, move to GAP-003 (Scenario/Regime Detector).