# Post-Proof Dwell — Long-Term Policy Ruleset

**ID:** `FEAT-POST-PROOF-DWELL-2026-10`  
**Status:** DRAFT policy (measure → shadow → Brad GO live)  
**Edge class default:** `ATTENTION_ONLY_less_loss_path` until multipair CF + live N clear a higher bar  
**Date:** 2026-10-05  
**Related:** tryout lifecycle, TCS post-TP rebuy, scale-window eject, membership sticky, eject cohort card

---

## 0) Plain English (product intent)

**Problem:** After a name pays (TP/trail), we often **flat → $25 tryout → eject → cooloff → tryout again**. That is **re-optioning**, not compounding. High same-pair churn is unstable, fee-heavy, and fights daily uptrends (LINK-class).

**Intent:** After **proof**, treat the name as a **graduated hold sleeve** for a bounded time:

- Keep **exchange SL** (sudden dump protection — your “a little more risk is OK”).
- Keep **trail/TP** as bank tools (we do **not** ban taking profit).
- **Stop** treating the name as a disposable kindling option (no scale-window auto-eject on graduated lots; no fresh $25 reincarnation while graduated).
- Scale only via **add-risk / proven kindling**, not shell thrash.

**Not the intent:** Buy/hold everything. Disable ejects on dead unproven shells. Perma-favor LINK. Claim 10% edge from two weeks of tape.

---

## 1) Roles (who is who)

| Role | Meaning | Eject loop? | Default size path |
|------|---------|-------------|-------------------|
| **tryout_shell** | Unproven timed option on kindling | **Yes** — dead kindling → full exit | $25 shell |
| **graduated_hold** | Post-proof dwell sleeve | **No** scale-window auto-eject | Hold + SL/trail; adds via add-risk |
| **sticky_core** | BTC/ETH-class ballast (existing) | No tryout eject | Rebalance / add-risk |
| **park/ballast** | PAXG / powder | Preserve rules | Not this policy |

Graduation is **earned and expiring**, not a lifetime VIP list.

---

## 2) Proof events (entry to `graduated_hold`)

A pair becomes **post-proof** when **any** of these fire (fee-aware where PnL exists):

| ID | Proof | Notes |
|----|--------|------|
| **P1** | `take_profit_trail` or `take_profit_fixed_tp` SELL with **fee-aware net ≥ +$0.50** (or ≥ +1.5% net on notional) | Primary — LINK/SOL meat |
| **P2** | **2** closed primary RTs in **14d** with **combined fee-aware net > 0** and ≥1 non-eject exit | Secondary — consistency |
| **P3** | Live kindling add filled (`tryout_scale_up*`) **and** structure_ok at add | Scale path actually cleared — rare today |

**Explicit non-proof (do not graduate):**

- Scale-window eject (even gross green)
- Dust / process_bug / orphan sweeps
- Same-day buy→eject
- Paper `would_scale` without live add
- Sentiment spike alone / RSI wash alone

---

## 3) Rights of `graduated_hold` (while active)

1. **May hold** an open lot through normal SL + trail/TP stack.  
2. **Exempt from** `tryout_scale_window` **auto-eject** (`live_apply` skip if lot or pair marked graduated).  
3. **Blocked from** new **tryout shell** seats (`limit_first_buy` / RSI-event tryout composer) for the dwell window.  
4. **May add** only if:
   - add-risk / rebalance path allows, **and**
   - aged eng ≥ money bar (0.35), **and**
   - RSI not cooked, **and**
   - `max_add` / min_move / profit gates pass  
5. **Not** auto-promoted to permanent sticky_core (BTC/ETH). Membership Manager may *consider* later under separate GO.

---

## 4) Duties / risk bounds (this is the “higher risk” contract)

| Bound | Rule | Rationale |
|-------|------|-----------|
| **SL always on** | Exchange SL required; naked lot = P0 repair (existing law) | Dump protection |
| **Trail/TP still live** | Graduated ≠ never sell | Bank meat; avoid god-bag |
| **Notional cap** | While graduated, open graduated sleeve ≤ **min($150, 8% NAV)** unless separate GO | Churn cut ≠ size blowout |
| **One graduated add step / day / pair** | Max one add-risk fill per UTC day | Anti pile-on |
| **No pyramid from tryout mouth** | Composer cannot open second shell | Stops reincarnation |
| **Fee-aware scorekeeping** | Dwell PnL reported net of fees | No cosmetics |

