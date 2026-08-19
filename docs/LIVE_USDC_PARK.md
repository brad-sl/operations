# Live USDC park — operator guide

**Trader name:** part of **Smart Park** (“cash + yield”) — see `docs/features/PARK_SMART_IDLE_CASH.md`.

Per-account optional path: when the platform says **pause new crypto risk**, you can hold parking-lot money in **USDC** (a dollar-like stablecoin) so it may earn **whatever yield the exchange currently offers**. When rules allow crypto again, unwind extra USDC and run the normal buy path.

**Never market a fixed APY.** Show a live venue rate or say “may earn yield at the exchange’s current rate.”

**Research baseline:** `docs/research/REGIME_USDC_OPTIMIZATION.md`  
**Code:** `phase6/core/usdc_park_executor.py`, `phase6/core/usdc_park_transitions.py`, `phase6/core/trader_account_config.py`  
**Personalized settings:** `docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md`  
**Full Smart Park (cash + optional gold):** `docs/features/PARK_SMART_IDLE_CASH.md` · package spec · checklist · `config/park_package.json` · `phase6/core/park_package.py`

**2026-08-07 honesty:** Primary account still has USDC park **off**. Package coordinator W0 is status-only by default. Don’t claim “Smart Park fully on” until the checklist go-live.

---

## 1. What each mode does

| Mode | Toggle | Regime signal | Daily rebalance behavior |
|------|--------|---------------|---------------------------|
| **Stand-down only** | `enabled: false` | park (`usdc_park`) | `rebalance_cap_usd=0` — no new buys, **no** forced sells |
| **Live park** | `enabled: true` | park | SELL alts → BUY `USDC-USD` to ~`target_usdc_pct` |
| **Redeploy** | `enabled: true` | deploy (e.g. bull, cap &gt; 0) | SELL excess USDC → USD, then **same cycle** continues ARCH-4 / legacy deploy |
| **Armed** | `enabled: true` | neither park nor deploy edge | Wait; normal rebalance if cap allows |

**Park signal:** `strategy_mode=usdc_park`, `scenario_id=usdc_hold`, or `risk_free_preference=USDC` with `rebalance_cap_usd=0`.

**Deploy signal:** not park signal and `rebalance_cap_usd > 0` (or non–`usdc_hold` scenario in analyst shadow).

---

## 2. Configuration

### File: `config/trader_accounts.json`

| Field | Default | Meaning |
|-------|---------|---------|
| `live_usdc_park.enabled` | **false** | Master opt-in per `portfolio_uuid` |
| `target_usdc_pct` | 0.92 | Target USDC share of NAV after park |
| `min_usd_reserve_usd` | 50 | USD left unconverted after park |
| `min_sell_usd` | 15 | Min alt position to market-sell |
| `skip_if_usdc_pct_above` | 0.88 | Skip park if already parked (little alts left) |
| `redeploy_target_usdc_pct` | 0.05 | USDC to keep after redeploy unwind |
| `redeploy_min_usd_for_deploy_usd` | 80 | Min USDC unwind size to bother trading |

### CLI

```bash
.venv/bin/python scripts/manage_trader_account.py show <portfolio_uuid>
.venv/bin/python scripts/manage_trader_account.py usdc-park <portfolio_uuid> on
.venv/bin/python scripts/manage_trader_account.py usdc-park <portfolio_uuid> off
.venv/bin/python scripts/manage_trader_account.py park-status <portfolio_uuid>
```

Env override for account id: `COINBASE_PORTFOLIO_UUID` / `PHASE6_ACCOUNT_ID`.

---

## 3. Toggle transition process (runbook)

Operational phase is tracked in:

`data/state/usdc_park/<account>_transitions.json`

Each daily rebalance calls `plan_usdc_park_for_daily_rebalance()` before ARCH-4.

### A. Off → On (`off_to_on`)

**Operator:** `manage_trader_account.py usdc-park … on` (or set `enabled: true` in JSON, then run CLI once to record transition if you edited by hand).

| Step | System |
|------|--------|
| 1 | Phase → **`armed`**; `last_transition=off_to_on` |
| 2 | Next rebalance: if **park signal** → run **live park** (sells + USDC buy), phase → **`parked`** |
| 3 | If **no park signal** yet → no liquidation; wait until flat/bear/recent overlay applies park |

**You do not need to restart the runner** — config reloads each cycle.

### B. On → Off (`on_to_off`)

**Operator:** `usdc-park … off`.

| Step | System |
|------|--------|
| 1 | Phase → **`standdown_only`**; live park **disabled** |
| 2 | **No automatic USDC → USD** on off (capital stays where it is) |
| 3 | Rebalance follows **regime knobs only** (e.g. still cap 0 in flat → stand-down, no new deploy) |

Use this when you want research stand-down without forced liquidation, or you will manually manage USDC.

### C. On + Park → Market redeploy (`park_to_redeploy`)

**Trigger:** Toggle still **on**, regime flips from park to deploy (e.g. flat → bull): `last_park_signal` was true, now deploy signal and not park.

| Step | System |
|------|--------|
| 1 | Phase → **`redeploy_unwind`** |
| 2 | Market **SELL** `USDC-USD` for excess above `redeploy_target_usdc_pct` (min size `redeploy_min_usd_for_deploy_usd`) |
| 3 | Decision logged as `usdc_park_redeploy_unwind` |
| 4 | **Same daily rebalance** continues into normal ARCH-4 / legacy path (deploy alts per regime winner) |
| 5 | Phase → **`armed`** after successful unwind |

**Orderly re-deploy:** unwind first, then deploy in one rebalance day — not a silent one-shot flip.

---

## 4. Execution details (live park)

1. CR-03 suspend protective orders  
2. Market SELL each basket alt above `min_sell_usd`  
3. Market BUY `USDC-USD` with USD above `min_usd_reserve_usd`  
4. Live SELL failure → abort (no convert)  
5. Snapshot: `data/state/usdc_park/<account>_latest.json`

---

## 5. Observability

| Artifact | Contents |
|----------|----------|
| `*_transitions.json` | Phase, `last_transition`, regime, park/deploy flags |
| `*_latest.json` | Last park or unwind run |
| Decision context | `path=usdc_park` or `usdc_park_redeploy_unwind` |

Logs: `[USDC-PARK]` prefix.

---

## 6. Safety & testing

- Default **toggle off** for all accounts.  
- Isolation: `phase6/core/test_isolation_usdc_park_live.py`  
- Multi-trader: one `accounts` entry per `portfolio_uuid`, independent toggles and state files.

---

## 7. Related files

```
config/trader_accounts.json
config/regime_knob_map.json
config/risk_free_benchmark.json
phase6/core/rebalance_coordinator.py   # orchestration hook
scripts/manage_trader_account.py
```