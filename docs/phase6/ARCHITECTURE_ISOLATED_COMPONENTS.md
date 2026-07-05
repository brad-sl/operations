# Phase 6: Clean Architecture — Isolated Callable Components

**Date**: 2026-06-15  
**Status**: Proposed (for review + adoption)  
**Goal**: Eliminate divergence between runner, hybrid rebalancer, signal generator, opportunity scanner, and allocation logic. Make evaluation, decision-making, execution, and rebalancing into small, testable, callable units that the orchestrator (or tests/backtests) can invoke cleanly.

## Current Problems (Grounded)
- **Divergent decision logic**: 
  - `phase6/core/phase6_runner.py` computes signals every cycle via `SignalGenerator` but **only logs them** (never turns BUY/SELL into trades).
  - All live capital deployment and trades flow exclusively through rebalance paths: `_perform_daily_rebalance()` + `deploy_capital()` (scripts/) + `rebalance_plan()` (allocation_engine).
  - `HybridRebalancer` (rebalancing/hybrid_rebalancer.py) is a narrow *trigger* (sentiment deltas + thresholds + rule-based AI filter). Its `generate_rebalance_plan` was retired in P4-03 (thin compat shim only). Runner/ARCH-4 uses Allocator + RebalanceStrategy exclusively for plans. HybridRebalancer remains narrow *trigger* only.
  - Fresh Start has its own (slightly different) inverse-vol + sentiment weight calc.
  - `opportunity_scanner.py` produces ranked proposals (shadow-only, to jsonl) with its own scoring (RSI + sentiment velocity + momentum/vol + diversification). Not wired to anything that trades.
- **Monolithic runner**: 1300+ lines handling scheduling, data refresh, SL coordination (CR-03), execution, dashboard, state, *and* the only active trade logic. Hard to test, optimize, or A/B.
- **Consequence**: No reliable entry points across pairs for weeks → idle capital, tiny basket, rebalancing has nothing meaningful to act on, daily fluctuations ignored. Inconsistent logic makes optimization, backtesting, and debugging painful.
- **Data duplication risks**: Hybrid rebalancer duplicates sentiment cache parsing (own default path, neutral fallbacks, schema handling) instead of using `sentiment_scorer`. Reviews (Fable 5 batches) repeatedly flagged this + in-memory state + normalization issues.
- **Rebalancing without positions**: Current design makes rebalancing the *primary* (almost only) way to deploy capital. With no entries, the system starves itself.

This matches the user's observation exactly.

