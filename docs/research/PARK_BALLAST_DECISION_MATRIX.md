# Park / Ballast — One-Page Decision Matrix

**Status:** OPERATOR DOCTRINE (canonical cheat sheet)  
**Date:** 2026-08-04 · **Posture note:** 2026-08-07  
**Live posture today:** Calm cash (USD primary; USDC yield opt-in off) · optional tiny gold if armed · crypto only under gates — **Smart Park** voice: `docs/features/PARK_SMART_IDLE_CASH.md`  
**Full 20% gold:** manual scale only · **Gold crash ladder:** OFF  
**Package FEAT:** technical + coordinator W0; **live package off**. Never hard-code unquoted USDC APY in UI.

---

## 0. Stack (do not reverse)

| Bucket | Asset | Role | Default |
|--------|--------|------|---------|
| **A** | **USDC / USD** | Primary defense + dry powder | **On whenever parked** |
| **B** | **PAXG** (Hold + deep E1 ≈ −32% arm) | Optional real-value ballast | Off or micro until you scale |
| **C** | Basket (BTC/ETH/alts) | Offense / regime deploy | Only when REGIME + re-entry gates allow |

**Recite:** Cash is the park. Gold is optional ballast (not safe). Crypto is gated. Gold is never the timer.

```
Park / risk-off     →  A full, B optional, C no new risk
Preserve            →  A + B (static hold), C still gated
Thaw / deploy       →  C may open; B → default trim to cash UNLESS Keep-Hold (corner)
Gold crisis         →  E1 may sell B; stay in A; do not revenge-buy alts
```

---

## 1. Initiate B (arm ballast)

| # | Condition | Required? |
|---|-----------|-----------|
| I1 | Crypto **parked** (bear/transition / no new buys / util already low — not mid bag average-down) | **Yes** |
| I2 | Venue OK: PAXG tradeable, E1 path known (probe **A**), min notional OK | **Yes** |
| I3 | Operator intent (arm command / explicit OK) — **no silent arm** | **Yes** |
| I4 | Prefer B **from idle A cash only** — never fund B by raising C caps | **Yes** |
| I5 | Optional research AND (not required for static ballast): bear/transition ≥14d, BTC 30d ≤ −10%, deep 12m hole | Nice-to-have for *large* B |

| Decision | Action |
|----------|--------|
| Any of I1–I4 fail | **Do not arm** — stay **A only** |
| I1–I4 pass, first live | **Arm MICRO** (~$75 Hold + E1) |
| Micro clean + you accept gold path DD | **Arm FULL** target **20%** of *(A cash + B MTM)* only |
| Bored of cash / want “something to do” | **Still A only** — boredom ≠ initiate |

**Data:** Static **20% PAXG / 80% cash** beat pure cash on ~18m and beat most timed BTC→gold theater. Timed entry is **optional**, not the v1 gate.

---

## 2. Size · scale · de-scale B

| Step | B size | When | Auto? |
|------|--------|------|-------|
| **S0** | 0% | Default / disarm / venue fail | Default |
| **S1 MICRO** | ~$75 (or ≤1–2% book) | First arm; ops + E1 learning | Manual |
| **S2 FULL** | **20%** of preserve base (cash+gold) | After micro gate* + explicit full arm | Manual |
| **S3 OVERSIZE** | >20% up to **30% hard cap** | Separate decision only — not default | Manual + written OK |
| **No-add latch** | Hold qty; **no top-ups** | B ≤ **−12%** from arm VWAP | Intent / config |
| **E1** | Sell residual B | Price ≤ arm × (1 − 0.32) on exchange | Exchange resting |
| **DeRisk ladder** | staged −12/−18/flat | — | **FORBIDDEN** |

\*Micro → full gate: E1 observed healthy · clean sleeve logs · you accept ~mid-single-digit book hit if gold −28% at 20% size · **not** automatic after N days alone.

