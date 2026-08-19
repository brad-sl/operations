# Task Handoff Document

**Task ID:** `P6-OPT-EX-05-DOSE-20260813`  
**Parent Task:** `P6-OPT-EXAMINE-PACK-20260813`  
**Assigned To:** crypto-engineer  
**Date Assigned:** 2026-08-13  

### Objective
Verify **Daily Dose v4** actually published (or last artifact) with basket-pair diversity and domain markdown links — not BTC×5 + raw URLs.

### Context
v4 editorial 2026-08-13: max 2 BTC-only, prefer non-BTC core basket primaries, `[domain](url)` links, no platform-why line. Cron SSOT Hermes only. DOSE-TPL-01 still blocked on content-editor (marketing profile — do not pull that profile into this pack).

### Must Do
- Find latest Dose artifact / preview / telegram body on disk
- Check: ≥1 non-BTC primary, ≤2 BTC-only, links are `[host](url)`, no “Why it matters on this platform”
- If cron didn’t fire yet, assess last pipeline preview and say so
- Call: `watch` if v4 held / `pursue` if regression (file a fix card, don’t silently rewrite editorial)
- Write `reports/OPT_EX_05_DOSE_2026-08-13.md`

### Must Not
- Change editorial rules again unless regression proven
- Publish to Telegram from this card
- Touch marketing consultancy

### Files
- Read: `phase6/core/daily_dose_publish.py`, `phase6/scripts/run_daily_dose.py`, latest dose state/output
- Write: report only

### Skills
`phase6-product-comms`

### Success
Quoted snippet of latest body + pass/fail on diversity + links.
