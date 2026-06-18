# Handoff: GAP-003 – Scenario / Regime Detector

**Task ID**: GAP-003  
**Priority**: Medium-High  
**Created**: 2026-06-04  
**Status**: Ready for implementation

---

## Goal

Create a lightweight `RegimeDetector` in `phase6/core/risk/regime_detector.py` that identifies market regimes and provides adjustment signals for:

- RSI thresholds (tighter in high volatility)
- Position sizing
- Rebalancing sensitivity

---

## Background

Phase 5 had informal regime awareness in several scripts. Phase 6 currently has none. A simple regime detector will make the system more adaptive without heavy ML.

---

## Requirements

### Detected Regimes (MVP)

- `HIGH_VOL` / `LOW_VOL`
- `TRENDING` / `RANGING`
- `HIGH_CORR` (correlation clusters)

### Public API

```python
class RegimeDetector:
    def detect(self, prices: list, atr: float, correlation: float = None) -> dict:
        """
        Returns: {
            "regime": "HIGH_VOL",
            "confidence": 0.8,
            "adjustments": {"rsi_buy": 28, "rsi_sell": 72}
        }
        """
```

---

## Must Do

1. Create `phase6/core/risk/regime_detector.py`
2. Implement simple rule-based detection using ATR + optional correlation
3. Return actionable adjustments
4. Keep it lightweight (no heavy dependencies)

---

## Must Not Do

- Do not over-engineer with complex state machines in v1
- Do not require external data beyond price/ATR

---

## Success Criteria

- Detector returns consistent regime labels
- Provides useful threshold adjustments
- Integrates cleanly with `SignalGenerator` and `ATRCalculator`

---

## References

- `phase5_full_spec.py` (informal regime logic)
- `rolling_correlation.py` (for HIGH_CORR detection)

---

**Next Step**: After this, the core RSI-related gaps (001–003) will be complete.