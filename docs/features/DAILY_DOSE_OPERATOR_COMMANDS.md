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

---

## Jev ranker shadow (measure-only)

Does **not** replace TG publish. Skim compare board; expand platform-relevance only if quality wins multi-day.

```bash
cd /home/brad/projects/crypto-trading-bot

# Against today's dose cards (no RSS refetch)
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ranker.py \
  --from-latest --top 5 --max-judge 8 --print-compare

# Full RSS pool → Jev (more spend)
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ranker.py --top 5 --max-judge 16

# Offline mock
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ranker.py --dry-run --from-latest
```

Artifacts:
- `data/state/daily_dose_jev_latest.json`
- `data/state/daily_dose_jev_compare.md`
- `data/state/daily_dose_jev_preview.txt` (marked 🧪 shadow)
- `data/state/daily_dose_jev_crumbs.jsonl`

Cron: `phase6-daily-dose-jev-ranker` — `15 7 * * *` PT → local only.

---

## Locked-pool A/B (fair twin — Brad GO 2026-09-19)

Runs **after** 08:00 publish so A and B share the same candidate freeze.

- **A** = published TG top-N (`daily_dose_edited.json`)
- **B** = Jev re-rank of `daily_dose_latest` draft ∪ A ids (same freeze)
- Plain move notes + optional Brad gut mark (`b_better` / `a_better` / `mixed`)
- Does **not** replace live dose · **not** a second TG brief · **not** a trade signal

```bash
cd /home/brad/projects/crypto-trading-bot

# Live locked A/B (uses today's edited + draft)
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ab.py --print-card

# Short operator card only
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ab.py --print-tg

# Offline
.venv/bin/python3 scripts/phase6/run_daily_dose_jev_ab.py --dry-run --print-card
```

Artifacts:
- `data/state/daily_dose_jev_ab_latest.json`
- `data/state/daily_dose_jev_ab_card.md`
- `data/state/daily_dose_jev_ab_history.jsonl`

Cron: `phase6-daily-dose-jev-ab` `ea05c1edf8b4` — `10 8 * * *` PT → **local**  
Optional TG short card: `DOSE_AB_TG=1` on the wrapper (default off).

Mark series (optional, chat): `dose ab b_better` | `a_better` | `mixed` — collect multi-day before any promote talk.

