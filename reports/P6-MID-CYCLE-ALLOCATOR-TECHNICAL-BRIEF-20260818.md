# P6-MID-CYCLE-ALLOCATOR-EVAL-20260807 — Technical Brief
**Task:** t_322b78ea (Review mid-cycle allocator code, config, and risks)
**Date:** 2026-08-18
**Status:** Study/eval only. No live changes.

## Confirmation (Acceptance Criteria)
- `global_settings.mid_cycle_allocator_enabled`: **false** (verified in `config/trading_config_phase6.json:32` and shadow overlay).
- All inspection via read/search only. **No config flips, no code changes, no live capital paths touched.**
- Concrete references below.
- Sufficient for offline eval plan without further archaeology.

## Flag & Wiring Map
- **Config flag:** `global_settings.mid_cycle_allocator_enabled` (default false for live safety).
  - File: `config/trading_config_phase6.json:32`
  - Also in: `config/shadow_overlays/DEPLOY-PCT-078-LEAN-IN_base_config.json:24`
  - Backups and reports consistently show false.
- **Load:** `phase6/core/phase6_runner.py:214`
  ```python
  self.mid_cycle_allocator_enabled = bool(gs_flags.get("mid_cycle_allocator_enabled", False))
  ```
  Logged at init: `mid_cycle_shadow=...` (line 340).
- **Primary path guard:** `_use_primary_allocator_path()` (uses `use_new_allocator` + `NEW_ALLOCATOR_AVAILABLE`) — line 345.
  - ARCH-4 import guard: lines 96-101.
- **Mid-cycle call site:** Only from non-rebalance cycles.
  - `phase6/core/cycle_coordinator.py:48-49`:
    ```python
    if not rebalance_needed:
        self._maybe_mid_cycle_shadow(runner)
    ```
  - Rebalance due: `_should_rebalance` or `_evaluate_hybrid_rebalance` (time/hybrid driven).
- **Impl (shadow only):**
  - `cycle_coordinator.py:264-330` (`_maybe_mid_cycle_shadow`):
    - Guard 1: `if not getattr(runner, "mid_cycle_allocator_enabled", False): return`
    - Guard 2: `if not runner.shadow_mode: warning + return` ("live blocked")
    - Guard 3: `if not runner._use_primary_allocator_path(): return`
    - Requires `runner._last_proposals` (from unified eval earlier in cycle).
    - Builds norm positions + raw `cash = exchange.get_account_balance("USD")`
    - `allocator = create_allocator_from_config("rotation", runner.config_dict)`
    - `plan = allocator.allocate(...)`
    - Logs: `[P4-02 MID-CYCLE SHADOW] actions=... accept_rate=... exposure=...`
    - `[P4-02 SHADOW EXEC] Would execute N legs (not sent)`
    - Stores: `runner._last_mid_cycle_plan = plan` (never consumed for execution).
- **Allocator used:** `phase6/core/allocator.py` (same as rebalance primary path)
  - `Allocator.allocate(...)` → `RotationStrategy.decide(...)` (default).
  - `create_allocator_from_config` in `phase6/core/runtime_knobs.py:165` (pulls from `global_settings` + `allocator:` section + risk).
- **Rebalance contrast path (for comparison):** `phase6/core/rebalance_coordinator.py:159+` (only when rebalance_needed)
  - Same allocator + **additional filters** then `_execute_trade_plan`.
- **Dashboard exposure:** `phase6_runner.py:1168` includes `mid_cycle_shadow` flag + `_last_proposals` + `last_plan` (rebal), but **not** `_last_mid_cycle_plan` directly.
- **No other call sites:** Grep confirms mid-cycle logic confined to coordinator + runner init. `_last_mid_cycle_plan` only set, never executed.

## Intended vs Current Behavior
**Intended (from handoffs + MASTER):**
- P4-02: Unified per-cycle `evaluate_universe` snapshot (replaces parallel logs).
- Shadow-only mid-cycle allocator on *non-rebalance* cycles (when `mid_cycle_allocator_enabled` + shadow_mode).
- Signals drive *plans* between daily rebalance windows without live trades.
- Flag default false; safe to enable in paper/shadow for study.
- "One evaluate_universe snapshot per cycle."

**Current (code as of review):**
- Matches: unified eval runs every cycle (freshness guarded by signal mtime in `_should_run_full_evaluation`).
- Mid-cycle **only** on `!rebalance_needed`, only under all 3 guards.
- Produces `TradePlan` via RotationStrategy using real proposals + current portfolio/cash.
- Pure logging + state set. Never reaches `_execute_trade_plan` (explicit comment + shadow guards in exec).
- Proposals logged as `[ARCH-4 PROPOSAL]`.
- Works in shadow runs; blocked in live.

