#!/usr/bin/env bash
# One-shot ~30d Stoch observe recheck (parent CLOSED continue_observe_only 2026-08-04).
# Real data only. No live config. No combo-fishing. Writes reports + plain-English brief to stdout.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PY="${PWD}/.venv/bin/python3"
DAY=$(date -u +%Y-%m-%d)

echo "=== Stoch 30d re-eval (${DAY} UTC) ==="
echo "Parent: STOCH-RSI-PARALLEL-20260721 (CLOSED continue_observe_only)"
echo "Question: with more organic tags, would any decision of substance change?"
echo

# 1) Instrumentation still healthy (cache+history), not trial RUNNING gate
echo "--- cache / history snapshot ---"
"$PY" - <<'PY'
import json
from pathlib import Path
from datetime import datetime, timezone
cache = json.loads(Path("data/state/rsi_cache.json").read_text())
rsi = cache.get("rsi") or {}
n = len(rsi)
n_stoch = sum(1 for v in rsi.values() if isinstance(v, dict) and v.get("stoch_k") is not None)
ts = cache.get("timestamp")
print(f"pairs={n} with_stoch={n_stoch} cache_ts={ts}")
hist = Path("data/state/rsi_indicator_history.jsonl")
print(f"history_lines={sum(1 for _ in hist.open()) if hist.exists() else 0}")
PY

# 2) Entry-time Stoch→SL dig (do not mutate closed child trial JSON)
echo
echo "--- entry-time Stoch→SL dig (no-state) ---"
"$PY" phase6/research/run_stoch_sl_predictor.py \
  --phase reeval30d \
  --no-state \
  --start 2026-07-11T00:00:00+00:00

DIG_MD=$(ls -1t reports/STOCH_SL_PREDICTOR_REEVAL30D_*.md 2>/dev/null | head -1 || true)
if [[ -n "${DIG_MD}" ]]; then
  echo "Dig report: ${DIG_MD}"
  # Pull plain-English lines
  grep -E '^\*\*(Plain English|Recommendation)\*\*|^## Primary test|Lift \(low/high\)' "$DIG_MD" | head -20 || true
fi

# 3) Parallel instrumentation counts since original launch (adhoc report, non-final)
echo
echo "--- parallel instrumentation counts (adhoc) ---"
"$PY" phase6/research/run_stoch_rsi_trial_report.py --phase adhoc || true
ADHOC=$(ls -1t reports/STOCH_RSI_TRIAL_ADHOC_*.md 2>/dev/null | head -1 || true)
if [[ -n "${ADHOC}" ]]; then
  echo "Adhoc report: ${ADHOC}"
  head -40 "$ADHOC"
fi

# 3b) Allocator/rotation missed-opportunity dig (log-only shadow)
echo
echo "--- Stoch rotation / allocator opportunity dig ---"
"$PY" phase6/research/stoch_rotation_opportunity.py --phase reeval30d --start 2026-07-21T00:00:00+00:00 || true
ROPP=$(ls -1t reports/STOCH_ROTATION_OPP_*.md 2>/dev/null | head -1 || true)
if [[ -n "${ROPP}" ]]; then
  echo "Rotation opp report: ${ROPP}"
  head -45 "$ROPP"
fi

# 4) Decision of substance gate (stdout brief for Telegram)
echo
echo "=== Plain-English go/no-go ==="
"$PY" - <<'PY'
import json, re
from pathlib import Path
from datetime import datetime, timezone

# Prefer newest reeval dig JSON
cands = sorted(Path("reports").glob("STOCH_SL_PREDICTOR_REEVAL30D_*.json"), reverse=True)
if not cands:
    print("NO_GO: missing reeval dig JSON — check runner.")
    raise SystemExit(0)
payload = json.loads(cands[0].read_text())
a = payload.get("analysis") or {}
rec_obj = a.get("recommendation") or {}
if isinstance(rec_obj, dict):
    rec = rec_obj.get("enum") or "(missing)"
    plain = rec_obj.get("plain_english") or ""
    go_live = bool(rec_obj.get("go_live_sl_change"))
    go_alloc = bool(rec_obj.get("go_allocator_change"))
    go_shadow = bool(rec_obj.get("go_shadow"))
else:
    rec = str(rec_obj or a.get("enum") or "(missing)")
    plain = a.get("plain_english") or a.get("summary") or ""
    go_live = go_alloc = go_shadow = False
