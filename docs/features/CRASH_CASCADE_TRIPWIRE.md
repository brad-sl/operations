# Crash Cascade Tripwire — Live Production

**Live status:** ✅ ACTIVE  
**Brad GO:** 2026-10-29  
**Tier 2A (freeze + alert):** LIVE  
**Tier 2C (auto-flatten):** SHADOW (no auto-liquidate without explicit GO)

---

## Purpose

**Detect systemic BTC+ETH air-pocket crashes in progress** and freeze adds before cascading losses extend to SL. Market-triggered recovery (not time-bound) re-arms the seeder once tape stabilizes.

**Not:** A news-based detector (Binance theft, headlines). **Is:** A tape-based cascade alarm.

---

## Tripwire Tiers

### Tier 0 (Always-on, low trigger)
- **Condition:** Any BTC *or* ETH 1h return ≤ **−1.5%**
- **Action:** Freeze seeder (`data/state/c2_ballast_seeder_KILL`), prevent new adds
- **Cost:** False positive on normal 1h volatility

### Tier 1 (Systemic confirm)
- **Condition:** Both BTC *and* ETH in same hour ≤ **−2.0%**  
  **OR** both 4h returns ≤ **−3.5%**
- **Action:** Alert + freeze (same as Tier 0, but higher confidence)

### Tier 2A (Ops triage loop)
- **On trip:** Telegram alert with snapshot (held pairs, book notional, tape context)
- **Recommendation:** Immediate triage + optional hard risk cut

### Tier 2C (Auto-flatten, shadow by default)
- **Config:** `config/crash_cascade_tripwire.json` → `tier2_auto_flatten: false`
- **To enable:** Set `tier2_auto_flatten: true` + Brad GO
- **Action:** Protected market exit BTC+ETH full, leave PAXG

---

## Recovery Path (Market-Triggered)

Once tripped, system arms recovery waiting (`data/state/crash_cascade_recovery_armed`).

### Recovery gate
- **Condition:** Dual reversal — both BTC *and* ETH 1h ≥ **+1.5%** from trip low
- **OR:** Time window expired (24h default), auto-disarm
- **Action:** Kill `recovery_armed` flag, remove seeder KILL, re-enable ballast seeder

### Why market-triggered?
Panic dumps often recover in **4–8h**. Time-bound (e.g. 48h cooldown) misses quick bounces and loses ~0.5–1% of edge. Tape reversal = actual market behavior, not calendar.

---

## State & Receipts

| File | Purpose |
|------|---------|
| `data/state/crash_cascade_tripwire_KILLED` | Manual kill switch (prevent all tiers) |
| `data/state/crash_cascade_recovery_armed` | Recovery gate active (re-arm on dual reversal) |
| `data/state/crash_cascade_tripwire_latest.json` | Last trip snapshot (tier, signal, tape) |
| `data/state/crash_cascade_trip_history.jsonl` | History of all trips + recoveries |
| `config/crash_cascade_tripwire.json` | Live config + thresholds |

---

## How It Works (Runtime)

1. **Every rebalance cycle** (via `phase6/core/rebalance_coordinator.py`):
   - Call `evaluate_tripwire()` — check Tier 0/1 conditions on live 1h Coinbase candles
   - If trip: `execute_tripwire()` — freeze seeder, alert ops
   - Else: `check_recovery_conditions()` — test if armed recovery gate has cleared

2. **On trip:**
   - Seeder KILL stamped (blocks C2 ballast adds)
   - Shell freeze stays active (from Runway C)
   - Telegram alert with context (held pairs, book, signal)
   - Recovery armed

3. **On recovery:**
   - Both BTC+ETH 1h ≥ +1.5% detected
   - KILL file deleted, seeder live again
   - Next rebalance resumes normal ballast adds
   - (Or manual Brad GO after 24h if no recovery)

---

## False-Positive Tax

