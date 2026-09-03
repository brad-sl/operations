## Candidate C · angle=evidence_clock
### Primary (exactly one task id)
`P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816`
### Optional secondary (0–1)
none
### Why now (≤5 bullets)
- GAP-04 is the explicit HARD-EXIT-EVIDENCE-CLOCK (COLLECTING); only staff if clock can mature per context table
- Finish/unblock ≤7d via watch on frozen bars + existing harness (READY flags); watch-not-build for immature clocks (n=0)
- Matches evidence_clock angle exactly; do not invent staged decisions; idle-with-reason OK
- Low drag, high evidence_honesty; avoids all live writes, prioritizes harness-ready over new build
- Provides clean unblock signal for L1 scale path without touching orders/capital or mid-cycle
### Kill / pass criteria
- Pass: clock matures (evidence collected, n>0) within ≤7d using only frozen bars / existing harness
- Kill: clock remains immature (n=0) after 7d, or requires live config / new code / staged decisions
### Must not touch
- No live config / order / capital writes from this packet
- No live promote without Brad
- Prefer frozen bars + existing harness; no build when clock n=0
- Ground IDs only from this table; idle-with-reason OK
### Effort class: S
