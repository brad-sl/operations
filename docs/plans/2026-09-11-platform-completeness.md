# Platform Completeness — Implementation Plan

> **For Hermes:** MASTER SSOT is `PLATFORM-COMPLETENESS-20260911`. Kanban board `crypto-bot-project`. Do **not** auto-dispatch gated/parked cards. Staff only `[STAGED]` with Brad GO + handoff.

**Goal:** Close the gap between “end-to-end lab subsystems exist” and “core trading platform is leak-free, lot-true, and on a proven less-loss → net-edge path.”

**Architecture:** No new seventh subsystem. Finish integrity + both-ends trade lifecycle + deploy realism + proof scoreboard. Mission order: trust → edge → scale.

**Tech stack:** Phase 6 runner, ledger, protective registry, REGIME-CASH, shadow CF arms, Hermes Kanban, isolation tests under `scripts/phase6/`.

**Date:** 2026-09-11  
**Brad GO (docs/pack only):** 2026-09-11 — completeness card + Kanban pack. **Live knobs / runner / book: leave-as-is** unless a child card has explicit Brad GO.

---

## Gap map (frozen)

```text
[Universe] → [Qualify] → [Size/Execute] → [Protect] → [Exit] → [Cooloff] → [Learn]
    OK           OK          THIN           BETTER        WEAK      OK-ish      THIN
```

| # | Gap | Priority | Card |
|---|-----|----------|------|
| 1 | Episode / lot identity (A2 full) | **P0** | PC-01 |
| 2 | Exit stack proof (TP bank > SL tax) | **P0** | PC-02 |
| 3 | Open sleeve real (eng sent + tryout fills) | **P0** | PC-03 |
| 4 | L2 deployability on paper ADDs | **P1** | PC-04 |
| 5 | Limit-first fill-rate evidence | **P1** | PC-05 |
| 6 | Attribution closed loop (stamped RTs) | **P1** | PC-06 |
| 7 | Portfolio risk kernel SSOT | **P2** | PC-07 |
| 8 | Shadow→live promote gate (no auto) | **P2 GATED** | PC-08 |
| 9 | Process book 14d proof (tax≈0) | **WATCH** | PC-09 |
| — | Reviewer / completeness gate | — | PC-REV |
| — | Multi-book / AUM scale | **OUT** | (mission step 4 — do not staff) |

**Explicit non-goals (this epic):** STAMPEDE/on-chain rotation, tier-C flood, more shadow toys, volume grind for fee tier, multi-tenant runtime, live basket auto-swap.

---

## Wave graph

```text
Wave 0 (docs — DONE this session)
  PC-HUB  PLATFORM-COMPLETENESS pack

Wave 1 — Reliability + sleeve (parallel STAGED; staff one-at-a-time unless Brad says fan-out)
  PC-01  Episode identity A2 full          [STAGED] P0  crypto-engineer
  PC-02  Exit stack proof / TP bank        [STAGED] P0  crypto-engineer (+ analyst read)
  PC-03  Tryout sleeve real (sent+fills)   [STAGED] P0  crypto-engineer

Wave 2 — Deploy realism (after or parallel if no code clash)
  PC-04  L2 deployability score            [STAGED] P1  crypto-engineer
  PC-05  Limit-first fill evidence         [STAGED] P1  crypto-engineer  (needs real buy attempts)
  PC-06  Attribution RT scoreboard         [SHADOW/WATCH] P1  crypto-analyst

Wave 3 — Scale readiness (not now)
  PC-07  Portfolio risk kernel             [PARKED] P2
  PC-08  Promote gate automation           [GATED]  P2  needs Brad + HC+L2

Continuous
  PC-09  Process book 14d proof            [WATCH]
  PC-REV Completeness sign-off             parents=PC-01..PC-06 when claimed DONE
```

---

## Task breakdown (bite-sized per card)

### PC-01 — Episode identity (A2 full)

**Objective:** Every lot is identity-true through SL/TP/ratchet/blocks — no prior-bag bleed.

**Must do:**
1. Design note: bag_id schema `{pair}:{buy_order_id}` (or successor) — grill before multi-file rewrite.
2. Ledger: bag_id on BUY and SELL legs.
3. Protective registry + ratchet: filter/update by bag_id only.
4. live_state / peak_lot keyed or sanitized by bag_id.
5. Isolation: new bag never inherits prior peak_r / stop / lockout incorrectly.
6. Isolation: flat pair clears only that bag’s protectives.

**Must not:** live knob changes; half-refactor without isolation green; force-rebalance “to test.”

**Files (expected):** `stop_loss_manager.py`, `sl_floor_ratchet.py`, `protective_orders_registry.py`, `exchange_fill_reconciler.py`, ledger writers, `shadow_tp.py` peak sanitize, tests `test_isolation_episode_identity_a2.py`.

**Depends on:** A1/A3/A4 already shipped (`PLATFORM-MISSION-P0-CLOSEOUT-20260910`).

**Success:** isolation green + one live monitor week with zero “stale peak / ghost stop on fresh lot” class.

---

### PC-02 — Exit stack proof

**Objective:** Exits bank progress more than they bank process tax; SOP both-ends “get out” is measurable.

