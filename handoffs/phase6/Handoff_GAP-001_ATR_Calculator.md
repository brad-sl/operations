# Handoff: GAP-001 – Implement ATR / Volatility Calculator

**Task ID**: GAP-001  
**Priority**: High  
**Created**: 2026-06-04  
**Status**: Ready for implementation

---

## Goal

Create a clean, reusable `ATRCalculator` module in `phase6/core/risk/atr_calculator.py` that provides Average True Range (ATR) calculation. This will serve as a foundational building block for:

- Dynamic position sizing
- Volatility-adjusted risk management
- Future regime detection (GAP-003)
- Enhanced signal generation (GAP-002)

---

## Background

Phase 5.1 (`phase5_full_spec.py`) contained a working `_calculate_atr` method. This capability was not carried forward into Phase 6. ATR is a standard volatility measure that significantly improves risk management over static position sizing.

---

## Requirements

### Public API

```python
class ATRCalculator:
    def calculate_atr(self, highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Return the latest ATR value."""

    def calculate_atr_series(self, highs: list, lows: list, closes: list, period: int = 14) -> list:
        """Return full ATR series (for backtesting / visualization)."""
```

### Behavior
- Use the standard Wilder ATR formula (smoothed).
- Handle insufficient data gracefully (return `None` or neutral value).
- Support both single-value and series output.

---

## Must Do

1. Create `phase6/core/risk/atr_calculator.py`
2. Implement standard ATR logic (True Range → Smoothed ATR)
3. Add unit tests or inline validation
4. Expose the module via `phase6/core/risk/__init__.py`
5. Document usage in the file header

---

## Must Not Do

- Do not over-engineer with unnecessary pandas dependencies if pure Python/NumPy works.
- Do not hardcode period=14 everywhere — make it configurable.

---

## Integration Points (Future)

- `allocation_engine.py` — volatility-adjusted weights
- `signal_generator.py` (GAP-002) — ATR-based filters
- `hybrid_rebalancer.py` — volatility spike detection

---

## Success Criteria

- `calculate_atr()` returns sensible values on real market data
- Module is importable and documented
- Ready to be consumed by allocation and signal layers

---

## References

- `phase5_full_spec.py` → `_calculate_atr`
- `src/indicators/rsi.py` (style reference for clean indicator modules)
- Standard ATR definition (Wilder)

---

**Next Step**: After implementation, create handoff for GAP-002 (SignalGenerator).