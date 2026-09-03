# Independent adversarial review — Preserve Mode PRD

**Date:** 2026-08-02  
**Status:** REVIEW COMPLETE (replacement after cron stream failure on grok-4.5)  
**Reviewer role:** Adversarial / truth-seeking pass against authoring materials  
**Primary:** `docs/research/PRESERVE_MODE_PRD.md`  
**Evidence checked:**  
- `docs/research/USD_HOLD_VALUE_CONTINGENCY_POLICY.md`  
- `reports/USD_HOLD_CONTINGENCY_BACKTEST_2026-08-01.md`  
- `data/state/paxg_drawdown_anatomy.json`  
- `data/state/usd_hold_contingency_backtest_latest.json` (skim)  
- `docs/research/BULL_REENTRY_LAYERED_SPEC.md` (skim)  

**Note on independence:** First scheduled job (`660f69931515`, grok-4.5) failed with SSE timeout before producing output. This report is a structured adversarial review against the frozen docs/numbers. A second-model cron may be attached later; treat **this file** as the actionable review until then.

---

## 1. Verdict

### **revise-before-shadow**

**Why:** The product thesis (Park → Preserve → Deploy, size-as-airbag, no 3% gold SL, exchange-first ladder, sleeve honesty) is directionally sound and better than notify-only. It is **not** ready to shadow-implement until several **P0** gaps are closed in the PRD itself:

1. Ladder economics vs measured vol can **sell the ballast during the exact drawdown gold is “supposed” to ride** (S3 at −26% ≈ realizing the 2026 worst path).  
2. Concurrent multi-stop on Coinbase is still an **unproven dependency** — architecture collapses to a different product if false.  
3. State machine **PARK vs PRESERVE vs crypto util** interactions (including capital_event / suspend protective / force_rebalance) are underspecified and will ship bugs.  
4. Backtest **does not** include staged exits — “20% static” success metrics ≠ live Preserve with S1–S3.

Shadow only after PRD patches + venue probe answers, not after code enthusiasm.

---

## 2. What the PRD gets right

- **Names the problem correctly:** USDC park is right for crypto beta and emotionally barren; alt-nibble is the real failure mode.  
- **Doctrine:** truth box §6A, non-claims, sleeve PnL split, no “gold = cash.”  
- **Sizing as primary control:** 20% × −28% ≈ −5.6% book is the right intuition.  
- **Rejects crypto 3% SL on ballast:** consistent with median/p90 gold dips (−3.8% / −8%).  
- **Exchange-first over notify-only:** correct resilience priority; kill-bot test is the right gate.  
- **No armed-naked:** place+verify before “on.”  
- **Human for up-risk only:** good incentive design.  
- **Backtest humility:** static ballast beat timed BTC→gold theater; go/no-go `shadow_static_ballast_first` matches data.  
- **Positioning:** modes > “we discovered gold.”

---

## 3. Critical blind spots / risks (ranked)

### P0 — Must resolve in PRD before any implementation spike

