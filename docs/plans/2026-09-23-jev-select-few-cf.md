# Jev select-few counterfactual paper book

> **For Hermes:** Measure-only. No live orders, no tryout knobs, no X budget changes, no auto-promote.
> Brad GO 2026-09-23: staff select-few CF sleeve.

**Status:** SHIPPED thin (shadow + cron + isolation) — 2026-09-23  
**Parent:** `docs/plans/2026-09-18-jev-judgment-layer-lab.md` (L5-ish CF book)  
**Bar context:** week wait + `$150/mo` BE one-pager (separate track)

---

## 0. Thesis

**Jev judges a short list (prod tryout-eligible ∩ held, max 3) using OHLCV+RSI+aged eng sent already on disk.**  
Python opens **paper $25 seats** only when `paper_would_buy_tag` clears, marks forward returns, never calls ExecutionPort.

---

## 1. Scope

| In | Out |
|----|-----|
| Universe = `production_tryout_eligible_sources` + held risk names | Full basket / tier A ballast as CF universe |
| Cap **top 3** judged / tick | Continuous multi-pair HF |
| Paper notional **$25**, max **4** open CF seats | Live size / kindling / promote |
| Crumbs + book + 1h/4h/24h marks | Edge claims before n_closed≥20 |
| Separate call budget **12/day** | Shared silent drain of main lab 24 without tracking |
| Aged eng sent via `build_pair_state` | New paid X firehose for CF |

---

## 2. Architecture

```
phase6/core/jev_select_few_cf.py     # universe + paper book + mark/close
scripts/phase6/run_jev_select_few_cf.py
scripts/phase6/test_isolation_jev_select_few_cf.py
phase6/scripts/run_jev_select_few_cf_cron.sh
~/.hermes/scripts/run_jev_select_few_cf.sh
data/state/jev_select_few_cf_{latest,book,crumbs,budget}.*
reports/JEV_SELECT_FEW_CF_LATEST.md
```

Reuses: `JudgmentPort` / `run_lab` / `confidence_gate_paper` / `forward_return` / OHLCV 1h refresh helper.

**Hard invariants**
- `would_order` always **false**
- `measure_only` / `no_knobs`
- Kill: API fail, inverse calibration, any order path

---

## 3. Schedule

| Job | When | Deliver |
|-----|------|---------|
| `phase6-jev-select-few-cf` | `15 8,14,20 * * *` PT | **local** (quiet); crumbs on disk |
| `phase6-jev-select-few-cf-weekly` | `30 18 * * 0` PT (Sun, after BE 18:00) | **telegram** short week card |

CLI: `run_jev_select_few_cf.py --weekly`

---

## 4. Success / kill

**Attention (not edge):** stable schema, paper seats open/close, n_closed grows, L4-style join readable.  
**Edge claim:** forbidden until n_closed≥20 **and** Brad GO — still not live.  
**Kill:** p95 latency bad, cost spike, flat/inverse paper vs fwd, any money-path wire attempt.

---

## 5. Run

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_jev_select_few_cf.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_jev_select_few_cf.py --dry-run
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_jev_select_few_cf.py --tg
```

---

## 6. Plain English

Side **paper book** on the same few doors the bot can try out. Jev says skip/buy-tag; we track **would-have $** at $25 notional. Live LINK/PAXG book and BE one-pager stay separate. No auto trade from this sleeve.
