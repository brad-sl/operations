# Predictive Filter: Opportunity Scanner (IDEALOOP-002)

**Status:** Shadow-only implementation (proposals generated and logged from real data; gated by IDEALOOP-005 shadow AB). No live deployment or state mutation.  
**Date:** 2026-06-17 (document created)  
**Owner:** Scotty (per user directive)  
**Related:** 
- `docs/IDEALOOP-002_Opportunity_Scanner_Loop_Design.md` (original design)
- `docs/IDEALOOP_Scanner_Tracking_Enhancement.md` (tracking & validation)
- `phase6/core/opportunity_scanner.py` (implementation)
- `phase6/tests/test_isolation_opportunity_scanner_baseline.py` and related ARCH isolation tests
- `docs/MASTER_TASK_TRACKING.md` (this entry)
- `data/state/opportunity_proposals.jsonl` + `data/state/scanner_origins.jsonl` (logs)
- Allocator / RotationStrategy in `phase6/core/allocator.py` and `phase6/core/evaluation.py`

## Purpose
Shifts from purely **reactive** trading (exit on RSI reversal, sentiment drop, SL/TP hits, or idle cash thresholds) to **proactive/target-oriented** identification of buying/expansion opportunities.

The scanner scores the full opportunity pool (current basket + candidates) and proposes small test allocations or basket adds for high-scoring pairs. This creates explicit "targets" for capital deployment and rotation.

It enhances buying opportunities by surfacing pairs with positive composite scores before they become obvious reactive signals.

## Scoring Logic (Real Data Only)
Core function: `score_opportunity(pair, rsi, sentiment, vol, momentum_pct, is_current)` in `opportunity_scanner.py`.

Weighted composite (0-1, higher = stronger case for test buy/expansion):

- **40% RSI-momentum** (oversold bias): `max(0.0, (50.0 - rsi) / 25.0)` — lower RSI (e.g. 42) yields higher component.
- **20% Sentiment velocity**: `max(0.0, min(1.0, (sentiment + 0.3) * 2.0))` — uses current real cache values (X primary + Reddit overlay).
- **25% Vol-adjusted historical edge**: Derived from `compute_vol_and_momentum(prices, n=30)` on `price_history.json` (recent mom% scaled by vol penalty). Low-vol + positive recent momentum boosts score.
- **15% Diversification**: `0.30` if pair not in current basket, `0.05` if already held. Explicitly rewards expansion.

Ranking + proposal generation (top 1-2 above ~0.15-0.25 threshold):
- Current basket: small tilt (e.g. +$25-50 test).
- Non-basket: basket expansion (e.g. +$36 test alloc).
- All proposals shadow-gated; logged with full reason breakdown (RSI/Sent/Mom/Vol/Div components).

Data sources (conservative, no fabrication):
- `rsi_cache.json` (15m fresh)
- `price_history.json` (for vol/edge/momentum proxies)
- `sentiment_cache.json` + `x_sentiment_cache.json` (real non-zero values)
- Rebalance/live state for context/basket

## Current Behavior & Evidence
- Runs periodically or on demand (standalone `python -m phase6.core.opportunity_scanner` or via evaluation facade).
- Example output (recent lackluster market, ~$614 cash, 4-pair basket): Top proposals for ADA-USD (score ~0.357, RSI 42.23 + mom/vol + div), DOGE-USD, etc.
- Outputs feed `evaluate_universe()` (unified Proposal dataclass with source="opportunity_scanner", side="ROTATE_IN", score, metadata).
- Tracked for validation: Every proposal appended to `opportunity_proposals.jsonl` and human-readable MD in `logs/opportunity_scanner/IDEALOOP-002_proposals_*.md`. Origins logged in `scanner_origins.jsonl` with status progression.
- Isolation tests exist and have run (e.g. `arch0_isolation_scanner_evidence.json` shows real proposals surfaced; baseline tests confirm read-only, real-data behavior).
- Integrated into Allocator (ARCH-2+): High-score scanner proposals drive rotation redeploys in `RotationStrategy` (catch-the-wave).

See `IDEALOOP_Scanner_Tracking_Enhancement.md` for full queryable tracking schema and how to measure proposal → deploy → P&L attribution.

