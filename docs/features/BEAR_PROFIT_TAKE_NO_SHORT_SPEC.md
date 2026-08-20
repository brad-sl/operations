# Feature Spec — Bear profit-take (no shorting)

**ID:** FEAT-BEAR-PROFIT-TAKE-2026-08  
**Status:** Phase 1 **shadow shipped** — **no live orders**  
**Date:** 2026-08-20  
**Audience:** Platform product + Phase 6 ops  
**Related:** `docs/REGIME_EXIT_POLICY_MAP.md`, `docs/EXIT_AUTOMATION.md`, `docs/features/TRADER_MESSAGE_COMPOSE_NO_AI.md`, `docs/research/PARK_REGIME_POLICY.md`

---

## 1. Problem

We have spent little product effort on **bear**. Entry is mostly **park / no new buys**.  
Profit-side map today for bear is **ride / SL only** (`regime_exit_policy_map` — offline prior: early fixed TP hurt).

When a real bear hits, lazy traders will still hold residual winners and catch **relief rallies**. Without a prepared playbook we either:

- give back open gains into the next leg down, or  
- FOMO-rebuy after any trim.

We need a **prepared, automated, no-short** path to **realize** profit into strength — evidence first.

---

## 2. Product north star (revised rank — ease + reliability)

Not statistical “probability.” **Friction × emotional reliability for set-and-forget traders.**

| Rank | Method | Product role |
|------|--------|----------------|
| **1** | **Laddered % scale-out (rules)** | Default automation candidate |
| **2** | **Pre-set limit TP levels** | Execution of the ladder (exchange later) |
| **3** | **Extra trim on relief strength** | Optional overlay (v2 trough/bounce) |
| **4** | **Proceeds → stables (+ optional modest yield later)** | Preserve after realize |
| **—** | Crypto-backed loans | **Out of scope** — liquidity tool, not take-profit |

**Principles**

- No shorting, no perps, no options required.  
- Partial, early, often > perfect top.  
- **No instant FOMO rebuy** after a take-profit leg (cooldown / cash-first).  
- Trader copy = **script templates only** (no AI in live path).  
- **Shadow → evidence → Brad OK → one knob flip.** Never auto-promote.

---

## 3. Tension with existing bear exit map (honest)

| Layer | Current bear default | This feature |
|-------|----------------------|--------------|
| `regime_exit_policy_map` bear | No fixed TP / trail / RSI exit shadow | Unchanged for global TP |
| Offline prior | Early single-shot TP hurt vs ride-to-SL | Still respected |
| **Bear profit-take** | — | **Separate** shadow: **partial ladder** on strength, not full dump at +6% |

**Hypothesis to test in shadow (not assumed true):**  
In bear, **scaling out 25% slices** on modest green vs entry (and parking proceeds conceptually in stables) beats **full ride-to-SL** on residual winners *and* beats **one-shot full TP**.

If shadow + path study fails → **drop** ladder; keep ride/SL + park entries.

---

## 4. Scope

### In (Phase 1 — this ship)

- Spec + config `config/bear_profit_take.json`  
- Shadow engine: ladder would-fire when `regime == bear` (or force for tests)  
- State/events jsonl + plain-English status  
- Isolation tests  
- Runner hook (after regime_exit_shadow) — still no orders  
- Message compose helper for IM/email/dashboard  
- Epic + plan + skill pointer  

### Out (later phases)

- Live sells / exchange limit attach  
- Real yield venue integration  
- Full relief-rally detector (trough → +15–50% bounce)  
- Loans  
- Auto-promote  
- Changing bull/flat TP map  

---

## 5. Config knobs (few)

`config/bear_profit_take.json`:

| Knob | Default | Meaning |
|------|---------|---------|
| `mode` | `shadow` | `off` \| `shadow` \| `live` (live forced off until Brad) |
| `live_apply` | `false` | Must stay false unless explicit promote |
| `enabled` | `true` | Master switch |
| `active_regimes` | `["bear"]` | Only evaluate when regime in list |
| `ladder.tranches` | +3%→25%, +5%→25%, +8%→25% | Cumulative r from entry; sell_frac of **original** notionals conceptually |
| `ladder.leave_moon_bag_frac` | `0.25` | Residual never shadow-exited by ladder |
| `min_position_usd` | `25` | Dust skip |
| `rebuy_block_hours_after_tp` | `72` | Shadow intent; live uses capital controls later |
| `proceeds_destination` | `stables` | Message + future park wire |
| `promotion.auto_promote` | `false` | Hard rule |

---

## 6. Shadow behavior

Each runner cycle (or CLI):

1. Resolve regime from `regime_cash_status` (same as cash policy).  
2. If not in `active_regimes` → status `idle_wrong_regime` (still write heartbeat).  
3. Load open book (live_state / runner).  
4. For each position with entry + mark → `r = (mark-entry)/entry`.  
5. For each ladder tranche where `r >= tranche.r_pct` and tranche not yet “filled” in shadow ledger → **would-fire** partial sell.  
6. Log episode (dedupe: pair+level, gap ≥ 30m).  
7. **orders_placed = false** always in Phase 1.  
8. Compose plain-English: “In a down market we’d take some profit here…”  

---

## 7. Accuracy / honesty bars

- Real marks and entries only (no synthetic).  
- Would-fire **episode** counts ≠ tick spam.  
- Do not claim live edge from shadow alone.  
- Path/offline study required before promote discussion (`promotion` gates).  
- Bear entry park stays; this is **exit of existing risk**, not new buys.

---

## 8. Trader messaging (no AI)

Use `phase6.core.trader_message_compose` patterns:

- Dashboard / Telegram / email from structured would-fire facts.  
- Plain English; no `usdc_park` / RSI jargon in user lines.

---

## 9. Promotion (future)

Minimum before any live discussion:

- Calendar days in **bear** with shadow on (see config)  
- ≥ N unique ladder episodes  
- Offline path CF: ladder vs ride-to-SL on bear-labeled legs  
- Brad explicit OK  
- `mode=live` + `live_attach` style one flip — not per-trade chat  

---

## 10. Acceptance (Phase 1)

- [x] Spec + epic  
- [x] Config + shadow module + isolation PASS  
- [x] No orders when mode shadow / live_apply true  
- [x] Runner hook best-effort  
- [x] Messages script-only  
- [x] Wrong regime does not fire ladder  
- [x] Bear + green book can fire ladder would-fires  

---

## 11. Code map

| Piece | Path |
|-------|------|
| Config | `config/bear_profit_take.json` |
| Engine | `phase6/core/bear_profit_take_shadow.py` |
| Tests | `phase6/core/test_isolation_bear_profit_take_shadow.py` |
| CLI | `phase6/research/run_bear_profit_take_shadow.py` |
| Compose | `trader_message_compose.compose_bear_tp_channels` |
| Runner | `phase6_runner` after regime_exit_shadow |
| State | `data/state/bear_profit_take_shadow_status.json` · `…_events.jsonl` |
