# Tryout decision discipline (Jev-process map)

## Intent
Raise P(profitable tryout outcomes) by borrowing **process discipline** from
the HFT/Jev architecture — not by bolting a sub-second model onto a multi-hour
funnel.

```
deterministic funnel state
        → atomic judgments (our sensors)
        → code policy (config thresholds)
        → hard veto (kill / regime / toxic src)
        → action + calibration triple
```

## What ships
| Piece | Path |
|-------|------|
| Config SSOT | `config/tryout_decision_discipline.json` |
| Core | `phase6/core/tryout_decision_discipline.py` |
| Composer hook | `rsi_event_tryout_seat_composer` (shadow) |
| Outcome crumb | `pair_funnel_dwell.on_tryout_exit` → outcomes jsonl |
| Triples | `data/state/tryout_decision_triples.jsonl` |
| Latest | `data/state/tryout_decision_discipline_latest.json` |

## Default fence
- **`live_apply: false`** — logs `would_block` / `would_reduce`; **does not**
  change seat money path.
- Flip only after calibration N + Brad GO in the config file (not a chat vibe).

## Atomic judgments
regime_door · rsi_wash_depth · sent_clear · eng_source_grade · latch_fresh ·
seat_headroom · behavior_prior (dwell N) · setup_quality (0–3 composite)

## Policy ladder (first match)
kill/regime → toxic source → sent fail → no seats → behavior skip (N≥5) →
stale latch observe → low conf observe → reduced shell → full shell

## CLI
```bash
PYTHONPATH=. python3 scripts/phase6/run_tryout_decision_discipline.py
PYTHONPATH=. python3 scripts/phase6/run_tryout_decision_discipline.py --pair LINK-USD --rsi 35 --eng 0.40
PYTHONPATH=. python3 scripts/phase6/test_isolation_tryout_decision_discipline.py
```

## Why this should help P&L (honest)
1. **Abstain on toxic/weak eng sources** when live (free/tee already blocked;
   discipline makes the ladder explicit + logged).
2. **Skip chronic fast-SL / sl_heavy names** only after dwell N — cuts process
   tax, not folklore.
3. **Reduced shell on middling setup** when live — same dual-clear, less capital
   at risk while learning.
4. **Calibration triples** turn monthly dwell into reliability curves before
   any live gate.

## Not in scope
- Jev API / TypeSafe spend
- Sub-bar microstructure MM
- Replacing evaluate_buy_entry hard doors
