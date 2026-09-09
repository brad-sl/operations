# Platform optimization after 3 weeks of patches

> **For Hermes:** Do not implement until Brad explicit **go**. Then use subagent-driven-development per phase. Live book / knobs / seats stay frozen until named in a go.

**Goal:** Stop the last three weeks of reliability patches from *creating* process tax, then enforce the leak classes we already measured — so the book can compound toward ~5%/mo dep-adj instead of churning $75 tryouts into SL.

**Architecture:** Diagnose first (already done here), then **one reliability closeout** (ratchet/ledger/gates already coded, uncommitted), then **tactics as fewer round-trips** (enforce post-SL 72h + post-TP 24h on *all* buy paths, no same-session re-seat), then **cost cut** (keep limit-first, do not grind volume for Advanced 1). No new indicators. No auto-promote of sweet-rule CF.

**Tech Stack:** Phase 6 runner, TradeLedger JSONL, `regime_cash_policy`, `exit_automation.json`, isolation tests under `scripts/phase6/` and `phase6/core/`.

---

## Current context (facts, 2026-09-09)

### What the last 3 weeks actually were

Committed git since 2026-08-19 is mostly **daily safe-code backups + Hermes mirrors**. Real *named* feature commits: basket promote (ZEC/STX/ADA), bear ladder **shadow**, dash Why-idle, regime boundary/cream **shadow**, ops cron fixes.

The live-impacting work lived in **working tree + daily backups**, not tidy feature PRs:

| Theme | What shipped | Profit impact |
|-------|----------------|---------------|
| Ledger SSOT + live TP lot bind (Sep 7) | Defense-in-depth journal; fail-closed TP | Prevents fake-green TP dumps (LINK ghost +8.7%) |
| Limit-first Phase D (Aug 31 GO) | post_only 45s; today 2/2 fills | **Cost cut only** (0.4% maker vs 0.8% taker) — not alpha |
| Live TP trail 4/2 + fixed 6% | `exit_automation.json` mode=live | Aug TP +$75.62 vs SL −$136 — TP helps when it fires |
| SL floor ratchet | Intended: lock profit on multi-baggers | **Created** LINK same-session wound (stale `existing_stop`) |
| Quality tryout / $75 / max 2 seats/day | Flat B thaw | Correct size; still re-entered LINK 12h after SL |
| Dashboard KPI/NAV/cash-bucket truth | Many patches | Stops lying; does not print money |
| Sentiment clock, discovery, stand-down C, sweet-rule CF | Shadow | `ATTENTION_ONLY_less_loss_path` — not live |

**Code quality pattern:** patches stacked *on* attach/ledger/ratchet without episode identity. Each fix is locally sensible; together they import prior-bag state onto new lots.

### Scoreboard (not a guarantee)

| Window | Dep-adj | Process tax (leak-adjacent SL $) | Notes |
|--------|---------|----------------------------------|--------|
| 2026-06 | −25.1% | −$6.68 | Pre-deposit, SL-heavy |
| 2026-07 | −28.2% | −$63.19 | +$2k flow; 55 SL vs 8 other |
| 2026-08 | −3.3% | −$90.89 | Best month still miss; 13 SL −$136 vs 3 TP +$76 |
| 2026-09 MTD | **−0.01%** | −$1.44 | Quiet; LINK wound is the leak |

North star ~5%/mo on ~$2.3k ≈ **+$115 this month**. Gap is **not** “need more alts.” It is **stop manufacturing 1.8% stops and post-TP/SL reseats**.

Live now: NAV ~$2,286 · util **6.7%** · cash powder ~$200 + USDC park ~$1.93k · held **LINK + PAXG MICRO** · regime **flat B** (BTC 30d +4.5%, bull bar +15%) · Exit WR path **0.0 on last 6 metric trades** · fleet wound **breach** (LINK 7d).

Fees: **Intro 2 — 0.8% taker / 0.4% maker**. Round-trip market ≈ **1.6%** before edge. Limit-first is the only honest fee lever.

Detector honesty: OHLCV last **2026-09-02**, `lag_days=7`, `gap_days_not_filled=6`. Flat label may be stale. Do **not** thaw bull on this meter.

### Already done this session (uncommitted)

- Ratchet: ignore ghost `existing_stop` on fresh buys; reject stale-low anchors; `open_only` registry.
- Closed 173 ghost LINK registry opens.
- Backfilled missing LINK BUY `9e64ad6c` (6.24 @ 12.004).
- TE ledger journal logging + exchange client resolution.
- Trades UI: crypto first, cash moves separate, dust hidden.
- Isolation: `scripts/phase6/test_isolation_sl_floor_ratchet.py` PASS.
- Runner bounced onto new SL code (pid file `logs/phase6_runner.pid`).

**Not done:** 72h post-SL still failed this morning on ARCH-4 tryout; `market_fallback_max_usd=75` on limit-first; dual_peak live sell journal follow-up; commit of WT; sweet-rule still shadow.

