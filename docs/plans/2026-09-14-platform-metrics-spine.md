# Platform Metrics Spine — justify + optimize (2026-09-14)

**North star:** ~5%/mo deposit-adjusted take-home. Metrics exist to **justify** (go/no-go) and **optimize** (which lever moves month_path) — not to decorate dashboards.

**Status 2026-09-14:** **P0+P1+P2 SHIPPED** — lifecycle spine + promote graduation charts  
- P0+P1 Core: `phase6/core/platform_metrics_spine.py`  
- P2 Core: `phase6/core/promote_graduation_chart.py` (SVG funnel/outcomes/paper; claim bar)  
- CLI: `run_platform_metrics_spine.py`, `run_promote_graduation_chart.py`  
- Isolation: both suites green  
- Artifacts: spine latest + `promote_graduation_chart_latest.json` + `reports/charts/promote_graduation_*.svg`  
- Cron: spine `63cc2c821018` 07:45 PT; promote chart `af423d285b52` **12:40 PT daily** (after pick-metrics)  
- Dashboard (API only, no full pane yet): `/api/promote-graduation`, `/api/platform-metrics-spine`, `/charts/promote-graduation/{funnel,outcomes,paper}.svg`  
- **Hard rule:** measure-only — never flips `live_membership_swaps`, never auto-promotes, never hard-ejects.

**Rules (non-negotiable):**
- No live config / membership / knobs from metric jobs.
- L1 CF ≠ fills ≠ PnL. WR is secondary.
- Thin N → `edge_claim_allowed=false` / `ATTENTION_ONLY`.
- One spine board; siloed latest.json stay as **feeds**, not competing truths.

---

## 1. Funnel (money path) — the spine

```
Scout / CF arms  →  Shortlist (M0–M5 novelty)  →  Paper preferred arm
      →  Operator promote (Brad GO)  →  Seat (basket)  →  Signal (RSI/sent)
      →  Fill  →  Protect (SL/TP)  →  Exit RT  →  Attribution / process tax
```

**Success is layer-local.** Never roll L1 excess into “runner success.”

| Layer | Question | Primary metric | Fail mode if confused |
|-------|----------|----------------|------------------------|
| L0 Process | Did runner cycle clean? | cycle ok / rebal slot / SL attach | “bot broken” when gates correctly idle |
| L1 Paper pair pick | ADD vs REMOVE price | arm ex7, hit7, sleeve Δ, HC | meme ADD jackpot sold as edge |
| L2 Deploy realism | Would runner buy ADD? | L2 pass rate | promote names that never seat |
| L3 Seat | Did promote stick? | seated / eject / residual | config churn as alpha |
| L4 Signal | Did seat ever trip BUY? | signal\|seat | idle seats blamed on “wrong pair” |
| L5 Fill | Did BUY fill? | fill\|signal, fee bps | limit-first cosplay |
| L6 Exit | How did bag die? | TP/SL/dust banks, process_tax $ | Exit WR alone |
| L7 Book | Deposit-adj path | 1D/7D/14D/30D, month_path | deposit cliff / double-count |
| L8 Arm switch | Right paper attention? | preferred vs alt forward CF | live PnL from paper flip |

---

## 2. Your list → existing feeds → gaps

### A. Runner / rebalancing success rate
| Have | Gap |
|------|-----|
| Dashboard KPIs (deposit-adj periods, Exit WR, Util, SL OK) | No single **runner ops success** definition |
| Rebalance logs, capital events, tryout readiness | Slot success ≠ edge: empty TradePlan can be correct |
| Exit stack proof (PC-02), naked-bag A1 | “Success” must split: **ops integrity** vs **PnL** |

**Define:**
- `runner_ops_ok` = cycle heartbeat + SL coverage on open bags + no naked bag + rebal slot ran when due
- `rebal_deploy_rate` = buys attempted / slots where `can_buy` true (not / all slots)
- `rebal_idle_correct` = slots with can_buy false and 0 buys (armor working)

### B. Basket swap pair selection
| Have | Gap |
|------|-----|
| HC board + arm proposals (`basket_select_arms/*`) | No **criteria ablation** board (which score features predict forward excess) |
| dual_agree, goldilocks urgency, novelty M5 | Selection quality still L1-only in most boards |
| regime arm switch crumbs | Not joined to arm CF forward windows |

**Define:** selection success = preferred-arm **paper** ADD−REMOVE excess **conditional on M-ok + novelty class**, not raw L1 mean.

### C. Automatic swap pair success rate
| Have | Gap |
|------|-----|
| `live_membership_swaps: false` (correct) | **N/A live** — auto-swap success is undefined until Brad opens gated live |
| Paper arms collecting | Need **shadow auto-swap CF** episode log: would-swap → forward 7d vs hold basket |

**Define now (paper):** `auto_swap_shadow_hit` after would-swap.  
**Define later (live, Brad GO):** same funnel as promote (seat→fill→RT) with ≤1/day cap.

### D. Basket pair promotion success rate
| Have | Gap |
|------|-----|
| `basket_pick_metrics.jsonl` + summary + graduation | Graduation thin; many promotes never fill |
| Live snapshot (2026-09-14): n_picks=8, filled=2, filled_win=0, hit_rate_7d=0.25, avg 7d ret −9% | Board exists but not on operator daily spine |

**Define (already almost there):**
- paper MTM success @ 1/3/7/14/30d
- excess vs REMOVE
- graduation: seat → signal → fill → win|loss
- **promote_talk_ok** only if N≥ threshold and win|fill not decorative