## Backtesting & Longer-Term Impact Measurement
Fully supported by existing infrastructure (per user preference for code isolation testing + real data):

- **Scoring is pure and replayable**: `score_opportunity` + `compute_vol_and_momentum` take simple inputs (rsi, sent, vol, mom, is_current). Can be called on historical price series without side effects.
- **Historical data**:
  - `price_history.json` for recent edge (per-pair lists of closes).
  - Dedicated 12-month OHLCV archives (used in `test_isolation_phase5_vs_phase6_12m_backtest.py`, rotation backtests, etc.).
- **Harness & isolation tests**:
  - Existing: `test_isolation_opportunity_scanner_baseline.py`, `test_isolation_evaluation.py`, `test_isolation_allocator.py`, `test_isolation_catch_wave_rotation.py` (validated +8.89% on 12mo proxy data with 100% exposure).
  - `BACKTEST_HARNESS_DESIGN.md` and `phase6/backtest/run_comparison.py`.
  - Prior corrected backtests compare strategies side-by-side on identical real data (MTM via weighted daily returns from closes).
- **Plan for predictive filter impact** (to be executed as follow-up task):
  1. Standalone isolation backtest script (e.g. `phase6/tests/test_isolation_predictive_filter_backtest.py`).
  2. Replay historical bars → at intervals compute proxies/RSI + run exact scanner scoring.
  3. Generate historical proposals.
  4. Feed into Allocator (rotation_catch_wave or rebalance tilt) vs reactive-only baseline (SignalGenerator only).
  5. Metrics: cumulative return, Sharpe, max DD, avg capital utilization/exposure, # predictive-driven rotations, hit-rate/P&L attribution on scanner-proposed pairs, churn.
  6. Variants: scanner weight tweaks, threshold sensitivity, predictive-only vs hybrid.
  7. Output: JSON evidence + summary in `data/state/`, update MASTER with numbers.
- This directly measures whether the "having a target" layer improves outcomes vs pure reactivity (as requested).

All prior backtests followed real-data, no-fab, isolation-wrapper discipline.

## Inverse: Sell-Side / Avoidance Filter to Enhance Buying Opportunities
Yes — the system already has partial inverses, and a symmetric predictive sell/avoidance filter would further enhance buying quality and capital efficiency.

**Existing inverses (reactive + some proactive):**
- **SignalGenerator** (`phase6/core/signal_generator.py`): Explicit symmetry.
  - BUY: RSI <30 + positive sentiment (weighted, conservative, or rsi_primary modes).
  - SELL: RSI >70 + negative sentiment (or strict AND in conservative mode).
  - Overbought penalty in weighted mode reduces score.
- **RotationStrategy / catch-the-wave** (in `allocator.py`): Proactive inverse behavior.
  - Exit weak pairs (RSI flip from oversold + sentiment neutral/negative; or low score/HOLD).
  - Hard stops on cliffs (-12% default).
  - Immediately redeploy freed capital + cash to **strongest current Proposals** (the predictive buy targets from scanner).
  - Cash as brief intermediary only. This frees capital and avoids drag, directly enhancing the pool/quality of buying opportunities.
  - Validated in isolation backtests (+8.89% gross on 12mo downtrend data vs ~-34% for buy-hold or conservative paths; 100% avg exposure, 454 rotations).
- Allocator pluggable strategies already consume unified Proposals (scanner contributes high-score ROTATE_IN; low-score can trigger ROTATE_OUT).

**Proposed enhancement — Predictive Sell/Avoidance Filter (symmetric to opportunity scanner):**
- Mirror the scoring for **exits/reductions**: High "risk/avoid" score for pairs that are overbought (high RSI), negative/declining sentiment, poor or negative vol-adjusted edge (recent mom negative + high vol), high correlation to current basket (anti-diversification), or regime mismatch.
- Output: Ranked "exit proposals" or "avoid targets" → feed Allocator for proactive rotation out (free capital for better scanner buys) or position sizing down.
- Benefits for buying opportunities:
  - Better timing of exits → more capital available for high-conviction predictive buys.
  - Avoid adding to (or holding) deteriorating pairs → improves overall hit rate and utilization of the buy-side predictive filter.
  - Could be a second scorer in evaluation.py or a dedicated `avoidance_scorer.py`.
  - Tunable weights, integrated into same Proposal stream (side="ROTATE_OUT" or metadata for risk).
