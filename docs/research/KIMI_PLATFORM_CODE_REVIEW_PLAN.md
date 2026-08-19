# Kimi systematic platform code review — test plan

**Owner:** Hermes orchestrator · **Reviewer:** `code-reviewer` profile (`moonshotai/kimi-k2.7-code` on OpenRouter)  
**Repo:** `/home/brad/projects/crypto-trading-bot` · **Scope:** Phase 6 live trading platform (not archive/phase5)

## Goals

1. Independent security/reliability review of production paths (real money, real data).
2. Find integration gaps (helpers defined but not wired), silent failure modes, and missing isolation coverage.
3. Produce **actionable backlog** items — not a deploy gate PASS/REJECT for the whole repo.

## Non-goals

- Line-by-line style review of every test file.
- Rewriting architecture; reviewer **does not implement fixes**.
- Treating scenario backtest winners as production approval.

## Method

| Step | What |
|------|------|
| 1 | Eight **slices** (bounded file sets + focus prompts) in `data/state/code_review/slices/` |
| 2 | Runner `scripts/hermes/run_platform_code_review_slice.sh <slice_id>` → Kimi via `code-reviewer chat` |
| 3 | Full run `scripts/hermes/run_platform_code_review_all.sh` → per-slice artifacts + rollup |
| 4 | Human triage: HIGH → handoff/MASTER; MED → backlog; LOW → optional |

## Slice map

| ID | Name | Primary paths | Isolation tests (run if present) |
|----|------|---------------|----------------------------------|
| S1 | Foundation | `paths.py`, `config_loader.py`, `exchange_client.py` | `test_isolation_product_metadata` (core) |
| S2 | Runner & rebalance | `phase6_runner.py`, `rebalance_coordinator.py`, `cycle_coordinator.py`, `cron_rebalance.py` | `test_isolation_cycle_coordinator`, `test_isolation_current_rebalance_path` |
| S3 | Execution & ledger | `order_executor.py`, `trade_ledger.py`, `live_portfolio_manager.py` | `test_isolation_allocator_platform_executor` |
| S4 | Stop-loss & risk | `stop_loss_manager.py`, `sl_preflight.py`, `sl_risk_scorer.py`, `agentkit_sl.py`, `stop_loss_coordinator.py` | `test_isolation_sl_preflight`, `test_isolation_sl_insufficient_fund` |
| S5 | Allocation & data refresh | `allocator.py`, `allocation_engine.py`, `signal_generator.py`, `pre_rebalance_data_refresh.py`, `sentiment_scorer.py` | `test_isolation_pre_rebalance_refresh`, `test_isolation_allocator` |
| S6 | ANALYST-OPT & research | `run_scenario_leaderboard.py`, `arch4_scenario_runner.py`, `promotion_gates.py`, `scenario_knobs.py`, `optimization_brief.py` | `test_scenario_date_range_override`, `test_isolation_scenario_knob_parity` (research/) |
| S7 | Ops scripts & intel | `generate_trading_intelligence_report.py`, `deploy_capital.py`, `refresh_sentiment.py`, `capital_deployment_runner.py` | `test_isolation_strategic_brief` |
| S8 | Cross-cutting & test gaps | `docs/DATA_FLOW_AND_LOCATIONS.md`, scan for hardcoded paths / fake data in `phase6/core` | List isolation tests under `phase6/tests` vs core modules |

## Reviewer deliverable (every slice)

```markdown
# Slice <ID>: <name>
## Summary (3-6 bullets)
## Strengths
## Issues — High / Medium / Low (file:line when possible)
## Integration gaps (defined but not called)
## Test gaps
## Suggested backlog IDs (ANALYST- or ENG- style one-liners)
SLICE_STATUS: REVIEWED | BLOCKED (reason)
```

## Execution commands

```bash
cd /home/brad/projects/crypto-trading-bot
# One slice:
scripts/hermes/run_platform_code_review_slice.sh S4
# Full platform (sequential, ~30-60 min):
scripts/hermes/run_platform_code_review_all.sh
# Rollup only:
scripts/hermes/rollup_platform_code_review.sh
```

## Artifacts

| Path | Purpose |
|------|---------|
| `data/state/code_review/slices/S*.md` | Input packets |
| `data/state/code_review/out/S*.md` | Kimi outputs |
| `data/state/code_review/PLATFORM_REVIEW_ROLLUP.md` | Merged findings + deduped HIGH |
| `docs/handoffs/KIMI_PLATFORM_REVIEW_<date>.md` | Handoff after rollup |

## Success criteria

- All 8 slices `SLICE_STATUS: REVIEWED` (or BLOCKED with explicit reason).
- Rollup lists **≥1 verified** isolation test command per critical slice (S2–S5).
- No claim of "platform safe" — only prioritized backlog.

## Re-run policy

- After major deploy touching a slice: re-run that slice only.
- Quarterly or pre-live-capital increase: full `run_platform_code_review_all.sh`.