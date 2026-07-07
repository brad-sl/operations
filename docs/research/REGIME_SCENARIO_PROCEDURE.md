# Regime scenario procedure (ANALYST-OPT)

**Purpose:** Avoid “bull-market hero” configs that fail when regime shifts — especially when stop-loss behavior was never stress-tested.

## Should you compare A/B/C/D?

**Yes — as a gate, not as a single winner pick.**

| Regime | Role | What it catches |
|--------|------|-----------------|
| **A — Bull** | Upside / churn | Over-trading, no SL discipline, concentration |
| **B — Bear** | Drawdown + SL | Your -80% class failures; bad trailing stops, late rotation |
| **C — Flat / chop** | Whipsaw | False rotations, fee bleed, allocator noise |
| **D — Recent (rolling)** | Drift vs live | Params that worked historically but not now |

**Do not** promote a knob set that only wins in **A**. Promotion requires **passing minimum bars in B and C** (and **D** when OHLCV overlaps live).

## Ranking rule (multi-regime)

1. Run **separate scenario packs** per regime window (same knob matrix).
2. Build a **regime scorecard** per scenario: rank or pass/fail per regime.
3. **Eligible for shadow** only if:
   - Beats baseline in **≥2 regimes** including **bear or flat**
   - Max drawdown in bear ≤ baseline + slack (default **+5 pp**)
   - **SL stress:** bear-regime max DD not worse than production since-go-live (when comparable)
4. **Live promotion** still requires Path C gates + user approval (MASTER).

## Suggested windows (BTC-anchored labels)

Calibrate quarterly from OHLCV; example on current file (`2025-04-20` → `2026-04-19`):

| Label | Example window | Notes |
|-------|----------------|-------|
| Bull | 2025-10-01 → 2025-12-31 | Label via BTC return > +15% over window |
| Bear | 2025-08-01 → 2025-09-30 | BTC return < -10% |
| Flat | 2026-01-01 → 2026-03-31 | \|BTC return\| < 8% |
| Recent | Last 90d of available OHLCV | Until ledger overlap exists |

Pack file: `phase6/research/scenarios/regime_quad_pack.json` (four `date_range` entries, same scenarios).

## Tie to stop-loss

- Bear + flat packs are **mandatory** before any “increase exposure” proposal.
- Intelligence brief should surface: “Winner in bull only — **reject for deploy**.”
- R3 proposals from optimization are **shadow-trial** class until regime scorecard passes.

## References

- `phase6/research/promotion_gates.py` — single-pack gates (R3)
- `docs/research/BACKTEST_LIVE_GAP_MATRIX.md` — Path B vs live gaps
- Epic ANALYST-OPT §4 metrics (drawdown tie-breaker)