- This would make the "predictive filter" bidirectional: proactive targets for entry + proactive signals for exit/avoidance.
- Low-churn controls (min_score_delta, cooldowns) would be critical (as learned from rotation experiments).
- Can be backtested in the same harness (compare "buy predictive only" vs "buy + sell predictive" vs reactive baseline).

**Recommendation:** Treat as follow-on to the buy-side predictive filter. Add as PREDICTIVE-002 or part of the same backtest task. Start with price/RSI/vol proxies (sentiment history limited).

## Open Opportunities & Tracking
- Formal backtest of predictive filter's incremental impact (buy-side first).
- Development of inverse avoidance/sell predictive scorer.
- Deeper wiring (post-shadow AB): Use scanner proposals to drive actual (small) test allocations and measure real attribution.
- Optimization: Tune weights on historical proposal success (use scanner_origins.jsonl + P&L data).
- Dashboard/observability: "Predictive Targets" card showing current top scores + reasons.
- All tracked in `MASTER_TASK_TRACKING.md` (see dedicated entry below) + handoffs/phase6/ for delegation.

**Files to reference for implementation:**
- Scanner: `phase6/core/opportunity_scanner.py:160` (score_opportunity) and `scan_opportunities`.
- Evaluation unification: `phase6/core/evaluation.py`.
- Decision: `phase6/core/allocator.py` (RotationStrategy.decide consumes Proposals).
- Tests: `phase6/tests/test_isolation_*` (scanner baseline, evaluation, allocator, catch_wave_rotation).
- Data: `data/state/price_history.json`, caches, `opportunity_proposals.jsonl`.

Real data only. Shadow by default. Code isolation testing for any changes. Update MASTER on progress.

---

## Entry Optimization Using Predictive Filters (or Complementary Methods)

**Diagnosis (from current data + logic):**  
The core predictive filter (`score_opportunity`) and `SignalGenerator._weighted_signal` are heavily biased toward **mean-reversion / oversold entries**:
- Scanner: 40% weight on `max(0, (50 - rsi)/25)` → RSI 55-70 yields ~0 RSI component.
- Signal: +0.4 only if RSI <30; +0.3 if sent >0.2.
- Allocator: strong ROTATE_IN requires score >0.55; fallback >0.3 marginal.
- Result: Even "strong RSI" (50-65) + strong sentiment (ADA 0.82, LINK 0.76, OP 0.43) produce scanner scores ~0.23 and signal ~0.3. Proposals rarely trigger. SOL (70.5 overbought) actively penalized.

Simulation with your exact values (mild +mom assumed):
- Current scanner: 0.15-0.24 across board (none above 0.25 proposal threshold).
- High-sent pairs get marginal credit only from sentiment component.

Current system excels at catching bounces in lackluster/oversold markets (validated in rotation backtests). For continuation or neutral-strong setups, entries are under-served.

**Proposed Methods (ranked by estimated probability of improving entry capture/quality in "strong RSI + strong Sent" regimes, grounded in project constraints: real-data, isolation-testable, low fab, leverage existing price_history/sentiment/RSI caches, alignment with +8.89% rotation validation).**

