# Final report — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

**Trial:** Polymarket influence re-run post sensor fix (bad 024 meter data)  
**Window:** 2026-09-02 22:00 UTC → 2026-09-16 final_at (scored through 2026-09-19 stamps)  
**Kind:** offline_analysis · observe-only · **live promote blocked**  
**As of:** 2026-09-19  
**Machine scoreboard:** `reports/POLYMARKET_INFLUENCE_RERUN_20260902.md` · `data/state/analyst_polymarket_influence_rerun_20260902_latest.json`

---

## Go / no-go (read this first)

| Question | Answer |
|----------|--------|
| Did we fix the broken meter that killed 024? | **YES** — post-fix bias has real range (not stuck at 0.5). |
| Do we have enough joined crypto exits to claim “Polymarket bias lifts sell PnL”? | **NO** — sparse crypto N; **zero** risk_on-bucket exits in window. |
| Wire bias into allocator / live haircuts? | **NO-GO** (protocol + evidence). |
| Keep the sensor running as a sideboard? | **Reasonable** (observe-only). |
| Proposed decision enum | **`continue_observe_only`** |
| Outcome class | **`inconclusive_sparse_N`** |
| Follow-on | **`none`** (or optional later extend if you want more crypto exits under risk_on regimes) |

**One-line:** Meter is healthy now; **edge is unproven** because the book barely produced crypto exits while bias was mostly risk_off — not because the sensor is stuck again.

---

## Why this trial existed

Parent **ANALYST-20260627-024** was sealed **`sensor_degenerate`**: `risk_on_bias` stuck at **0.5** (Gamma `outcomePrices` JSON-string parse + polarity). That was a **bad meter**, not a clean “no edge” study.

This re-run only scores stamps **after** `fix_cutoff_utc = 2026-09-02T22:00:00+00:00`. Historical stuck rows were **not** rewritten.

---

## What we measured

### A) Sensor health (primary process goal) — PASS

| Metric | Need | Got | Pass |
|--------|------|-----|------|
| Post-fix influence snapshots | ≥10 | **52** | yes |
| Unique bias (3dp) | ≥5 | **40** | yes |
| Bias stdev | ≥0.02 | **0.060** | yes |
| Stuck at 0.5 | forbid | **false** | yes |
| Bias min / max / mean | range | **0.316 / 0.652 / 0.367** | yes |
| Preflight code | `sensor_ok` | **`sensor_ok`** | yes |

Health cron view matches: meter has range.

### B) Join / scoreboard (edge claim) — FAIL bar (sparse)

Protocol freeze: `min_joined_sells ≥ 15` and lift needs **risk_on n≥5** and **neutral n≥5**.

| Slice | n sells | n joined (bias ≤24h of exit) | Notes |
|-------|---------|------------------------------|-------|
| All ledger sells post-cutoff | 20 | **20** (100%) | Includes USDT/USDC park/rotation noise |
| **Crypto only (ex-stables)** | 10 | **10** | **All LINK-USD** |
| risk_off bucket | — | 8 crypto / 16 all | Dominant regime in window |
| neutral bucket | — | 2 crypto / 4 all | Below bar |
| **risk_on bucket** | — | **0 / 0** | **No coverage — lift bar impossible** |

**Crypto-only bucket means (honest sideboard, not a promote claim):**

| Bucket | n | WR | mean PnL $ | sum $ | What it mostly is |
|--------|---|----|------------|-------|-------------------|
| risk_off | 8 | 0.0 | −0.50 | −3.97 | LINK rotation $0 + two SL hits |
| neutral | 2 | 1.0 | +2.27 | +4.55 | LINK fixed-TP win (~+$4.54) + dust |
| risk_on | 0 | — | — | — | **empty** |

So the “neutral looks better” line is **one good LINK TP**, not a Polymarket regime edge. Do **not** read this as HIT.

### C) Process bug found while closing (fixed for this score)

