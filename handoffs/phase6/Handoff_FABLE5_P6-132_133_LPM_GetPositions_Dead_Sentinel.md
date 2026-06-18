# Handoff: FABLE5-P6-132/133 (P0-Critical)

**Title**: LivePortfolioManager.get_positions is dead code (defined only under `if __name__`) + violates verified sentinel contract (returns {} on error); 5-pair hardcode; invisible positions for any added pairs

**From**: Fable 5 Batch 3 review (2026-06-10, top-ranked new CRITICAL)

**Objective**: Make get_positions() (and supporting methods) a first-class, importable method on the class. Enforce the verified-sentinel contract already established for holdings (P6-101, now closed at client level). Derive pair list from config. Never silently return {} or fall back from live to internal state.

**Files in scope (must touch)**:
- phase6/core/live_portfolio_manager.py (core change)
- phase6/core/phase6_runner.py (call sites for has_open_positions, get_enriched_positions, Fresh Start gate)
- phase6/core/exchange_client.py (if needed for wrapper)
- config/trading_config_phase6.json (confirm universe)
- Any callers in hybrid_rebalancer, stop_loss_coordinator, order_executor, deploy logic

**Standing constraints (must preserve)**:
- Real data only.
- Fresh Start = bootstrap-only on *explicit verified zero* (tri-state: verified=False is NOT zero for triggering Fresh Start).
- Sticky holdings + proportional adjustment (never full renormalize small deltas).
- Withdrawal reserve respected.
- Sentinel must distinguish "unverified due to error" from "confirmed empty/zero".
- Code Isolation Testing + real-data shadow verification + Scotty (crypto-orchestrator) sign-off required before this card can be moved to done.

**Must Do**:
1. Move `get_positions(self, force_refresh=False)` into the main class body (it is currently under `if __name__ == "__main__":` — confirm via full file read).
2. Return shape: `{"positions": dict, "verified": bool, "error": Optional[str]}` or equivalent tri-state (mirror get_holdings_verified).
3. `has_open_positions()` and `refresh()` must correctly propagate verified state (never treat unverified or error as "no positions" for Fresh Start trigger).
4. Derive DEFAULT_UNIVERSE / pair list from config at runtime (support 5 or 6 pairs; no hardcode).
5. Add import-time smoke test / assertion that the method exists on the class.
6. Ensure LPM delegates to exchange.get_holdings_verified() + get_enriched_positions() for verification.
7. Update any reconciliation / PnL paths (P6-134/135 sibling issues) to use verified data.
8. Write a standalone Code Isolation Test: `scripts/test_fable5_p6_132_133_lpm_verified.py` proving:
   - Method is importable.
   - Unverified/error paths return verified=False + error, never {} as "zero".
   - Fresh Start decision logic in runner only triggers on explicit verified=False.
9. Scotty runs the test in shadow with realistic fixtures on both the phase6/ and src/ versions of LPM if they differ; adds detailed sign-off comment to card.

**Must Not Do**:
- Do not treat {} or None from error as verified zero.
- Do not leave method under `if __name__`.
- Do not hardcode 5-pair list.
- Do not allow silent fallback live → paper state.
- No changes to live trading code until isolation test passes + Scotty comment.

**Deliverables**:
- Patched live_portfolio_manager.py (class-level clean method + sentinel).
- Updated callers in runner (Fresh Start gate, _perform_daily_rebalance, etc.).
- Standalone isolation test script that passes with evidence.
- Scotty sign-off comment on Kanban card with test output + before/after.
- Reference this handoff in card body.

**Success criteria**:
- Isolation test passes cleanly in shadow with realistic data.
- Scotty (crypto-orchestrator) reviews output, confirms sentinel contract, adds "SCOTTY SIGN-OFF" comment.
- Card moved to done only after sign-off.
- Fable 5 closure review (if run) confirms the method lives at import time and sentinel is uniform.

**References**:
- Fable 5 Batch 3 response.md (P6-132/133 section + sentinel uniformity check table).
- Prior P6-101 handoff and P6-101 isolation test for pattern.
- phase6/core/phase6_runner.py Fresh Start logic.
- Current board card will reference this file.

**Created**: 2026-06-10 by Scotty (crypto-orchestrator) as part of small-batch ingest.