### E. Trial correlation / best criteria for future selection
| Have | Gap |
|------|-----|
| Arm CF by method, recovery tryout qualify (ledger SL/TP rates) | No **feature → outcome** correlation table across promotes + tryouts |
| Attribution RT weekly (entry RSI/sent stamped) | N_rt_primary=7, edge_claim false |
| novelty_class, missfire, M-ok | Not yet scored as predictors of filled_win |

**Define:** offline correlation pack (read-only):
- features: novelty_class, M-ok, goldilocks urgency, arm source, entry RSI/sent bins, tier, age/volume
- outcomes: 7d excess, fill occurred, RT pnl, process_tax flag
- report: rank features by **expectancy**, not WR; inverse controls; half-sample stability

### F. Lead vs lag indicators (get in / get out)
| Have | Gap |
|------|-----|
| Doctrine: RSI structure, sent reinforce; stand-down C on elevated tape | Sparse historical stamps; many digs ATTENTION_ONLY |
| trade_signal_events + attribution_rt_weekly | Need lead/lag board: entry feature vs forward path + exit feature vs giveback |
| shadow TP / exit asymmetry reports | Not folded into one “timing” spine row |

**Define:**
- **Lead (entry):** feature at decision vs mark @ +1h/+4h/+1d and vs actual exit (hold-to-horizon dual score)
- **Lag (exit):** exit RSI/sent/trail vs max giveback after exit; TP vs SL class
- Tag `sensor_thin` until stamp coverage real — do not fish

---

## 3. Additional pieces (same spine)

| Piece | Role |
|-------|------|
| Process tax bank | SL + dust + same-session recycle $ (north-star bleed) |
| Fee drag | fees/notional, fees/NAV, maker share |
| Limit-first evidence | attempt/fill/skip (cost cut, not alpha) |
| L2 deployability | preferred arm ADD × live gates |
| Regime arm switch metrics | tape → arm map accuracy vs forward arm CF |
| Tryout readiness | can_buy, seats, eng sent, latch |
| Account path | deposit-adj 7D/14D/30D (month_path) |
| Novelty graduation | restricted → graduated packet, not jackpot |

---

## 4. Target artifact (one spine)

```
data/state/platform_metrics_spine_latest.json
reports/PLATFORM_METRICS_SPINE_LATEST.md
# optional later: reports/charts/platform_metrics_spine_{date}.png
```

**Board sections (fixed order):**
1. Book path (deposit-adj) — justify scale
2. Runner ops integrity — justify trust
3. Funnel rates (seat→signal→fill→win) — justify deploy
4. Membership / promote scoreboard — justify Brad GO
5. Paper arms + regime switch — justify attention
6. Timing lead/lag (thin-N honest) — justify entry/exit research
7. Process tax + fees — justify “repair first”
8. Go/no-go strip (no prose fog)

Each row: value · N · window · claim_allowed · feed path.

---

## 5. Build order (no live writes)

| Phase | Deliverable | Depends |
|-------|-------------|---------|
| **P0** | Spine aggregator read-only: join existing latest.json → one MD/JSON | nothing |
| **P1** | Runner ops success block (rebal slot, SL coverage, naked-bag, can_buy split) | P0 |
| **P2** | Promote + graduation chart (from pick_metrics) | P0 |
| **P3** | Regime arm switch metrics join (crumbs × arm CF forward) | crumbs history ≥14d ideal |
| **P4** | Criteria correlation dig (offline, isolation + report) | stamped RTs growing |
| **P5** | Lead/lag timing board (sensor_preflight first) | stamp coverage |
| **P6** | Dashboard pane or weekly TG short-board (quiet) | P0 stable |

**Cron:** optional daily/weekly **local** deliver after P0; TG only on claim_allowed flips or spine red integrity.

---

## 6. Live snapshot (grounding, 2026-09-14)

| Signal | Read |
|--------|------|
| Tryout can_buy | **false** (sent/RSI/blocks) |
| Preferred arm | `rel_btc_stable` (regime flip from `risk_adj_mom`) |
| Live swaps | **OFF** |
| HC | rel_btc_stable HC true (ex7~+5.7, n7=46); risk_adj_mom HC false |
| Promote graduation | 8 seated · 8 signaled · **2 filled · 0 win** |
| Promote 7d hit | **25%**; avg 7d ret **−9%** |
| Attribution 7d | n_rt=7; tax bank −$4.05 vs non-tax +$8.18; **edge_claim false** |
| L2 / limit_first boards | last built ~09-12 — refresh on spine build |

**Plain English:** scaffolding metrics exist in silos; money-path funnel says **promotes and tryouts are not yet a printer**; spine job is to make that one page so optimize targets the real choke (today: fill/win and process tax — not more scout names).

---

## 7. Optimize loops (what spine unlocks)

| If spine shows… | Optimize lever (still Brad GO for live) |
|-----------------|------------------------------------------|
| High seat, low signal | entry floors / clock / latch (already A1/A2/B1 path) |
| High signal, low fill | limit-first / liquidity / size |
| High fill, high SL tax | entry quality, rebuy blocks, size, tape stand-down |
| Promote 7d red, L1 green | stop trusting L1; require L2 + novelty |
| Arm switch thrash | dwell / thresholds |
| Lead/lag thin stamps | stamp coverage before indicator fishing |

---

## 8. Acceptance

- One command builds spine from disk SSOT
- Isolation test: fixture feeds → stable board; no network required for unit
- `edge_claim_allowed` false under thin N
- Zero writes to `config/`, pairs, or live_membership_swaps
- Operator can answer in 30s: “what’s broken — ops, membership, deploy, or exit?”
