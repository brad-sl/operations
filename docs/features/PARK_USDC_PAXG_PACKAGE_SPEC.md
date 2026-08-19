# Feature Spec — Park package (USDC carry + PAXG Hold)

**ID:** `FEAT-PARK-USDC-PAXG-PACKAGE-2026-08`  
**MASTER:** `FEAT-PARK-USDC-PAXG-PACKAGE-20260807`  
**Trader-facing name:** **Smart Park** → [`PARK_SMART_IDLE_CASH.md`](./PARK_SMART_IDLE_CASH.md)  
**Status:** SPEC + COORDINATOR SHIPPED · **LIVE PACKAGE OFF** (default)  
**Date:** 2026-08-07  
**Domain:** park / capital  
**Related:**  
- **Product voice (novice traders):** `docs/features/PARK_SMART_IDLE_CASH.md`  
- Doctrine: `docs/research/PARK_BALLAST_DECISION_MATRIX.md`, `PARK_REGIME_POLICY.md`  
- Layers: `docs/LIVE_USDC_PARK.md`, `docs/research/PRESERVE_HOLD_MVP_SPEC.md`  
- Prefs: `docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md`  
- Code: `phase6/core/park_package.py`, `config/park_package.json`  
- Checklist: `docs/features/PARK_USDC_PAXG_OPERATOR_CHECKLIST.md`

---

## 0. Plain English (start here)

### Differentiator (use this in product)

**Smart Park:** when it’s not time to buy more crypto, we don’t leave you stuck in endless trading *or* in clueless idle cash. Most money goes to a **calm cash parking lot** (dollars or USDC that can earn the exchange’s current yield when you opt in). You may add a **small optional gold sleeve**. Crypto risk comes back only under clear rules. **You stay in control** — gold never auto-scales to a huge size.

Full novice story, feature→benefit table, and competitive contrast:  
→ **`docs/features/PARK_SMART_IDLE_CASH.md`**

### Operator one-liner

Park is a **stack**, not one mystery toggle:

| Bucket | Asset | Role (friendly) |
|--------|--------|-----------------|
| **A** | **USDC** (preferred) or USD | Parking lot + optional yield |
| **B** | **PAXG** + deep exchange stop | Optional gold ballast — **not** “safe” |
| **C** | Crypto basket | Active risk only when gates open |

**Recite:** Cash parks. Gold is optional. Crypto waits its turn.

Until this package, A (USDC tools) and B (Preserve gold) were **separate**. This FEAT is **one coordinated product**: profiles, arm order, unwind order, cash rules, honest APY copy, and a planner that does **not** silently turn on live risk.

### Name map (UI ↔ internal)

| Trader sees | Internal profile |
|-------------|------------------|
| Simple pause (cash) | `off` |
| Cash + yield (USDC) | `a_only` |
| Cash + yield + tiny gold | `a_plus_b_micro` |
| Larger gold eligible (advanced) | `a_plus_b_full_eligible` |

---

## 1. Goals / non-goals

### Goals
1. Single **profile** language: `off` | `a_only` | `a_plus_b_micro` | `a_plus_b_full_eligible`.  
2. **Ordered** park and thaw sequences (A before B on enter; B→A before C on default deploy).  
3. Config object `park_package` that **coordinates** existing `live_usdc_park` + `preserve_mode` (does not replace them).  
4. Operator checklist + isolation tests.  
5. Safe defaults: **master package off**; primary USDC park stays off until Brad opts in.

### Non-goals
- Auto-arm PAXG or auto scale to 20%.  
- DeRisk ladder (forbidden).  
- Hard-coding **3.5% APY** (or any APY) in UI without a **live venue quote**.  
- Turning on live USDC park or full Hold as part of this ship.  
- Auto trim-on-deploy of B (still shadow doctrine until separate enable).  
- Multi-tenant SaaS settings UI (see personalized-settings FEAT).

---

## 2. Profiles

| Profile | A (USDC/USD) | B (PAXG) | Intended user |
|---------|--------------|----------|----------------|
| `off` | REGIME-CASH only (often **USD** cash, no live USDC convert) | None / existing sleeve unmanaged by package | Default book |
| `a_only` | Live USDC park **eligible** when regime parks | B not part of package (disarm or leave untouched — see policy) | Yield-oriented park, no gold |
| `a_plus_b_micro` | USDC park eligible | MICRO ~$75 Hold + E1 **after** A parked and operator arm | Learning / doctrine stack |
| `a_plus_b_full_eligible` | USDC park eligible | MICRO allowed; **full 20%** only via separate explicit arm (package only marks *eligible*) | Power users after micro gate |

