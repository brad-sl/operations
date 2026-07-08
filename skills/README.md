# Hermes skills (shareable)

Portable **[Hermes Agent](https://hermes-agent.nousresearch.com/docs)** skills from the Phase 6 / ANALYST-OPT orchestrator workflow. Copy into any project or straight into `~/.hermes/skills/`.

## Contents

| Skill | Use when |
|-------|----------|
| [**platform-orchestrator-loop**](platform-orchestrator-loop/SKILL.md) | Building or refactoring a long-lived platform with slice-based epics, isolation tests, file-backed run ledgers, shadow-before-live |
| [**crypto-analyst-scenario-run**](crypto-analyst-scenario-run/SKILL.md) | *Example vertical* — optimization scenarios, gates, regime scorecard (this repo’s trading stack) |

## Quick install (one skill)

```bash
SKILL=platform-orchestrator-loop
mkdir -p ~/.hermes/skills/$SKILL
curl -fsSL "https://raw.githubusercontent.com/YOUR_ORG/crypto-trading-bot/main/skills/$SKILL/SKILL.md" \
  -o ~/.hermes/skills/$SKILL/SKILL.md
```

Replace `YOUR_ORG/crypto-trading-bot` with your fork after publish.

**From a local clone:**

```bash
cp -r skills/platform-orchestrator-loop ~/.hermes/skills/
```

## Use in Hermes

1. Restart not required — skills load each message.
2. In chat: `skill_view(name='platform-orchestrator-loop')` before a big build session.
3. Optional: add to profile `skills/` or pin via `hermes curator pin platform-orchestrator-loop`.

## Bootstrap a new repo

1. Copy [`platform-orchestrator-loop/QUICK_START_ORCHESTRATOR_PROMPT.md`](platform-orchestrator-loop/QUICK_START_ORCHESTRATOR_PROMPT.md) into the first message (fill `{{PROJECT}}`, etc.).
2. Install the orchestrator skill (above).
3. Create `docs/epics/YOUR-EPIC.md` using [reference epic](../docs/epics/ANALYST-OPT_EPIC.md) in this repository as a template.

## What makes this manageable

- **R0…Rn slices** — one exit test per phase  
- **`test_isolation_*`** — agent claims backed by fast scripts  
- **jsonl + `*_latest.json`** — memory that compounds without bloating Hermes context  
- **Handoffs** — survive session compaction  
- **Gates + shadow overlay** — experiments don’t accidentally become production  
- **Pitfalls in SKILL.md** — mistakes become procedure (`skill_manage(patch)`)

## License

Same as the parent repository. Skills are documentation/procedure — adapt freely; attribution appreciated.

## Also in this repo

- `docs/hermes/shareable/` — mirror of these files (kept in sync when we update the pack)
- `docs/research/CRYPTO_ANALYST_PERSONALITY.md` — persona spec for the analyst vertical