---

## Must not touch (until named in Brad go)

- Live orders, LINK flatten, PAXG E1, USDC park amount
- Auto-promote sweet_A48 / stand-down C / cream / ladder
- `enforce: false` on regime-cash
- Raising tryout above $75 or same-day seat pile-on
- Grinding volume to unlock Advanced 1 (negative EV at 0.8% taker)
- New indicator mashups / MACD-class OPT

---

## Diagnosis in one paragraph

The platform is not missing a secret entry. Closed months miss 5% because **SL banks red faster than TP banks green**, amplified by **post-TP rebuy, post-SL reentry, pile-on, elevated-RSI large tickets**, plus **engineering that tightens stops on fresh lots** and **skips the 72h block on tryout**. Reliability patches (ledger, TP bind, ratchet, limit-first) were the right *class* of work; ratchet + tryout bypass turned them into **process tax**. Optimization = **close those holes**, then **sit in flat B** with $75 tryouts that are actually blocked after SL/TP.

---

## Recommended tactic lock (go/no-go)

| # | Tactic | Rec | Why |
|---|--------|-----|-----|
| T1 | Keep flat B, $75 tryout, max 2 new seats/day | **Keep** | Size is not the 5% gap; churn is |
| T2 | Pause **new** LINK seats until 72h clock from last SL (this bag may ride) | **Yes** | 3d wound + 12h reentry; leave current lot |
| T3 | Enforce 72h post-SL + 24h post-TP on **ARCH-4 / quality_tryout / limit-first**, not only capital_events | **Yes — P0** | Config already 72h; path hole is the bug |
| T4 | Live-gate `sweet_A48_B_large_D` | **No — shadow** | CF is association not FIFO; `ATTENTION_ONLY`; n_block=23 |
| T5 | Keep limit-first; **remove tryout market fallback $75** or log it as explicit IOC | **Remove fallback** | Contradicts skip-unfilled doctrine; small seats become taker churn |
| T6 | Keep live TP trail 4/2 + fixed 6% | **Keep** | Aug TP was the only green exit bucket |
| T7 | Ratchet stays on for **continuous bags only** (code already gated) | **Keep gated** | XLM-style lock is the original intent |
| T8 | Cap SSOT: `global_settings.rebalance_cap_usd=150` vs live policy **$75** | **Document + align to 75** | Dual SSOT is how “cap ignored” bugs start |
| T9 | Commit today’s ratchet/UI/ledger WT | **Yes** | Otherwise next backup is the only history |

---

## Phase 0 — Proof the closeout is real (no book change)

**Objective:** Evidence pack before any new tactic.

**Files:** `docs/plans/2026-09-09-platform-opt-after-3w-patches.md` (this), uncommitted diffs.

**Steps:**

1. Isolation already run: `PYTHONPATH=. python3 scripts/phase6/test_isolation_sl_floor_ratchet.py` → `PASS sl_floor_ratchet isolation`
2. `PYTHONPATH=. python3 phase6/core/test_isolation_ledger_write_path.py` → PASS
3. Curl trades grouping: `/api/trades` `grouping=trades_then_cash_dust_hidden`; top crypto row LINK BUY 6.24
4. Confirm runner pid live: `ps -p $(cat logs/phase6_runner.pid)`
5. Commit allowlisted code only (no `data/`, no ledger JSONL): ratchet, coordinator, manager, registry helper, dashboard, TE, isolation test

**Proof:** `git log -1 --stat` shows those files; isolation re-PASS.

---

## Phase 1 — P0 process-tax holes (code)

### Task 1: 72h post-SL on ARCH-4 / tryout

**Objective:** A pair that just `stop_loss_exchange` cannot `quality_tryout` / `rebalance_buy` for 72h.

**Files:**
- Modify: `phase6/core/rebalance_coordinator.py`
- Modify: `phase6/core/runner_capital_events.py` (`_get_recently_stopped_pairs` must see `stop_loss_exchange`)
- Modify: `phase6/core/regime_cash_policy.py` / `evaluate_buy_entry` buy_block
- Test: `scripts/phase6/test_isolation_stop_exchange_disposition.py` + new case `test_arch4_tryout_respects_72h_sl_block`

**Failing test idea:**

```python
def test_arch4_tryout_blocked_within_72h_of_stop_loss_exchange():
    # ledger SELL LINK stop_loss_exchange 12h ago
    # plan action quality_tryout / rebalance_buy LINK $75
    # apply_to_runner_plan / filter → BUY dropped, reason includes sl_rebuy_block
```

**Implement:** One choke in `evaluate_buy_entry` / `collect_buy_block_pairs` so ARCH-4 cannot bypass capital_events. Restart runner after merge.

**Proof:** Isolation PASS; log line `[REGIME-CASH] BLOCK BUY LINK-USD reasons=[...sl...72h...]` on a dry replay of this morning.

### Task 2: Same-session / same-day re-seat

