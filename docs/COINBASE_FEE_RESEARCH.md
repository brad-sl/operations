# Coinbase Transaction Fee Research

> **SUPERSEDED (2026-08-31) on path + live rates**  
> This doc claimed “we use limit orders → maker fees.” That was **aspiration, not the live executor path**.  
> Baseline live path = MARKET IOC buys/sells + STOP_LIMIT exits.  
> Live account tier (API `transaction_summary`, 2026-08-31): **Intro 2** — taker **0.8%** / maker **0.4%**.  
> Realized fill median fee **0.8%** matches taker.  
> **SSOT now:** `reports/FILLS_MARKET_PATH_DIG.md` · design: `docs/design/LIMIT_FIRST_BUY_DESIGN.md`  
> **Venue mix:** see § *Coinbase volume mix (institutional vs consumer)* below.  
> Tier tables below may also drift vs Coinbase; always prefer live `transaction_summary`.

**Date:** 2026-03-29 (original) · **banner/mix section:** 2026-08-31  
**Source:** Coinbase Exchange API Documentation + Help Center + Coinbase-reported Consumer/Institutional volume  
**Status:** SUPERSEDED on path/rates (kept for history); **venue-mix section is current**

---

## Coinbase volume mix (institutional vs consumer) — 2026-08-31

**Why this section exists:** fee drag and “whale/FOMO” framing only make sense against **who actually trades** and **who pays the take rate**. Brad clarification; Coinbase-reported categories only (no separate “whale” bucket).

### Volume split (stable ~80% institutional since ~2022–2023)

Coinbase reports two categories: **Consumer** (retail) and **Institutional** (Prime, custody, block, professional clients).

| Period | Consumer | Institutional | Inst share of volume |
|--------|----------|---------------|----------------------|
| **FY2025** | $239B | $982B | **~80.4%** |
| **Q4 2025** | $59B | $237B | **~80%** |
| **Q1 2026** | $36B | $166B | **~82%** |
| **FY2023–FY2025 avg** | — | — | **~81.9%** (peak ~**84%** FY2023) |

**Long arc:** Institutional ~**20%** of volume in Q1 2018 → ~**56%** FY2019 → **~80%+** in recent years. Split has been fairly stable since ~2022–2023.

**“Whales”:** not broken out. Most large organized flow sits in **Institutional**. Some high-net-worth individuals remain classified as **Consumer**.

### Revenue vs volume (the part that hits *us*)

| Cohort | ~Share of volume | Effective take rate (2025 figures, as reported) |
|--------|------------------|--------------------------------------------------|
| Institutional | ~80% | ~**5 bps** (0.05%) |
| Consumer / retail | ~20% | ~**1.4%** |

- Smaller **retail** slice generates **most transaction revenue**.
- Our live account = Advanced Trade **Intro 2** (**0.8% taker / 0.4% maker**) → firmly on the **high take-rate / paying-for-the-party** side of the venue, not Prime economics.

### Implications for Phase 6 (honest — not alpha claims)

1. **Whale / FOMO lag as a long signal** — weaker still. Public “size move” lag is often *after* institutional flow already printed; retail FOMO is residue. Prefer **C stand-down** (hostile-tape filter) over chase. See MACRO discussion + `STANDDOWN_FILTER_C_DIG`.
2. **Fee drag is structural** for this book size/tier. Cutting round-trips + maker-preferring buys (limit-first pilot) is **house-tax mitigation**, not edge discovery. Design: `docs/design/LIMIT_FIRST_BUY_DESIGN.md`.
3. **Tier climb to ~5 bps** is volume / Prime economics — **not** a bot feature. Limit-first at best halves the *buy* leg (0.8% → 0.4% if rested); it does **not** get Intro 2 to institutional bps.
4. **No “prints money” revision** from the 80/20 mix. Inst-dominated tape can look “smart” while 0.8% legs still lose. Prior conclusion stands: no method on this book clears ~6% NAV/mo house cut without fewer RTs + lower fees.

**Does not change ops:** leave book as-is unless Brad GO; no whale-follow product; C shadow; limit-first D caps (3 buys / $300/day) + kill file.

**Also logged:** `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md` (2026-08-31 volume-mix note).

---

## Actual Coinbase Advanced Trade Fees (HISTORICAL TABLE — may drift)

### Fee Structure (Tiered by 30-Day Volume)

| Tier | Volume Threshold | Maker Fee | Taker Fee |
|------|-----------------|-----------|-----------|
| **Intro 1 (Base)** | < $1,000 | 0.60% | 1.20% |
| **Intro 2** | $1,000 - $9,999 | 0.35% | 0.75% |
| **Advanced 1** | $10,000 - $49,999 | 0.25% | 0.40% |
| **Advanced 2** | $50,000 - $99,999 | 0.15% | 0.30% |
| **Advanced 3** | $100,000 - $499,999 | 0.10% | 0.25% |
| **Advanced 4** | $500,000 - $999,999 | 0.05% | 0.20% |
| **Pro** | ≥ $1,000,000 | 0.00% | 0.10% |

