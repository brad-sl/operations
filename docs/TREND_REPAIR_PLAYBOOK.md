# Trend Repair Playbook

**Status:** active platform process (2026-07-24)  
**Owner:** Analyst / OPT (monitor + test + propose) · Live runner (apply **current** gates only) · Operator (promote)  
**North star:** deposit-adjusted **equity trend** bends up over time **and** drawdowns stay controlled — not one-off bag picks, not growth-only.

Related: `docs/REGIME_GATES_AND_ANALYST_LOOP.md`, dashboard Account health (`equity_trend`), REGIME-CASH epic, ANALYST-OPT epic.

---

## 1. Why this exists

Point-in-time tiles (1D / 7D / 30D) are necessary but incomplete. A **smoother** path after risk controls can still be a **downtrend**. The platform must:

1. **Measure** deposit-adjusted equity path + slope (not raw NAV after deposits).
2. **Diagnose** which layer drives the path (churn / open-book MTM / fees / regime park drag / bad entries).
3. **Act in tiers** that prefer durable gate/process fixes over discretionary “wins.”
4. **Feed Analyst** so monitoring → tests → gated proposals is routine, not a chat one-off.

---

## 2. Canonical metrics (single source of truth)

| Metric | Source | Meaning |
|--------|--------|---------|
| Equity index path | `compute_equity_trend` → `/api/performance.equity_trend` · `data/state/trend_repair_status.json` | Index starts at 100; external deposits/withdrawals stripped |
| Window return | `equity_trend.window_return_pct` | Full-sample deposit-adj path return |
| Recent path (~7d) | `equity_trend.recent_return_pct` | Tail of path (complements 7D tile) |
| Slope | `equity_trend.trend.slope_pct_per_day` | Linear fit on index (health label) |
| Health label | `equity_trend.health` | recovering / stabilizing_up / sideways / soft_down / declining |
| Regime stance | `regime_cash_status.json` | park vs deploy, util target, cap |
| Open-book drag | live positions + cost basis | Residual MTM while park blocks new buys |
| Since go-live | daily brief production metrics | Long scoreboard (deposit-adj) |

**Do not** treat 7D wallet % as proof that 3% position SL failed. See skill `phase6-capital-and-dashboard-kpis` / period-return-vs-position-sl.

**Code entrypoints**

- `phase6/core/dashboard_serve_helpers.compute_equity_trend`
- `phase6/research/trend_repair.py` — snapshot, diagnosis, tier recommendations, brief lines
- Dashboard: Account health card in `phase6_dashboard.html`
- State: `data/state/trend_repair_status.json` (refreshed by intel brief / weekly OPT / explicit run)

---

## 3. Diagnosis framework (Analyst every cycle)

Answer in order:

### A. Shape
- Is **slope** negative over ≥14d while **recent path** is better/worse than window?
- Segment path (pre-policy / post-policy) when a control change lands (park, flat option B, SL wire, etc.).

### B. Layer attribution

| Layer | Signal | Typical fix tier |
|-------|--------|------------------|
| **Re-entry churn** | High rebalance count, Exit WR low, util stays high after stops | Tier 0–1 gates (park, cooldown, no force rebalance) |
| **Open-book MTM under park** | Buys blocked but util ≫ target; few names drive unrealized red | Tier 1 inventory (SELLs allowed); not new buys |
| **Fee / churn friction** | Many small rotates, flat edge | Tier 0 stop discretionary rebalances; raise min trade |
| **Regime mislabel** | Stale OHLCV, wrong bull/flat bar | Research + detector hygiene; no capital |
| **Policy too tight / too loose** | Smooth downtrend forever vs renewed whip | Tier 2 gated micro-deploy **after** evidence window |
| **Strategy edge missing** | Deploy allowed, gates pass, still lose on overlap | Tier 3 ANALYST-OPT scenarios — **not** live guess |

### C. Platform vs lottery
Prefer changes that:

- Encode in **JSON gates / coordinator / tests**
- Apply **every** similar regime day
- Have **rollback** (policy + knob_map)
- Show up on **equity_trend** and isolation tests

Avoid: one-pair hero trades with no rule; `enforce: false` as “thaw”; sim-green → live without overlap + live_param.

---

## 4. Action tiers (long-term ladder)

### Tier 0 — Process integrity (default, always on)

- Keep **current** REGIME-CASH enforce path; SELLs allowed; BUYs gated.
- No `force_rebalance` / cash-hold clear unless operator intentionally risk-on.
- No deposit-same-cycle redeploy (`capital_event_force_rebalance: false` preferred under repair).
- OHLCV / live BTC merge freshness for regime detector.
- USDC carry on idle cash when available (basis points, correct sign under park).
- **Success:** churn metrics stable; no surprise redeploy; equity path not re-whipping.

### Tier 1 — Inventory & utilization (under park or anytime)

- Reduce **open-book drag** via rules-based trims (exit knobs: overbought RSI, max_sentiment_hold, thesis break) — **not** random bag-picking as policy.
- Glide **util toward regime target** (e.g. transition park ~45%) by raising cash, not buying.
- Leave names that pass hold rules; document pair→rule mapping in proposal.
- **Platform form:** exit checks in coordinator / documented exit section of `regime_cash_policy.json`; optional “repair trim” proposal type in Analyst backlog.
- **Success:** recent path ≥ window; util gap to target shrinks; slope less negative over 14d.

### Tier 2 — Gated micro-optionality (policy experiment)

Only after **evidence window** (see §5):