## Desired Properties
- **Isolated & callable**: Evaluation, Allocation/Decision, Execution, Rebalancing-as-strategy, and SL coordination are small modules with clear contracts (dataclasses for inputs/outputs). Importable from tests, backtests, paper harness, manual scripts, and the thin orchestrator.
- **Single source of truth for decisions**: One place (the Allocator) decides "given current state + proposals + capital + risk params, here is the executable plan." No shadow-only eval layers.
- **Evaluation always feeds action**: Signals + opportunity scoring + any future strategies produce `Proposal` objects that the Allocator consumes.
- **Rebalancing is a strategy, not a peer system**: "Daily rebalance", "fresh start", "signal-tilt deployment", "recovery" become modes or strategies inside the Allocator. Hybrid threshold logic can become one trigger strategy.
- **Thin orchestrator**: `Phase6Runner` (or a new `Orchestrator`) becomes a scheduler + coordinator that *invokes* the components on a cycle (or on events). ~200-300 lines max for the loop.
- **Measurable & testable**: Every component has pure(ish) functions or small classes. First-class isolation tests (user's preferred pattern: standalone wrappers that exercise the exact logic with real data and assert outputs). Easy to measure proposal→plan→execution rate, capital utilization, signal quality, etc.
- **Real data only**: All paths use canonical caches (via `sentiment_scorer`, rsi_cache, price_history, trade_ledger, LivePortfolioManager).
- **Dynamic basket support**: Config-driven opportunity pool + current holdings. Components accept basket as input.
- **Safety orthogonal**: SL suspend/reattach (StopLossCoordinator), withdrawal reserve, cooldowns, circuit breakers wrap execution windows but do not duplicate decision logic.

## Proposed Layered Architecture

```
Data Layer (canonical, shared)
├── sentiment_scorer.py (load_sentiment_scores, get_aged_..., get_sentiment_adjusted_weights)
├── price_history / rsi_cache (decoupled 15m pipeline)
├── LivePortfolioManager + exchange_client (verified holdings + enriched)
├── TradeLedger
└── Config (trading_config_phase6.json + dynamic basket)

Evaluation Layer (produces Proposals — always actionable)
├── SignalGenerator (existing, enhanced) → Proposal
├── OpportunityScanner (existing logic, refactored) → list[Proposal]
├── (future) RegimeDetector, ATR, correlation, etc. as pluggable scorers
└── Unified: evaluate(basket, prices, sentiment, rsi, current_positions) -> list[Proposal]

Allocator / Decision Layer (the "trading logic" single source)
├── allocator.py (ARCH-2: RotationStrategy (catch-the-wave) + RebalanceStrategy + Allocator facade)
│   - Consumes list[Proposal] from evaluate_universe (ARCH-1)
│   - Produces TradePlan (actions + new_allocs + exposure + rotation count)
│   - Reuses allocation_engine primitives + deploy_capital (as building block)
│   - Churn controls: min_move_usd, min_score_delta, etc.
│   - RotationStrategy implements validated catch-the-wave (+8.89% historical in isolation)
├── deploy_capital.py (building block, used inside strategies with relaxed gates)
├── allocation_engine.py (rebalance_plan, compute_inverse_vol, plan_static — primitives)
├── RebalanceStrategy (lower churn: inv-vol base + proposal tilt)
└── RotationStrategy (primary: exit weak → immediate opportunistic redeploy to strong Proposals)
├── HybridTrigger (extracted/adapted from HybridRebalancer — one of several triggers)
├── Strategies:
│   ├── rebalance_strategy(current, proposals, capital, config) -> Plan
│   ├── signal_tilt_strategy(...)
│   ├── fresh_start_strategy(...)
│   └── recovery_strategy(...)
└── Unified allocator( current_positions, proposals, available_capital, risk_params, mode="daily_rebalance" ) -> TradePlan

Execution Layer (thin, safe)
├── OrderExecutor (execute_buy/sell, execute_plan)
├── StopLossCoordinator (wraps windows: suspend → trade → reattach)
├── ReserveEnforcer (pre/post checks)
└── TradeLedger + error handling

Orchestrator (thin scheduler)
├── Phase6Runner (or new slim version)
│   - Cycle: fetch/refresh data → evaluate() → allocate() → if plan: execute(wrapped)
│   - Scheduling: time-based rebalance trigger + hybrid trigger + manual force
│   - State, dashboard cache, telegram digests, recovery
└── Invoked by: main loop (5-30min), cron, paper harness, backtest engine, CLI force scripts

**Rebalancing (now a strategy inside Allocator, not a separate system)**
- Computes target weights (inverse vol + sentiment) + deltas to current
- Can be triggered by time, hybrid thresholds, or opportunity strength
- Produces the same TradePlan shape as signal-driven deployment

**Catch-the-Wave Rotation Strategy (new, to be implemented as pluggable strategy)**
- Core idea (validated in 2026-06-15 experiments): Use cash only as temporary parking. On exit signal (e.g. RSI no longer oversold + sentiment neutral/negative) or stop-loss, immediately redeploy freed capital opportunistically to the strongest current signals/opportunities in the basket ("catch the wave").
- Keeps exposure near 100% in relative-strength environments even during overall down markets.
- Proven to deliver positive ROI (+8.89% net with 0.1% fees) on the full 12-month 2025-04-20 to 2026-04-20 downtrend period where buy-and-hold, pure inv-vol, and prior conservative deploy_capital paths produced ~-34%.
- High turnover (454 rotations in daily version) is the main cost; fees were ~$4.4k on $10k notional. Stop-loss (hard cliffs) is orthogonal and feeds the same redeploy path.
- Fits as one of the Strategies in the Allocator layer: `rotation_strategy(current_positions, proposals, available_capital, config) -> TradePlan`.
- Reuses building blocks: deploy_capital (for opportunistic redeploy of freed capital), rebalance_plan (for deltas with min_move), compute_inverse_vol_allocations (for stable base weights), plus signal strength scoring from Evaluation.
- Churn reduction (min_move, lower freq, continuous score-tilt vs binary, conviction gates, cooldowns) and hybrid with inv-vol base are explicit tunable parameters of this strategy. Architecture allows A/B testing rotation variants independently of evaluation or execution.
- Real data: Must use sentiment_scorer + price/rsi history. Initial validation used proxy for full historical alignment (real daily sentiment series not available for the test window); live/current uses canonical real scores.
- Stop-loss integration: Hard stops (or CR-03 coordinator) free capital that immediately flows into the rotation redeploy logic.
- This replaces/augments the current conservative weight-tilt + reserve-gated deploy_capital as the primary "trading logic" for signal-driven capital movement.
```

**Core Contracts (dataclasses — keep simple)**
- `Proposal`: pair, side ("BUY"/"SELL"), score/confidence, reason, suggested_usd_hint?, metadata (rsi, sent, etc.)
- `TradePlan`: list of moves {pair, action, usd_amount, reason, sl_params?}, total_capital_deployed, mode, timestamp
- `RebalanceDecision` (keep/adapt from hybrid): should_rebalance, reason, triggered_by, confidence
- Allocator always returns a (possibly empty) `TradePlan` + diagnostics.

**How Signals Finally Produce Trades**
- Every cycle: Evaluation layer (SignalGenerator + OpportunityScanner + any others) runs on the full opportunity pool + current basket.
- Proposals flow directly into Allocator.
- Allocator (in "live" or "opportunity" mode) can decide to deploy small test sizes on high-score new pairs or tilt existing, subject to the same gates (RSI, sentiment min for new, reserve, cooldown, rebalance_cap, etc.).
- Result: Rebalancing still happens on schedule for drift correction, but the system can also take opportunistic entries/exits without waiting for "daily rebalance time."

**Rebalancing Fit**
- Keep the daily 21:00 anchor (good for NA volume).
- HybridRebalancer logic becomes `hybrid_trigger.evaluate(...)` — one possible input to "should we run allocator in rebalance mode now?"
- Allocator's rebalance_strategy handles the actual weight calc + plan (reusing/enhancing current deploy_capital + rebalance_plan code).

## Migration Path (Phased, Low-Risk)
1. **Audit + Isolation Baseline** (do first): Write standalone test wrappers that exercise *current* paths with real data (signals only log, rebalance paths produce plans). Document exact current behavior + idle capital stats. This becomes the "before" for regression.
2. **Extract Evaluation**: Make SignalGenerator + OpportunityScanner produce consistent `Proposal` objects. Add a thin `evaluate_universe()` facade. Wire it so runner (temporarily) can at least log rich proposals.
3. **Unify Allocator**: Evolve `deploy_capital` + `allocation_engine` + extracted hybrid logic into a single `allocator.py` (or keep names but make one entrypoint). Rebalancing logic moves here as a strategy. Make it accept a list of Proposals.
4. **Wire Signals to Action**: Change the runner's signal block from "log only" to "collect proposals → feed allocator → if non-empty plan and risk allows, execute (or shadow first)".
5. **Thin the Runner / Add Orchestrator**: Move heavy logic out. Runner becomes the cycle coordinator + safety wrapper.
6. **SL + Safety**: Keep/strengthen StopLossCoordinator as the wrapper around any execution window.
7. **Tests & Measurement**: Isolation tests for each layer. Add metrics (capital deployed per cycle, proposal acceptance rate, utilization %). Backtest the new allocator with real proposal streams.
8. **Cleanup**: Delete duplicate parsing, old scripts/ copies once canonical paths are proven, update all consumers to the new facades.

## Benefits
- **Optimization becomes possible**: You can A/B signal modes, allocator strategies, rebalance frequency independently. Measure impact on idle capital and P&L.
- **Testability**: Isolation tests (your preferred pattern) become trivial and permanent. "Run this exact evaluation with this cache snapshot and assert the proposals."
- **Maintainability**: Small files, clear ownership. New signal source? Add to Evaluation layer only.
- **Actionability**: Evaluation is no longer decorative. Capital can enter on signals *and* get rebalanced daily.
- **Debuggability**: When a trade happens, you can trace Proposal → Allocator decision → Plan → Execution with reasons at each step.

## Risks / Tradeoffs
- Over-engineering: Start minimal (3-4 core classes + facades) rather than full strategy pattern on day 1.
- Performance: Irrelevant for this universe size (10-12 pairs, 5-30 min cycles).
- Short-term velocity: Phase 1-2 will feel like "no new features," but it unblocks everything after.
- State continuity: Preserve trade_ledger, positions, and rebalance history during refactor.

## Open Questions for You
- Priority: Get *some* signal-driven entries working quickly (even if still rebalance-heavy), or full clean layers first?
- How aggressive on deprecating the old hybrid_rebalancer internals vs. adapting them?
- Do we want the Allocator to be strategy-pluggable from the start (e.g. class with `compute_plan()`), or a single smart function with a `mode` param for v1?
- Measurement dashboard additions you want early (capital utilization, proposal-to-trade conversion, etc.)?

This design directly solves the divergence you described while preserving (and improving) the working pieces (deploy_capital gates, inverse-vol + sentiment, CR-03 SL, canonical data, 21:00 rebalance anchor).

---

**Next**: I'll seed a single canonical `docs/MASTER_TASK_TRACKING.md` with this as a major initiative, broken into bite-sized phases with success criteria, isolation test requirements, and handoff points. Then we can proceed.

Let me know if this direction is good, any adjustments, or "proceed to write the master list + start Phase 1 isolation baseline immediately."


## ARCH-3 Status (2026-06-15)
Integrated stack simulation complete.
- New path (evaluate_universe + Allocator) now has a dedicated isolation test that mimics the runner cycle.
- TradePlan is the contract between decision and execution.
- Wiring guidance documented in the ARCH-3 MASTER entry.
- Next: actual patch to phase6_runner.py with feature flag.

See test_isolation_integrated_evaluation_allocator.py and data/state/arch3_integrated_stack_evidence.json for details.

