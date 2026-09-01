# Limit-first (maker-preferring) buy — design

**Status:** Phase **D pilot LIVE** · mode=`limit_first_v1` · enabled=**true** · caps **3 buys / $300/day**  
**As of:** 2026-08-31  
**Owner context:** Fills dig + fee tier Intro 2 (taker 0.8% / maker 0.4%)  
**Related:** `reports/FILLS_MARKET_PATH_DIG.md`, C stand-down shadow, `docs/COINBASE_FEE_RESEARCH.md` (superseded on rates/path)

### Brad decisions locked (2026-08-31)
1. **Unfilled → skip** (no market fallback)
2. **Pilot universe → full basket** (when Phase D enabled)
3. **fill_wait_s = 45** OK
4. **Start Phase A/B now** (shipped) → C shadow → **D GO this session**

### Implementation map
| Piece | Path | Live effect |
|-------|------|-------------|
| Fee tier snapshot | `phase6/core/fee_tier_snapshot.py` | Read-only |
| Policy helpers | `phase6/core/limit_first_buy.py` | Pure |
| Client | `place_limit_buy` / `get_order` / `get_best_bid_ask` | Used when pilot slot open |
| Executor | `OrderExecutor.execute_buy` limit branch | **ON under caps** |
| Platform path | `TradeExecutor` → delegates to OrderExecutor when limit-first ON | **Wired** |
| Pilot controls | `phase6/core/limit_first_buy_pilot.py` | Caps + kill file |
| Config | `entry_execution.mode=limit_first_v1`, `enabled=true` | **Pilot** |
| Isolation | `test_isolation_limit_first_buy*.py` | PASS |

### Phase C shipped
Shadow CF board still runs (market-buy fee Δ upper bound).

### Phase D shipped (2026-08-31)
| Control | Value |
|---------|-------|
| mode | `limit_first_v1` |
| enabled | **true** |
| post_only | true · bid · 45s · skip unfilled |
| pilot_max_buys_per_day | **3** |
| pilot_max_usd_per_day | **300** |
| over-cap / kill | → **market IOC** (legacy), not total buy block |
| kill switch | `data/state/limit_first_buy_KILL` or `LIMIT_FIRST_BUY_KILL=1` |
| park/USDC convert | `force_market=True` |
| elevated tape | abort (C shadow best-effort) |
| board | `reports/LIMIT_FIRST_BUY_PILOT_LATEST.md` |
| runner | restarted with TradeExecutor↔OrderExecutor wire |

**Still NO:** Phase E promote. Review after ≥30 limit attempts or 14d. Cost-cut only — not alpha.

---

## 0. Plain English

**What:** Prefer resting **limit buys** so entry can pay **maker (0.4%)** instead of **taker (0.8%)** on this account.

**What it is not:**
- Not a signal upgrade
- Not a money printer (exits still mostly taker; churn still dominates)
- Not “flip a config flag” alone — needs Phase D GO + fill-rate review
- Not mandatory fill — unfilled / partial is a first-class outcome (**skip**)

**GO/NO-GO live pilot:** **NO** until Brad Phase D GO after Phase C shadow (optional) + review.

**Honest EV ceiling (Intro 2, buys only):** ~0.4% of buy notional if *every* buy rests as maker. 30d fantasy ~$40 on this book. Round-trip still ~1.2% if exit is taker (vs 1.6% today).

---

## 1. Why this feels “only now discovered” (postmortem)

| Layer | What people believed | What was true |
|-------|----------------------|---------------|
| `docs/COINBASE_FEE_RESEARCH.md` (2026-03-29) | “We use **limit orders** → maker fee” | **Aspiration written as fact** |
| `config_loader` fee constants | Advanced 1: 0.25% / 0.40% | **Stale** vs live **Intro 2: 0.4% / 0.8%** |
| `config_loader.order_type` | Looks configurable | **Hardcoded `"market"`** |
| `OrderExecutor.execute_buy` | — | **Always** `place_market_buy` → `market_market_ioc` |
| `CoinbaseExchangeClient.place_*` | Full order toolkit | market buy/sell, stop-limit sell, bracket — **no limit buy** |
| Legacy `coinbase_wrapper_FIXED.place_limit_buy` | Exists | **Off Phase 6 path**; never called by executor |
| Verified fills 90d | — | MARKET + STOP_LIMIT only; median fee **0.8% = live taker** |