- Example pattern (flat option B is the template): small `rebalance_cap_usd`, stricter entry (RSI/sentiment), `deploy` + `allow_new_buys`, **both** `regime_cash_policy.json` **and** `regime_knob_map.json`.
- Transition micro-deploy (if ever): tinier cap than flat B; tighter entry than bull; never knob_map cap 0 left behind.
- **Not** `enforce: false`.
- Shadow / paper / tiny cap first when possible.
- **Success:** equity slope ≥ 0 for 14d **and** max path DD not worse than pre-change band; else rollback.

### Tier 3 — Strategy / research (Analyst OPT)

- Scenario packs, regime scorecards, param sweeps, overlap vs production.
- Promotion: leaderboard → shadow → **live_param_audit** → USDC/hurdle → **operator apply**.
- North star in scoring: **return improvement and loss minimization** (not Growth>DD alone).
- **Success:** proposal with real-data overlap, gates green, explicit rollback.

---

## 5. Evidence windows (anti–one-week overfit)

| Decision | Minimum evidence |
|----------|------------------|
| “Recent path is better” (observation) | ≥7d recent vs window (dashboard already) |
| Claim **stabilizing** | ≥**14d** recent_path ≥ 0 **or** slope improving vs prior 14d |
| Claim **recovering** / promote Tier 2 | ≥**14d** slope_pct_per_day > 0 **and** window not collapsing |
| Promote Tier 2 → wider caps | ≥**28d** post-change path + no gate-audit regression |
| Rollback Tier 2 | Any 7d path DD worse than pre-band by agreed margin **or** live_param fail spike |

Analyst must print these clocks on proposals (`evidence_days`, `baseline_slope`, `post_slope`).

---

## 6. Analyst operating loop (mandatory)

```
each daily intel / weekly OPT:
  1. refresh trend_repair_status.json
  2. classify health + primary layer (churn | open_book | fees | regime | edge)
  3. emit tier-ranked recommendations (no auto-apply)
  4. if Tier 1–2 material: add Type:test or strategic proposal with:
       - hypothesis
       - metric to move (slope, recent_path, util_gap)
       - test plan (offline / instrumentation)
       - rollback
  5. dig OOS / overlap when first-pass misleads
  6. close decide on evidence (no endless “watch”)
```

**Hooks**

| Hook | What |
|------|------|
| Daily intel brief | Honest Assessment + Wealth lines include TREND-REPAIR summary |
| Weekly OPT | `run_analyst_opt_weekly` / regime continuous should refresh trend repair status |
| Dashboard | Account health card (operator eyeball) |
| MASTER / backlog | Proposals tagged `trend_repair` + tier |
| Isolation | `scripts/phase6/test_isolation_trend_repair.py` |

CLI:

```bash
PYTHONPATH=. .venv/bin/python3 -m phase6.research.trend_repair
# → data/state/trend_repair_status.json + stdout summary
```

---

## 7. Reference snapshot (2026-07-24) — keep for replay

Context only; re-run metrics live rather than trusting stale numbers.

| Item | Value |
|------|--------|
| Health | Declining |
| Window (dep-adj ~27d) | ~−15% to −16% |
| Recent ~7d path | ~−1.0% (better than window; matches 7D tile) |
| Slope | ~−0.7 index pts/day |
| Segments | Pre~Jul7 **+3.3%**; Jul7–14 **−11.5%** (main damage); Jul14–21 **−3%**; last7 **~−1%** (smoothed) |
| Regime | transition / **PARK** / cap $0 / enforce true / BTC 30d ~+12% (bull bar 15%) |
| Book | util ~69% vs park target ~45%; cash ~$780; SOL soft MTM; LINK slight green |
| Interpretation | July controls reduced whip and upside; residual red ≈ **open-book under park**, not active buy churn |
| Stance | Tier 0 hold; Tier 1 rules-based inventory/util; Tier 2 only after §5 clocks; Analyst owns monitoring |

Lesson encoded: **smoothing ≠ winning**. Park is correct when regime says so; repair then targets **inventory and process**, then **gated optionality**, then **edge research**.

---

## 8. Proposal template (copy into strategic / MASTER)

```markdown
### TREND-REPAIR-YYYYMMDD-##
- **Tier:** 0 | 1 | 2 | 3
- **Hypothesis:** …
- **Primary layer:** churn | open_book | fees | regime | edge
- **Metrics to move:** slope_pct_per_day, recent_return_pct, util_gap_to_target, max_path_dd
- **Baseline (status as_of):** …
- **Evidence required:** (§5)
- **Test:** offline scenario / instrumentation / shadow
- **Live change surface:** policy | knob_map | coordinator | none
- **Rollback:** …
- **Does NOT:** auto-promote; enforce:false; one-pair lottery without rule
```

---

## 9. Anti-patterns

- Judging repair success on a **single green day** or one pair RSI.
- Thaw via **`enforce: false`**.
- Policy deploy with knob_map still **usdc_park / cap 0**.
- Treating deposit-inflated NAV as trend repair.
- Auto-promoting param sweep “best bull bar 10%” into live without overlap + audit.
- Infinite “watch the dashboard” with no decide/close.

---

## 10. Changelog

| Date | Note |
|------|------|
| 2026-07-24 | Initial playbook + `trend_repair` module + brief/status hooks; baseline snapshot §7 |
| 2026-07-24 | Tier 0 applied: `capital_event_force_rebalance=false` + runner restart. Tier 1 scanner: `phase6/research/tier1_exit_glide.py` → `data/state/tier1_exit_glide_draft.json` (draft only). |
