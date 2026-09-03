# Decide packet — GAP-05 closeout (testable decision)

**Date:** 2026-08-18  
**Parent:** `P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816`  
**Primary CR:** **`enforce_config_72h`** (shipped code alignment)  
**Rejected as first lever:** SL 3% → 2%  
**Live promote of new policy knobs:** false until 14d watch passes  
**Live book sizing / SL %:** **unchanged** (still 3% base, adaptive 1.5–5%)

---

## Plain English (why the daily trickle)

The bleed is mostly **rebuy-after-stop → stop again**, not “stops are 1% too wide.”

| Fact | Value |
|------|------:|
| Core SL episodes (non-dust) | 38 |
| Re-entries | 29 |
| Second SL after rebuy | **79%** |
| Rebuys inside advertised 72h block | **52%** of rebuys |
| CF: if 72h block had held | ~**$136** second-SL ledger loss avoided (historical) |
| Current stop | **3%** base (`sl_base_pct` / `stop_loss_pct`) |

Config already said **hold cash + 72h pair block**. Code on some paths still used **24h**. That is an **enforcement gap**, not a missing “optimal gap” search.

---

## Decision matrix (frozen)

| Option | What it does | Verdict | Why |
|--------|----------------|---------|-----|
| **A. Enforce config 72h on all auto-BUY paths** | Remove hardcoded 24h; one helper = config hours | **DO NOW** ✅ | Highest leverage, matches written policy, no new risk knob |
| **B. Lengthen block 72→96/120/168** | Longer lockout | **DEFER** until 14d watch | CF gains diminishing; prove enforce first |
| **C. SL 3% → 2%** | Tighter stop | **NO as first move** | Cuts upside / more stop-outs; does **not** fix recycle; trickle is rebuy path |
| **D. Trail / TP as recycle fix** | Profit exits | **OUT OF SCOPE** here | Different lane (exit map / shadow TP) |
| **E. Shorten block to “catch bounce”** | Faster rebuy | **FORBIDDEN** | Opposite of evidence |

### Recommended CR string
```
enforce_config_72h + watch_14d + no_sl_pct_change
```

---

## What shipped (code)

| File | Change |
|------|--------|
| `phase6/core/rebalance_coordinator.py` | Recovery `deploy_capital` cooldown: `hours=24` → config default via `get_deployment_cooldown_pairs(runner)` |
| `phase6/core/runner_capital_events.py` | Deposit redeploy cooldown: same helper (was hardcoded 24h ledger lookback) |
| ARCH-4 path | Already used `filter_trade_plan_manual_cooldown` @ config hours — unchanged |

**ISO:** `scripts/phase6/test_isolation_post_sl_block_enforce.py` — PASS  
**Not changed:** `stop_loss_pct` / adaptive SL band, hold_cash flags, capital amounts.

---

## Counterfactual (ledger, non-dust rebuys) — block length menu

| Block hours | Rebuys blocked | 2nd-SL $ avoided (ledger) | Remaining 2nd-SL $ | 2nd-SL rate on allowed |
|------------:|---------------:|--------------------------:|-------------------:|-----------------------:|
| 24 | 4 | −29 | −129 | 0.80 |
| 48 | 6 | −61 | −96 | 0.78 |
| **72** | **15** | **−136** | **−22** | **0.64** |
| 96 | 22 | −152 | −6 | 0.57 |
| 168 | 26 | −158 | −0 | 0.33 |

**Read:** 72h is the knee if enforcement is real. 96–168 shave a little more but starve re-entry sample and need a separate offline trial after the watch.

---

## Testable success bars (14-day watch)

| Gate | Pass | Fail |
|------|------|------|
| `early_rebuy_frac_lt_72h` on **new** core SL→rebuy episodes after ship | **≤ 0.10** (allow dust/ops exceptions logged) | \>0.20 → reopen enforce / path audit |
| `second_sl_rate` on new rebuys with rebuy_hours≥72 | record only (no auto flip) | — |
| Auto-BUY of pair with SL in last 72h on ARCH-4 + recovery + deposit paths | **0** in runner logs / ledger join | any hit → P0 path fix |
| ISO `test_isolation_post_sl_block_enforce` | green on CI/local | fail blocks claim |
| SL % change | none | any unapproved change = process fail |
| Live promote longer block or 2% SL | **Brad gate only** after watch report | |

**Re-run command (weekly OK):**
```bash
cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. .venv/bin/python scripts/phase6/run_post_sl_reentry_eff.py
PYTHONPATH=. .venv/bin/python scripts/phase6/test_isolation_post_sl_block_enforce.py
```

**Watch artifact:** append dated row to `data/state/post_sl_reentry_eff_latest.json` history or re-run report; compare `early_rebuy_lt_block_h` trend post-2026-08-18.

---

## On “optimal gap”

We are **not** optimizing a free continuous gap. We are:

1. **Making the stated 72h gap real** (this ship).  
2. **Measuring** whether trickle slows.  
3. Only then optionally A/B **96h vs 72h** offline (GAP-05c) — still not 2% SL.

---

## GAP-03 (sizing) — parked note only

You’re right that **cap scope / sizing is regimen-sensitive** (bull vs flat vs bear, cash-only vs rotation). That is **GAP-03**, not this packet. Stays **STAGED NEXT**. Do not mix SL% or post-SL block into the cap matrix trial.

---

## Must-nots

- Do not set `stop_loss_pct` to 0.02 to “stop the drip” without a separate offline regimen + Brad go.  
- Do not shorten `stop_loss_exchange_block_rebuy_hours`.  
- Do not clear cooldowns to force re-risk.  
- Do not claim daily loss fixed until 14d early-rebuy gate posts.

## Follow-on IDs

| ID | Intent |
|----|--------|
| `P6-SCALE-GAP-05b-ENFORCE-WATCH-20260818` | 14d measure early_rebuy + path integrity |
| `P6-SCALE-GAP-05c-BLOCK-HOURS-CF` (optional) | Offline 72 vs 96 only if watch pass but trickle remains |
| `P6-SCALE-GAP-03-...` | Cap scope matrix (separate) |