### Key Points

1. **Maker vs Taker:**
   - **Maker:** Order placed on book that doesn't immediately fill (limit orders) → Lower fee
   - **Taker:** Order immediately filled from existing orders (market orders) → Higher fee

2. **Our Use Case (HISTORICAL CLAIM — FALSE for baseline Phase 6 path as of 2026-08-31):**
   - ~~We use **limit orders** → **MAKER FEE**~~
   - **Baseline actual:** market IOC buys + market/stop-limit sells → **taker** at live Intro 2 (0.8%).
   - **Limit-first Phase D pilot (2026-08-31):** enabled under caps (3 buys / $300/day); unfilled → skip; park forced market. See `docs/design/LIMIT_FIRST_BUY_DESIGN.md`. Not institutional bps.

3. **Applicable Rate for Phase 4:**
   - Expected Phase 4 volume: ~200 trades × $1,000 average = $200K over 30 days
   - **Tier:** Advanced 2 ($50K-$99,999) or Advanced 3 ($100K-$499,999) depending on prior volume
   - **Conservative estimate:** Use **0.25% maker fee** (Advanced 1 minimum, likely will hit Advanced 2/3)

4. **Previous Error:**
   - Used 0.4% (0.004) — this was invented/incorrect
   - Actual fees range from 0.60% (base tier) down to 0% (Pro tier)
   - For Phase 4, realistic rate is **0.25% - 0.35% maker fee**

---

## Fee Calculation (Corrected)

### Formula
```
transaction_fee = (order_price × quantity) × maker_fee_rate
```

### Example: $1,000 Trade at 0.25% Fee
```
Notional: $1,000
Fee: $1,000 × 0.0025 = $2.50 per trade
```

### Expected P&L After Fees

For 10 trades @ $1,000 each with assumed 60% win rate:
```
Gross P&L (before fees):     ~$200 (2% avg win per trade × 10 trades × $1,000)
Total fees (10 trades):      10 × $2.50 = $25
Net P&L (after fees):        ~$175

Result: Gains over $100 after trading fees ✅
```

---

## Code Update Required

**File:** `config_loader.py`  
**Update:**
```python
# OLD (WRONG)
COINBASE_MAKER_FEE_RATE = 0.004  # 0.4% — INVENTED

# NEW (CORRECT - Conservative tier)
COINBASE_MAKER_FEE_RATE = 0.0025  # 0.25% (Advanced 1+ tier)
COINBASE_TAKER_FEE_RATE = 0.0040  # 0.40% (Advanced 1+ tier, emergency only)
```

**Rationale:**
- 0.25% is conservative (assumes Advanced 1 tier minimum)
- Phase 4 volume should reach Advanced 2/3 (0.15%-0.10% maker), so 0.25% is a safe upper bound
- If volume reaches Pro tier (≥$1M), actual fees drop to 0% maker / 0.10% taker

**Adjustment Protocol:**
- Query actual fees via Coinbase `/fees` API endpoint at Phase 4 start
- If actual tier is lower, fees will be LOWER than expected → bonus profit
- If volume doesn't reach threshold, fees will be HIGHER → adjust position sizing

---

## Backtest Recalculation (Corrected)

**Using 0.25% maker fee rate:**

For 14 trades over 48 hours (from real backtest data):
```
Average order size: ~$1,000 notional
Transaction fee per trade: $1,000 × 0.0025 = $2.50

Total fees: 14 trades × $2.50 = $35
Reported P&L (no fees): $99.27
Net P&L (after fees): $99.27 - $35 = $64.27

Win rate: 64.3% (9/14 trades) ✅
Result: Positive P&L after realistic fees ✅
```

---

## Validation Checklist

- [x] Coinbase Advanced Trade fees researched (official docs)
- [x] Actual fee tiers documented (0.60% base → 0% Pro)
- [x] Conservative rate selected (0.25% maker = Advanced 1+)
- [x] Taker fee noted (0.40% for emergencies, not normal use)
- [x] Fee formula verified (notional × rate)
- [x] Example calculations confirmed (60% win rate → $100+ gains)
- [x] Code update identified (config_loader.py)
- [ ] Code updated and tested
- [ ] Backtest rerun with 0.25% fees
- [ ] Phase 4 launch with corrected fees

---

## References

- Coinbase Exchange API: https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/fees/get-fee
- Coinbase Help: https://help.coinbase.com/en/exchange/trading-and-funding/exchange-fees
- API Endpoint: `GET /fees` returns `maker_fee_rate` and `taker_fee_rate` for current user
- Live tier SSOT: `data/state/fee_tier_snapshot_latest.json` · `reports/FILLS_MARKET_PATH_DIG.md`
- Venue mix + product stance: § above · `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md`
- Limit-first design/pilot: `docs/design/LIMIT_FIRST_BUY_DESIGN.md`