| Scale **up** | Only S1→S2 (or rare S3) with eyes open; from **A**, never from forced C sells |
| Scale **down** | See §3 (deploy / thaw / fail) and §4 (Keep-Hold) |
| Never | Buy more B because crypto MTM crashed (equity illusion) · treat B like 3% crypto SL pair |

**Preserve equity base for %:** `USD/USDC available to bot + PAXG MTM only` — **exclude** C inventory.

---

## 3. Close / trim B → deploy C (default path)

**Default doctrine:** when C turns on for real, **trim B → A first**, then size C on **existing** crypto gates. Do **not** rotate gold proceeds straight into alts.

| Trigger (any one) | B action | Then C |
|-------------------|----------|--------|
| **D1** Layered re-entry / bull deploy / size-up path **ON** | **TRIM_DEFAULT** → target **0%** B (`on_deploy_target_pct=0`) unless §4 Keep-Hold | Deploy per REGIME-CASH |
| **D2** BTC 30d ≥ **+10%** (early thaw probe) | **REDUCE** B (e.g. half toward A) if oversized; full trim still OK | C still gate-bound |
| **D3** Operator **disarm** | **FLAT B** → A | Unchanged |
| **D4** Venue / E1 failure / naked B | **FLAT B** → A; Preserve off | Park A only |
| **D5** E1 fill | B gone by design | Stay A; no panic C |
| **D6** Dual-stack risk too high (large B + large C) | Trim B to ≤ Keep floor or 0 | Cut C util if needed — reliability first |

**Order of operations on deploy trim:** cancel/replace protection as designed → sell B to target → cash in A → only then add C risk.

**Data:** Exit on **bull / serious thaw**, not on every flat_b flicker. Static hold still won simple comparisons; default trim-on-deploy is **risk-budget** discipline, not a claim that gold always underperforms risk-on.

---

## 4. Corner case — **Keep-Hold** (PAXG outperforming the basket)

**Odds:** slim in classic risk-on (beta usually leads). Still define it so we don’t **force-sell the only winner** out of habit.

### 4.1 What “outperforming” means (simple, checkable)

All of:

| # | Test (use ~30d, same window) |
|---|------------------------------|
| O1 | B **ret_vs_arm > 0** (sleeve actually green since arm) **or** PAXG 30d > 0 |
| O2 | PAXG 30d return **≥** BTC 30d return **+ 5 pp** (clear margin, not noise) |
| O3 | PAXG 30d return **≥** equal-weight **deploy basket** 30d **+ 5 pp** (pairs you actually trade) |
| O4 | C is allowed or opening (otherwise this section is irrelevant — stay in normal park hold) |

If O1–O3 fail → **no Keep-Hold** → §3 default trim.

### 4.2 Keep-Hold actions (not a new strategy)

| Mode | B target while C deploys | Rules |
|------|-------------------------|--------|
| **KEEP_MICRO** | Hold ≤ micro / ≤ **~2%** book | Default Keep-Hold if O1–O4 and you want zero drama |
| **KEEP_PARTIAL** | Hold up to **min(current B, 10%)** of preserve base | Only if O1–O4 and dual-stack OK |
| **KEEP_FULL** | Hold up to **20%** while C also on | **Rare;** needs explicit operator OK same day — dual beta + gold path risk |
| **RESUME_TRIM** | Back to **0%** | Any fail of O-tests on **weekly** review, or D3/D4/D5, or C drawdown needs powder |

**Hard rules while Keep-Hold is on:**

1. **Do not** raise C rebalance caps because gold is winning.  
2. **Do not** add to B on strength during deploy (no chase). Hold qty; E1 stays.  
3. **Do not** skip crypto SL / regime gates on C.  
4. **Fund C from A**, not by defaulting to “sell the winner first” *unless* you need cash and Keep-Hold is off.  
5. If **A cash < planned C entry**, either skip C size or **partially** trim B (liquidity beats purity).  
6. Label UI: **Preserve · KEEP** (not “risk-free”, not “outperform mode strategy”).  
7. **Review every 7d** or on each deploy size-up: re-test O1–O3; fail → RESUME_TRIM.  
8. DeRisk ladder still **OFF**. E1 still **on**.

