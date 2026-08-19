# Feature Spec — Trader personalized settings (capital hold + park)

**ID:** `FEAT-TRADER-PERSONALIZED-SETTINGS-2026-08`  
**Status:** PARTIAL LIVE — **W1+W2 shipped** (2026-08-08) · W3 UI banner PLANNED  
**Date:** 2026-08-07  
**Audience:** Product + platform (SaaS trader accounts)  
**Related live docs:** `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md`, `docs/LIVE_USDC_PARK.md`, `config/trader_accounts.json`  
**Related code:** `phase6/core/capital_controls.py`, `phase6/core/trader_account_config.py`, `phase6/core/runner_capital_events.py`

---

## 1. Plain English

Each trader account needs a small set of **personal capital preferences** that are **not** strategy alpha. They answer:

- “I sold by hand — leave that cash alone until I say otherwise.”
- “Block the bot from buying back what I just sold for a while.”
- “When the bot pauses crypto buying, do I want simple cash, cash that can earn a little, and/or a tiny optional gold sleeve?” (see **Smart Park**)

Today Brad’s single book uses **global runner state** for cash hold + cooldown, and **per-portfolio** JSON for live USDC park. Multi-tenant must make these **first-class personalized settings** per `portfolio_uuid` / TradingAccount — visible, defaulted, and reversible without SSH.

---

## 2. Scope

### In scope (this feature)

| Setting cluster | Purpose |
|-----------------|---------|
| **Manual cash hold** | Do not auto-deploy proceeds (or a dollar amount) from operator/manual liquidations |
| **Rebuy cooldown** | Temporary block of BUY on pairs the trader sold manually (or via exchange SL, if configured) |
| **Auto-hold policy toggles** | Whether *new* manual sells auto-add hold / auto-start cooldown (today: `global_settings` keys) |
| **Smart Park prefs** | How idle money behaves when crypto is paused: simple cash, cash+yield (USDC), optional tiny gold — see `PARK_SMART_IDLE_CASH.md` |
| **Live USDC park** | Opt-in: parked money prefers USDC (may earn exchange yield) — part of Smart Park “cash + yield” |
| **Gold sleeve prefs** | Opt-in interest in a small gold (PAXG) sleeve — *preferences only*; turning gold on stays a clear confirm |

### Out of scope

- Changing REGIME-CASH winners or OPT params from settings UI  
- Personalized “advice” or discretionary stock picks  
- Auto-arm full 20% PAXG  
- Custody / withdrawing for the user  

---

## 3. Manual cash hold — product definition

### What it is

A **dollar reserve** the allocator must treat as non-deployable:

```
deployable_cash ≈ max(0, exchange_cash_usd − manual_liquidation_cash_hold_usd − min_reserve)
```

It does **not** move funds on the exchange. It only shrinks what ARCH-4 / rotation may spend.

### When it should turn ON (defaults)

| Trigger | Default | Rationale |
|---------|---------|-----------|
| Trader **manual** sell of crypto → USD/USDC (bot detects `manual_liquidation_to_cash`) | **ON** — add sold notional to hold | Operator intent: “I reduced risk; don’t buy it back immediately with the same dollars.” |
| Exchange **stop-loss fill** | Config: `capital_event_stop_loss_exchange_hold_cash` (live book may be true/false — **per-account override in SaaS**) | SL already expressed risk cut; some traders want hold, some want recycle into better names |
| Deposit | **OFF** for hold (separate: optional force rebalance) | New capital is not “manual sell proceeds” |
| Withdrawal | Reduce hold by min(hold, withdrawn) when implemented | Don’t pretend parked cash still exists after user withdrew |

**Pair rebuy cooldown** is orthogonal: even after hold is released, a pair can stay blocked for N hours.

### When it should turn OFF

| Action | Who | Effect |
|--------|-----|--------|
| **Release cash hold** | Trader (UI) or operator (flag/CLI) | `manual_liquidation_cash_hold_usd → 0`; next rebalance may deploy under regime caps |
| Withdrawal that exhausts held cash | System | Partial/full clear (see CAPITAL events) |
| Account close / full flatten policy | Ops | Clear all controls |