**Root cause:** Early stack optimized for **deterministic rebalance completion** (IOC market fill → attach SL). Fee research and constants described the **desired** economics; the executor implemented the **reliable** path. No automated check ever asserted “order_type on fills ⊆ maker.” Fee drag only became impossible to ignore once NAV-relative house cut (~6%/mo) was measured on **this** book.

**Not a secret regression.** It was never wired. Discovery lag = missing fill-path invariant + stale authoritative fee doc.

---

## 2. Goals / non-goals

### Goals
1. Resting limit buy path that can earn **maker** fee when it rests.
2. Explicit outcomes: `filled_maker` | `filled_taker_cross` | `partial` | `unfilled_cancelled` | `fallback_market` | `aborted`.
3. SL/TP attach only on **verified filled size**, never on requested size.
4. Shadow mode that logs would-be limit vs actual market (counterfactual fee) without orders.
5. Feature flag default **OFF**; live requires Brad GO + pilot cap.

### Non-goals
- Maker exits for SL (stop-limit is taker by nature when triggered).
- Churning volume to reach Advanced 1.
- Replacing C stand-down (elevated tape still hostile — limit-chasing a rip is worse).
- Guaranteeing fill within rebalance window.
- Multi-reprice loops that look like spoofing / burn rate.

---

## 3. Current vs target flow

### Current (live)
```
rebalance / trade plan
  → OrderExecutor.execute_buy(pair, usd)
      → place_market_buy (market_market_ioc, quote_size)
      → fetch_verified_order_fill
      → stop_loss_manager.attach_stop_loss(filled)
```

### Target (flag ON, after GO)
```
rebalance / trade plan
  → OrderExecutor.execute_buy(pair, usd, policy=...)
      → if policy.limit_first and not force_market:
          place_limit_buy (post_only? , price, base_size from usd/px)
          wait up to T_fill (poll order status)
          if filled (full or partial ≥ min):
              cancel residual if any
              verify fill → attach SL on filled only
              record liquidity + fee
          elif policy.market_fallback:
              cancel resting
              place_market_buy(residual_usd)   # explicit taker, tagged
          else:
              abort buy (cash stays) — preferred default for non-urgent
      else:
          place_market_buy  # legacy path
```

---

## 4. API / module design

### 4.1 `CoinbaseExchangeClient` additions

```text
place_limit_buy(
  product_id,
  base_size: float,          # quantized
  limit_price: float,        # quantized
  *,
  post_only: bool = True,    # default True = reject if would take
  time_in_force: "GTC" | "GTD",
  cancel_after_s: optional for GTD if API supports
) -> {success, order_id, error, post_only, raw}

get_order(order_id) -> full order dict (status, filled_size, avg price, completion %)
cancel_order(order_id) -> already exists
```

**Implementation note:** Port shape from `coinbase_wrapper_FIXED.place_limit_buy` (`limit_limit_gtc`) onto `CoinbaseExchangeClient`, add `post_only` if Coinbase field supported (`post_only: true` on limit config — verify against current Advanced Trade schema at implement time). Do **not** call legacy wrapper from executor long-term; one client.

**Quote vs base:** Market buys use `quote_size` (USD). Limits typically need `base_size` + `limit_price`. Derive:
```text
px = mid or bid (see pricing)
base = quantize_size(usd_amount / px)
```
Recompute notional = base * fill_px after fill; never assume full usd deployed.

### 4.2 Pricing policy (frozen knobs — pre-register before shadow)

| Knob | Default (proposal) | Meaning |
|------|--------------------|---------|
| `limit_price_ref` | `bid` | Buy at bid (more maker-likely) vs `mid` vs `ask-1tick` |
| `limit_offset_bps` | `0` | Optional under-bid (more passive) or through-spread (more fill, risk taker) |
| `post_only` | `true` | If would take, exchange rejects → treat as no-cross; optional one requote |
| `fill_wait_s` | `45` | Max rest time before cancel (rebalance must not hang forever) |
| `poll_interval_s` | `2` | Status poll |
| `min_fill_usd` | `10` | Below this → cancel + no SL junk |
| `partial_policy` | `keep` | `keep` filled + cancel rest · `cancel_all` rare |
| `market_fallback` | `false` | **Default false** — unfilled = skip (preserves “don’t pay taker to force”) |
| `market_fallback_when` | `none` | Optional later: `rebalance_urgent` only under explicit plan flag |
| `force_market_reasons` | `{dust, park, protect_exit_related}` | Never limit these |
| `elevated_tape_policy` | `abort` | If C primary (r24≥5): **do not** limit-or-market enter (aligns C) |
| `max_requotes` | `0` | v1: zero requotes (no chase). v2: at most 1 mid reprice |