| ID | Issue | Why it hurts | Evidence / first principles |
|----|--------|--------------|------------------------------|
| **P0-1** | **Staged ladder can liquidate the safety asset into the measured worst drawdown** | S3 at **−26%** from HWM sits **inside** the open 2026 episode (**−28.1%** peak→trough). A Preserve arm near the Jan’26 peak would have **fully flattened** into the hole — converting “ballast” into **realized** gold loss + cash, then missing any recovery. PRD sells “ride normal gold vol” but engineers **exit near historical max pain**. | `paxg_drawdown_anatomy.json` worst −28.07%; PRD S3 −26% |
| **P0-2** | **Backtest ≠ product with ladder** | Offline winner is **static 20% hold**. Live PRD adds S1/S2/S3 sells. No sim of: path through −12/−18/−26, refill policy, whipsaw re-arm cooldown, fee drag on stages. Success metric “edge vs USDC” may **fail** under ladder even when static passes. | Backtest report vs §6B |
| **P0-3** | **Concurrent partial stops are load-bearing and unknown** | Entire L1 resilience story assumes 3 resting legs. If Coinbase allows one protective / one stop per product, product becomes S3-only or bot-dependent stages — **contradicts** “bot down still works” for S1/S2. | PRD checklist item still open; no venue proof in repo |
| **P0-4** | **Protective-order blast radius** | Crypto paths: suspend protective, cancel-on-manual-sell, capital_event stop handling. One shared `cancel_all` / suspend without sleeve filter **strips gold ladder** while “Preserve armed” UI still green → **silent naked ballast**. | PRD mentions risk; not specified which call sites must whitelist |
| **P0-5** | **Target % vs equity definition** | `ballast_nav / total_equity` — includes unrealized crypto? USDC external? Staked? During crypto MTM crash, Preserve **auto-looks underweight** and bot may **buy more PAXG** into stress if not `adds_blocked`. Inverse: crypto rips, gold overweight, bot trims gold into strength without Deploy policy. | §7 build rule underspecified |
| **P0-6** | **Funding rule vs residual crypto inventory** | “Idle cash only” + REGIME-CASH park with **open book still held** (util ≫ target) is the live pain case. Preserve does not say: block arm until util ≤ X, or allow arm with cash sleeve only while alts bleed. User can be **long alts + long gold** — correlation of bad feelings if both red (2022-ish macro). | Trend-repair docs; PRD hard rule 3 incomplete |

### P1 — High likelihood of wrong behavior or false confidence

| ID | Issue | Why it hurts | Notes |
|----|--------|--------------|-------|
| **P1-1** | **HWM trail up-only while bot dead** | Rally then dump with dead bot: stops anchored to **stale low HWM** → stages fire **earlier** than design (tighter), or if never trailed, vs arm_vwap only. PRD says “looser than ideal” for dead-bot — actually **either** early or late depending on path. Need explicit: ref = max(arm_vwap, last_written_hwm) persisted on exchange client metadata / local registry dual-write. | §6B failure table too soft |
| **P1-2** | **Stop-limit gap risk on thin PAXG** | Gap through limit → leg rests unfilled while price free-falls; S3 same failure mode. “Optional stop-market S3” should be **default for S3** or market-if-touched backup — safety valve that doesn’t fill is theater. | First principles + thin gold books |
| **P1-3** | **S1 −12% is common enough in 2025–26** | Not just “uncommon historically.” 3m path −16%, multiple ≤−8–11% episodes. Expect **frequent S1** in stressed gold regimes → churn, short-term capital gains, support “why did safety sell.” | Anatomy episodes |
| **P1-4** | **Adds_blocked vs band rebalance** | After S1, actual % < target. Cycle logic that “tops up to 20%” fights stages unless adds_blocked is hard and **survives restart**. Persist flag in state, not memory. | Ops |
| **P1-5** | **Deploy trim vs ladder race** | Bull flip: bot market-trims to 0% while S1–S3 still live → oversell / insufficient funds / orphan stops. Need **cancel ladder first, then trim**, single critical section. | State machine gap |
| **P1-6** | **PAXG ≠ allocated gold** | Issuer/custody/peg/venue risk uncorrelated with XAU. Depeg or secondary discount can hit stops on “gold” that physical didn’t do — or fail to hit when product stuck. Integrity valve mentioned lightly; needs oracle/XAU basis kill switch as **P0 for multi-tenant**. | Non-claim exists; no mechanism |
| **P1-7** | **Opportunity cost framing** | 18m static 20% **+8.9%** vs USDC4% **+6.1%** — modest edge after fees/ladder may vanish. 12m static 20% **~+4%** ≈ USDC4%. Differentiator is **behavioral** (less alt nibble), not compound outperformance. PRD should say that explicitly. | Backtest tables |
| **P1-8** | **Correlation blind spot** | Gold can fall with real yields / USD strength **while** crypto is also in bear (macro tightening). “Safety when crypto parks” ≠ negative beta guaranteed. 2022 gold DD −21% overlapped crypto winter. | Anatomy 2022 episode |