**Important product rule:** Hold is **sticky until explicit release**. It does **not** expire with the rebuy cooldown clock. (2026-08-07 incident: Aug 4 LINK manual sell left **$627.86** hold while pair cooldown had already emptied — dry powder looked idle but was correctly locked.)

### How traders should use it

| Situation | Recommended |
|-----------|-------------|
| You panic-sold or de-risked by hand and want the bot to **wait** | Leave hold ON; optionally keep pair cooldown |
| You’re ready for the bot to **use that cash again** under normal gates | **Release cash hold** (this control). Do not expect midnight auto-clear. |
| You only wanted “don’t buy LINK back for 48h” but cash can go to UNI/SOL | Clear hold if still set; keep **pair** cooldown on LINK only |
| Flat/bear park, you want yield not alts | Hold is wrong tool — use **USDC park** / Preserve prefs, not permanent cash hold |

### UI (personalized settings)

**Surface:** Account → Settings → Capital controls (or Portfolio → “Cash on hold” banner)

| Control | Type | Copy (plain) |
|---------|------|--------------|
| Cash on hold | Read-only $ + timestamp of last add | “Cash the bot will not auto-spend until you release it.” |
| Release cash hold | Primary button when $ > 0 | “Allow bot to deploy this cash again (still follows market regime rules).” |
| Hold cash after my manual sells | Toggle (default ON) | Maps to `capital_event_manual_sell_hold_cash` per account |
| Hold cash after stop-loss fills | Toggle (default OFF unless product decides otherwise) | Maps to `capital_event_stop_loss_exchange_hold_cash` |
| Rebuy block after manual sell | Hours (0–168, default 48) | `capital_event_manual_sell_block_rebuy_hours` |
| Clear rebuy blocks | Button / per-pair | Existing `clear_manual_sell_cooldown` |

**API / backend (today → multi-tenant):**

| Today (single book) | Multi-tenant target |
|---------------------|---------------------|
| `data/state/phase6_runner_state.json` → `manual_liquidation_cash_hold_usd` | Per-account row / state file keyed by `portfolio_uuid` |
| `touch clear_manual_cash_hold.flag` | `POST /accounts/{id}/capital/clear_cash_hold` (authz) |
| `capital_user_controls.json` UI read model | Same schema, per account |
| `global_settings` in `trading_config_phase6.json` | Defaults in `trader_accounts.json` + account overrides |

### Config shape (planned in `config/trader_accounts.json`)

```json
"capital_controls": {
  "manual_sell_hold_cash": true,
  "manual_sell_block_rebuy_hours": 48,
  "stop_loss_exchange_hold_cash": false,
  "stop_loss_exchange_block_rebuy_hours": 24,
  "ui_show_hold_banner": true
}
```

Runtime **amount** held stays in **state**, not config (state = current lock; config = policy for future events).

### Acceptance criteria

1. Manual sell with policy ON increases hold by ≈ sold USD; allocator deploy cash drops by that amount.  
2. Release control zeroes hold; audit log entry with `cleared_usd` + actor.  
3. Hold does not expire solely because rebuy cooldown expired.  
4. Multi-tenant: account A hold never reduces account B deployable cash.  
5. Dashboard never shows “idle cash ready to deploy” without subtracting hold (KPI honesty).

---

## 4. Related personalized settings (same settings surface)

### 4.1 Smart Park — cash + optional yield (USDC)

**Trader story:** `docs/features/PARK_SMART_IDLE_CASH.md`  
**Toggle today:** `live_usdc_park` in `trader_accounts.json` (see `docs/LIVE_USDC_PARK.md`).

