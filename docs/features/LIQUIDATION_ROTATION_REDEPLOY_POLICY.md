# Liquidation → partial rotation redeploy (product policy)

**Status:** Canonical policy v1 — **2026-08-16**  
**Audience:** product, analyst, engineer, ops  
**Live default:** **OFF** (hold / disposition first). Shadow path defined; live partial needs Brad OK + evidence gates.  
**Related:** catch-the-wave intent (2026-06), flat option-B `$75` lab, capital disposition holds, FAQ.

---

## 1. Intent (what Brad wants)

After a **liquidation-class free-capital event** (rotation sell, large stop, manual/liquidation disposition), the platform should have a **clear optional path** to redeploy **some portion** of proceeds into a **stronger setup** — not always park 100% forever, and not always full-size hop.

That path must answer:

| Question | Answer location |
|----------|-----------------|
| **Why allowed?** | Evidence gates below + fee floor |
| **When used?** | Mode + trigger + candidate filters |
| **Benefit?** | Measured: follow-leg expectancy after fees vs hold-cash baseline |
| **If unreliable?** | FAQ + this doc — default stays hold |

---

## 2. Live truth today (do not confuse with Signals BUY)

| Layer | Behavior |
|-------|----------|
| Signals tile BUY/HOLD/SELL | **Context only** (SignalGenerator) — not an order |
| Free capital after big sell | Often **`hold_cash` + pair rebuy cooldown`** (disposition) |
| Flat option-B | Small **cash** deploy cap (`rebalance_cap_usd` ~$75), RSI/sent gates |
| Mid-cycle `ROTATE_IN` logs | Proposals; **not** automatic fills |
| Immediate weak→strong hop | **Not live** as a completed two-leg product |

**2026-08-16 example:** BTC `rotation_exchange` ~$1,992 → disposition cash / block BTC rebuy → **zero** follow BUYs into LINK/RAVE despite Signals BUY.

---

## 3. Evidence (this book, cut ≥ 2026-07-01)

Regenerate anytime:

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python -m phase6.research.run_liquidation_redeploy_study
```

Artifacts: `reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md`, `data/state/liquidation_redeploy_study_latest.json`.

### Snapshot (2026-08-16 run)

| Finding | Result |
|---------|--------|
| BUY→SL within 72h | **n=43**, sum SL PnL **≈ −$163** (10 under 6h) |
| Free-cap sells ≥$50 | **33** events |
| Other-pair BUY within 24h | **20 / 33** |
| Those follow buys → SL in 7d | **35** legs, sum PnL **≈ −$242** |
| Immediate 6h redeploy >$10 | **Rare** under hold policy |
| Rotation ≥$50 → follow SL PnL | Net **negative** on observed follow buys |
| Early sim (2026-06 catch-the-wave) | Gross green on proxy tape but **fee-heavy** at high turnover |

### Verdict enum

| Code | Meaning |
|------|---------|
| `unreliable_as_default` | **Current** — post free-cap redeploy looks lossy / fee-sensitive on live tape |
| `promising_needs_shadow` | Follow-leg expectancy ≥0 after fees on adequate n — still no auto-live |
| `ready_for_brad_partial` | Shadow gates met + Brad OK for `mode=live_partial` |
| `keep_hold_only` | Explicit product choice: never auto-hop after liquidation |

**Go/no-go (2026-08-16):** **NO-GO** live partial redeploy as default.

---

## 4. Product path (clear modes)

Config surface (proposed — **not live-wired until ISO + Brad**):

```json
{
  "liquidation_redeploy": {
    "mode": "off",
    "comment": "off | shadow | live_partial",
    "portion_pct": 0.25,
    "max_usd": 75,
    "min_proceeds_usd": 100,
    "max_legs": 1,
    "fee_rt_assumed": 0.006,
    "min_expected_edge_multiple_of_fee": 2.0,
    "allow_after": ["rotation_exchange"],
    "deny_after": ["stop_loss_exchange"],
    "require_regime_allow_new_buys": true,
    "require_entry_gates": true,
    "block_same_pair": true,
    "shadow_log": "data/state/liquidation_redeploy_shadow.jsonl"
  }
}
```

