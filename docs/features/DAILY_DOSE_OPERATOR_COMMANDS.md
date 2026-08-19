# Daily Dose — operator quick commands

**Spec:** `docs/features/DAILY_DOSE_PUBLICATION_CYCLE.md`  
**TG:** scheduled via Hermes cron `daily-dose-telegram` → this channel (Brad OK)

```bash
cd /home/brad/projects/crypto-trading-bot

# Full pipeline (D0→D1→D2) + print publish body
bash phase6/scripts/run_daily_dose_pipeline.sh

# D0 only — machine draft
.venv/bin/python3 phase6/scripts/run_daily_dose.py --print-preview

# D1 — content-editor package (APPROVED or REVISE)
.venv/bin/python3 phase6/scripts/run_daily_dose_edit.py \
  --status APPROVED \
  --reviewer content-editor \
  --top 5 \
  --notes "your cuts" \
  --print
# optional: --drop-ids id1,id2  --keep-ids id1,id2
#           --title-override 'id=New title'
#           --why-override is deprecated no-op (platform-why retired 2026-08-13)

# D2 — publisher disk ship (blocks unless APPROVED + diversity)
.venv/bin/python3 phase6/scripts/run_daily_dose_publish.py --print

# Artifacts
#   data/state/daily_dose_latest.json
#   data/state/daily_dose_edited.json
#   data/state/daily_dose_publish_ready.txt
#   data/state/daily_dose_telegram_preview.txt   (D0 only)
#   data/state/daily_dose_brad_telegram_ok.flag
```

**Editorial v4 (2026-08-13):**  
- **No** per-bullet “Why it matters on this platform” lines (retired)  
- Diversity: **max 2** pure `btc_tape` + **max 2 BTC-only** cards; prefer non-BTC basket primaries  
- TG links: `[domain](article-url)` — no raw long URL lines  
- Tone: positive but honest (no gloom-porn)  
- Publish gate: APPROVED + btc_tape ≤ 2 + btc_only ≤ 2  
- Method: `v4_basket_pair_diversity_domain_links_2026-08-13`  

**Publish gate:** `editorial_review.status` must be `APPROVED`.  
**Cron:** `daily-dose-telegram` — `0 8 * * *` America/Los_Angeles → Telegram home.
