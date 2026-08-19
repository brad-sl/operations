# Crypto trading bot — documentation hub

**Project:** Phase 6 live trading platform + ARCH Automation SaaS engineering  
**Repo:** `projects/crypto-trading-bot`

## Start here

| Role | Document |
|------|----------|
| **Specs / PRDs / doctrine / “where is X?”** | **[`docs/SPECS_INDEX.md`](SPECS_INDEX.md)** |
| **Specs ↔ code gaps + what to deprecate** | [`SPECS_CODE_GAP.md`](SPECS_CODE_GAP.md) |
| **In vs out of repo** | [`PROJECT_BOUNDARY.md`](PROJECT_BOUNDARY.md) |
| **What shipped / queued (execution)** | [`MASTER_TASK_TRACKING.md`](MASTER_TASK_TRACKING.md) |
| **Feature specs only** | [`features/README.md`](features/README.md) |
| **Epics** | [`epics/`](epics/) |
| **Operator FAQs** | [`faq/`](faq/) |

## Do not use as current SSOT

- `SPEC.md`, `PHASE6.md`, `FUNCTIONAL_SPEC*.md` — historical snapshots (see SPECS_INDEX §5)  
- `docs/archive/**` — archived on purpose  
- `phase6/specs/*` — legacy mirrors; verify against `docs/`  

## Live config (behavior truth)

- `config/trading_config_phase6.json`  
- `config/regime_cash_policy.json`  
- `config/exit_automation.json`  
- `config/trader_accounts.json`  
- `config/regime_exit_policy_map.json`  

## Agents

1. Read `SPECS_INDEX.md` for the domain.  
2. Open the **primary** doc from the cheat sheet (§8).  
3. Confirm against live config + runner state before claiming behavior.  
4. If you add a FEAT, register it in the index the same session.

---

*Hub rewritten 2026-08-07 (replaces stale Phase 5.1 test-only README).*
