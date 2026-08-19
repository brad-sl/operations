# End-to-end test regimen (adoption-grade)

**Status:** Canonical — 2026-08-17  
**Owner:** Crypto-Analyst + Brad (oversight)  
**Supplements:** `docs/testing/ANALYST_TEST_CYCLE.md` (state machine) · `docs/testing/ANALYST_TEST_STRATEGY.md` (what to queue)

## Why this exists

v2 trial cycle defined **states**. It did **not** stop incomplete offline digs from landing as `REPORT_READY` with:

- 11-line trial JSON (no protocol, no success gates, no MASTER)
- Sparse N waved through as “inconclusive”
- A proposed enum that never became a **logged decision**
- No CR accept/reject packet, no DM, no follow-on ticket

That is **not** a testing regimen. It is a file drop.  
**Rule:** Nothing is “done testing” until Design → Outcome → **Accept CR / Reject** → log → notify → follow-on (or explicit none).

---

## The eight steps (mandatory)

| # | Step | Done when | Artifact |
|---|------|-----------|----------|
| 1 | **Design a test** | Hypothesis, non-goals, arms, data, duration, kill rules frozen | `docs/testing/trials/<ID>_PROTOCOL.md` + trial JSON `design` |
| 2 | **Define success criteria** | Binary adopt bar **before** running (not after looking at charts) | Protocol §Success + trial `success_criteria` |
| 3 | **Determine actual outcome** | Real data run finished; metrics vs bar; N honesty | `reports/<STEM>.md` + `.json` with `outcome` |
| 4 | **Accept as CR or reject** | Human (Brad) maps outcome → decision enum | `decision` on trial + **decision packet** |
| 5 | **Log decision** | Disk + MASTER + INDEX; not chat-only | `trial_cycle.py decide` + `docs/testing/decisions/` |
| 6 | **Advance follow-on** | If warranted: new plan/MASTER/shadow; else explicit `follow_on: none` | Strategy roadmap / MASTER child / cron |
| 7 | **Notify decision makers** | Brad gets a short decision notice (TG or inbox) | `docs/testing/inbox/DECIDED_*` (+ delivery) |
| 8 | **Manage end-to-end** | Status machine enforced; stale review alerts; capacity honest | `trial_cycle` + strategy slots + stale scan |

**Close is a function call**, not a vibe:  
`python3 phase6/research/trial_cycle.py decide <TRIAL_ID> <enum> --note '…'`

---

## Step detail

### 1. Design a test

Must answer, in writing, **before** code runs for score:

| Field | Required |
|-------|----------|
| `trial_id` / family / kind | offline_analysis \| parallel_instrumentation \| shadow_observe |
| Hypothesis (one sentence) | falsifiable |
| Non-goals | especially: no silent live config |
| Arms / control | named baseline (e.g. BASE_RSI, live policy fingerprint) |
| Data | paths or public OHLCV; real only |
| Primary window | e.g. `long_tape` — short windows are **context only** |
| Kill / abort rules | empty runner, path fail, N impossible |
| Isolation | command if code changes |

**Launch gate (offline):** protocol + trial JSON with `design` + `success_criteria` + runner command.  
If any missing → status stays pre-RUNNING; **not launched**.

Template: `docs/testing/templates/PROTOCOL_OFFLINE.md`.

### 2. Define success criteria (before results)

Frozen on trial JSON:

```json
{
  "success_criteria": {
    "primary_window": "long_tape",
    "min_n_trades": 15,
    "must_beat_baseline_ret_pp": 0.0,
    "must_beat_baseline_dd_pp": 0.0,
    "require_both_ret_and_dd": true,
    "absolute_ret_floor_pct": null,
    "usdc_hurdle": false,
    "sparse_is": "inconclusive_not_promote",
    "live_promote_allowed": false,
    "shadow_ok_if": "primary_pass_and_n_ok"
  }
}
```

**Honesty classes** (outcome must pick one):

| Class | Meaning | Adopt? |
|-------|---------|--------|
| `HIT_CRITERIA` | Primary window meets frozen bar | CR path open |
| `EDGE_VS_BAGS_ONLY` | Beats crashing BH; still fails absolute/baseline bar | **Reject** promote; optional observe note |
| `inconclusive_sparse_N` | N &lt; min | **Reject** promote; optional `extend_trial` |
| `unstable_or_no_edge` | Long tape fail / worse than baseline | **Reject** |
| `process_incomplete` | Ran without design/gates (legacy debt) | **Reject** or re-run under regimen |

Sparse short windows **never** alone justify `promote_*`.

### 3. Determine actual outcome

Report **must** include:

1. Plain-English go/no-go first  
2. Table: arm × window × mean ret × maxDD × **N**  
3. Δ vs named baseline on **primary window**  
4. `outcome.class` + `outcome.primary_pass: true|false`  
5. Proposed `recommendation_enum`  
6. `live_writes: false` (or explicit blocked)

**Completeness gate:** `trial_cycle.py finalize-report` refuses `REPORT_READY` unless protocol/design + success_criteria + report paths + enum + outcome block exist.

### 4. Accept as CR or reject

| Decision enum | CR meaning |
|---------------|------------|
| `promote_primary` / `promote_blend` | **Accept CR** → shadow/live path only via promotion gates (never silent) |
| `propose_scoped_experiment` | **Accept scoped CR** → new shadow/spec only |
| `continue_observe_only` | **Reject promote**; keep logging; calendar re-eval |
| `extend_trial` | **No CR yet**; new trial ID + longer/ better design |
| `drop` | **Reject** — stop this line |
| `abort` | **Reject process** — did not complete regimen (zombie/bad launch) |

