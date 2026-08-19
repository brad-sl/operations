# Decision packet — <TRIAL_ID>

| Field | Value |
|-------|--------|
| Trial | |
| Family | |
| Decided at (UTC) | |
| By | brad |
| Enum | drop \| promote_* \| … |
| CR | **ACCEPT** `CR-…` \| **REJECT** \| **NO_CR** (observe/extend/abort) |

## Design (summary)
- Hypothesis:
- Primary window:
- Success bar (frozen):

## Outcome (measured)
- Primary pass: yes/no
- Class:
- N (primary):
- Δret vs baseline (pp):
- ΔDD vs baseline (pp):
- Report: `reports/…`

## Decision rationale
<3–6 sentences; plain English first>

## Follow-on
- `none` \| `extend` \| `scoped_shadow` \| `promotion_queue`
- Detail / ids:

## Notify
- Inbox: `docs/testing/inbox/DECIDED_…`
- Delivered: yes/no (channel)

## Live boundary
- Config writes this decision: **none** (or list gated next steps only)
