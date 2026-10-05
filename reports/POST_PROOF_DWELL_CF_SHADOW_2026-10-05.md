# Post-Proof Dwell — CF + Shadow ship receipt

**Date:** 2026-10-05  
**Brad GO:** GO both (CF + shadow, still no live)  
**Edge class:** `ATTENTION_ONLY_less_loss_path`  
**live_apply:** **false** (kill file + config)

## What shipped

| Piece | Path |
|-------|------|
| Config | `config/post_proof_dwell.json` |
| Core | `phase6/core/post_proof_dwell.py` |
| CF pack | `phase6/research/run_post_proof_dwell_cf.py` |
| Isolation tests | `scripts/phase6/test_isolation_post_proof_dwell.py` (8/8) |
| Policy | `docs/features/POST_PROOF_DWELL_POLICY.md` |
| Plan | `docs/plans/2026-10-05-post-proof-dwell.md` |
| CF report | `reports/POST_PROOF_DWELL_CF_LATEST.md` |
| CF JSON | `data/state/post_proof_dwell_cf_latest.json` |
| State | `data/state/post_proof_dwell.json` (seeded from ledger) |
| Shadow crumbs | `data/state/post_proof_dwell_shadow_crumbs.jsonl` |

### Wires (shadow-safe)

1. **Ledger SELL** → `stamp_proof_from_sell` (TP graduate / SL demote)
2. **Composer** → `apply_to_composer_candidate` (would_block log; skip only if live_apply)
3. **Scale-window** → `should_skip_scale_window_eject` (shadow keeps would_eject; live would clear)
4. **Weekly analyst** → `context.post_proof_dwell` + output contract section

## CF first read (honest)

### Tier A — post-TP tryout ban

| Arm | Blocked tryout buys | Est eject fees avoided | TP-after blocked (miss $) | Net sketch |
|-----|--------------------:|-----------------------:|--------------------------:|-----------:|
| 24h | 1 | +$0.45 | 0 | **+$0.45** |
| 48h | 5 | +$1.35 | 2 (−$3.84 TP) | −$2.49 |
| 7d | 8 | +$1.80 | 3 (−$6.19 TP) | −$4.40 |

**Read carefully:** longer bans block more thrash **and** can block a later TP on a re-seated shell. That is not “ban longer = better.” Prefer **graduate + short post-TP ban** over blanket 7d tryout freeze. 24h arm is fee-positive on this thin N; 48h/7d net sketches go red because they also block shells that later printed TP.

### Tier B — hold-after-TP mark @7d

- 5 TP events; 3 with OHLCV mark  
- Mark green after RT fee est: **1/3**  
- Path hit ~−3% SL band: **1/3** (LINK trail TP Sep 29 → path min −8.7%)  
- LINK fixed TP Sep 18 → mark +14% after fee (supports dwell **after** that proof)  
- SOL trail Oct 2 → mark ~flat after fee  

**Cannot claim buy/hold alpha.** Context only.

### Per-pair tax (matches churn thesis)

- LINK: 2 TP (+$6.90), 3 eject, **3** post-TP tryout ≤48h  
- SOL: 1 TP (+$2.43), 1 eject, 1 post-TP tryout  
- ZEC: 2 TP (+$2.10), 0 eject, 1 post-TP tryout  
- HYPE/TIA: 0 TP, eject-only (dwell must **not** protect)

### Seeded graduated (if continuous stamps)

**LINK-USD, SOL-USD** active under default 7d window from last proof (shadow would_block LINK = true, apply_block = false).

## Safety

- `live_apply: false`  
- Kill: `data/state/post_proof_dwell_KILL`  
- Eject path for unproven shells unchanged  
- Scale-window shadow still shows would_eject for board honesty  

## Cycles to promote / adjust

1. Let shadow crumbs accumulate ≥7–14d on composer + scale-window board  
2. Re-run `python phase6/research/run_post_proof_dwell_cf.py --write` weekly  
3. Watch: false blocks of good shells vs avoided eject fee tax  
4. Tune: `post_tp_tryout_ban_hours` (start 24–48), dwell hours, min TP meat  
5. **Brad GO** required for `live_apply: true`  

## Tests run

- `test_isolation_post_proof_dwell.py` 8/8  
- `test_isolation_tryout_scale_window.py` 12/12  
- `test_isolation_analyst_weekly_trade_review.py` 6/6  

## CLI

```bash
PYTHONPATH=. .venv/bin/python phase6/research/run_post_proof_dwell_cf.py --write
PYTHONPATH=. .venv/bin/python -c "from phase6.core.post_proof_dwell import snapshot; print(snapshot())"
```