**Package master switch:** `park_package.enabled`  
- `false` (default): coordinator **evaluates + logs** only; does **not** force USDC toggle or arm B.  
- `true`: coordinator may **recommend** and, only if `execution.allow_coordinate_toggles` is true, align USDC toggle with profile — **still never auto-arms B**.

---

## 3. Config shape

### 3.1 File: `config/park_package.json` (book-level defaults)

```json
{
  "schema_version": 1,
  "enabled": false,
  "profile": "off",
  "research_usdc_apy_note": "Research class ~3.5% historically — NOT a live quote; UI must fetch venue rate or omit %",
  "buckets": {
    "A": {
      "prefer_asset": "USDC",
      "fallback_asset": "USD",
      "use_live_usdc_park_executor": true,
      "target_usdc_pct": 0.92,
      "min_usd_reserve_usd": 50.0
    },
    "B": {
      "asset": "PAXG-USD",
      "micro_usd": 75.0,
      "full_target_pct": 0.20,
      "e1_dd_pct": -0.32,
      "soft_no_add_dd_pct": -0.12,
      "derisk_enabled": false,
      "require_explicit_arm": true,
      "require_crypto_parked_before_arm": true,
      "allow_preserve_with_crypto_util": false
    },
    "C": {
      "controlled_by": "REGIME-CASH",
      "note": "Package never raises C caps to fund B"
    }
  },
  "sequences": {
    "enter_park": ["ensure_C_no_new_risk", "run_A_usdc_park_if_eligible", "offer_B_only_if_profile_and_operator"],
    "default_deploy_thaw": ["shadow_or_manual_trim_B_to_A", "run_A_usdc_redeploy_unwind", "C_arch4_deploy"],
    "gold_crisis_e1": ["B_flat_by_e1", "stay_A", "no_revenge_C"]
  },
  "execution": {
    "allow_coordinate_toggles": false,
    "auto_arm_b": false,
    "auto_trim_b_on_deploy": false,
    "write_status_each_cycle": true
  },
  "status_path": "data/state/park_package_status.json"
}
```

### 3.2 Per-account overlay: `config/trader_accounts.json`

```json
"park_package": {
  "enabled": false,
  "profile": "off"
}
```

Merge: account overrides book defaults (same deep-merge as `live_usdc_park`).

### 3.3 Existing knobs (still authoritative for execution)

| Layer | Config |
|-------|--------|
| A executor | `trader_accounts.json` → `live_usdc_park.*` |
| B sleeve | `trading_config_phase6.json` → `preserve_mode.*` |
| C gates | `regime_cash_policy.json` / knob map |

Package **must not** invent a second USDC seller or second PAXG buyer path.

---

## 4. Sequences (normative)

### 4.1 Enter park (risk-off)

```
1. C: REGIME-CASH already blocks / caps new risk (package does not sell C itself unless A executor park path does for live USDC)
2. A: If profile ∈ {a_only, a_plus_b_*} and live_usdc_park.enabled:
      plan_usdc_park_for_daily_rebalance → park to target_usdc_pct
   Else: A = USD (or existing cash) via stand-down only
3. B: If profile ∈ {a_plus_b_micro, a_plus_b_full_eligible}:
      Coordinator may OFFER_ARM_MICRO only when:
        - A parked or cash-dominant (util low / park signal)
        - venue probe OK
        - require_explicit_arm → operator runs arm_preserve_hold
      NEVER auto-arm
4. Double-spend check: cash reserved for B micro must remain in A until arm; arm funds B from A only
```

### 4.2 Default deploy / thaw

```
1. B: doctrine TRIM_DEFAULT_TO_A (shadow until auto_trim enabled) — do not spray gold into alts
2. A: USDC redeploy unwind (if live USDC park on) → USD for ARCH-4
3. C: normal allocator / regime caps
```

### 4.3 Keep-Hold corner

