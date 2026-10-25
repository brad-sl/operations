# Measure-collect health — process (2026-10-25)

## Incident class
We ship a shadow/measure collector, values never populate (or stay stuck at defaults), and we only notice at the 14d/GO window. W2 would-arm: **523 rows** with `hours_held≡0` and `has_tryout_lot≡false` while real tryout shells were open.

Same family as Polymarket 024 `sensor_degenerate` (stuck 0.5) — but **collect streams** lacked an ongoing health gate. `sensor_preflight` existed for offline digs; collectors only checked “file grows.”

## Root failure modes (checklist)
| Mode | Symptom | Example |
|------|---------|---------|
| **A Dead inputs** | Required fields always default | hours_held=0, tryout_lot=false |
| **B Wrong join** | Collector reads empty dict / wrong SSOT | open_lots key never set on matrix |
| **C Empty book cosplay** | 0 treatment fires because class not in book | no tryouts → “0 would-arm” looks like “no need” |
| **D Contaminated clock** | Calendar days tick while meter broken | 11d span, 0 sensor_ok days |
| **E Isolation-only green** | Unit tests mock happy path; live path never smoke-checked | classify() tested; evaluate_open_* inputs not |

## Process changes (required for every new measure stream)

### 1. Ship contract (day 0 — before cron)
Declare in code or `data/state/<name>_collect_contract.json`:
- `required_row_fields`
- `stuck_defaults` (values that mean “meter dead,” not “market quiet”)
- `treatment_field` (what “would_X” means)
- `min_snaps` / N-day gate uses **`sensor_ok_days`**, never raw calendar alone

Lib: `phase6/research/measure_collect_health.py`

### 2. Day-0 live smoke (same session as ship)
After first real `run_and_persist` against **live** state:
1. Open `*_latest.json`
2. Assert ≥1 row has non-default on each stuck_default field **OR** honest `collect_empty_book_ok` with plain-English why
3. Write `data/state/measure_collect_health_<name>_latest.json`
4. If `sensor_degenerate` / `sensor_broken` → **fix meter same day**; do **not** start 14d clock

### 3. Collect tick embeds health
Every snap must carry:
```json
"measure_health": { "code", "collect_clock_ok", "plain_english", ... }
"collect_clock_ok": true|false
```
Cron / dig-out TG line must print `health=… clock_OK|FROZEN` (never silent).

### 4. Clock rule
| Health | Day counts toward N-day GO gate? |
|--------|----------------------------------|
| `collect_armed` / `sensor_ok` | Yes |
| `collect_empty_book_ok` | Yes as sensor day; **GO still needs fires or closed-leg CF bound** |
| `sensor_degenerate` / `broken` / `thin` | **No** — clock FROZEN |

**Never** say “we have 14d history” when `sensor_ok_day_estimate == 0`.

After a meter **repair**, stamp `data/state/w2_meter_post_fix_since.txt` (or stream equivalent). Contaminated pre-fix history does **not** count; `sensor_ok_days` only after the stamp.

### 5. GO packet lead line (hard)
First lines of any promote/GO packet:
1. `measure_health.code`
2. `sensor_ok_days` / need_days
3. `n_treatment_true` (or closed-leg CF bound if open book empty)
4. Then edge/less-loss numbers

If health ≠ ok family → outcome = `sensor_*` / `fix_meter`, **not** “no edge” / “N_INSUFFICIENT from good collect.”

### 6. Isolation tests must include degenerate fixture
- Happy path → `collect_armed`
- Stuck defaults fixture → `sensor_degenerate` + `collect_clock_ok=false`
- Core-only all-false tryout → **not** degenerate (honest empty class)
- Rollup registry has all active streams

### 7. Closed-leg bound when open book empty
If treatment never fires for ≥3d while alts/shells existed in ledger: run offline CF bound (like W2 scoreboard) and attach to health — distinguishes “rule never matches live wiring” from “no shells.”

### 8. System health agent (ops)
| Piece | Path |
|-------|------|
| Agent | `scripts/ops/measure_collect_health_agent.py` |
| Wired into | `scripts/ops/ops_engineer.py` (every ops tick) |
| Rollup | `data/state/measure_collect_health_rollup_latest.json` |
| Repair packets | `data/state/measure_health_repairs/` + MASTER append |
| Auto-repair (safe) | W2: re-run would-arm collector + stamp post_fix |
| Never auto | flip `live_apply`, money path, or bank-trail GO |

Agent catches `clock_FROZEN` / `sensor_degenerate`, opens one packet per stream/code/day (idempotent), alerts TG, initiates safe repair, leaves money path alone.

## Registered streams (STREAM_REGISTRY)
| Stream | Health fn | Severity if bad |
|--------|-----------|-----------------|
| `w2_would_arm` | row contract + history | HIGH |
| `bank_trail` | CF legs + path_mfe + Sunday | WARNING |
| `jev_select_few` | crumbs / seats | WARNING |
| `decision_discipline` | triples jsonl | WARNING |

Add new streams to `STREAM_REGISTRY` in `measure_collect_health.py` at ship time.

## W2 concrete
| Piece | Path |
|-------|------|
| Health lib | `phase6/research/measure_collect_health.py` |
| Isolation | `phase6/research/test_isolation_measure_collect_health.py` |
| Collector attach | `phase6/core/sl_width_would_arm_shadow.py` `run_and_persist` |
| Input SSOT | `tryout_scale_up_open_lots.json` + ledger last BUY hours |
| Dig-out TG | `phase6/core/dig_out_shadow_board.py` |
| Health artifact | `data/state/measure_collect_health_w2_latest.json` |
| Post-fix stamp | `data/state/w2_meter_post_fix_since.txt` |

**Pre-fix history (Oct 13–25):** contaminated (`hours_held≡0`). Do **not** count as W2 14d sample. After meter fix + stamp, **new** clock from post_fix sensor_ok_days only.

## Bank-trail concrete
| Piece | Path |
|-------|------|
| CF attach | `phase6/core/bank_trail_while_green_cf.py` |
| Sunday gate | `phase6/core/bank_trail_while_green_decision.py` (blocks letter GO if clock_FROZEN) |
| Health artifact | `data/state/measure_collect_health_bank_trail_latest.json` |

`N_INSUFFICIENT` with live path_mfe is **sample size**, not meter fail. All-zero path_mfe with n_legs≥3 → `sensor_degenerate`.

## Do not
- Start a multi-week collect without day-0 smoke on live state
- Equate “jsonl line count” with “sensor working”
- GO from calendar span while `clock_FROZEN`
- Call stuck zeros “no shells needed fuse”
- Count pre-fix contaminated history toward N-day after a meter repair