| Rank | Method | Description | Why Addresses the Gap | Est. Probability | Notes / Risks |
|------|--------|-------------|-----------------------|------------------|---------------|
| 1 | **Bullish/Continuation Predictive Scorer Extension** (to opportunity_scanner) | Add `score_bullish_entry(pair, rsi, sent, mom, vol, regime)` or dual scorer. Weights: 30% RSI in 40-68 band (peak ~54-60), 35% strong sent, 25% positive mom, 10% low-vol. Regime-aware. Feed as ROTATE_IN proposals when bullish regime. | Directly predictive for the exact scenario (mid RSI + high sent). Scanner already logs proposals; this makes it bidirectional (mean-rev + momentum). | **High (75-85%)** | Easiest extension of IDEALOOP-002. Can run in parallel with oversold scorer. Backtest via replay on price_history. |
| 2 | **Positive Momentum + Trend Filter** | Add component in scanner/signal/evaluate: bonus if mom_pct >0 (or price > short EMA from price_history). Require for any non-oversold entry. | Filters out "strong RSI but drifting down" cases. Complements sent without lowering bars. Uses existing compute_vol_and_momentum. | **High (70-80%)** | Simple, low risk. Reduces false positives in chop. |
| 3 | **Integrate Dynamic Regime Detection** | Wire `indicators/dynamic_rsi_strategy.py` (UPTREND buy thresh=20, DOWNTREND=40 etc.) + regime bonuses into SignalGenerator, evaluate_universe, and scanner scoring. | Existing code! In UPTREND, relax RSI to allow 45-65 + sent. Boosts "strong RSI" precisely when regime supports continuation. | **High (65-80%)** | Integration work (currently not wired to phase6 core). High leverage since already implemented. |
| 4 | **Sentiment Velocity (Delta) Predictive** | Track short-term sent delta (e.g. last 2-4 sentiment refreshes). Strong +vel bonus even if absolute sent moderate. Cache in unified or x cache. | Rising sentiment is often leading indicator for near-term price move. Predictive layer on top of static sent. | **Medium-High (60-75%)** | Requires light time-series on sentiment (add to sentiment_scorer or price_history style). High signal-to-noise if done. |
| 5 | **Tiered Test-Entry Policy for High-Sentiment** | In allocator/deploy/scanner: if sent > 0.5 and RSI 40-70 (not overbought), allow small test alloc ($25-50) even on marginal score 0.25-0.45. Mirror scanner's "test tilt" logic. | Lowers barrier for exactly the strong-sent cases without overhauling scoring. Aligns with "proactive targets" philosophy. | **Medium (55-70%)** | Increases small position churn; needs good SL. Easy to shadow/AB test. |
| 6 | **StochRSI Timing Overlay** | Use existing `indicators/stochrsi_strategy.py` (%K>%D crossover while RSI neutral + sent strong) as entry trigger/timing filter. | Adds precision within the RSI band. Good for avoiding entries mid-consolidation. | **Medium (50-65%)** | May lower frequency; requires price series. Good complement, not replacement. |
| 7 | **Historical Conditional Edge Scoring** | For current (RSI_bucket, sent_bucket, mom_sign), lookup historical forward 12-24h returns from price_history archives. Assign score = avg past edge or winrate. | True "predictive" using real past outcomes for similar setups. | **Medium-Low (40-60%) initially** | Requires backtest harness extension + sufficient history. Powerful long-term. |

**Immediate Validation Path (isolation discipline):**
1. Standalone test script: `phase6/tests/test_isolation_bullish_entry_scorer.py` (feed real/user data or historical, assert scores for high-sent pairs rise meaningfully vs baseline).
2. Replay on 12mo price_history + cached RSI/sent proxies.
3. Compare: # entries triggered, capital utilization, forward P&L attribution on "predictive bullish" vs pure oversold or reactive.
4. Shadow AB via IDEALOOP-005 style.

**Recommendation:** Start with #1 + #2 (extend scanner with bullish scorer + mom filter). This gives predictive filter symmetry for entries without waiting for regime wiring. Update `score_opportunity` to accept mode="oversold" | "bullish" | "hybrid". Then wire to evaluate_universe.

Example alternative (from quick isolation sim above):
```python
def bullish_entry_score(rsi, sent, mom, vol):
    rsi_cont = 0.0
    if 40 <= rsi <= 68:
        rsi_cont = 0.35 + 0.15 * (1 - abs(rsi - 54)/14)
    sent_cont = max(0.0, min(0.4, sent * 0.5))
    mom_cont = max(0.0, min(0.25, mom / 10.0)) if mom > 0 else 0.0
    ...
    return min(1.0, rsi_cont + sent_cont + mom_cont)
```
With your data: ADA/LINK/OP jump to 0.9-1.0; most others 0.6+; SOL suppressed.

**Inverse synergy:** A bullish entry predictive filter pairs perfectly with the proposed predictive avoidance/sell filter (PREDICTIVE-002 candidate) — exit deteriorating high-RSI + falling sent, redeploy to new high-scoring bullish entries.

All real-data only. Add to backtest plan in this doc. Track as extension of PREDICTIVE-001.

---

*This document serves as the primary reference for the predictive filter concept and related opportunities. Linked from MASTER_TASK_TRACKING.md.*