**Tuning assumptions** (from Oct 29 crash):
- BTC: Worst 1h **−2.48%**, worst 4h **−3.7%**, peak→trough ~9h **−5.6%**
- ETH: Worst 1h **−3.36%**, worst 4h **−4.0%**, peak→trough ~9h **−6.6%**
- Detected at **~20:00Z** (4h after hard leg), saved **~3–5%** vs ride to −8% SL

**Daily occurrence** of BTC −2% 1h = ~2–3 false trips/year if single-leg trigger.  
**Dual Tier 1 filter** (both coins same hour) cuts FP rate to **<1 per year**.

---

## Config & Tuning

`config/crash_cascade_tripwire.json`:

```json
{
  "live_apply": true,
  "tier0_threshold_pct": -1.5,
  "tier1_dual_1h_pct": -2.0,
  "tier1_dual_4h_pct": -3.5,
  "tier2_freeze_adds": true,
  "tier2_auto_flatten": false,
  "recovery_reversal_pct": 1.5,
  "recovery_window_hours": 24
}
```

**To tighten (fewer FP):** Raise `tier1_dual_1h_pct` to −2.5%, raise `tier0_threshold_pct` to −2.0%.  
**To loosen (catch earlier):** Lower both, but expect more noise.

---

## Interaction with Other Guards

| Feature | Status | Notes |
|---------|--------|-------|
| **8% SL (default)** | Active | Tripwire fires before SL; still the hard floor |
| **Shell Freeze (Runway C)** | Active | Shells already frozen; tripwire adds no new pairs |
| **C2 Ballast Seeder** | Frozen on trip | Resumed on market recovery |
| **Vol-Risk Scalar** | Shadow only | No live bind (separate monitoring) |
| **RSI/Sent gates** | Active | Standard regime policy applies to new entries |

---

## Manual Controls

**Disable tripwire entirely:**
```bash
touch data/state/crash_cascade_tripwire_KILLED
```

**Re-enable after manual kill:**
```bash
rm data/state/crash_cascade_tripwire_KILLED
```

**Force recovery (skip waiting):**
```bash
rm data/state/crash_cascade_recovery_armed
```

**Enable auto-flatten (Tier 2C live):**
1. Edit `config/crash_cascade_tripwire.json`: `tier2_auto_flatten: true`
2. Brad GO explicit in Telegram or here
3. Next trip will auto-exit BTC+ETH full

---

## Alerts & Triage

On trip, Telegram alert includes:
- Tier number + signal (which leg, % drop, duration)
- Held pairs + book notional USD
- Recommendation (freeze stays, recommend ops review)
- Recovery gate (when dual reversal ≥ +1.5% or after 24h)

**Ops response:** Review tape context, confirm no structural break, decide GO for hard flatten if needed (Tier 2C) or wait for market recovery.

---

## Limits & Caveats

- ✅ Detects **cascade in progress** (not news)
- ✅ Saves **3–5% vs SL** if it fires
- ✅ Market-triggered recovery (no false cooldowns)
- ❌ Cannot predict **when** crash starts
- ❌ Single-leg crashes (only alt down) will not trip Tier 1
- ❌ Slow bleed (−0.2%/h for days) is a **regime** issue, not tripwire

---

## Verification

Live on production:
- Tripwire evaluates every rebalance tick (~2–5m)
- Recovery checks same frequency
- **No shadow-only mode** (Tier 2A alert + freeze are live immediately)

**Test:** `python3 scripts/phase6/test_isolation_crash_cascade_tripwire.py` (PASS)

---

## References

- **Source:** `phase6/core/crash_cascade_tripwire.py`
- **Integration:** `phase6/core/rebalance_coordinator.py` (line ~269)
- **Config:** `config/crash_cascade_tripwire.json`
- **History:** `data/state/crash_cascade_trip_history.jsonl`
- **Oct 29 event:** Triggered at ~20:00Z, recovered ~00:00Z next day (market stabilized)
