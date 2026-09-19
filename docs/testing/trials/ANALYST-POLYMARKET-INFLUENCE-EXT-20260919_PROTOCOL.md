# Protocol — ANALYST-POLYMARKET-INFLUENCE-EXT-20260919

**Master task:** `ANALYST-POLYMARKET-INFLUENCE-EXT-20260919`  
**Kind:** `offline_analysis`  
**Family:** `polymarket_influence`  
**Parent:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902` (CLOSED `extend_trial` 2026-09-19 — incomplete crypto N)  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Created:** 2026-09-19 (Brad GO — extend until enough trades for relevance)

---

## 0. Why extend (not restart from zero)

Parent **ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902** closed as:

| Fact | Detail |
|------|--------|
| Sensor | **OK** — 52 post-fix stamps, bias range real (not stuck 0.5) |
| Edge sample | **Incomplete** — crypto joined n=10 (all LINK), **risk_on n=0** |
| Brad | Lack of trades → trial incomplete for relevance; extend collect |

This child **keeps** the same fix cutoff (`2026-09-02T22:00:00+00:00`). It does **not** reopen 024. It does **not** live-promote.

---

## 1. Hypothesis

With longer post-fix collect and **ex-stable** sell joins only, either:

1. **Relevance bar clears** (enough crypto exits / bucket coverage) and we can honestly score risk_on vs neutral lift, **or**
2. Hard stop hits still sparse → **drop** / observe-only with eyes open.

---

## 2. Non-goals

- No live trading config / allocator influence writes without Brad + promotion gates  
- No scoring pre-fix contaminated stamps  
- No counting USDT/USDC park rotations as edge sample  
- Real data only; WR secondary to mean PnL / join honesty  

---

## 3. Design

| Item | Value |
|------|--------|
| Control | neutral bias (0.45–0.55) on **crypto** joined sells |
| Arms | risk_off <0.45 · neutral · risk_on >0.55 |
| Data | `influence_stack_log.jsonl` since fix cutoff · `trades/phase6_trades.jsonl` sells with `pnl` |
| Edge universe | **Exclude** stable pairs (USDT/USDC/…) from bucket scoreboard |
| Runner | `phase6/research/run_polymarket_influence_backtest.py --rerun` |
| Health | `phase6/research/run_polymarket_influence_health.py` (cron `6183c52efe35`) |
| Start | `2026-09-19T18:03:08.367111+00:00` |
| Mid check | `2026-09-29T18:03:08.367111+00:00` |
| **Hard stop final_at** | `2026-10-10T18:03:08.367111+00:00` (~21d) |

**Early close allowed:** if relevance bars clear before hard stop → finalize-report + review-request immediately.

---

## 4. Success / relevance criteria (frozen)

| Gate | Value |
|------|--------|
| sensor_preflight_ok | required |
| min_unique_bias_3dp | ≥5 |
| min_bias_stdev | ≥0.02 |
| forbid stuck 0.5 | yes |
| **Relevance (either)** | `crypto_joined ≥ 15` **OR** (`risk_on_n ≥ 5` **AND** `neutral_n ≥ 5`) |
| Lift (attention only) | risk_on mean_pnl − neutral ≥ 0 with both n≥5 |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | **false** |
| hard_stop | final_at above — then finalize even if sparse |

**CR accept (scoped shadow)** only if sensor_ok + relevance + lift bar.  
**Never** silent live promote from this trial.

---

## 5. Outcome classes

Same set as parent protocol. Prefer:

- relevance not met at hard stop → `inconclusive_sparse_N`  
- sensor regress → `sensor_*`  
- lift weak with enough N → `unstable_or_no_edge` / `ATTENTION_ONLY`  
- HIT only if protocol lift + N clear  

---

## 6. Decision path

1. Health silent-OK through collect  
2. Mid ~10d: scoreboard snapshot (no decide required)  
3. When relevance clears **or** hard_stop: runner `--rerun` → final report  
4. `finalize-report` → `review-request` → Brad `decide`  
5. Packet under `docs/testing/decisions/`  

Closeout watchdog will OVERDUE if past final_at still open.

---

## 7. Follow-on policy

| If | Then |
|----|------|
| sensor fail | fix meter; do not score |
| hard_stop still sparse | drop or continue_observe_only (Brad) — **do not** infinite extend |
| ATTENTION_ONLY | continue_observe_only; no live haircut |
| HIT_CRITERIA | propose_scoped_experiment (shadow only) |
| no_edge with enough N | drop |

**Rule:** one extend generation from parent. Another open-ended extend needs fresh Brad GO + new id.

---

## 8. Notify

Decision packet + DECIDED inbox. Lead with: sensor_ok? relevance cleared? lift? promote blocked.
