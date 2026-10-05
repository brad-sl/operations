# Post-Proof Dwell — Implementation Plan

> **For Hermes:** Prefer this plan after Brad GO on phase; do not live-gate without explicit GO.

**Goal:** Implement post-proof dwell so proven names stop tryout reincarnation churn while keeping SL/trail.

**Architecture:** Config + state stamp on TP proof → composer/scale-window read graduated set → TCS-style CF + shadow would-block before live_apply.

**Tech stack:** Python phase6 core, ledger jsonl, existing TCS dig/CF, tryout composer, scale-window.

**Policy SSOT:** `docs/features/POST_PROOF_DWELL_POLICY.md`

---

### Task 1: Config skeleton (shadow defaults)

**Files:**
- Create: `config/post_proof_dwell.json`
- Defaults from policy §10; `live_apply: false`

### Task 2: State module

**Files:**
- Create: `phase6/core/post_proof_dwell.py`
- Functions: `load_config`, `load_state`, `stamp_proof_from_sell`, `is_graduated(pair)`, `would_block_tryout(pair)`, `should_skip_scale_window_eject(pair|lot)`, `write_state`
- State path: `data/state/post_proof_dwell.json`

### Task 3: Isolation tests

**Files:**
- Create: `scripts/phase6/test_isolation_post_proof_dwell.py`
- Cases: TP stamps graduate; eject does not; expiry; tryout block; eject skip; SL demote

### Task 4: Offline CF pack (Tier A+B)

**Files:**
- Create: `phase6/research/run_post_proof_dwell_cf.py`
- Arms: block tryout 24h/48h/7d after TP; hold-after-TP mark@7d with fees+SL path
- Out: `reports/POST_PROOF_DWELL_CF_LATEST.md`, `data/state/post_proof_dwell_cf_latest.json`
- Edge tag forced `ATTENTION_ONLY_less_loss_path` unless bars say otherwise

### Task 5: Shadow wire (no orders)

**Files:**
- Modify: tryout seat composer / decision discipline path to consult `would_block_tryout`
- Crumbs: `data/state/post_proof_dwell_shadow_crumbs.jsonl`
- `live_apply` false ⇒ log only

### Task 6: Live gates (Brad GO only)

**Files:**
- Stamp on protected TP exit / ledger sell path
- Scale-window: skip auto-eject if graduated
- Composer: skip new shell if graduated
- Kill file: `data/state/post_proof_dwell_KILL`

### Task 7: Docs registry + weekly analyst hook

**Files:**
- Register FEAT in `docs/features/README.md` + `SPECS_INDEX.md`
- Weekly fact pack snapshot `context.post_proof_dwell`

---

**Verify:** isolation green → CF report → shadow 14d → only then live GO.