**Allocator strategy (RotationStrategy — "catch-the-wave"):**
- Weak exits: ROTATE_OUT/SELL or (HOLD and score < 0.5 - min_score_delta)
- Strong buys: ROTATE_IN/BUY above threshold (relaxed in emergency <=2 positions)
- Hard stops inside: drawdown > dd_threshold or entry_dd <= -stop_loss_pct or score<0.2 → SELL + force_re_evaluate
- Cooldown on weak rotations (internal to allocator instance)
- Opportunistic redeploy of freed + cash to top strong (capped slices)
- Fallback light tilt if cash only
- Post: min_move_usd filter on actions
- Config knobs (via runtime_knobs): min_move_usd=50, min_score_delta=0.05, stop_loss_pct=0.03, cooldown=6h, dd=0.08, max_pairs=5 (from `allocator:` + global_settings + risk_management)

**Key difference vs rebalance:** Mid-cycle shadow plans are "raw" allocator output. Rebalance applies post-filters before exec.

## Risk Notes, Failure Modes, Edge Cases, Live Coupling
**Hard live-safety (enforced):**
- Flag false in prod config.
- `!shadow_mode` → explicit warning + skip (even if flag true).
- No path from mid-cycle to order execution (no call to _execute, no TradeExecutor, no OrderExecutor).

**Coupling to live (read-only, safe):**
- Shared: `FIXED_UNIVERSE` (from paths.py), `_last_proposals` (unified eval), `portfolio.get_enriched_positions()`, `exchange.get_account_balance("USD")`, `price_history` (indirect), config_dict, trade_ledger (for other things).
- No writes. No SL attachment, no orders.

**Bypassed guards in mid-cycle shadow (vs rebalance path):**
- `runner_capital_events.py`:
  - `filter_trade_plan_manual_cooldown` (post-SL block-rebuy, manual sell cooldowns)
  - `filter_trade_plan_near_open_stop` (hard: any BUY on pair with open armed SL in registry + pos >= min; soft: near-stop gap/unrealized for tilt reasons)
- `regime_cash_policy.py:apply_to_runner_plan` (regime veto, cap clamp to 0 in park/cautious, prefer_exit)
- Trade buffer (recent trades within trade_buffer_hours)
- `effective_allocator_cash_usd` (subtracts min_reserve + manual_hold) — mid uses raw cash.
- Withdrawal reserve enforcement (only in rebal).

**Allocator-internal risks (apply to both but shadow sees raw):**
- Emergency recovery mode if <=2 active pairs (relaxed buy scores).
- Drawdown exits set `force_re_evaluate=True` (unused in mid).
- Regime tie-breaker only if `intelligence_brief` passed (not passed in mid or rebal path).
- `recent_prices`/`entry_prices`/`current_prices` not passed → limited drawdown logic (uses only trailing from provided recent in some paths).
- Cooldown (`last_rotation`) is per-allocator-instance (recreated every call via create_...) → never spans cycles; cooldowns ineffective for mid-cycle planning. (Cross-cycle churn control relies on ledger-based filters instead.)
- Sizing: equal slice of available to top N strong; min_move filter post-facto. Can over-allocate if not clamped elsewhere.
- No max exposure / position count hard cap beyond config max_pairs (lightly used).

**Failure / edge modes:**
- Mid-cycle fires between rebalances → can surface "would rotate now" signals that rebalance filters would have killed.
- If flag flipped true in live (forbidden): would still skip due to !shadow, but proposals eval always runs.
- Stale proposals (freshness guard mitigates for full eval).
- Zero proposals or all HOLD → silent skip.
- Portfolio positions dict shape variations (code has normalization).
- Cash=0 + no weak exits → no actions.
- Allocator state not persisted → repeated shadow runs may propose same rotations without cooldown.
- Hybrid rebalance or time slots can suppress mid-cycle unexpectedly.
- If NEW_ALLOCATOR_AVAILABLE=False → mid skipped.
- Preserve/park paths run after, but don't affect mid planning.

**Position sizing / risk coupling points:**
- `risk_management` section: near_stop_* (bypassed), stop_loss_pct (used in allocator + near-stop calc), deploy_pct (not directly in mid).
- `allocator:` subsection + global_settings capital_event_* , rebalance_cap (rebal only).
- `preserve_mode` (E1 etc. — separate, runs in cycle but no interaction with mid plan).
- Stop loss coordinator / registry (used only in near-stop filter — bypassed).
- No direct mid-cycle impact on SL/TP or re-attach.

