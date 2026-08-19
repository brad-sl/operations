# Capital, Deposits, and Manual Trades (User Guide)

Audience: operators and future dashboard users.  
Phase: **6 live runner** (`phase6_runner.py`).

This guide explains how the bot reacts when **you** move money or trade outside the bot, and how to **release** protections when your intent changes.

---

## Overview

| Event | What you did | Bot detects | Default behavior |
|-------|----------------|-------------|------------------|
| **Deposit** | USD/USDC in, holdings unchanged | `deposit` | Log + optional **force rebalance** to deploy |
| **Withdrawal** | Cash out, holdings unchanged | `withdrawal` | Log only; KPI-adjusted returns |
| **Manual sell → cash** | Sold crypto on exchange (e.g. OP → USD) | `manual_liquidation_to_cash` | **Cash hold** + **rebuy cooldown** on sold pairs |
| **Manual crypto swap** | Sold one coin, bought another | `manual_crypto_swap` | Log + cancel stops on sold leg; no fake deposit |

Manual sells are **not** counted as deposits (NAV stays roughly flat).

---

## Configuration (`trading_config_phase6.json` → `global_settings`)

```json
"capital_event_min_flow_usd": 50.0,
"capital_event_force_rebalance": true,
"capital_event_deposit_deploy_cap_usd": 0.0,
"capital_event_manual_sell_hold_cash": true,
"capital_event_manual_sell_block_rebuy_hours": 48,
"capital_event_stop_loss_exchange_hold_cash": false,
"capital_event_stop_loss_exchange_block_rebuy_hours": 24,
"capital_event_stop_loss_ledger_lookback_hours": 48,
"capital_event_manual_sell_cancel_stops": true
```

| Key | Meaning |
|-----|---------|
| `capital_event_force_rebalance` | On **deposit**, schedule rebalance same cycle |
| `capital_event_manual_sell_hold_cash` | Proceeds from **true manual** liquidation are **not** auto-deployed |
| `capital_event_manual_sell_block_rebuy_hours` | Block **BUY** back into pairs you sold manually (default **48h**) |
| `capital_event_stop_loss_exchange_hold_cash` | When **false** (default), exchange stop fills do **not** add to cash hold |
| `capital_event_stop_loss_exchange_block_rebuy_hours` | Rebuy block for pairs sold via **`stop_loss_exchange`** ledger (default **24h**) |
| `capital_event_stop_loss_ledger_lookback_hours` | How far back to match ledger SELL reasons to disposition pairs |
| `capital_event_manual_sell_cancel_stops` | Cancel exchange stop orders on manually sold pairs |

---

## Logs and state files

| File | Purpose |
|------|---------|
| `data/state/capital_events_runner.jsonl` | All runner capital + manual disposition events |
| `data/state/capital_external_flows.jsonl` | Deposits/withdrawals only (dashboard KPIs) |
| `data/state/capital_control_actions.jsonl` | User clear actions (audit) |
| `data/state/capital_user_controls.json` | **UI read model** — hold, cooldowns, `capital_controls_policy` (v2), available actions (primary mirror) |
| `data/state/capital_controls/{account_id}/state.json` | **Per-account state** — hold $ + rebuy cooldown map (W2 SSOT) |
| `data/state/phase6_runner_state.json` | Legacy mirror of hold/cooldown for primary book |
| `config/trader_accounts.json` → `capital_controls` | Per-account **policy** (hold after manual sell / SL, rebuy hours) — W1 |

---

## User controls (CLI today, UI tomorrow)

### Read status

```bash
cd /home/brad/projects/crypto-trading-bot
.venv/bin/python -m phase6.scripts.capital_controls status
# optional: --account-id <portfolio-uuid>
```

Dashboard:
- `GET /api/capital/controls?account_id=`
- `POST /api/capital/clear-cash-hold` body `{"account_id"?,"source"?}`
- `POST /api/capital/clear-cooldown` body `{"account_id"?,"all"?,"pairs"?}`

Poll `data/state/capital_user_controls.json` or per-account `data/state/capital_controls/{id}/capital_user_controls.json` — schema version **`2`**, fields: hold $, cooldowns, **`capital_controls_policy`**, `ui_actions` (enabled, labels, `api_path`).

### Release cash hold (“I’m done parking cash — bot may deploy again”)

**Live runner (recommended):** flag consumed next cycle:

```bash
touch data/state/clear_manual_cash_hold.flag
```

**Immediate (offline edit of state):**

```bash
.venv/bin/python -m phase6.scripts.capital_controls clear-cash-hold
```

Or request flag via CLI:

```bash
.venv/bin/python -m phase6.scripts.capital_controls request-clear-cash-hold
```

### Clear manual-sell rebuy cooldown

**All pairs** (next runner cycle):

```bash
touch data/state/clear_manual_sell_cooldown.flag
```

**Specific pair(s):**

```bash
echo '{"pairs": ["OP-USD"]}' > data/state/clear_manual_sell_cooldown.json
```

**Immediate CLI:**

```bash
.venv/bin/python -m phase6.scripts.capital_controls clear-cooldown --all
.venv/bin/python -m phase6.scripts.capital_controls clear-cooldown --pair OP-USD
```

Flag/JSON files are **removed** when consumed (same pattern as `force_rebalance.flag`).

---

## Future UI mapping

| UI control | Backend |
|------------|---------|
| “Cash on hold: $X — Release” | `POST clear_manual_cash_hold` or touch `clear_manual_cash_hold.flag` |
| “Rebuy blocked: OP-USD until …” | Show `manual_sell_cooldown_active` from `capital_user_controls.json` |
| “Allow bot to buy OP again” | `clear_manual_sell_cooldown` with `pairs: ["OP-USD"]` |
| Deposit landed | Read `capital_events_runner.jsonl`; optional “Deploy now” → `force_rebalance.flag` |

**Product / multi-tenant:** Cash hold + cooldown + auto-hold *policy* are personalized account settings — when to arm hold, when traders should release, and per-account toggles. Canonical feature spec:

→ `docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md` (`FEAT-TRADER-PERSONALIZED-SETTINGS-2026-08`)

### Sticky hold vs cooldown (operator note)

| Control | Expires automatically? | Clears how |
|---------|------------------------|------------|
| **Cash hold ($)** | **No** — sticky until release (or withdrawal reduction) | Release button / flag / CLI |
| **Pair rebuy cooldown** | **Yes** — after configured hours | Time expiry or clear-cooldown |

Idle-looking USD with a non-zero hold is **expected**, not a stuck rebalance.

---

## Related operator actions

| Goal | Action |
|------|--------|
| Deploy idle cash after upgrade | `touch data/state/force_rebalance.flag` |
| Force full rebalance | `touch data/state/force_rebalance.flag` |
| Release manual cash hold | `touch data/state/clear_manual_cash_hold.flag` |

See also: `docs/Trading_Bot_FAQ.md` (FAQ section).

*Last updated: 2026-08-07*