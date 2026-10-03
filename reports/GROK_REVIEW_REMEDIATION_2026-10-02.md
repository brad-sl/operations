# Grok 5.6 review remediation — 2026-10-02

Source: Brad-forwarded Grok review of last-week tryout/rotation/money-arms changes.
No live orders. Isolation tests re-run green after patches.

## Commit scope (durable)

Staged for safe code backup (not `*_LATEST.md`, not `*.bak_*`):

- `phase6/core/runner_capital_events.py` — eject ≠ post_tp stack; rotation ≠ manual
- `phase6/core/tryout_scale_window.py` — cooloff DEFAULT/fallback **24h**; live_apply honesty; dry-run naked not success; skip double dwell on live eject
- `phase6/core/allocator.py` — multi-token RSI-OB detect; emergency does **not** bypass core-sleeve RSI hold
- `phase6/core/protected_market_exit.py` — SW-03 hard reattach (entry→mark→get_price + retries + fail-closed)
- `phase6/core/tryout_seat_ledger.py` — open_lots flock + `write_open_lots_raw`
- `phase6/core/tryout_scale_up_shadow.py` — OPEN_LOTS writes go through flock
- `config/tryout_scale_window.json` — cooloff 24h, live_apply true
- `docs/features/TRYOUT_LIFECYCLE_PROCESS.md` — money arms ON honesty
- isolation tests (scale_window, core_sleeve, protected exit, lifecycle bg, disposition)

## Issue map

| # | Finding | Disposition |
|---|---------|-------------|
| 0 | Uncommitted capital + 24h cooloff | **Committed** this session |
| 1 | Docs lie (`live_apply: false` / measure-only) | **Fixed** process SSOT 2026-10-02 |
| 2 | 48h leftover fallback/docstring | **Fixed** DEFAULTS + eject fallback use 24 |
| 3 | Dry-run SL reattach not hard (SW-03) | **Hardened** multi-pass + fail-closed; eject dry path no longer forces success on naked |
| 4 | Registry truth / races / double dwell | **Partial:** flock on open_lots; live eject `skip_dwell` after ledger hooks; purge still held-map guarded |
| 5 | RSI-only hold string-fragile | **Fixed** multi-marker + md rsi_14/indicators |
| 6 | Emergency recovery bypasses core-sleeve | **Fixed** RSI-OB hold always, even thin book |
| 7 | Git hygiene noise | Scoped commit only; LATEST/bak left unstaged |

## Tests run (`.venv`, `PYTHONPATH=.`)

- `test_isolation_core_sleeve_rotation_guards.py` → **7/7** (added reason-variant + emergency thin-book)
- `test_isolation_tryout_scale_window.py` → **10/10**
- `test_isolation_protected_market_exit.py` → **ALL PASSED**
- `test_isolation_tryout_lifecycle_bg.py` → **7/7**
- `test_isolation_stop_exchange_disposition.py` → **ALL PASS**

## Residual (honest)

- Registry flock is best-effort (timeout proceeds unlocked with warning) — not a distributed lock.
- Scale-up shadow still has dual write path; both now prefer seat-ledger lock.
- Auto-money remains **product GO** (not a silent regression); 7d monitor still through 2026-10-08.