Accepted trade: **slightly longer adverse path risk** between TP opportunities, in exchange for **fewer RT fees** and **more time in a proven name’s trend**. SL is the hard floor — not hope.

---

## 5) Dwell length, demotion, expiry

### 5.1 Default dwell clock

| Clock | Default | Meaning |
|-------|---------|---------|
| **Dwell after proof** | **7 calendar days** | Tryout re-seat banned; eject exempt if held |
| **Extension** | +7d if during dwell: trail/TP banks again **or** live kindling add fills net-green | Compounding proof |
| **Max continuous dwell** | **21 days** then mandatory review (measure board) | Prevent silent forever-hold |

### 5.2 Demote to tryout_shell (or flat) immediately if

- Exchange **SL** fill (post-SL block remains 72h — existing)  
- Hard-exit / dump path fires (existing)  
- Fee-aware open MTM ≤ **−1R** from graduated entry basis **and** structure break (optional shadow first)  
- Operator kill / pair on perma scar list  
- Two failed graduated add attempts with fee-red results in dwell window  

### 5.3 Expire softly

If dwell ends with **no open lot** and no extension proof → pair returns to normal tryout eligibility under door/floors (not banned).

---

## 6) Interaction with existing laws (no contradictions)

| Existing | How post-proof dwell fits |
|----------|---------------------------|
| Scale-window eject | **Unproven shells only.** Graduated lots skipped. Dead HYPE/TIA-class still eject. |
| `post_eject` 24h / repeat 72h | Unchanged for eject path. Dwell is **orthogonal** (post-**TP**, not post-eject). |
| `post_tp_block_rebuy_hours` (24h, structure early release) | **Too weak** for tryout reincarnation. Dwell **extends** tryout ban to 7d default; does not wipe post-SL 72h. |
| `graduate_on_tp` first-fill probation | Related but **different**: size/seat next ADD. Dwell = **role + anti-churn**. May share stamp. |
| Signal-first 0.35 floor | Still applies to any new risk. |
| PAXG preserve / sticky BTC ETH | Untouched. |
| Perma `buy_block_pairs` | Still scars only — not for winners. |
| Dual_agree / membership swaps | Still manual GO. Dwell ≠ basket swap. |

---

## 7) Concrete decision table (operator / agent)

| Situation | Action |
|-----------|--------|
| Fresh name, no proof | tryout_shell; eject if kindling dead |
| Shell never clears kindling | Eject + cooloff (current) — **do not** graduate |
| TP/trail banks net meat | Stamp proof → **graduated_hold** 7d |
| Graduated + still holding | SL/trail on; **no** scale-window eject |
| Graduated + flat (sold TP) | **No new tryout shell** for remainder of dwell; wait for add-risk quality or expiry |
| Want exposure during dwell without shell | Only add-risk path if gates green |
| SL dumps graduated bag | Demote; 72h post-SL block |
| LINK-like daily grind up after TP | Stay graduated; avoid $25 thrash; let trail work |
| HYPE/TIA never TP | Stay tryout; eject hygiene — **out of scope** for dwell |

---

## 8) Can backtests “prove” this?

### Honest answer

**No single backtest proves long-term alpha.**  
N is thin; regime mix is short; buy/hold CF on one pair is **path anecdote**, not `HIT_10`.

What we **can** run (and should, in order):

### Tier A — Process counterfactual (primary, free, honest)

**Question:** If we **blocked tryout re-seat for N hours/days after TP**, what fee-aware $ did we avoid on post-TP→eject chains?

| Input | Ledger SELL PnL + reasons (SSOT) |
|-------|----------------------------------|
| Arms | `off` vs `block_tryout_24h/48h/72h/7d` after TP/trail |
| Metric | Avoided eject tax + avoided same-day churn $; **not** fantasy buy/hold compound |
| Multipair | LINK + SOL + ZEC minimum (≥2 pairs to generalize) |
| Edge tag if green on tax only | `ATTENTION_ONLY_less_loss_path` |

**Already adjacent:** TCS dig/CF (`B48_post_tp`), trade comparison standard shadow would-block.

**First sketch (Aug→Oct 2026 ledger, rough):**

| Pair | TP n / $ | Eject n / $ | Post-TP rebuy ≤72h |
|------|----------|-------------|--------------------|
| LINK | 2 / ~+$6.90 | 3 / ~−$0.50 | 2 |
| SOL | 1 / ~+$2.43 | 1 / ~−$0.08 | 1 |
| ZEC | 2 / ~+$2.10 | 0 | 1 |
| HYPE/TIA | 0 | 4 / ~−$2.4 | 0 (different disease) |