Sell loader only read `realized_pnl*` / `pnl_usd` and missed ledger field **`pnl`** → first final attempt showed **0 joined** despite 20 sells. Fixed in `run_polymarket_influence_backtest.py` before this packet. Without that fix the trial would have died as false `sensor_thin`.

---

## Success criteria vs result

| Gate (frozen) | Result |
|---------------|--------|
| `sensor_preflight_ok` | **PASS** |
| min unique / stdev / not-all-0.5 | **PASS** |
| min_joined_sells ≥ 15 | **PASS on all-sells (20)**; **FAIL on crypto-only (10)** — call sparse for *edge* |
| min_join_rate ≥ 0.10 | **PASS** (1.0 in window) |
| lift: risk_on mean − neutral ≥ 0 with n≥5 each | **FAIL** (risk_on n=0) |
| `live_promote_allowed` | **false** (unchanged) |

**Outcome class:** `inconclusive_sparse_N`  
**Runner recommendation:** `continue_observe_only`  
**Not:** HIT / ATTENTION_ONLY / promote_* 

---

## Plain-English story

1. **024 failed the instrument.** Re-run was required so we wouldn’t treat stuck-0.5 as “no edge.”
2. **Instrument is fixed.** 52 post-fix stamps, wide unique bias, health OK. That alone justifies the re-run.
3. **Book did not give the study a fair edge sample.** Window was mostly risk_off bias; crypto exits were almost only LINK; half the “joined sells” are stable rotations with ~$0 PnL.
4. **No allocator story.** Even if someone squints at neutral vs risk_off, N is tiny and risk_on is empty. Protocol says sparse → not promote.
5. **Close the trial with eyes open:** keep metering if useful; do not spend another 14d hoping for risk_on exits unless you explicitly want `extend_trial`.

---

## Recommended decision (for Brad)

| Field | Suggested value |
|-------|-----------------|
| **decision** | `continue_observe_only` |
| **CR** | `NO_CR` (observe / no accept-promote) |
| **follow_on** | `none` |
| **note** | Sensor OK post-fix; edge unproven (crypto n=10, risk_on n=0); no live influence wiring |
| **Alternatives** | `drop` if you don’t want Polymarket sideboard at all · `extend_trial` only if you want another collect window aimed at risk_on regimes + more non-LINK exits · **never** `promote_*` on this packet |

### What “continue_observe_only” means here

- Keep influence stamps / health if already cheap.  
- **No** live allocator haircut, **no** tryout gate, **no** promote.  
- Optional later: separate scoped shadow experiment only after more crypto exits **and** explicit GO.

### What it does **not** mean

- Not “Polymarket helps sells.”  
- Not “reopen 024 as HIT.”  
- Not permission to change live knobs.

---

## Decide command (when you’re ready — after any report edits you want)

```bash
cd /home/brad/projects/crypto-trading-bot
.venv/bin/python3 phase6/research/trial_cycle.py decide \
  ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902 \
  continue_observe_only \
  --note 'Sensor OK post-fix; edge unproven (crypto n=10, risk_on n=0); no live influence wiring' \
  --follow-on none
```

Or `drop` / `extend_trial` with your own note.

---

## Artifacts

| Path | Role |
|------|------|
| This file | Human final report |
| `reports/POLYMARKET_INFLUENCE_RERUN_20260902.md` | Machine scoreboard |
| `data/state/analyst_polymarket_influence_rerun_20260902_latest.json` | Machine JSON |
| `data/state/polymarket_influence_rerun_health_latest.json` | Health |
| `docs/testing/trials/ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_PROTOCOL.md` | Frozen design |
| `docs/testing/decisions/CR_ANALYST-20260627-024_PROCESSED_INCONCLUSIVE.md` | Parent 024 CR |
| `docs/testing/inbox/REVIEW_ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902.md` | Decision ask (after finalize) |

---

## Caveats (top 3)

1. **N is LINK-heavy** — not a multi-pair regime study.  
2. **Stables inflate join counts** — edge reading must use crypto-only.  
3. **risk_on never appeared on exits** — cannot test the interesting arm of the hypothesis in this window.