### P2 — Important but not ship-blockers for a tiny solo shadow

| ID | Issue |
|----|--------|
| **P2-1** | Tax lots / wash-ish churn from stages — tenant support burden |
| **P2-2** | No specification of min notional / dust interaction when 25% of small position < min size → skipped S1, jumps to fat tails |
| **P2-3** | Dashboard “safety” wording still risks App Store / marketing misuse even if internal doctrine is clean |
| **P2-4** | Multi-tenant: one Coinbase portfolio mixing sleeves; sub-accounting hard |
| **P2-5** | Time-under-water backup can **double-sell** with exchange S1 if both fire |
| **P2-6** | TRX/other “held value” assets correctly out of v1 — keep them out; feature creep risk |

---

## 4. Exchange ladder critique

### Concurrent stops
- PRD correctly flags unknown multi-leg support.  
- **Improvement:** make **venue probe the first MVP milestone**, with frozen fallbacks:  
  - **A (ideal):** 3 GTC stop-limits  
  - **B:** 1 stop-limit S3 + bot-owned S1/S2 (document resilience downgrade)  
  - **C:** single stop-limit at −18% for 100% (simpler product; fewer surprises)  
- Do not write abstract registry code before A/B/C choice.

### Stop-limit gaps
- Limit buffer 0.3–0.6% may be **optimistic** on PAXG-USD.  
- Recommend: **S3 stop-market** (or stop-limit with aggressive buffer + immediate market escalate if stop triggers and limit rests > T seconds) — only if Coinbase API supports.  
- Shadow must log: trigger time vs fill time vs slip bps.

### HWM trail when bot dead
- Persist `ref_px` on every amend to disk **and** in order client_id/metadata.  
- On restart: rebuild from registry, never from “current price is HWM.”  
- Consider **arm_vwap-only stages** for v1 (no trail) to reduce amend/cancel races — less optimal, more auditable. Trail = v1.1.

### Partial fills
- Crypto SL reconcile is non-trivial already; **3 legs × partials** multiplies state.  
- Need explicit: remaining qty math after partial S1 before amending S2/S3 sizes (otherwise over-allocated sells → reject or short).  
- **Re-size remaining open legs after any fill** is mandatory, not optional polish.

### Interact with crypto suspend/cancel-all
- Enumerate every code path that cancels stops (grep in impl phase): manual sell, capital_event, pair delist, emergency flatten, testing hooks.  
- PRD should require **allowlist registry by sleeve** and integration tests: “crypto suspend does not cancel preserve_* orders.”

### Coinbase-specific hazards
- Advanced Trade stop-limit GTC semantics / trigger from last trade vs mark.  
- Weekend/holiday gold liquidity (PAXG may track differently than futures).  
- Portfolio margin / buying power if cash locked in open orders.  
- **Min size:** stage fractions on $50–100 shadow may be **below min** — PRD should set **minimum arm notional** (e.g. ≥ $500 ballast or stages collapse to single S3).

### Internal inconsistency to fix
- §6 table still says ballast purpose “hold through noise” while §6B **sells 25% at −12%** (noise-adjacent in bad years). Rephrase purpose: “hold through **small** noise; **staged reduce** through severe gold DD; size limits book damage.”

---

## 5. Economics & honesty

| Claim vibe | Reality check |
|------------|----------------|
| Safety sleeve | **Smaller crash than alts**, not safe. 20%×−28% hurts; ladder may **lock in** gold losses. |
| Beats dead cash | **Sometimes.** 18m static yes vs 0%; vs 4% APY slim; with stages unproven. |
| Inflation hedge | Plausible long sample; **not** proven for every CPI regime; tokenized basis risk. |
| Differentiator | Real if **modes + exchange ladder + sleeve accounting** work; fake if just “we bought PAXG.” |
| Timed overlay | Backtest: often worse than static; keep **out of MVP** (PRD already leans this — good). |

**Honesty patch:** Add a worked example to PRD:

