# Exit / SL / REGIME-CASH dig — 2026-08-15

**Role:** crypto-analyst (offline + live shadow read)  
**Live writes:** none  
**Follows:** Fib entry shadow `drop` → dig higher-EV path (exits + cash envelope)

---

## 0. Plain English (read this)

**Go/no-go today**

| Question | Call | Why |
|----------|------|-----|
| Flip live take-profit / trail? | **NO-GO** | Shadow day **~9 / 60**. Only **flat** regime collected. Need bull+bear too + Brad OK. |
| Flip auto RSI hard-exit? | **NO-GO** | Operator loop stays. Live SL CF N=4 (2 with prior signal). Tiny $. |
| Change REGIME-CASH / thaw? | **NO-GO** | Flat option B is correct: cap **$75**, RSI≤55, sent≥0.25, enforce on. |
| Biggest money leak right now? | **Exit asymmetry** | Stops bank losses; greens often ride then stop. No live profit bank. |
| Is the map “broken”? | **No** | Logging; LINK/PAXG would-fire in profit *right now* — shadow only by design. |
| Best next move | **Keep collecting** + don’t re-open indicator grids | Weekly SL CF is the watch. After ~45–60d or first non-flat regime: re-score. |

**North star reminder:** better returns **and** less loss. Underwritable ~5%/mo avg. One green 14d is not a strategy win.

---

## 1. What we refreshed today

| Artifact | Result |
|----------|--------|
| `run_sl_exit_counterfactual_report.sh` | **NO-GO live exits — collecting (early)** |
| `run_exit_threshold_regime_study.py 120` | enum **`regime_dependent`** (same family as 2026-08-06) |
| Live `regime_cash_status` | **flat** · deploy · cap $75 · util target 65% · entry RSI≤55 / sent≥0.25 |
| Live `regime_exit_shadow_*` | day **9.01/60** · flat episodes **76** · bull/bear **0** |
| Open would-fire (no order) | **LINK** r≈+15% (TP+trail) · **PAXG** r≈+7.6% (TP) |

---

## 2. Glossary (one line each)

- **SL** — exchange stop ~3% from bag entry; **live**, caps downside.  
- **Shadow TP / trail** — “would have banked +5–6% or trailed”; **log only**, no sell.  
- **Would-fire / episode** — unique pair+kind signal (not every 5‑min tick).  
- **Hard exit** — RSI/sentiment dump proposal; needs **your OK** before auto-sell.  
- **REGIME-CASH** — BTC 30d mood → park vs small deploy envelope (not pair RSI).  
- **Δ$** — if early shadow signal had sold vs actual SL fill (positive = early exit better).

---

## 3. Exit stack truth

### 3.1 Layers (do not conflate)

| Layer | Live default | Policy source |
|-------|--------------|---------------|
| Exchange SL ~3% | **Live** | trading_config risk |
| Regime exit map (flat TP~5% + trail + RSI≥65 watch) | **Shadow** | `regime_exit_policy_map.json` |
| Global shadow TP ~6% | **Shadow**, TG muted | `exit_automation.json` (legacy log) |
| Hard exit RSI/sent | Shadow + **operator_approve** | regime_cash hard_exit |

`live_apply` is hard-blocked on the map. Correct.

### 3.2 Why the book still struggles (economics)

From platform review 2026-08-13 (still the right thesis):

- Realizing sells are **mostly stops** (Exit WR ~12%).  
- Rotations bank some green; **no live TP** means winners often don’t lock.  
- Re-entry churn recycled losses; **armed-stop race fix shipped** (2026-08-13) — keep watching same-session BUY→SL = 0.

Today’s open book is the poster child:

| Pair | Mark r (approx) | Shadow signal |
|------|-----------------|---------------|
| LINK | **+15%** (peak ~+17.6%) | fixed_tp + trail would-fire |
| PAXG | **+7.6%** (peak ~+8.2%) | fixed_tp would-fire |
| Others | small / flat | — |

That is **not** “map failed.” That is **policy: shadow only until multi-regime collection.**

### 3.3 Live SL counterfactual (clean clock ≥2026-08-06)

| Leg | SL | Prior shadow? | Best early vs SL |
|-----|-----|---------------|------------------|
| OP 2026-08-09 | −1.69% (−$1.56) | RSI hard-exit @ +1.14% | **+$2.09** |
| UNI 2026-08-11 | −4.17% (−$6.31) | RSI hard-exit @ +2.85% | **+$10.62** |
| RAVE ×2 | −1.7% / −5.1% | none | n/a |

- Sum Δ if best early taken on legs with signal: **~$+12.71**  
- N=4 SL legs, 2 with prior signal → **directionally interesting, statistically thin**  
- Does **not** unlock auto hard-exit or live TP