# primary lift if structured
primary = a.get("primary_7d_stoch30") or a.get("primary") or a.get("primary_test") or {}
lift = None
if isinstance(primary, dict):
    lift = primary.get("lift")
    if lift is None and "rate_low" in primary and "rate_high" in primary:
        try:
            hi = float(primary["rate_high"]) or 1e-9
            lift = float(primary["rate_low"]) / hi
        except Exception:
            pass
# fallback scan markdown twin
md = cands[0].with_suffix(".md")
text = md.read_text() if md.exists() else ""
m = re.search(r"Lift \(low/high\):\s+\*\*([0-9.]+)\*\*", text)
if m and lift is None:
    try:
        lift = float(m.group(1))
    except ValueError:
        pass
m2 = re.search(r"\*\*Recommendation:\*\*\s+\*\*(\w+)\*\*", text)
if m2 and rec == "(missing)":
    rec = m2.group(1)
m3 = re.search(r"\*\*Plain English:\*\*\s+(.+)", text)
if m3 and not plain:
    plain = m3.group(1).strip()

n_stoch = a.get("n_with_entry_stoch")
n_buys = a.get("n_buys")
print(f"Coverage: buys={n_buys} with_entry_stoch={n_stoch}")
print(f"Dig recommendation: {rec}")
if plain:
    print(f"Plain English: {plain}")
if lift is not None:
    print(f"Primary entry Stoch lift (low/high @7d): {lift}")

# Gates — same class rules as entry-time dig
# inverted/flat → no substance change; do not open live SL/allocator work
substance = False
reason = []
if isinstance(lift, (int, float)):
    if lift >= 1.5:
        substance = True
        reason.append(f"lift {lift:.2f} ≥ 1.5 (would justify scoped shadow SL-risk only, still not live)")
    elif lift < 0.9:
        reason.append(f"lift {lift:.2f} still inverted/flat — no leading SL utility")
    else:
        reason.append(f"lift {lift:.2f} mild — observe only, not substance for live knobs")
rec_l = str(rec).lower()
if rec_l in {"no_utility_drop", "drop"}:
    substance = False
    reason.append(f"enum={rec} → keep observe tags only")
elif rec_l in {"scoped_shadow_sl_risk", "propose_scoped_sl_risk_experiment", "propose_scoped_experiment"}:
    substance = True
    reason.append(f"enum={rec} → substance only as shadow proposal, not allocator")
if go_live or go_alloc:
    substance = True
    reason.append(f"runner flagged go_live_sl={go_live} go_allocator={go_alloc} (still requires Brad go)")
elif go_shadow and rec_l not in {"no_utility_drop", "drop"}:
    substance = True
    reason.append("go_shadow=True — shadow proposal class only")

print()
if substance:
    print("SUBSTANCE?: YES (proposal-class only — still no auto live change)")
    print("Next: human review dig report; do not combo-fish; no allocator/SL live without Brad go.")
else:
    print("SUBSTANCE?: NO — nothing of substance changed vs 2026-08-03/04 close posture")
    print("Next: keep 15m RSI+Stoch logger; no new Stoch mashup trials; free capacity for other roadmap.")
# Rotation / allocator opportunity appendix
ropp = sorted(Path("reports").glob("STOCH_ROTATION_OPP_*.json"), reverse=True)
if ropp:
    ra = (json.loads(ropp[0].read_text()).get("analysis") or {})
    rr = ra.get("recommendation") or {}
    print()
    print("--- Allocator/rotation opportunity ---")
    print(f"Rotation dig enum: {rr.get('enum')}")
    print(f"Plain English: {rr.get('plain_english')}")
    fwd = ra.get("forward_compare_72h") or {}
    print(f"72h buy-vs-stoch-alt n={fwd.get('n')} mean_delta={fwd.get('mean_delta_alt_minus_bought')}")
    print(f"missed_stoch_buy_events={ra.get('missed_stoch_buy_events')} flags={ra.get('flag_counts')}")
    if rr.get("go_allocator_change"):
        substance = True
        reason.append("rotation dig flagged allocator change (still requires Brad go)")

print("Rules: real data only; no live config; entry-time not exit-time trailing; no combo-fishing.")
print("Reports: STOCH_SL_*REEVAL*, STOCH_ROTATION_OPP_*, STOCH_RSI_TRIAL_ADHOC_*")
print("Generated:", datetime.now(timezone.utc).isoformat())
for r in reason:
    print(f"- {r}")
PY

echo
echo "DONE stoch 30d re-eval"