**v1 recommendation:** `post_only=true`, `market_fallback=false`, `max_requotes=0`, `fill_wait_s=45`, price=`bid`. Accept lower fill rate; measure it.

### 4.3 `OrderExecutor.execute_buy` contract extension

Return dict **gains** (backward compatible):
```text
success, order_id, entry_price, size, qty,
execution_style: "market_ioc" | "limit_post_only" | "limit_gtc" | "market_fallback",
liquidity: "M" | "T" | "mixed" | "unknown",
fee_usd, fee_pct,           # if exchange returns
fill_status: "full" | "partial" | "none",
limit_order_id, residual_cancelled: bool,
actual_fill_used, fill_verified,
sl_attached, tp_attached,
pair, action, side
```

Ledger / reconcile must persist `execution_style` + `liquidity` so next fee audit is not heuristic-only.

### 4.4 Settlement ownership (keep existing invariant)

- **Do not** add a second settlement poll owner.
- Limit path: poll **order status** until terminal or timeout → cancel → `fetch_verified_order_fill`.
- SL attach still owned by `stop_loss_manager.attach_stop_loss` with verified fill only (ENG-S3-*).
- Partial fill: SL size = **filled_size only**.

### 4.5 Cancel / race safety

1. Timeout → `cancel_order` → re-fetch order (fill may race cancel).
2. If fill landed during cancel: treat as filled; never double-market the same usd.
3. Client order ids unique; idempotent ledger by `order_id`.
4. Rebalance plan: if buy aborts unfilled, **do not** invent success; allocator sees residual cash next cycle.

---

## 5. Interaction with other arms

| Arm | Rule |
|-----|------|
| **C stand-down** | If elevated primary, **abort** entry (limit or market). Maker fee does not fix toxic late process. |
| **SL** | Unchanged stop-limit sells (taker on trigger). Out of scope for maker. |
| **Protected market exit** | Stays market — urgency > fee. |
| **Preserve / park / dust** | Force market or existing special paths. |
| **Shadow TP / trail** | Unaffected; still after true entry. |
| **Rotation sells** | Still market via protected exit unless separate design later. |

---

## 6. Phased delivery (gates)

### Phase A — Honesty + observability (no behavior change)
1. Mark `docs/COINBASE_FEE_RESEARCH.md` **superseded** on path/rates; point to fills dig + live tier.
2. Fix comments/constants: load fee tier from `transaction_summary` into state (read-only cron ok).
3. Ledger fields: record `order_type` already; add `execution_style` when available.
4. Invariant test: **fail CI** if live executor buy path calls anything other than documented styles.
5. Optional: alert if rolling median fee_pct ≉ live taker (drift).

### Phase B — Client + unit isolation (still no live limit)
1. Implement `place_limit_buy` + `get_order` on `CoinbaseExchangeClient` (shadow simulates rest/fill).
2. Isolation tests: quantize, post_only reject, cancel race, partial SL size.
3. No runner flag on.

### Phase C — Shadow counterfactual (no orders)
1. On each live **market** buy (or rebalance plan), log:
   - would limit price, wait T, assumed fill probability model **or** simply “limit not attempted”
   - fee delta vs maker rate if it had rested
2. Board: `data/state/limit_first_buy_shadow_latest.json` (mirror C shadow pattern).
3. Success metrics: not “saved $” fiction — **fillability proxy** only until paper.

Better shadow: **paper limit** using public book/trades — complex; v1 = fee delta accounting only + fill rate when Phase D pilot runs.

### Phase D — Live pilot (Brad GO required)
1. Flag `entry_execution.mode = limit_first_v1` default off in config.
2. Pilot: **one pair class** or **max N buys/day** + **max usd/day**.
3. `market_fallback=false` initially (measure true rest rate).
4. Kill switch: any unexplained open order count, or fee_pct still 0.8% on “limit” fills → investigate (crossed book / post_only off).
5. Review after ≥30 limit attempts or 14d.

### Phase E — Promote decision
Promote only if:
- Maker liquidity flag or fee_pct ≈ live maker on majority of “limit” fills
- Fill rate acceptable vs allocation drift (define bar with Brad, e.g. ≥40% full fill in 45s **or** accept cash residual)
- No increase in SL attach failures / orphan positions
- Still not claimed as alpha — cost reduction only