**Objective:** No second LINK (or any alt) tryout within 24h of a SL **or** a BUY on that pair (Brad: no same-day flip pile-on).

**Files:** `phase6/core/run_lifecycle.py` or `rsi_primary_deploy.py` day-seat pace; `evaluate_buy_entry`

**Test:** two BUY plans same UTC day same pair → second blocked `same_day_pair`.

### Task 3: Limit-first fallback honesty

**Objective:** `market_fallback_max_usd=75` either **deleted** (unfilled=skip) or renamed + logged `[LIMIT-FIRST] tryout_ioc` so we do not pretend maker.

**Files:** `config/trading_config_phase6.json` `entry_execution.limit_first`; `phase6/core/limit_first_buy.py`; `phase6/core/test_isolation_limit_first_buy.py`

**Rec:** delete `market_fallback_max_usd`; keep `market_fallback: false`. Small unfilled tryout **skips** until next slot — cheaper than 0.8% + 3% SL.

### Task 4: Ghost registry hygiene

**Objective:** On pair **flat** (exchange qty dust), close leftover `status=open` registry rows so ratchet cannot see them even if `open_only` regresses.

**Files:** `phase6/core/protective_orders_registry.py`; call from fill-recon after SL/TP; isolation.

---

## Phase 2 — Tactics (knobs, still no book)

Only after Phase 1 isolation + runner restart.

| Knob | Action |
|------|--------|
| `buy_block_pairs` | Add **LINK-USD** until 72h after 2026-09-09T04:07Z SL **or** until Brad clears (current long may stay) |
| `global_settings.rebalance_cap_usd` | Set **75** to match live policy (now 150 vs 75) |
| `post_tp_block_rebuy_hours` | Keep 24; verify tryout path (Sep 8 TP → Sep 8 21:01 rebuy was ~24.0h on the nose — treat as **block if <24h+1s**, not equal) |
| `sl_ratchet.enabled` | Keep true |
| Live TP | Keep live |
| UNI/RAVE | Stay blocked |

**Proof:** `data/state/regime_cash_status.json` cap 75; buy_block includes LINK; no new LINK BUY in ledger for 72h unless Brad go.

---

## Phase 3 — Profitability operating loop (2 weeks)

Not new alpha. Scoreboard only:

1. **Daily:** month_path MTD, process_tax $, same-session wound count, limit-first fill rate, fee USD.
2. **Do not** add seats because util is 6.7% in flat. Idle cash in USDC park is **correct** under B + powder $200.
3. If 14d still red **and** process_tax ≈ 0: then (and only then) staff a **size/util** conversation — not this week.
4. Sweet-rule CF stays **shadow**; if 14d of blocked-would-have-SL with isolation, bring to Brad as less-loss gate — never as printer.

**Commands:**

```bash
python3 -m phase6.research.month_path_scoreboard   # or existing cron script
curl -sS -m 8 http://127.0.0.1:8502/api/metrics
PYTHONPATH=. python3 scripts/phase6/audit_fee_drag_and_entry_labels.py
```

---

## Phase 4 — Code quality debt (scheduled, not same-day)

| Item | Why | When |
|------|-----|------|
| `run_lifecycle` dual_peak live sell → TradeLedger | Independent review residual | Next ledger card |
| Fill-recon `is_coinbase_trading_bot_order` missed limit-first LINK | P0 buy hole | With Task 1 |
| Regime detector OHLCV 7d lag | Flat/bull mislabel risk | Data job, not thaw |
| Daily backup as only history | Feature branches `feat/P6-…` | Starting this plan |
| `live_attach_on_buy: false` while live market TP | TP is software exit not native TP | Document; don’t flip same day |

---

## Proof of done (whole plan)

- [ ] WT committed; isolation ratchet + ledger PASS
- [ ] Isolation: tryout cannot buy within 72h of `stop_loss_exchange`
- [ ] No `market_fallback_max_usd` (or explicit IOC log)
- [ ] Cap SSOT 75
- [ ] Fleet wound 7d count does not increment from a *new* manufactured LINK episode
- [ ] Month-path process_tax MTD stays near 0 (not a print guarantee)
- [ ] Live book unchanged unless Brad names a flatten

---

## Risks

| Risk | Mitigation |
|------|------------|
| Skipping tryouts misses a real ripper | Doctrine: no late FOMO; discovery ≠ seat |
| Gated ratchet fails to lock XLM-style runner | Isolation `test_continuous_bag_keeps_existing`; PAXG path |
| 72h block “too tight” vs 48h CF | Config already 72; CF A72 has higher recall — keep 72 |
| Runner restart mid-slot | Already bounced once today; next restart after Phase 1 only |

---

## Open (Brad)

1. **LINK current 6.24 lot:** ride vs flatten? Rec: **ride** (leave book).
2. **Sweet-rule live?** Rec: **no**.
3. **Limit-first $75 IOC fallback?** Rec: **delete**.

---

## Awaiting

Brad **go** on Phase 0 commit + Phase 1 code, or adjust T2–T5.