### Mode semantics

| Mode | Behavior |
|------|----------|
| **`off`** | **Default.** Disposition hold / normal flat lab only. No liquidation-triggered hop. |
| **`shadow`** | On free-cap event, compute would-redeploy candidate + size; **log only**; no order. |
| **`live_partial`** | Same filters; place **at most one** BUY ≤ `min(portion_pct × proceeds, max_usd, rebalance_cap)`. Rest stays cash/hold policy. |

### When utilized (all must pass for live_partial)

1. **Trigger:** SELL in `allow_after` (start with **rotation only**; SL-funded hop stays denied until separate study).  
2. **Size:** `min(portion × proceeds, max_usd, regime cap)`.  
3. **Candidate:** Top eligible **other** pair: regime entry gates + score floor; **not** cooldown-blocked; not dust.  
4. **Fee floor:** Only if model edge ≥ `min_expected_edge_multiple_of_fee × fee_rt × size` (else skip → cash).  
5. **One leg max** per event; no multi-hop churn.  
6. **Never** auto-promote from shadow without Brad.

### Why “portion” not “all”

- Full hop doubles fee surface and repeats the **manufactured loss** pattern (free cash → new bag → SL).  
- Portion keeps **optional wave capture** while preserving dry powder and matching flat-lab risk.

---

## 5. Overall benefit (how we measure)

| Metric | Hold baseline | Partial redeploy |
|--------|---------------|------------------|
| Follow 7d realized on hop leg | $0 (no hop) | Sum PnL − fees |
| Second-SL rate on hop | n/a | Must not exceed book baseline |
| Fee drag | 1× sell only | + buy (+ later sell) |
| Opportunity | Miss wave | Capture if edge > fees |

**Promote `live_partial` only if** shadow over ≥**30d** and ≥**15** eligible events shows:

- Net hop expectancy **> 0 after fees**  
- Second-SL rate **≤** control (no-hop / delayed deploy)  
- No increase in same-session BUY→SL fleet wound KPI  

---

## 6. Unreliable? Documented stance

**Yes — as a default full or aggressive hop, unreliable on current evidence.**

Reasons:

1. Live follow-buys after free capital were **net stop-lossy** (~−$242 on follow legs in study window).  
2. Early rotation sim needed **high turnover** → fees dominate (2026-06).  
3. Exit stack still **SL-asymmetric** (TP shadow); hop increases SL inventory.  
4. Signals BUY ≠ entry-gate pass under flat B (e.g. RSI>55).

Therefore FAQ + ops default: **cash hold / gated small deploy**, not “sell BTC → buy tile BUY.”

---

## 7. Implementation roadmap (no silent live)

| Step | Deliverable | Status |
|------|-------------|--------|
| A | Ledger study + report (regenerable) | **DONE** 2026-08-16 |
| B | This policy + FAQ | **DONE** 2026-08-16 |
| C | Shadow logger + multi-regime backfill (would-fire only) | **DONE** 2026-08-16 — `run_liquidation_redeploy_shadow` · ISO PASS · orders=0 |
| C2 | **Auto-append** on live free-cap | **DONE** 2026-08-16 — disposition + fill-recon hooks → `liquidation_redeploy_shadow.jsonl` |
| D | ISO: filters, portion math, fee floor, never orders in shadow | with C |
| E | Brad OK → `live_partial` single-account | BLOCKED on C evidence |

---

## 8. Non-goals

- Full NAV redeploy on every liquidation  
- Mid-cycle spam hops from every `ROTATE_IN` log  
- Using SL proceeds to chase the next bag (denied until separate less-loss proof)  
- Raising flat `$75` cap to “use the BTC cash”

---

## 9. Pointers

- Study: `reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md`  
- FAQ internal: `docs/faq/Internal_Trading_Platform_FAQ.md` § Rotation after liquidation  
- FAQ external: `docs/faq/External_Client_FAQ.md` § After a large sell  
- Scale lanes: `docs/testing/SCALE_TEST_LANES.md` (capital / manufactured-loss)  
- Historical intent: catch-the-wave / fees — session notes 2026-06-15