### 3.4 Offline path study (120d ledger legs, refreshed)

Enum: **`regime_dependent`** — forbid one global TP/RSI live flip.

| Regime | N | Call | Read |
|--------|--:|------|------|
| Bear | 21 | **prefer_sl_ride** | Early TP/RSI hurt or no lift — ride stop |
| Bull | 21 | **prefer_tp_tp_06** | ~6% TP beat SL-only on path |
| Flat | 35 | **prefer_tp_tp_05** | ~5% TP beat SL-only on path |

Pooled “best RSI 60” is **not** a license for global auto hard-exit — bear cell says ride SL; map already separates knobs.

Cached TP path study (2026-08-05, 60d): ~**59%** of loss legs touched +6% first (`design_shadow`). Supports *collecting* TP evidence, not flipping today.

---

## 4. REGIME-CASH (entry envelope — keep)

**Now:** flat · BTC 30d ≈ **−1.2%** · deploy · cap **$75** · util target **65%** · entry RSI≤**55** / sent≥**0.25** · enforce **true**.

| Temptation | Call |
|------------|------|
| Raise cap / util because 14d green | **No** — micro thaw only after evidence clocks; 14d is noise |
| Treat pair RSI heat as risk-on | **No** — pair bullish ≠ thaw |
| Park everything (full USDC) | **No** unless trend-repair T0 escalates; flat B is intentional cautious deploy |
| Fib / new indicator entry grid | **Drop** (prior dig) |

Cash layer is **working as designed**. Profitability gap is **not** “wrong park switch” — it’s **exit one-sidedness + legacy churn**.

---

## 5. Collection gates (before any live profit talk)

From map promotion + skill:

| Gate | Need | Have (2026-08-15) |
|------|------|-------------------|
| Calendar shadow days | ~60 (early flag 45) | **~9** |
| Episodes / regime | ≥5 unique | flat **76** · bull **0** · bear **0** |
| Closed legs after signal / regime | ≥15 hint | flat **0/15** closed-after-signal |
| Multi-regime | bull+bear+flat | **flat only** |
| Offline study | regime_dependent OK | refreshed **aligned** with map knobs |
| Brad OK | required | not asked |

**Regimes ready hint:** 1/3 (flat only).

---

## 6. Ranked actions (profitability)

| # | Action | When | Live? |
|---|--------|------|-------|
| 1 | **Keep shadow map + weekly SL CF** (Sun cron) | ongoing | no |
| 2 | **Do not** live TP / trail / hard-exit auto | until gates + Brad | no |
| 3 | Watch open **LINK / PAXG** peaks vs eventual exit reason | each week | observe |
| 4 | Keep **armed-stop / near-stop** gates; same-session BUY→SL = 0 | ops | already live |
| 5 | REGIME-CASH flat B unchanged | until non-flat + scorecard | no |
| 6 | After first **bull or bear** week with ≥5 episodes: re-run this dig | event | no |
| 7 | At ~45–60d: readiness scorecard → **propose** only | calendar | no |
| 8 | Indicator / Fib / combo entry grids | — | **drop** |

---

## 7. Honesty limits

- Daily OHLCV TP studies are **optimistic** on same-bar touch; SL wins ties.  
- Live Δ$ on 2 legs can be **selection luck** (LINK RSI spam episodes ≠ independent N).  
- Would-fire **ticks** (15k+) ≠ episodes (76). Use episodes.  
- Absolute long-tape “enter daily + 3% SL” sims are churn junk for entry research; exit digs use **ledger legs + path**.  
- Sticky hold / util overshoot are **less-loss / leftover bags**, not proof REGIME-CASH is wrong.

---

## 8. Recommendation enum

`continue_observe_only`

- **Not** `promote_*`  
- **Not** `propose_scoped` live TP  
- **Not** regime-cash thaw  
- Sibling Fib entry: already **`drop`**

---

## 9. Paths

| Piece | Path |
|-------|------|
| This dig | `reports/EXIT_SL_REGIME_CASH_DIG_2026-08-15.md` |
| SL CF | `reports/SL_EXIT_COUNTERFACTUAL_LATEST.md` |
| Offline thresholds | `reports/EXIT_THRESHOLD_REGIME_STUDY_2026-08-15.md` |
| Map config | `config/regime_exit_policy_map.json` |
| Collection | `data/state/regime_exit_shadow_collection.json` |
| Prior readiness | `reports/OPT_EX_01_EXITS_2026-08-13.md` |
| Platform thesis | `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md` |

---

*No live config, TP, hard-exit, or REGIME-CASH writes from this dig.*
