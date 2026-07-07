# Memory & Learning — Crypto-Analyst / ANALYST-OPT

**Canonical paths** (see also `docs/DATA_FLOW_AND_LOCATIONS.md`):

| Store | Path | Writer | Reader |
|-------|------|--------|--------|
| Scenario run ledger | `data/state/analyst_scenario_runs.jsonl` | `run_scenario_leaderboard.py` | Analyst, brief (R2), MASTER |
| Latest leaderboard | `data/state/analyst_scenario_leaderboard_latest.json` | harness | Brief, dashboards |
| Cycle learnings | `data/state/analyst_learnings.json` | brief cron, harness `--record-learning` | Brief, Hermes memory sync |
| Proposals | `data/state/analyst_proposed_backlog.json` | `generate_trading_intelligence_report.py` | MASTER, Kanban |
| Strategic proposals | `data/state/analyst_strategic_proposals.json` | analyst jobs | MASTER |

---

## Learning record shape (scenario batch)

Each line in `analyst_scenario_runs.jsonl`:

```json
{
  "run_id": "OPT-20260707-001",
  "pack_id": "r0_smoke_three",
  "started_at": "ISO8601",
  "data_fingerprint": {"ohlcv": "backtests/data/backtest_historical_ohlcv_*", "pairs_loaded": 5},
  "baseline_scenario_id": "baseline_7d",
  "primary_metric": "sharpe_ratio",
  "ranking": ["expanded_7d", "baseline_7d", "baseline_14d"],
  "scenarios": [{ "id": "...", "metrics": { ... } }]
}
```

**Rule:** Promotion to proposals requires a `run_id` cited in the proposal body.

---

## analyst_learnings.json (evolution)

Schema version 1. Each learning:

- `cycle` — business date or rebalance anchor  
- `thesis` — what we expected  
- `outcome` — what metrics/logs showed  
- `evolution_note` — what changes next run (params, gates, code)

**Dedup:** On append, skip if same `(cycle, thesis, outcome)` within 24h (R2 cleanup for historical duplicates).

---

## Hermes memory vs file memory

| Use Hermes `memory` for | Use file state for |
|-------------------------|-------------------|
| User preferences (21:00 PT, no fake data, delegation style) | Numeric outcomes, run IDs, leaderboards |
| Stable conventions (isolation tests, MASTER as SoT) | Anything that must survive profile resets |

After a verified optimization workflow, offer `skill_manage` for `crypto-analyst-scenario-run` (R2).

---

## Compounding loop

1. Run scenario pack → jsonl + leaderboard  
2. Analyst reads leaderboard + prior learnings → honest assessment  
3. If beat baseline + gates → `ANALYST-*` proposal → MASTER  
4. Engineering implements in shadow → ledger/monitor metrics → new learning  
5. Optional: patch analyst skill with new pitfall

**Failure patterns must feed the next run** (telemetry → adjust gates or knobs), not only human dashboard glances.