# Protocol — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

**Master task:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902`  
**Kind:** `offline_analysis`  
**Family:** `polymarket_influence`  
**Parent / predecessor:** `ANALYST-20260627-024` (CR inconclusive → sealed as **sensor_degenerate**)  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Created:** 2026-09-02 (Brad GO — re-try on good sensor data)

---

## 0. Why this re-run is required (read first)

**024 is not a clean “no edge” result.** It ran on a **dead meter**.

| Fact | Detail |
|------|--------|
| What 024 saw | `influence_stack_log` risk_on_bias **stuck at 0.5** (unique≈1, stdev=0) for ~168 snapshots; event `yes_p` stamps also collapsed to 0.5 |
| Root cause | Gamma `outcomePrices` often a JSON **string**; naive list index → `'['` → fallback 0.5. Polarity also missed Fed rate-cut framing → many `sent_p=0.5` |
| Process failure | Scoreboard language before **sensor preflight** framed degenerate input like an edge study |
| What was fixed (code) | `_parse_outcome_prices` / `_get_yes_probability` on all paths; polarity keywords; `sensor_preflight.py` + isolation |
| What was **not** fixed | Historical log **not rewritten**. Live overlay can leave 0.5; old rows stay stuck |
| 024 CR | `docs/testing/decisions/CR_ANALYST-20260627-024_PROCESSED_INCONCLUSIVE.md` — **no promote**; class **`sensor_degenerate`** |
| This trial | **New id.** Score **only post-fix stamps** (`sensor_ok` gate). Do **not** reopen 024 as HIT on old log |

**Rule:** Degenerate/broken sensor ≠ inconclusive edge. Re-run needed because **test data (the bias meter) was bad**, not because we disliked the conclusion.

Refs: `phase6/research/sensor_preflight.py`, `test_isolation_sensor_preflight.py`, skill ref `offline-strategy-honesty` → `sensor-preflight-polymarket-024-20260902.md`.

---

## 1. Hypothesis

After the overlay parse+polarity seal, **fresh** Polymarket `risk_on_bias` has real range, and **joined closed sells** (bias ≤24h of exit, preferably entry stamp when available) show **measurable mean-PnL / WR lift** by bias bucket (risk_on vs neutral vs risk_off) — enough to justify **observe-only** allocator attention, **not** silent live promote.

---

## 2. Non-goals

- No live trading config / regime policy / allocator haircut writes without Brad + promotion gates  
- No scoring of **pre-fix** influence rows (treat as contaminated)  
- No invented backfill of historical bias onto old fills  
- Real data only; WR is **secondary** to mean PnL / join honesty  
- Short windows = context only if sparse  

---

## 3. Design

| Item | Value |
|------|--------|
| Control / baseline | neutral bias bucket (0.45–0.55) mean PnL / WR on joined sells |
| Arms / buckets | risk_off &lt;0.45 · neutral · risk_on &gt;0.55 (frozen) |
| Treatment | Polymarket regime bias from fixed overlay (post-2026-09-02 seal) |
| Data | `data/state/influence_stack_log.jsonl` **since** `fix_cutoff_utc` · `trades/phase6_trades.jsonl` sells with PnL |
| Preferred stamp | bias at **entry** on decision_context when present; else nearest bias ≤24h of exit (labeled) |
| Primary window | `post_fix_collect` (≥14d organic stamps after cutoff, or earlier if `sensor_ok` + min_n) |
| Context | live overlay smoke (bias ≠ 0.5); 024 preflight fail artifact |
| Fees | as recorded on sells (no fantasy maker) |
| Runner | `phase6/research/run_polymarket_influence_backtest.py --since 2026-09-02T00:00:00+00:00` |
| Isolation | `phase6/research/test_isolation_sensor_preflight.py` |
| Sensor lib | `phase6/research/sensor_preflight.py` **before** any WR/ROI table |
| Health | `phase6/research/run_polymarket_influence_health.py` (post-fix unique bias / stuck detect) |

**Ops (stamp path):** keep `~/.hermes/skills/crypto_analyst/polymarket_overlay.py` synced with project `hermes/skills/crypto_analyst/polymarket_overlay.py` — intel report candidate list can load the Hermes copy.

**fix cutoff (UTC):** `2026-09-02T00:00:00+00:00` — first calendar day of parse+preflight seal. Only influence snapshots with `ts ≥ cutoff` enter the scoreboard population.

---

## 4. Success criteria (frozen before score)

| Gate | Value |
|------|--------|
| primary_window | post_fix_collect |
| sensor_preflight_ok | **required** — `outcome_class == sensor_ok` |
| min_unique_bias_3dp | ≥ 5 on post-fix influence rows |
| min_bias_stdev | ≥ 0.02 |
| forbid_all_bias_equal | 0.5 |
| min_joined_sells | ≥ 15 (else `inconclusive_sparse_N` / `sensor_thin`) |
| min_join_rate | ≥ 0.10 of sells in window (soft; report both) |
| lift bar (attention) | risk_on mean_pnl − neutral ≥ 0 **and** risk_on n≥5 and neutral n≥5 |
| lift bar (CR shadow path) | same + risk_on WR ≥ neutral WR; still **live_promote_allowed=false** |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | **false** |
| WR role | secondary only |

**CR accept (scoped shadow / observe only)** only if primary gates + `sensor_ok` + lift bar.  
**Never** promote allocator influence from this trial without separate Brad GO + promotion gates.

---

## 5. Outcome recording

Report must set `outcome.class` ∈  
`HIT_CRITERIA` | `ATTENTION_ONLY` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete` | `sensor_broken` | `sensor_degenerate` | `sensor_thin` | `method_invalid`

Plus: `preflight` block, `n_post_fix_snapshots`, `n_joined`, bucket table, plain-English go/no-go first.

---

## 6. Decision path

1. Collect ≥14d (or sensor_ok + min_n earlier) with health silent-OK  
2. Isolation still green  
3. Runner with `--since` → report under `reports/POLYMARKET_INFLUENCE_RERUN_*`  
4. `trial_cycle.py finalize-report …` → REPORT_READY  
5. `review-request` → Brad `decide` + `--follow-on`  
6. Packet under `docs/testing/decisions/`

---

## 7. Follow-on policy

| If | Then |
|----|------|
| sensor_* fail again | fix meter; do not score; follow_on none or engineering ticket |
| sparse N | extend_trial collect window **or** drop |
| ATTENTION_ONLY / weak lift | continue_observe_only; no live haircut |
| HIT_CRITERIA | propose_scoped_experiment (shadow log only) — still no silent live |
| no_edge | drop; follow_on none |

---

## 8. Notify

Decision packet + DECIDED inbox (+ TG when delivered). Lead with: sensor_ok? lift? promote blocked.
