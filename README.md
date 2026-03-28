# Brad's Operations Network

**Org Model:** 6 autonomous departments + manager (Brad)  
**Communication:** GitHub (source of truth) + weekly digests  
**Task Tracking:** GitHub Projects board  

---

## Departments

| Department | Owner | Focus | MEMORY Location |
|-----------|-------|-------|-----------------|
| **SearchAds** | SearchAds Agent | Google Ads, keywords, search campaigns | `/searchads/MEMORY.md` |
| **CreativeStudio** | CreativeStudio Agent | Images, copy, Meta/TikTok, design | `/creative/MEMORY.md` |
| **TradingFloor** | TradingFloor Agent | Crypto bot, Phase 4, strategy | `/trading/MEMORY.md` |
| **Analytics** | Analytics Agent | Performance analysis, anomalies | `/analytics/MEMORY.md` |
| **Infrastructure** | Infrastructure Agent | APIs, configs, deployment | `/infra/MEMORY.md` |
| **Research** | Research Agent | Market trends, competitive data | `/research/MEMORY.md` |

---

## Directory Structure

```
operations/
├── searchads/
│   ├── MEMORY.md (auto-prune >30d, keep deliverables)
│   ├── deliverables/
│   │   ├── campaigns/
│   │   ├── keyword-research/
│   │   └── optimization-reports/
│   └── projects/
│
├── creative/
│   ├── MEMORY.md
│   ├── deliverables/
│   │   ├── assets/
│   │   ├── copy/
│   │   └── design-briefs/
│   └── projects/
│
├── trading/
│   ├── MEMORY.md
│   ├── deliverables/
│   │   ├── backtests/
│   │   ├── phase-reports/
│   │   └── strategies/
│   └── projects/
│
├── analytics/
│   ├── MEMORY.md
│   ├── deliverables/
│   │   ├── weekly-summaries/
│   │   ├── performance-analysis/
│   │   └── anomaly-reports/
│   └── projects/
│
├── infra/
│   ├── MEMORY.md
│   ├── deliverables/
│   │   ├── configs/
│   │   ├── incidents/
│   │   └── documentation/
│   └── projects/
│
└── research/
    ├── MEMORY.md
    ├── deliverables/
    │   ├── market-analysis/
    │   ├── competitive-research/
    │   └── insights/
    └── projects/
```

---

## Metadata Format

Every deliverable includes:

```yaml
---
project: [Project Name]
owner: [Department/Agent]
assignee: [Who needs to action it, if cross-team]
status: draft | in-review | approved | active | archived
created: 2026-03-27
updated: 2026-03-27
---

# Content here
```

---

## Status Updates

**Weekly Digest (Friday 6 PM PT):**
- SearchAds: Top keywords, campaign performance, optimization wins
- CreativeStudio: New assets, A/B test results, top performers
- TradingFloor: Trade stats, strategy tweaks, phase progress
- Analytics: ROAS trends, anomalies, recommendations
- Infrastructure: Uptime %, incidents, new tooling
- Research: Market trends, opportunities identified

**GitHub Projects Board:**
- Columns: Backlog → In Progress → Review → Done
- Each agent manages their own cards
- Brad can check anytime (no prompting needed)

---

## Collaboration Rules

**Direct agent-to-agent (no Brad approval):**
- SearchAds ↔ CreativeStudio (copy)
- Analytics ↔ Any department (data requests)
- CreativeStudio ↔ Research (trends)

**Requires Brad approval:**
- Budget changes >5% of plan
- New campaign launches
- Major strategy pivots
- Resource conflicts

**Brad gets heads-up (no approval needed):**
- Weekly summaries
- Critical alerts
- New opportunities
- Cross-team escalations

---

## Launch Timeline

**Monday (2026-03-31):**
1. Create GitHub repo `brad-sl/operations`
2. Spawn 6 agents
3. Initialize GitHub Projects board
4. Each agent sets up their MEMORY.md

**Week 1:**
- Agents transfer dept-specific knowledge
- First deliverables committed
- First weekly summary (Friday)

**Week 2+:**
- Auto-prune stale memories
- Full autonomy mode
- Brad checks task board 1x daily

---

## Success Metrics

- Token efficiency: MEMORY.md < 1000 lines per dept
- Decision velocity: 24-48h turnaround on requests
- Autonomy: <5% of decisions require Brad escalation
- Visibility: Brad reads task board 5 min, weekly summary 10 min