Thesis support: **churn tax clusters on names that already proved** (LINK/SOL), not on pure duds. Duds stay eject-only.

### Tier B — Hold-after-proof mark CF (secondary)

**Question:** After a TP proof event, if we had **kept a runner** (50% hold) or **full hold** with SL for 7d, what’s mark-at-7d and max DD vs banking 100% at TP?

| Rules | Real OHLCV only; fee haircut; SL ~3% path; no synthetic |
|-------|--------------------------------------------------------|
| Report both | (1) max favorable excursion (2) mark **at** horizon H |
| Fail pattern | Green MFE + red mark-at-H = chase trap → do not sell as buy/hold win |
| Edge | Usually `ATTENTION_ONLY` until multi-episode / multi-regime |

This **cannot** alone justify live size-up; it can justify **anti-reseat + dwell** if mark-at-H ≥ 0 more often than eject-rebuy paths after fees.

### Tier C — Forward live measure (required before “policy proven”)

| Gate | Bar |
|------|-----|
| Shadow would-block log | ≥14d, multipair, no orders |
| Live dwell (after GO) | ≥8 graduated episodes or 30d |
| Compare | Fee/turnover down; eject cohort % kindling + post-TP rebuy hits down |
| SL rate on graduated | Not worse than tryout baseline by agreed margin |
| Promote language | Still less-loss / stability until month_path moves |

### What will never count as proof

- One LINK daily chart screenshot  
- Paper MTM without fees  
- “We’d be up if we never sold the TP” without SL path  
- Disabling ejects on unproven shells and calling it dwell  

---

## 9) Implementation phases (no knob spray)

| Phase | What | Live money? |
|-------|------|-------------|
| **0 Policy** | This doc SSOT | No |
| **1 Offline CF** | TCS-style post-TP tryout-block CF + 7d hold-after-TP mark CF multipair | No |
| **2 Shadow** | `would_block` tryout seat if pair in graduated state; crumb log | No |
| **3 Stamp** | On TP fill → write `data/state/post_proof_dwell.json` (pair, proof_id, expires) | No |
| **4 Live gates (Brad GO)** | Composer skip tryout; scale-window skip eject on graduated lots | **Yes** — gates only |
| **5 Review** | Weekly analyst cites dwell board; demote/extend rules | Measure |

**Kill:** `data/state/post_proof_dwell_KILL` or `live_apply=false` in config.

---

## 10) Suggested frozen defaults (for CF + shadow; not live until GO)

```text
proof_min_net_usd: 0.50
dwell_days: 7
extend_days: 7
max_dwell_days: 21
tryout_reseats_while_graduated: false
scale_window_eject_while_graduated: false
graduated_notional_cap_usd: 150
graduated_notional_cap_pct_nav: 0.08
adds_per_day: 1
post_sl_still_72h: true
shadow_only_until_brad_go: true
edge_claim_allowed: false
```

---

## 11) Success / fail criteria (long-term policy)

**Keep / promote dwell if (after live GO window):**

- Post-TP tryout rebuy hits ↓ (≥50% vs baseline window)  
- Eject fee tax on post-proof names ↓  
- Graduated SL rate not systematically worse than tryout SL rate  
- Operator stability: less same-pair every-other-day thrash  

**Revert / demote policy if:**

- Graduated bags eat SL tax > saved fees + missed churn  
- Dwell becomes backdoor to ignore dead structure  
- Only one pair ever graduates (overfit)  

---

## 12) Bottom line

| Claim | Verdict |
|-------|---------|
| High same-pair churn is unstable + fee-heavy | **Supported** (LINK/SOL ledger) |
| Post-proof dwell is a sane long-term policy shape | **Yes** — role change after proof, SL kept |
| Backtests can **prove** higher returns forever | **No** |
| Offline CF can **support** less-loss + lower turnover thesis | **Yes** (Tier A/B) |
| Live without shadow multipair | **No-GO** |

**Policy one-liner:**  
*Prove → dwell hold under SL/trail → no tryout reincarnation → expire or re-prove. Never graduate a dead shell.*

---

## 13) Next actions (waiting on Brad)

1. **GO offline CF pack** (Tier A+B, multipair, report only)  
2. **GO shadow** stamps + would-block (no orders)  
3. **GO live gates** only after CF/shadow readback  

No live config writes from this document alone.