Human confirms. Agents propose only.

### 5. Log decision

`decide` writes:

1. Trial JSON `decision` + `CLOSED`  
2. `docs/testing/decisions/DEC_<TRIAL_ID>_<YYYYMMDD>.md` (decision packet)  
3. `docs/testing/inbox/DECIDED_<TRIAL_ID>_<YYYYMMDD>.md`  
4. MASTER status DONE (if `master_id`)  
5. Strategy roadmap sync  
6. INDEX reindex  

Packet template: `docs/testing/templates/DECISION_PACKET.md`.

### 6. Advance follow-on refining

On decide, packet **must** set one of:

- `follow_on: none` + reason  
- `follow_on: extend` → new trial id / plan  
- `follow_on: scoped_shadow` → spec path + cron  
- `follow_on: promotion_queue` → shadow overlay / param_audit path only  

No silent “we might look later.”

### 7. Notify decision makers

Minimum: decision packet + DECIDED inbox.  
Preferred: Telegram home (cron/agent delivery) with ≤15 lines:

- trial + enum  
- primary window pass/fail + N  
- CR accept/reject one-liner  
- follow_on  
- paths  

### 8. Manage end-to-end

| Control | Mechanism |
|---------|-----------|
| Capacity | 1 offline + 1 instru; review_pending ≤ 2 |
| Stale RUNNING | `trial_cycle.py stale` past `final_at` + grace |
| Stale REVIEW | `REPORT_READY`/`REVIEW_PENDING` &gt; 48h → alert |
| Thin JSON ban | finalize-report / transition to REPORT_READY gated |
| Live boundary | no `regime_cash_policy` / trading config from test agents |
| Strategy emit | blocked while review full; regime gates (`emit_only_when_regime`); bear/bull **parked** until live match **or** `emit --allow-historical-backtest PLAN_ID` |

---

## Mapping to trial status

```
Design+criteria → REGISTERED
Instrument/isolation → INSTRUMENTED
Run started → RUNNING
Outcome report complete (gated) → REPORT_READY
Decision packet ready for Brad → REVIEW_PENDING
decide() → CLOSED
```

**Illegal:** chat says “looks like a drop” while status stays `REPORT_READY` (blocks the whole strategy queue).

---

## Change Request (CR) shape (accept path only)

When enum is promote_* or propose_scoped_*:

| Field | Content |
|-------|---------|
| CR id | `CR-<family>-<date>` |
| Intent | what changes in product behavior |
| Evidence | primary window metrics + report path |
| Gates remaining | param_audit, shadow days, operator OK |
| Rollback | how to disable |
| Explicit non-goals | no auto-live |

Reject path does **not** mint a CR; packet records rejection evidence.

---

## Failure modes this regimen forbids

1. **Staged not run** — status pretends RUNNING/READY without runner exit 0 + report mtime  
2. **Sparse N as soft yes** — N &lt; min ⇒ cannot promote  
3. **Less-loss vs bags sold as edge** — class `EDGE_VS_BAGS_ONLY` ≠ CR accept  
4. **Recommendation without decide** — READY without CLOSED still occupies review slot  
5. **No notify** — decide without packet/inbox  
6. **Amnesiac follow-on** — “maybe later” without plan id or `follow_on: none`

---

## Commands (cheat sheet)

```bash
cd /home/brad/projects/crypto-trading-bot

# Design registered (protocol + JSON with success_criteria)
# … run offline runner …

# Gate + mark ready (fails if incomplete)
python3 phase6/research/trial_cycle.py finalize-report <TRIAL_ID> \
  --report reports/STEM.md --json reports/STEM.json \
  --enum drop --outcome-class unstable_or_no_edge

# Ask Brad (inbox)
python3 phase6/research/trial_cycle.py review-request <TRIAL_ID>

# Brad decides (logs packet + closes)
python3 phase6/research/trial_cycle.py decide <TRIAL_ID> drop \
  --note 'primary long_tape failed bar; N ok; reject CR' \
  --follow-on none

# Ops
python3 phase6/research/trial_cycle.py stale
python3 phase6/research/trial_cycle.py reindex
python3 phase6/research/analyst_test_strategy.py status
```

---

## Retro: FIB + SR (2026-08-15) — what went wrong

| Step | FIB | SR |
|------|-----|-----|
| Design | Thin / no protocol on trial | Same |
| Success criteria | Implied in report prose only | Same |
| Outcome | **Did run** real OHLCV; long tape measured | Same |
| CR accept/reject | Proposed `drop` only | Proposed `drop` |
| Log decide | **Not called** → stuck READY | Same |
| Follow-on | Unstated | Unstated |
| Notify | None | None |

**Substance:** long-tape evidence supports **reject** (not “no data”).  
**Process:** failed steps 4–8 until closed under this regimen.

---

## Related

- Cycle states: `docs/testing/ANALYST_TEST_CYCLE.md`  
- Queue/capacity: `docs/testing/ANALYST_TEST_STRATEGY.md`  
- Honesty classes: skill `offline-strategy-honesty`  
- Scale board: `docs/testing/SCALE_TEST_LANES.md`  
- CLI: `phase6/research/trial_cycle.py`  