Else: keep market path; keep C + turnover work.

---

## 7. Config sketch (not applied)

```json
"entry_execution": {
  "mode": "market_ioc",
  "limit_first": {
    "enabled": false,
    "post_only": true,
    "price_ref": "bid",
    "offset_bps": 0,
    "fill_wait_s": 45,
    "poll_interval_s": 2,
    "min_fill_usd": 10,
    "market_fallback": false,
    "max_requotes": 0,
    "elevated_tape": "abort",
    "pilot_max_buys_per_day": 3,
    "pilot_max_usd_per_day": 300
  }
}
```

`config_loader.get_config()` must **read** this block when implemented — never hardcode `"market"` without reading flag.

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Unfilled → under-deployed book | Accept in v1; track residual cash; optional next-cycle retry **without** chasing |
| Partial fill + SL on full size | SL on filled only; tests |
| post_only reject loops | max_requotes=0; log reject |
| Cancel/fill race double buy | Re-fetch after cancel; single residual_usd path |
| Limit on hot tape = still late | C abort elevated |
| Rebalance wall-clock blowup | hard fill_wait_s; parallel buys need budget |
| Thinking maker = edge | Product copy: cost reduction only |
| Stale fee doc again | Live tier snapshot in state; dig scripts |

---

## 9. Test plan (isolation first)

1. `place_limit_buy` body shape + quantize  
2. post_only rejection → success=false, no ghost id  
3. partial fill → SL size == filled  
4. timeout cancel → no market fallback when flag false  
5. fallback path tags `execution_style=market_fallback`  
6. elevated_tape abort before any place_*  
7. shadow mode never hits REST orders  
8. Executor source invariant: no bare `place_market_buy` without style tag when limit mode on  

---

## 10. Implementation order (when GO)

1. Supersede fee research + tier snapshot cron (A)  
2. `place_limit_buy` + tests (B)  
3. Executor branch behind flag default off (B)  
4. Shadow board (C)  
5. Brad GO pilot (D)  
6. Decide (E)  

**Explicitly out of first GO:** sell-side maker, smart order routing, multi-level ladder.

---

## 11. Why not “just enable legacy limit buy tomorrow”

- Legacy method returns different result shape (`id` vs `order_id`)  
- No post_only, no wait/cancel policy, no partial SL coupling  
- Rebalance assumes fill-or-fail market semantics today  
- Fee research assumed maker without measuring fills — do not repeat  

---

## 12. Success metrics (pre-registered)

| Metric | Window | Attention | Promote-ish |
|--------|--------|-----------|-------------|
| Share of entry notional with fee_pct ≤ maker+0.05% | 30d pilot | >25% | >60% |
| Limit attempt fill rate (full+partial≥min) | pilot | tracked | ≥ bar Brad sets |
| SL attach failure rate vs baseline | pilot | ≤ baseline | ≤ baseline |
| Orphan open entry orders | continuous | 0 | 0 |
| Net fee $ vs baseline (same notional) | 30d | any real save | save > ops cost |
| Abs book return | — | **not** a maker-path promote metric | — |

Edge class: `process_cost_reduction_candidate_not_alpha`.

---

## 13. Open questions for Brad (before any code beyond A)

1. **Unfilled default:** skip buy (recommended) vs market fallback?  
2. **Pilot universe:** BTC/ETH only vs full basket?  
3. **Rebalance SLA:** is 45s rest OK per buy, or need shorter + fallback?  
4. **Priority vs C:** ship C shadow observe longer first, or limit-first design implement in parallel (shadow only)?  

---

## 14. Artifacts

| File | Role |
|------|------|
| This doc | Design SSOT |
| `reports/FILLS_MARKET_PATH_DIG.md` | Why MARKET + live tier |
| `docs/COINBASE_FEE_RESEARCH.md` | Superseded banner (rates/path) |
| `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md` | Discussion log |
| Future: `phase6/core/limit_first_buy.py` | Not created until GO |

---

## 15. Bottom line

Maker-preferring entry is **real engineering**, justified as **toll reduction** on Intro 2 (0.8%→0.4% buy leg), not as alpha. It was “undiscovered” because docs claimed limits while the executor never did — fix the honesty layer first, then build limit-first behind a dark flag. **No live switch in this design pass.**
