# Jev (TypeSafe) Judgment Layer — Lab Validation Plan

> **For Hermes:** Lab / measure-only. No live orders, no tryout knobs, no X budget changes from this doc. Implement only after Brad GO on the **lab slice** below.

**Status:** LAB HARNESS SHIPPED (measure-only) — 2026-09-18/19  
**Date:** 2026-09-18  
**Source:** Brad + Grok dialog on TypeSafe Jev (System One model)  
**Access:** OpenRouter `POST /api/alpha/decisions` · model `~typesafe/jev-latest` (resolved `typesafe/jev-1.13-20260917` on first smoke)  
**Refs:** https://openrouter.ai/~typesafe/jev-latest · https://typesafe.ai · docs.typesafe.ai primitives (noul / choice / score)

---

## 0. One-line thesis

**Jev = fast typed judgment API (noul / choice / score + confidence), not an alpha model and not a replacement for Phase 6 deterministic money path.**  
Worth a **paper/shadow validation** on *fuzzy multi-factor* decisions we currently fake with thresholds, aging rules, or slow LLM glue. Keep sizing, seats, fees, SL/TP, Coinbase I/O in Python.

---

## 1. Product fit vs Phase 6 (honest)

| Layer | Keep in Python (deterministic) | Candidate for Jev lab |
|-------|--------------------------------|------------------------|
| Exchange / fills / SL attach / bag_id | Yes | No |
| Seat ledger, $75 cap, tryout math | Yes | No |
| RSI number, OHLCV, fee tier | Yes | No |
| **Knife / fakeout / wash-vs-dump** | Shadow rules today | **High** — noul fan-out |
| **X/headline materiality + shill/priced-in** | Paid X score + aging | **High** — cheaper than LLM JSON |
| **Should we trade this name now?** (inventory + funding + book) | Gate stack | **Medium-high** — second axis = confidence |
| **Regime label** (trend/range/squeeze/cascade) | BTC regime helpers | **Medium** — compare to existing tags |
| dual_agree promote / lagger→winner | Paper CF | **Low near-term** (promotion already unreliable; don’t add vendor vote as promote) |
| Directional BUY as sole edge | — | **No** (~35% in source dialog; we agree) |
| Kelly / vol target / rebalance weights | BookRebalance + math | **No** as owner; optional sleeve *nudge* later |

**Aligns with luck ladder:** R1 knife, R0 sensor quality, process-tax guardrails — not “new scout alpha.”

**Aligns with action architecture:** Jev sits behind a **JudgmentPort** adapter; `BookRebalance` / `RsiEventProbe` / `TryoutSeatBuy` stay owners. Jev never places orders.

---

## 2. What is verified publicly (vs marketing)

| Claim | Support |
|-------|---------|
| Typed outputs: noul, choice, score + probabilities/confidence | Cloudflare + TypeSafe docs examples |
| No free-text generation as product surface | Vendor positioning + reviews |
| Latency class hundreds of ms (not multi-second chat) | Vendor/blog benchmarks (~0.4s class cited) |
| Input ~$0.042 / MTok, output free (launch pricing) | TypeSafe blog; treat as **vendor list price, pin later** |
| Early access / quality will move | Funding launch ~days old; pin `jev-1.x` not `latest` |
| Crypto-specialized weights | **Not claimed** — domain = your state + criteria |
| Calibrated on *our* tape | **Must prove** — vendor confidence ≠ our win-rate calibration |

**Do not** put the only kill switch behind Jev API.

---

## 3. Highest-ROI lab (first build) — Grok’s packet, Phase-6 shaped

### Goal
Prove **calibration usefulness** on our state shape before any live gate.

### Scope (7–14 days shadow)
1. **One liquid pair** first (BTC-USD or ETH-USD), optional second tryout door (e.g. LINK) later.  
2. Each **event** (RSI wash tick, rebalance slot, or 15m bar): build **compact state JSON** (≪ 32k tok):
   - last N candles / RSI / run_phase  
   - eng sent + age + source  
   - held qty / tryout seat context  
   - optional: short headline snippet if already in cache (no new paid X unless budgeted)  
3. **One Jev fan-out** (atomic questions):
   - **choice** `action`: buy / sell / hold / reduce / flatten  
   - **choice** `regime`: trend_up / trend_down / range / squeeze / liquidation_cascade  
   - **score** `book_or_setup_quality`: thin / normal / toxic (or wash_quality)  
   - **noul** `is_fakeout_or_stop_run`  
   - **noul** `should_trade_name_now` (given inventory + gates summary in state)  
4. Python **logs raw answers** + joins forward marks (15m / 1h / 4h / to-exit if any).  
5. **Paper only:** confidence-gated “would_order” tag — **never** call ExecutionPort.  
6. Report: reliability curves (noul deciles vs realized), agreement with knife_filter_shadow + regime tags, cost/day, latency p50/p95.

### Explicit non-goals
- Live size, tryout auto-buy, promote, full-book HF loop  
- Replacing `evaluate_buy_entry`  
- Trusting action=buy as alpha  

### Kill criteria (lab)
- API flaky / no access after N days → park  
- noul vs outcome **flat or inverse** on ≥200 labeled events → no gate use  
- p95 latency > 2s or cost > budgeted micro-cap → throttle or stop  
- Any path that could place orders without dual hard limits → refuse merge  

### Success (attention bar only)
- Stable typed schema week-over-week  
- At least one question (e.g. fakeout noul or should_trade) shows **monotonic** calibration vs our labels  
- Clear “confidence floor” where skip rate is high and residual errors drop  
→ Then discuss **shadow feature** into knife / tryout latch — still measure-only  