> Arm $10k, 20% PAXG at peak. Path −28% with S1/S2/S3 filling near triggers. Show **realized** gold PnL + ending allocation vs pure static hold vs pure USDC. If authors won’t show the ugly path, don’t ship the ladder.

**2026 conflict:** Anatomy says worst DD still **open** (no recover to Jan peak). Product that arms Preserve **now** is buying into a post-crash gold tape, not the 18m backtest entry at start of window. **Path dependence of arm date** is missing from PRD.

---

## 6. Product / differentiation claims

| Overclaim risk | Mitigation |
|----------------|------------|
| “Safety mode” in UI | Prefer **Preserve / Ballast**; subtitle “real-asset sleeve, can fall 15–30%” |
| “Exchange-backed safety” | True only after multi-stop proof + kill-bot demo video/logs |
| Better than REGIME-CASH alone | Only if it reduces **override-to-alts** behavior or real drawdown — measure overrides, not just NAV |
| Platform moat | Moat is **integration + accounting + gates**; competitors add PAXG in a weekend |

REGIME-CASH alone already does the hard thing (not trading). Preserve is a **retention/real-value overlay**. Price it that way internally so eng priority stays: ladder correctness > gold alpha.

---

## 7. Ops & multi-tenant scaling

- **Runner dies after arm:** OK if ladder live; **dies during arm mid-ladder** → partial legs — need transactional arm (all 3 or rollback+disarm).  
- **Multi-account:** per-tenant preserve registry, per-tenant arm flags, no shared order ID maps.  
- **Tax:** stage sells = taxable events; tenants will ask; document “Preserve may realize gains/losses without user click.”  
- **Support:** “Why did safety sell my gold?” runbook with stage table.  
- **Monitoring:** alert on missing leg, arm without 3 IDs, preserve order cancel by non-preserve code path (P0 detect).  
- **Paper shadow:** prefer exchange sandbox or tiny size; shadow that only logs without resting orders **does not** validate the resilience claim.

---

## 8. Suggested PRD patches (concrete)

1. **§6B — Decision fork on ladder aggression**  
   - **Preserve-Hold (default recommend):** S3 only at **−30% to −35%**, no S1/S2 sells (adds_block at −12% bot or reduce-only flag). Matches “ballast” + worst-path ride.  
   - **Preserve-DeRisk (optional profile):** current S1/S2/S3.  
   - Do not silently ship DeRisk as the only meaning of Preserve.

2. **§6B — If keeping 3-stage DeRisk:** rewrite S3 to **−30% or −32%** (beyond measured −28.1%) **or** accept explicit goal “we cap gold pain by realizing near historical worst.”  

3. **§7 — Equity & arm gates**  
   - Define `total_equity`, `cash_available`, `crypto_util_max_to_arm` (e.g. util ≤ park target + band).  
   - `adds_blocked` persisted; survives restart; clears only on human re-arm or full flatten + cooldown.  

4. **§6B — Arm transactionality**  
   - “All stage orders accepted OR cancel any placed + mark arm failed.”  

5. **§6B — Post-fill leg resize** mandatory bullet.  

6. **§6B — Deploy/trim order of operations:** cancel preserve orders → sell residual → clear registry.  

7. **§10 — Success metrics add**  
   - Ladder path backtest (static vs staged) on 2022 and 2026 gold DD windows.  
   - Venue probe results attached as appendix.  
   - Min notional / min stage size.  

8. **§8 — UI copy bank**  
   - Forbidden strings list: risk-free, stable, can’t dump, guaranteed CPI.  
   - Required hover: worst measured path DD and book impact at target %.  

9. **§12 — Add open questions**  
   - Arm allowed while crypto residuals open?  
   - Preserve-Hold vs Preserve-DeRisk default?  
   - Stop-market on S3?  
   - Arm-date path dependence / don’t arm into open gold DD without warning?

10. **§1 Problem — add** “without introducing a second silent failure: unbacked ‘armed’ state or gold forced-liquidated at the bottom.”

11. **Config:** remove leftover ambiguity (`exchange_sl: false` vs `exchange_staged_exits: true` in long block — already partly cleaned; ensure single schema).  