See matrix §4. Package status surfaces shadow `KEEP_HOLD_*` from `park_ballast_shadow`; no auto override in v1.

### 4.4 E1 / naked B

```
Repair E1 or disarm → flat B → stay A → no panic C
```

---

## 5. Cash / double-spend rules

| Rule | Detail |
|------|--------|
| R1 | B funded **only** from A (USD/USDC), never by raising C util caps |
| R2 | MICRO notional ≤ `micro_usd` (default 75) unless full arm |
| R3 | Full B % base = cash_plus_preserve_mtm only (exclude C) |
| R4 | If `allow_preserve_with_crypto_util=false`, refuse arm while crypto util high |
| R5 | Package plan lists `cash_for_a_usd` / `cash_earmarked_b_usd` so A target leaves room for earmarked B when profile includes B and operator intends arm |
| R6 | Manual cash hold (capital_controls) still reduces deployable C; package does not clear holds |

---

## 6. Coordinator API (`phase6/core/park_package.py`)

| Function | Role |
|----------|------|
| `load_park_package_config(account_id=None)` | Merge book + account |
| `evaluate_park_package(runner|context)` | Pure plan: profile, gaps vs live toggles, ordered steps, double-spend OK? |
| `write_park_package_status(plan)` | `data/state/park_package_status.json` |
| `maybe_park_package_cycle(runner)` | Evaluate + write status; optional toggle coordinate if flags allow; **never** arm B |

### Plan fields (minimum)

- `package_enabled`, `profile`  
- `bucket_a`: usdc_toggle, park_signal, recommended_a_action  
- `bucket_b`: preserve armed/micro, shadow recommendation, arm_allowed_bool  
- `bucket_c`: regime, deploy_open, util  
- `sequence`: list of step dicts `{id, action, auto, blocked_reason}`  
- `consistency_warnings`: e.g. profile wants A but USDC toggle off  
- `orders`: always false unless a future exec mode is explicitly added  

---

## 7. Observability

| Artifact | Purpose |
|----------|---------|
| `data/state/park_package_status.json` | Latest package plan |
| `data/state/usdc_park/*` | A executor |
| `data/state/preserve_hold_*.json` | B sleeve |
| `data/state/park_ballast_decision_latest.json` | B shadow matrix |
| Decision log path | `path=park_package` when logging |

---

## 8. Copy / compliance

- UI and Dose: **never** “earn 3.5% APY” as a guarantee.  
- Allowed: “USDC may earn yield at the venue’s current rate” + optional live quote field later.  
- Gold: never “safe haven” / “crash proof.”

---

## 9. Implementation waves

| Wave | Deliverable | Status (2026-08-07) |
|------|-------------|---------------------|
| **W0** | Spec + checklist + config + evaluate/status coordinator + isolation | **THIS SHIP** |
| **W1** | Runner hook: `maybe_park_package_cycle` each cycle (status only) | W0 includes optional hook |
| **W2** | `allow_coordinate_toggles`: profile→USDC on/off with audit (still no auto B) | Later |
| **W3** | Auto trim B on deploy (gated) | Later + Brad OK |
| **W4** | Personalized settings surface for profile | With settings FEAT |
| **W5** | Live enable primary `a_plus_b_micro` | Brad OK only |

---

## 10. Acceptance (W0)

1. Spec + checklist in `docs/features/`.  
2. `config/park_package.json` exists, `enabled=false`, `profile=off`.  
3. Isolation tests PASS for profiles, sequence order, double-spend earmark, no auto-arm.  
4. Primary `live_usdc_park.enabled` remains false unless Brad changes it.  
5. MASTER task updated; SPECS_INDEX / gap doc linked.  
6. Skill gap note points at this FEAT as the package home.

---

## 11. Operator quick path

See **`docs/features/PARK_USDC_PAXG_OPERATOR_CHECKLIST.md`**.

```bash
# Status (package plan only)
PYTHONPATH=. .venv/bin/python -c "from phase6.core.park_package import evaluate_and_write_status; import json; print(json.dumps(evaluate_and_write_status(), indent=2)[:2000])"

# A layer
.venv/bin/python scripts/manage_trader_account.py park-status <uuid>

# B layer
.venv/bin/python scripts/phase6/arm_preserve_hold.py status
```

---

*FEAT filed and W0 built 2026-08-07.*