---

## 4. Second wave (only if lab passes)

| Priority | Use | Note |
|----------|-----|------|
| A | News/X item materiality + shill/priced-in | Can cut LLM-JSON pain; watch stack with free/X cache |
| B | Guardrail severity on candidate orders | Confidence-gated escalate; never sole kill |
| C | Journal / label factory post-trade | Feeds classical model later (AutoResearch pattern) |
| D | Strategy router | After A–C; catalog must be real |
| — | Portfolio rebalance owner | No |
| — | Sole directional model | No |

---

## 5. Architecture hook (when coding)

```
phase6/domain/ports/judgment.py     # Protocol
phase6/adapters/judgment_jev.py     # HTTP; pin model version
phase6/domain/services/decision_packet.py  # state builder + question set SSOT
scripts/phase6/run_jev_lab_shadow.py
scripts/phase6/test_isolation_jev_lab.py   # mock HTTP; schema only
data/state/jev_lab_crumbs.jsonl            # gitignored
```

**Budget:** separate lab lane in config; daily max calls; fail-open to “no Jev feature” (gates unchanged).

**Action architecture:** optional later `JudgmentEnrichAction` — not inside BookRebalance.

---

## 6. Access / ops (SHIPPED path)

- [x] OpenRouter key in `~/.hermes/.env` (`OPENROUTER_API_KEY`) — never git  
- [x] Model default `~typesafe/jev-latest` (smoke resolved `typesafe/jev-1.13-20260917`)  
- [x] Daily call cap lab default **24**/day (`data/state/jev_lab_budget.json`)  
- [x] offline `--dry-run` + isolation mock for CI  
- Optional later: pin exact `typesafe/jev-1.13-…` via `JEV_MODEL` / `--model` once version freezes  

**Endpoint:** `POST https://openrouter.ai/api/alpha/decisions`  
Body: `{ "model", "state", "questions" }` → typed `answers` (noul/choice/score).

### First live smoke (2026-09-19 UTC)

- BTC-USD · model `typesafe/jev-1.13-20260917` · **852 ms** · ~1006 in tok · cost ~**$0.000042**  
- action=**hold** (0.86) · regime=**range** · setup_quality≈1.11 (thin/mediocre)  
- fakeout noul=**0.17** · should_trade=**0.27** · paper_buy_tag=**false** · `would_order` always false  

---

## 7. Staffing tasks

| Task | Status | Deliverable |
|------|--------|-------------|
| L0 | SHIPPED | This plan + MASTER |
| L1 | SHIPPED | `JudgmentPort` + OpenRouter adapter + isolation |
| L2 | SHIPPED | `decision_packet` state + default fan-out questions |
| L3 | SHIPPED | `run_jev_lab_shadow` + crumbs + budget + cron wrapper |
| L4 | SHIPPED | 7d rollup: calibration + knife sideboard + cost/latency; honest N |
| L5 | OPEN | Brad stop: shadow feature beside gates vs park |

**Run:**

```bash
python3 scripts/phase6/run_jev_lab_shadow.py --dry-run
python3 scripts/phase6/run_jev_lab_shadow.py --pairs BTC-USD,ETH-USD
python3 scripts/phase6/run_jev_lab_calibration.py
python3 scripts/phase6/test_isolation_jev_lab.py
python3 scripts/phase6/test_isolation_jev_lab_calibration.py
```

---

## 8. Plain English for Brad

**Lab harness is live (measure-only).** OpenRouter Jev answers typed questions on compact BTC/ETH state; we log crumbs and never place orders.

**L4 harness is live (measure-only).** `run_jev_lab_calibration.py` joins crumbs → 1h/4h/24h fwd returns + confidence-route buckets. Current claim stays `N_INSUFFICIENT` until n_ok≥20 and bars age past ticks.  
**Next:** let cron collect ~7d crumbs, then re-read L4 board (still no edge claim until N).  
**Still no:** Jev buy, promote, or risk ownership.

---

## 9. Community tips audit (@0xMovez “20 tips”, 2026-09)

Source: https://x.com/0xMovez/status/2101026930967335040

| Tip theme | Our lab | Action |
|-----------|---------|--------|
| Not an LLM; state→typed decision | Already | Keep |
| Choice / Score / Noul only | Already | Keep |
| LLM generates, Jev decides, code controls, human uncertain | Architecture fit | Keep; human = escalate/skip route |
| No personas/preambles; atomic Q + criteria | Strengthened | Descriptive criteria |
| One judgment per question; combine in code | Already | Keep |
| Never ask to explain | Already | Keep |
| Clean small state | State compact | Prefer smaller packets over time |
| Batch questions; free output | 5-Q fan-out | OK to add more dims later |
| **Gate on confidence bands** (e.g. act ≥0.85 / escalate 0.55–0.85 / skip <0.55) | **Shipped paper route** | Starting points only; retune on crumbs |
| Never invent options; closed choice list | Already | Keep |
| Math/hard rules in code | Already | Keep |
| Pin version after thresholds tuned | `~typesafe/jev-latest` lab | Pin `jev-1.13.x` at L5 |
| Log model/probs/conf/route/outcome | Crumbs + route | L4 joins outcomes |
| In the loop not beside it | Later | Only after calibration; still no sole kill |
| Money workflows (support/lead/router) | N/A to trading | Skip |

**Verdict:** Valuable as **operating discipline**, not new alpha. We adopted confidence-route logging; thresholds stay measure-only until L4.
