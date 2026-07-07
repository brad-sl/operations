# Epic: ANALYST-OPT — Crypto-Analyst Scenario Optimization & Learning

**Status:** In progress (R0 started)  
**Created:** 2026-07-07  
**Owner:** crypto-analyst (Hermes profile) + platform engineering  
**Depends on:** Phase 6 real data paths; **feeds** ARCH isolated components (evaluation → allocator must match backtest surface)  
**Does not:** Place live orders, change live config without explicit approval, or use synthetic/placeholder prices for promotion decisions.

---

## 1. North star

**Crypto-Analyst** runs **optimization scenarios** on **real-world data** (OHLCV, cached sentiment/RSI when wired, ledger-derived outcomes) to **minimize losses and maximize risk-adjusted return** across multiple signals, methods, and environment variables.

**Memory / learning is foundational:** every scenario batch produces durable artifacts that compound — not one-off Telegram prose.

| Layer | Artifact | Purpose |
|-------|----------|---------|
| **Run ledger** | `data/state/analyst_scenario_runs.jsonl` | Append-only; every batch: `run_id`, scenarios, metrics, data fingerprints |
| **Learnings** | `data/state/analyst_learnings.json` | Thesis → outcome → evolution_note per cycle (deduped on write) |
| **Proposals** | `data/state/analyst_proposed_backlog.json` + MASTER | `ANALYST-YYYYMMDD-NNN` only when metrics beat baseline + gates pass |
| **Hermes memory/skills** | Profile + `~/.hermes/skills/` | Analyst persona, procedures, pitfalls after verified workflows |
| **Brief** | `generate_trading_intelligence_report.py` | Honest assessment + optimization summary section (R2) |

---

## 2. Three planes (recap)

```
OVERSIGHT (Brad): risk budget, deploy caps, shadow→live promotion
        ↓
CRYPTO-ANALYST: scenario design, interpretation, honest assessment, proposals
        ↓
EXECUTION (Phase 6): deterministic runner; shadow first; real data only
```

**Outcome loop (in-repo, not Superdense):** scenario spec → harness run → leaderboard → learning entry → optional proposal → shadow → live (gated).

---

## 3. Phases

### R0 — Scenario schema + leaderboard harness ✅ (this kickoff)

- `docs/research/scenario_schema.md` — JSON contract for scenario packs  
- `docs/research/MEMORY_AND_LEARNING.md` — how artifacts chain  
- `phase6/research/run_scenario_leaderboard.py` — isolation runner (3+ configs → ranked JSON)  
- `phase6/research/scenarios/r0_smoke_three.json` — smoke pack  
- **Success:** `python3 phase6/research/run_scenario_leaderboard.py` exits 0, writes `data/state/analyst_scenario_leaderboard_latest.json`, appends `analyst_scenario_runs.jsonl`

### R1 — Align harness with live strategy surface ✅ (2026-07-07)

- Gap matrix: `docs/research/BACKTEST_LIVE_GAP_MATRIX.md`
- `phase6/research/scenario_knobs.py` + `test_isolation_scenario_knob_parity.py` (PASS)
- ARCH-4 smoke from `baseline_7d` knobs: return_pct=-27.75, max_dd=29.63, trades=144
- **Promotion still blocked** on documented gaps until R1b (`engine: arch4` leaderboard)

### R1b — Path B leaderboard ✅ (2026-07-07)

- `engine: arch4` + pack `default_engine` in `run_scenario_leaderboard.py`
- `phase6/research/arch4_scenario_runner.py`
- Pack: `phase6/research/scenarios/r1_arch4_smoke_three.json` (rotation 7d/14d + rebalance 7d)
- Leaderboard field `engine_mode`; metrics normalized for Sharpe ranking on ARCH-4 equity curve

### R2 — Cron + brief integration (queued)

- Weekly Hermes cron: run default scenario pack → analyst brief **Optimization results** section  
- Auto-ingest winning proposals to MASTER backlog only if `gate` rules pass  
- Deduplicate stale learnings (fix duplicate 2026-07-04 entries)

### R3 — Shadow promotion pipeline

- Git-versioned config overlay + automatic rollback on monitor breach  
- Compare shadow PnL vs backtest prediction; feed drift into learnings

---

## 4. Primary metrics (default ranking)

1. **Max drawdown %** (minimize) — tie-breaker  
2. **Sharpe** (maximize)  
3. **Total return %**  
4. **Rebalance count / turnover** (penalize churn in gates)

Gates (promotion): must beat baseline on holdout; max drawdown ≤ baseline + slack; no synthetic data flag.

---

## 5. Hermes crypto-analyst profile

- **Model:** capable reasoning (orchestrator routes heavy analysis)  
- **Tools:** `terminal` (run harness), `read_file`, `write_file`, `patch`, `memory`, `skill_manage`  
- **Must:** mandatory honest assessment in briefs; no sugarcoating; cite `run_id` and metric table when proposing changes  
- **Must not:** `delegate_task` to change live runner config without MASTER task + user approval

---

## 6. References

- `docs/research/scenario_schema.md`  
- `docs/research/MEMORY_AND_LEARNING.md`  
- `phase6/scripts/generate_trading_intelligence_report.py`  
- `phase6/backtest/`  
- `docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md`  
- `handoffs/analyst/Handoff_ANALYST-OPT_Kickoff.md`