**Must do:**
1. Inventory live exit paths vs shadow (TP trail, dual_peak, hard_exit, SL exchange).
2. Scoreboard: TP bank vs SL bank (deposit-adj, 7d/30d) on **ledger RTs**.
3. Re-enable or replace archived shadow TP validation **as measure-only** if needed.
4. Close gaps that mis-tag disposition (manual vs TP vs SL) — trust SOP.
5. Link evidence to existing `[GATED] Profit-exit live path` — **no live promote without Brad**.

**Must not:** flip live TP/hard_exit without Brad GO; claim CF without stops as edge.

**Success:** report + gates packet; process_tax from exits declining; explicit go/no-go for any live exit knob.

**Related MASTER:** `P6-EXIT-PROFIT-LIVE-GATES-20260807`, `P6-EXIT-WR-IMPROVE-STACK-20260821`, trajectory gap handoff.

---

### PC-03 — Tryout sleeve real

**Objective:** Membership-open sleeve can actually seat when eng heat is real — not fake free-tee greens.

**Must do:**
1. Keep tryout readiness artifact fresh (`data/state/tryout_readiness_latest.json`).
2. Prove eng_sent path (X 15m/60m aging → reddit bridge) is clock-true mid-cycle.
3. Document floor SSOT (0.35 new pair vs tryout 0.30) — no silent bypass.
4. When eng clears floor: verify fill path (limit-first) + SL attach (A1).
5. Do **not** lower floors to manufacture green days without Brad GO.

**Must not:** force_eligible spam; tier-C on; auto force_rebalance.

**Success:** ≥1 honest tryout BUY→protected cycle **or** documented drought with sensor-not-broken proof for 7d.

**Artifacts:** `reports/TRYOUT_READINESS_LATEST.md`, sentiment pipeline skill.

---

### PC-04 — L2 deployability

**Objective:** Paper/CF ADD is scored “would runner buy?” before promote talk.

**Must do:**
1. Function: inputs pair + snapshot → reasons from `evaluate_buy_entry` (sent/RSI/recovery/cash/lockout).
2. Attach L2 column to basket CF / paper-primary board (`rel_btc_stable` first).
3. Isolation with fixture gates.

**Must not:** live membership swap; claim L1 CF as L2.

**Success:** CF board shows L1 + L2; promote packets require L2 pass rate.

---

### PC-05 — Limit-first fill evidence

**Objective:** Execution path has real attempt/fill stats (not “0 attempts because 0 buys”).

**Must do:**
1. Counters: limit placed / filled / skipped / market_fallback (must stay 0 if max_usd=0).
2. Report after N tryout attempts or 14d.
3. Tie to fee tier snapshot (maker share when fills exist).

**Must not:** enable market fallback to force fills; grind volume.

**Success:** honest fill-rate denominator > 0 when buys attempted; or explicit “no attempts — sleeve drought” linked to PC-03.

---

### PC-06 — Attribution closed loop

**Objective:** Enough stamped BUY→SELL RTs with RSI+sent to learn tax vs edge.

**Must do:**
1. Audit stamp coverage on new trades.
2. Weekly RT table: pair, entry stamps, exit reason, R, process_tax flags.
3. Feed month_path / analyst comparison standard — no vibes.

**Must not:** backfill fake stamps; promote from N&lt;threshold.

**Success:** report path + N threshold documented; OPT uses only stamped set.

---

### PC-07 — Portfolio risk kernel (PARKED)

**Objective:** One risk SSOT all paths cannot bypass (tryout, rebalance, ignition, park).

**Parked until:** PC-01..03 stable and process_tax watch green. Spec only if staffed early.

---

### PC-08 — Promote gate automation (GATED)

**Objective:** Shadow winner → production only via HC + L2 + missfire + size + **Brad GO**.

**Must not:** auto-promote. `live_membership_swaps` stays false until explicit GO.

---

### PC-09 — Process book 14d (WATCH)

**Objective:** Measure only — process_tax MTD≈0, no new manufactured wounds, month_path less-loss improving.

**Aligns:** `P6-5PCT-MONTH-PATH-20260909` 14d watch. No util staff until pass.

---

### PC-REV — Completeness sign-off

**Objective:** Orchestrator/reviewer verifies children against this plan; updates completeness %; no false DONE.

---

## Verification (epic-level)

```bash
cd /home/brad/projects/crypto-trading-bot
bash scripts/hermes/pre_ship_quality.sh
# per-card isolation as named in handoffs
hermes kanban --board crypto-bot-project list | rg 'PC-0|PLATFORM-COMPLETENESS|COMPLETENESS'
```

## Staffing rule

1. MASTER row status is SSOT.  
2. Kanban = dispatcher with title tags.  
3. Staff next default: **PC-01** (A2) unless Brad picks PC-03 ops first.  
4. Never staff PC-07/08 without Brad.  
5. PC-09 never gets a coding worker — measure only.

## Related docs

- `docs/PLATFORM_MISSION.md`
- `docs/AGENT_5PCT_MONTH_PATH.md`
- `docs/sop/TRUST_FIRST_TRADING_ENGINE.md`
- `docs/plans/2026-09-10-settlement-naked-bag-and-episode-id.md`
- `docs/KANBAN_MASTER_STATUS_FRAMEWORK.md`
- Session gap narrative: 2026-09-11 completeness review

## Status update 2026-09-12T01:45:20Z
- **PC-01** DONE (prior)
- **PC-02** DONE — exit stack proof builder + live packet
- **PC-03** DONE — tryout readiness builder + live board (drought-honest)
