# Additional verification — C vs B (2026-08-18)

**Question:** Is C close enough to B that more verification is worth it?  
**Method:** Ground-truth only (no second full BoN). Live dash + ledger + existing ISO.

## Verdict

| Ask | Answer |
|-----|--------|
| More **LLM** BoN / re-score? | **No** — diminishing returns; margin 0.2 already flagged escalate |
| Cheap **evidence** verify? | **Yes — done** (this note) |
| Still pick **C** for low-effort win? | **Yes**, with eyes open: cold path still fails SLA |
| Does ground-truth flip to **B**? | **No auto-flip** — B looks *more* staffable, not mandatory this week |

---

## C claims checked (`GAP-06`)

| Claim | Evidence | Result |
|-------|----------|--------|
| 60s perf cache shipped | `phase6/core/performance_api.py` TTL=60; `serve_dashboard.py` `api_performance_v2` + hit path | **TRUE** |
| Isolation harness exists | `scripts/phase6/test_isolation_kpi_truth.py` → **ALL PASSED** just now | **TRUE** |
| NEEDS_VALIDATE still real | Cold `/api/performance` **10.46s**; warm **0.10–0.16s**; concurrent×5 all HTTP 200 ~0.45–0.51s | **TRUE — cold > 8s SLA** |
| Full soak already done | No soak script/report artifact; only ad-hoc curls + kpi_truth | **FALSE (work remains)** |
| GAP-04 watch-not-build | `hard_exit_decisions.jsonl` = **6** lines (Jul); `regime_hard_exit_shadow.json` **n=0** proposals | **TRUE** |

### Live timings (127.0.0.1:8502)

```
cold:  try1  http=200  t=10.46s   (MASTER cold bar <8s → FAIL)
warm:  try2  http=200  t=0.16s    (warm bar <1s → PASS)
warm:  try3  http=200  t=0.10s
×5 concurrent after warm: all 200, ~0.45–0.51s, non-null JSON status=ok
```

**Implication for C:** Not a paper NEEDS_VALIDATE. Cold miss still product-risk under multi-account hammer (first poll after TTL). Effort stays **S–M small**: formalize soak + decide whether cold 10s is gap_in_code or document/raise SLA + ensure timeout≠silent wrong 0 (periods already have timeout source path in handler).

---

## B contrast (`GAP-05`) — light

| Claim | Evidence | Result |
|-------|----------|--------|
| Offline ledger exists | `trading_log/3176ac3f…/verified_fills_*.jsonl` **185** rows; **57** `stop_loss_exchange` sells | **TRUE** |
| min_n ≥15 reachable | Post-SL→rebuy episodes ≈ **18** (≥15) | **TRUE — upgrades feas7d** |
| Still M not S | Need proper report: rebuy@24/48/72, second-SL rate, $ recycle, enum + decide packet | **TRUE** |

Rough proxies (not the final report): rebuy within 72h sparse on this cut; second-SL-after-rebuy common enough to study. **B is more feasible than the first verifier pass implied** (feas was 15; data says staffable).

---

## Pairwise after evidence (not another 1–20 table)

| Dimension | Winner | Why |
|-----------|--------|-----|
| Close this week / low drag | **C** | Harness green; bug class reproduced in one curl loop |
| Fleet less-loss $ | **B** | L3; N honest possible now |
| Risk if wrong pick | C wrong → spent S on trust already mostly fixed warm-path | B wrong → delayed KPI soak while cold 10s still bites operators |
| Scenario flip to B | If Brad prioritizes manufactured-loss expectancy **this** week over dash trust formalization | Data supports starting B immediately |

**No scenario makes A or GAP-04-build the winner.**

---

## Recommendation

1. **Do not run another BoN round** on this decision.  
2. **Accept C as the low-effort staff pick** for the next closed loop — *because* cold 10.46s proves residual work, not because scores said 17.2.  
3. **Queue B as next** (no re-pilot needed); ledger N already clears the sparse-N fear.  
4. Optional same-week: if C finishes in &lt;1 day, start B offline report immediately (BASELINE shape without dual thrash).

### C success bar (tightened by this verify)

- Scripted cold+warm+concurrent soak → artifact under `reports/`  
- Assert: non-null periods when history exists OR explicit `source=timeout` (never silent fake 0)  
- Record cold p95; if still &gt;8s → `gap_in_code` or honest SLA amend in SCALE map L4  
- `test_isolation_kpi_truth` stays green  
- Decide packet; no live trading config writes  

---

## Files

- Live checks: this session (dash :8502 active, kpi_truth PASS)  
- Prior scores: `PILOT_20260818_RESULT.json`  