### 4.3 Why this is allowed

- Matrix goal is **less loss + honest optionality**, not “always 0 gold in bull.”  
- Forcing flat B when gold is the **only** positive sleeve is optional self-harm.  
- Keep-Hold is a **cap + review** exception, not permission to run a gold trading book.

### 4.4 Why this stays rare

- Risk-on tapes usually make **C** the opportunity sleeve; large B+C is two risks.  
- Gold can still drop **−15% to −28%** path while you hold it.  
- Default remains **trim-on-deploy**; Keep-Hold is opt-in when the numbers clear O1–O3.

---

## 5. Situation cheat sheet

| Situation | A cash | B PAXG | C crypto |
|-----------|--------|--------|----------|
| Short park / blip | Full | Off | No new buys |
| Long park, no gold desire | Full | Off | No new buys |
| Long park, ballast on | Most | Micro → 20% Hold | No new buys |
| Thaw / deploy, gold **not** outperforming | Full after trim | **→ 0** | Gates on |
| Thaw / deploy, gold **is** outperforming (O1–O3) | Keep powder | **Keep-Hold** micro/partial | Gates on; don’t boost caps |
| Need cash for C entry | Priority | Trim as needed | Size to remaining A |
| E1 / venue fail | Full | Flat | Park |
| Bored | Full | Off | Off |

---

## 6. Live vs research vs not coded

| Item | State |
|------|--------|
| A USDC/USD park (REGIME-CASH) | **Live** |
| B Hold + E1 micro | **Live ~$75** |
| B static 20% | **Policy + data; arm manual** |
| Auto initiate / scale ladder | **Not coded** (by design) |
| Default trim B on deploy | **Doctrine / PRD; confirm wiring before relying** |
| Keep-Hold outperform exception | **This matrix only until coded + UI badge** |
| DeRisk | **OFF** |

---

## 7. One-screen recite

1. **Park = A.**  
2. **B optional, static Hold, size is the airbag, E1 deep only.**  
3. **Initiate** only when parked + venue OK + you say so; micro then 20%.  
4. **Deploy ⇒ trim B to cash** unless **Keep-Hold** (PAXG clearly beats BTC & basket ~30d by ≥5pp and sleeve not a loser).  
5. **Keep-Hold** = hold capped B, no adds, no extra C risk, weekly re-test, else flatten.  
6. **Never** DeRisk-ladder gold; **never** fund gold by loosening alt caps.

---

## Pointers

| Doc | Role |
|-----|------|
| This file | **Canonical decision matrix** |
| `PARK_REGIME_POLICY.md` | Onboarding short form |
| `PRESERVE_MODE_PRD.md` | Product / E1 / equity base |
| `USD_HOLD_VALUE_CONTINGENCY_POLICY.md` | Research triggers sketch |
| `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md` | Static 20/80 numbers |

**Config hooks (when implementing Keep-Hold):**  
`on_deploy_target_pct` default `0` · `on_deploy_keep_hold_enabled` · `keep_hold_max_pct` (0.02 or 0.10) · `keep_hold_outperform_margin_pp` (5) · `keep_hold_lookback_d` (30) · weekly revalidate.

---

## Implementation status (2026-08-04)

| Item | State |
|------|--------|
| Decision matrix doc | Canonical |
| E1 inspect + auto-repair + alert | **Live** (`maybe_preserve_hold_tick`) |
| Status/dash `e1_open` / NAKED badge | **Live** |
| Shadow `park_ballast_decision_latest.json` | **Live** (no orders) |
| Auto trim-on-deploy | Not wired |
| Keep-Hold auto | Shadow only |
| Full 20% scale | Manual only |