12. **Appendix:** worked numerical ugly path (P0-1).

---

## 9. Test plan gaps

| Test | Why |
|------|-----|
| **Venue multi-stop probe** on live/sandbox PAXG | P0-3 |
| **Kill-bot after full arm** + price scrape / manual trigger simulation | Resilience claim |
| **Kill-bot mid-arm** (1 of 3 legs live) | Transactionality |
| **Crypto suspend_protective / cancel_all** does not strip preserve | P0-4 |
| **Stage fill → no crypto rebuy** + cash tag | Capital event interactions |
| **Partial S1 → S2/S3 qty amend** | Oversell |
| **Deploy flip race** cancel-then-trim | P1-5 |
| **Min-size shadow** $50 account stages | Skip/collapse logic |
| **Path stress backtest** 2022 −21% and 2026 −28% static vs staged | P0-1/2 |
| **False arm** UI if place fails | Armed naked |
| **Dust after S3** | Existing dust machinery sleeve-aware |
| **Depeg synthetic** (mark PAXG vs XAU feed) | Integrity |
| **Restart persistence** adds_blocked + registry | P1-4 |
| **Double-sell** time-under-water + exchange S1 | P2-5 |

---

## 10. Open questions before any code

1. Is default profile **Hold** (wide S3 only) or **DeRisk** (S1–S3)?  
2. Coinbase: concurrent stop-limits on PAXG-USD — yes/no/limits?  
3. Stop-limit only or stop-market for final stage?  
4. May user arm Preserve with **significant crypto util** still open?  
5. What is `total_equity` exactly for 20%?  
6. Minimum ballast notional for valid multi-stage ladder?  
7. After S1–S2, do we **stay disarmed from topping up** until full human re-arm even if price recovers? (Recommended: yes.)  
8. Tax/reporting commitment for solo vs tenants?  
9. Will shadow use **real resting orders** (required) or log-only (invalidates claim)?  
10. Who owns weekly ladder audit (order IDs vs inventory)?  

---

## 11. What NOT to do

- Do **not** implement notify-only “safety.”  
- Do **not** use crypto **3%** SL on PAXG.  
- Do **not** ship timed BTC→gold overlay in MVP.  
- Do **not** call Preserve “on” without verified resting protection (or explicit Hold mode with verified S3).  
- Do **not** mix gold MTM into crypto strategy scorecards.  
- Do **not** auto-raise ballast to 50%+ from backtest FOMO.  
- Do **not** cancel_all unprotected across sleeves.  
- Do **not** treat 18m static +8.9% as proof the **laddered** product works.  
- Do **not** skip ugly-path accounting (full stage fill through −28%).  
- Do **not** prioritize marketing pages before venue probe.  
- Do **not** average into gold while stages are firing.  

---

## Cross-checks (claims vs numbers)

| PRD / narrative | Check | Result |
|-----------------|-------|--------|
| Long sample ~+123–126% | anatomy `total_return_pct` 126.4 | OK |
| Worst path ~−28% | −28.07 Jan–Jul 2026 open | OK |
| 3m path worse than −12% | ~−16% | OK — reinforces S1 frequency |
| Static 20% ~+8.9% / −9.3% DD 18m | backtest report | OK |
| USDC 4% ~+6% 18m | backtest | OK |
| S3 −26% “near worst” | worst −28% | OK numerically; **policy intent conflict** (see P0-1) |
| Staged product validated by static backtest | — | **FAIL** — not the same strategy |

---

## Bottom line

Keep the architecture: **modes, honesty, size, exchange-backed de-risk, sleeve split.**  

Revise before shadow: **choose Hold vs DeRisk**, **reposition S3 relative to −28% truth**, **prove Coinbase multi-stop**, **specify equity/arm/cancel blast radius**, **simulate ladder on real gold DD paths**, **min notional + arm atomicity**.  

Until then, REGIME-CASH USDC park remains the only production-grade “safety” you actually have — and overselling Preserve as ready seatbelt would violate the PRD’s own doctrine.

---

*End of review.*