- **Offer as:** “While crypto is paused, keep most money in **calm cash**. Optionally use **USDC** so idle funds can earn whatever yield the exchange currently pays.”  
- **Use when:** Trader wants parked capital to work a little, not sit only as plain USD.  
- **Not when:** They want the simplest USD buffer only, or don’t want convert/unwind friction.  
- **Copy rule:** Never promise a fixed APY (no “guaranteed 3.5%”).

### 4.2 Smart Park — optional gold sleeve (preference only)

| Pref | Trader meaning |
|------|----------------|
| Interested in gold sleeve | Show education + allow “turn on tiny gold” controls |
| Start tiny (micro) | Prefer a small learning size before any larger gold |
| Don’t mix big crypto + gold | Default: park crypto risk first, then consider gold |

**Turning gold on stays a clear confirm** (button/CLI). Settings never silently create a large gold position.

**Product home:** Smart Park package — `PARK_SMART_IDLE_CASH.md` + `PARK_USDC_PAXG_PACKAGE_SPEC.md` (W0 shipped; live enable optional).

---

## 5. Smart Park product status (cash + optional gold)

**Trader pitch:** When it’s not time to buy more crypto, **Smart Park** structures idle money as calm cash (optional yield) plus optional tiny gold — with a plan to return. See `PARK_SMART_IDLE_CASH.md`.

**Live today (Brad book, 2026-08-07):**

| Layer | Status |
|-------|--------|
| Pause / limit new crypto risk (platform rules) | **Live** |
| Manual “leave my cash alone” hold | **Live** |
| USDC “cash + yield” path | **Built; off** on primary until you opt in |
| Tiny gold sleeve + exchange safety stop | **Available** (learning size; not the whole story alone) |
| Full **Smart Park** as one onboarding choice | **Product path W0 shipped** · **not** default-on for all accounts |

**What “fully on” means for a trader:**

1. Crypto pause rules apply.  
2. Most idle money in **cash parking lot**; USDC on if they chose yield.  
3. Optional **tiny gold** only after they confirm.  
4. Larger gold only if they later choose scale-up.  
5. When crypto is allowed again: orderly return — don’t blindly fling gold into random coins.

**Canonical:** `PARK_SMART_IDLE_CASH.md`, package spec, `PARK_BALLAST_DECISION_MATRIX.md`, `LIVE_USDC_PARK.md`.

---

## 6. Implementation waves (suggested)

| Wave | Deliverable |
|------|-------------|
| **W0** | Operator clear hold / cooldown (done); single-book honesty on dash |
| **W1** | **SHIPPED 2026-08-08** — Per-account `capital_controls` in `trader_accounts.json` + wire read path (`capital_controls_settings` → `_runner_capital_settings` overlay; status v2 policy field). Isolation: `test_isolation_capital_controls_policy.py` |
| **W2** | **SHIPPED 2026-08-08** — Per-account hold/cooldown **state** store `data/state/capital_controls/{account_id}/`; API `GET/POST /api/capital/*`; CLI `--account-id`; no cross-account bleed. Isolation: `test_isolation_capital_controls_state.py` |
| **W3** | Banner + release on portfolio home; audit in trader activity feed |
| **W4** | Park package: USDC park ON defaults research + Preserve pref linkage + one onboarding checklist |

---

## 7. Operator runbook (single book, now)

```bash
# Status
.venv/bin/python -m phase6.scripts.capital_controls status

# Release cash hold (live runner consumes flag next cycle; or process via core API)
touch data/state/clear_manual_cash_hold.flag
# or immediate state edit path:
# PYTHONPATH=. .venv/bin/python -c "from phase6.core.capital_controls import *"
```

**2026-08-07 action:** Cleared hold **$627.86** (source Aug 4 manual LINK liquidation) per operator request. State `manual_liquidation_cash_hold_usd=0.0`.

---

## 8. Non-goals / compliance

- Settings copy must not promise returns, fixed USDC APY, or “safe gold.”  
- Release hold ≠ guarantee buys — REGIME-CASH / flat $75 caps / RSI·sentiment gates still apply.  

---

*Last updated: 2026-08-07*
