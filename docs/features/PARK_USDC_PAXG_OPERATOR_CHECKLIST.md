# Smart Park — turn-on checklist (operators)

**Trader name:** **Smart Park** (idle cash that still works for you)  
**Friendly story:** `docs/features/PARK_SMART_IDLE_CASH.md`  
**FEAT:** `FEAT-PARK-USDC-PAXG-PACKAGE-2026-08`  
**Spec (technical):** `docs/features/PARK_USDC_PAXG_PACKAGE_SPEC.md`  
**Doctrine:** `docs/research/PARK_BALLAST_DECISION_MATRIX.md`  

**In one breath for a new trader:**  
When crypto isn’t a good buy, we park most money in **calm cash** (optional USDC yield) and only add **tiny gold** if you ask — then we have a plan to come back. We don’t hype fake APYs or call gold “safe.”

**Default live book today:** Smart Park **not fully enabled** · USDC park **OFF** · a small gold sleeve may already exist from earlier learning — that alone is **not** “Smart Park fully on.”

---

## 0. Before you touch anything

- [ ] Read matrix one-pager (A/B/C stack).  
- [ ] Confirm you will **not** promise fixed USDC APY in any user-facing copy.  
- [ ] Confirm DeRisk stays **OFF**.  
- [ ] Note manual cash hold: package does not clear it (`capital_controls`).  
- [ ] Runner may need restart only for `preserve_mode` flips in `trading_config_phase6.json` (USDC park hot-reloads).

---

## 1. Choose how parked money should behave (trader language)

| What the trader wants | Internal profile | Notes |
|----------------------|------------------|-------|
| **Simple pause** — crypto risk off, ordinary cash | `off` | Default; easiest |
| **Cash + yield** — prefer USDC while parked | `a_only` | Turn on USDC park separately |
| **Cash + yield + tiny gold** | `a_plus_b_micro` | Full Smart Park intent; gold still **manual arm** |
| **Larger gold allowed later** | `a_plus_b_full_eligible` | Still no auto 20% |

Set in `config/park_package.json` and/or per-account `park_package` in `trader_accounts.json`.  
`park_package.enabled=true` only turns on **coordination/status** (and future auto-align of the USDC toggle) — **never** auto gold.

---

## 2. Enable path — `a_only`

1. [ ] Set profile `a_only` (package enabled optional for status).  
2. [ ] `manage_trader_account.py usdc-park <uuid> on`  
3. [ ] Wait for **park signal** (flat/bear/usdc_park mode) → executor sells alts → buys USDC.  
4. [ ] Verify `data/state/usdc_park/<acct>_latest.json` and transitions phase `parked`.  
5. [ ] On deploy signal: confirm unwind then ARCH-4 in same rebalance day.  
6. [ ] To stop live USDC: `usdc-park … off` (does **not** auto-convert USDC→USD).

**Do not** arm PAXG “for fun” on a_only.

---

## 3. Enable path — `a_plus_b_micro` (full package intent)

### 3.1 Bucket A first
1. [ ] Profile `a_plus_b_micro`.  
2. [ ] Turn **USDC park ON** (same as §2).  
3. [ ] Prefer arming B only when **parked / low crypto util** (I1 in matrix).  

### 3.2 Bucket B (always explicit)
4. [ ] Venue OK (probe A already on book).  
5. [ ] `arm_preserve_hold.py status` — clean slate / understand current sleeve.  
6. [ ] Crypto parked enough; `allow_preserve_with_crypto_util` false → don’t dual-stack large C+B.  
7. [ ] **Arm MICRO only** (after `status` / dry-run):  
    `PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --dry-run`  
    then `… arm --i-understand` (micro via `preserve_mode.micro_live` / CLI — never full without explicit scale).  
8. [ ] Confirm E1 open / not NAKED (`preserve_e1_alert.json` absent).  
9. [ ] `park_package` status shows B armed micro; shadow may say `HOLD_B_IN_PARK`.  

### 3.3 Never on this path
- [ ] No auto 20%  
- [ ] No funding B by lifting C caps  
- [ ] No dust-sweep armed PAXG  

---

## 4. Scale micro → full 20% (optional, rare)

1. [ ] Micro clean ≥ your comfort (E1 healthy, sleeve logs OK).  
2. [ ] Accept book hit if gold −28% at 20% size.  
3. [ ] Explicit full arm CLI (not package auto).  
4. [ ] Profile may be `a_plus_b_full_eligible` (eligibility only).  
5. [ ] Record decision in MASTER or ops log.

---

## 5. Thaw / deploy (default)

1. [ ] Check shadow: `park_ballast_decision_latest.json` → often `TRIM_DEFAULT_TO_A`.  
2. [ ] **v1:** trim B manually / disarm if you want doctrine-true before big C deploy.  
3. [ ] USDC unwind happens if live USDC park on + deploy signal.  
4. [ ] C deploys under REGIME-CASH caps (e.g. flat $75) — package does not bypass.  
5. [ ] Keep-Hold: only if O-tests pass; shadow only unless you consciously hold micro gold.

---

## 6. Kill / fail paths

| Symptom | Action |
|---------|--------|
| E1 NAKED | Tick/repair or disarm immediately |
| USDC park sell fail | Executor aborts convert — check balances, fix, retry |
| Want out of gold | `arm_preserve_hold.py disarm` → cash to A |
| Want out of USDC path | `usdc-park off` + manual USDC manage |
| Package confusion | Set profile `off`, `enabled=false`, re-read status JSON |

---

## 7. Verify package coordinator

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python phase6/core/test_isolation_park_package.py
PYTHONPATH=. .venv/bin/python -c "
from phase6.core.park_package import evaluate_and_write_status
p = evaluate_and_write_status()
print('enabled', p.get('package_enabled'), 'profile', p.get('profile'))
print('warnings', p.get('consistency_warnings'))
for s in p.get('sequence') or []:
    print('-', s.get('id'), s.get('action'), s.get('auto'))
"
cat data/state/park_package_status.json | head -80
```

---

## 8. Go-live sign-off (primary book)

Do **not** tick until Brad OK:

- [ ] Profile chosen and written  
- [ ] `park_package.enabled` decision recorded  
- [ ] USDC on/off decision recorded  
- [ ] B arm/disarm decision recorded  
- [ ] Checklist §0–§3 complete  
- [ ] Isolation PASS  
- [ ] MASTER note under `FEAT-PARK-USDC-PAXG-PACKAGE-20260807`

---

*Checklist v1 — 2026-08-07*