## Eval Hooks, Tests, Metrics, Logs Available for Offline Eval
**Ready hooks (no further arch needed):**
1. **Isolation tests (safe, real data, no runner loop):**
   - `phase6/tests/test_isolation_mid_cycle_shadow.py` — full unified eval + allocator plan from real sentiment/RSI. Produces `data/state/p4_02_mid_cycle_shadow_isolation.json`. Run: `python phase6/tests/test_isolation_mid_cycle_shadow.py`
   - `phase6/tests/test_isolation_cycle_coordinator.py` — wiring + flag load + _run_cycle smoke (with temp config enabling flag).
   - `phase6/tests/test_isolation_allocator.py`, `test_isolation_rotation_shadow.py`, etc. for allocator unit.
2. **Full cycle simulation (shadow only):**
   - Instantiate `Phase6Runner(config_path=..., mode="shadow")` with temp config having `"mid_cycle_allocator_enabled": true`.
   - Call `runner._run_cycle(N)` (or let loop run during non-rebal windows).
   - Inspect: `runner._last_mid_cycle_plan`, logs, `data/state/phase6_live_state.json` (dashboard), `phase6.db`.
3. **Direct replay (for backtest):**
   - Load historical proposals (or re-run `evaluate_universe` on cached sentiment/rsi/price snapshots).
   - `from phase6.core.runtime_knobs import create_allocator_from_config`
   - `plan = allocator.allocate(proposals, current_allocs, cash, total)`
   - Compare actions vs rebalance-time plans or baseline (no mid).
4. **Logs / metrics produced in mid-cycle:**
   - `[P4-02 MID-CYCLE SHADOW] actions=... accept_rate=... exposure=... strategy=...`
   - `[P4-02 SHADOW EXEC] Would execute...`
   - Plan attrs: `actions`, `new_allocations`, `expected_exposure`, `rotations`, `stops`, `drawdown_exits`, `force_re_evaluate`, `strategy_used`, `notes`.
   - Accept rate calc (in coordinator): fraction of proposals that made it into actions.
   - Proposals: `[ARCH-4 PROPOSAL] pair: side score= src=`
5. **Other artifacts:**
   - `data/state/phase6_runner_state.json` (rebal dates)
   - Trade ledger + price_history for replay.
   - Dashboard cache + DB views for utilization.
   - Reports/OPT_EX_* and handoffs for prior context (keep flag off).
6. **Runner entry for paper eval:** `python -m phase6.core.phase6_runner --mode shadow --config <temp-with-flag-true>` (will log mid-cycle on non-rebal 30min/60s cycles). Use timeout or patch `_should_rebalance` temporarily for forced non-rebal cycles in a test harness.
7. **Gaps for full offline harness:** No dedicated "mid_cycle_replay.py" or historical signal time-series replay script visible. Use the isolation + manual proposal snapshot replay. No mid-cycle specific metrics persisted beyond the plan object/logs (rebal decision_context is richer).

## Recommended Offline Eval Approach (for child tasks)
- Use temp config or monkeypatch flag + shadow runner.
- Capture series of mid-cycle plans (non-rebal cycles) vs rebalance plans.
- Metrics: #actions per cycle, accept_rate, exposure, rotation count, overlap with next rebalance, "would have violated" near-stop/regime filters (post-apply the filters to mid plans for comparison).
- Baseline: same periods with flag=false (no mid plans) or synthetic off.
- Verify throughout: config remains false on disk; no orders generated.
- Artifacts: jsonl of plans + logs + filter simulation results.
- Do **not** promote flag; study only.

**Nothing live was changed. All paths remain blocked for production capital. Flag confirmed false.**

References (key files/lines):
- Config + flag: config/trading_config_phase6.json:32
- Runner wiring: phase6/core/phase6_runner.py:214,340,634-642,1168,1217-1231 (_exec guard)
- Coordinator + mid logic: phase6/core/cycle_coordinator.py:48-49,264-330
- Allocator: phase6/core/allocator.py:141-360 (Rotation.decide),442-492 (allocate),495+
- Knobs: phase6/core/runtime_knobs.py:119-175
- Filters (bypassed): phase6/core/runner_capital_events.py:415,610+
- Regime: phase6/core/regime_cash_policy.py:452+
- Rebal path: phase6/core/rebalance_coordinator.py:159-252
- Tests: phase6/tests/test_isolation_mid_cycle_shadow.py, test_isolation_cycle_coordinator.py
- Basket: phase6/core/paths.py + load_trading_basket

Ready for offline eval execution.