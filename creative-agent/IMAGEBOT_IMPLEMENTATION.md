# ImageBot End-to-End Implementation

**Status:** Ready for E2E Test  
**Date:** 2026-03-11 15:20 PDT  
**Scope:** Full ImageBot with checkpointing, resumption, and approval integration

---

## What ImageBot Does

1. **Receives:** Approved copy brief from CopyBot + project context
2. **Generates:** 15 DALL-E 3 images (5 themes × 3 each)
3. **Validates:** All images (format, size, compliance)
4. **Tracks:** Progress with checkpoints (STATE.json, MANIFEST.json)
5. **Outputs:** Manifest ready for human review + upload to GCS

**Cost:** $0.60 (15 images @ $0.04 each)  
**Time:** ~15 minutes (parallel would be faster in Phase 2)  
**Resumable:** Yes (via checkpoint system)

---

## Setup Complete ✅

### Files Created

1. **checkpoint-manager.ts** — Checkpoint I/O library
2. **spawn-with-memory.ts** — Sub-agent spawn utility
3. **SUB_AGENT_MEMORY_PROTOCOL.md** — Memory continuity spec
4. **SUB_AGENT_RECOVERY_PROTOCOL.md** — Recovery spec
5. **CREATIVE_AGENT_IMAGEBOT_TEMPLATE.md** — Integration guide

### Libraries Ready

- ✅ CheckpointManager (write/read state + manifest)
- ✅ spawnWithMemory (auto-attach MEMORY/USER/SOUL)
- ✅ checkpointOrStart (resume detection)

---

## ImageBot Task Definition

```typescript
import spawnWithMemory from "/workspace/lib/spawn-with-memory";

const imagebot_task = await spawnWithMemory({
  label: "imagebot-hr-saas-2026-03-11-e2e-test",
  task: `
## ImageBot — Generate 15 DALL-E Images

**Campaign:** HR SaaS (Phase 1 MVP)  
**Brief Status:** ✅ Approved by Brad (CopyBot complete)

### Context (Attached)
- MEMORY.md — Project state, decisions, progress
- USER.md — Brad's preferences & timezone
- SOUL.md — Operational philosophy
- CREATIVE_AGENT_IMAGEBOT_TEMPLATE.md — Job specification

### Your Job

1. **Read template** (attached: CREATIVE_AGENT_IMAGEBOT_TEMPLATE.md)
2. **Check checkpoint** (resumable from previous run?)
   \`\`\`
   const { isResume, checkpoint } = await checkpointOrStart("imagebot", SESSION_ID);
   if (isResume) {
     console.log("Resuming from checkpoint");
     startIndex = checkpoint.nextIndex;
   } else {
     console.log("Starting fresh");
     startIndex = 1;
   }
   \`\`\`

3. **Import CheckpointManager**
   \`\`\`
   import CheckpointManager from "/workspace/lib/checkpoint-manager.ts";
   const ckpt = new CheckpointManager("imagebot", SESSION_ID);
   \`\`\`

4. **Generate 15 DALL-E images** (5 themes × 3 each)
   - Speed: 3 images (sleek dashboard, fast throughput, competitive advantage)
   - Cost: 3 images (savings calc, budget optimization, cost reduction)
   - Quality: 3 images (quality metrics, reliability, performance)
   - Integration: 3 images (seamless data flow, connected ecosystem, API integration)
   - Social Proof: 3 images (customer testimonials, success stories, industry leaders)

5. **For each image:**
   \`\`\`
   // Generate
   const image = await dalle3(prompt, { size: "1024x1024", quality: "standard" });
   
   // Write checkpoint
   await ckpt.writeCheckpoint({
     progress: { completed: imageNum, total: 15, pending: 15 - imageNum },
     checkpointData: { 
       completedImages: [...allImages], 
       nextIndex: imageNum + 1 
     }
   }, allImages);
   \`\`\`

6. **Validate each image**
   - URL is HTTPS ✓
   - Status 200 (accessible) ✓
   - Content-Type: image/* ✓
   - Size < 100MB ✓
   - Dimensions 1024×1024 ✓
   - No policy violations ✓

7. **Generate final manifest**
   \`\`\`
   {
     "sessionId": "imagebot-...",
     "campaign": "HR_SaaS_Phase1",
     "generatedAt": "2026-03-11T22:20:00Z",
     "totalImages": 15,
     "totalCost": "$0.60",
     "images": [
       { "index": 1, "theme": "Speed", "prompt": "...", "url": "https://...", 
         "status": "valid", "validatedAt": "2026-03-11T22:05:00Z" },
       // ... 14 more
     ],
     "metadata": {
       "themes": ["Speed", "Cost", "Quality", "Integration", "Social Proof"],
       "imagesPerTheme": 3,
       "model": "dall-e-3",
       "quality": "standard"
     },
     "readyForUpload": true
   }
   \`\`\`

8. **Update memory logs**
   \`\`\`
   Append to /workspace/memory/2026-03-11.md:
   
   ### ImageBot Completion
   - **Time:** 2026-03-11T22:25:00Z
   - **Status:** ✅ Success
   - **Images:** 15/15 generated
   - **Cost:** $0.60
   - **Output:** imagebot_output.json + manifest
   - **Next:** Ready for Brad's review
   \`\`\`

9. **Mark complete**
   \`\`\`
   await ckpt.markComplete();
   \`\`\`

### Success Criteria
- [ ] 15 images generated (all themes)
- [ ] All validated (format, size, compliance)
- [ ] Manifest JSON created + validated
- [ ] Cost ≤ $0.60
- [ ] Ready for upload to GCS
- [ ] Checkpoint files created (STATE.json, MANIFEST.json, RECOVERY.md)
- [ ] Memory logs updated

### Failure Handling
- If API error: Log to memory/2026-03-11.md + checkpoint state
- If N images succeed: Save + offer resume option
- Never retry automatically (Brad decides next step)
  `,
  mode: "run",
  timeoutSeconds: 900,
  model: undefined  // Use default (openrouter/auto)
});

console.log(`✅ ImageBot spawned: ${imagebot_task.sessionId}`);
```

---

## End-to-End Test Plan

### Phase 1: Pre-Flight Check (Before Spawn)

```bash
✅ Verify all files exist:
   - /workspace/lib/checkpoint-manager.ts
   - /workspace/lib/spawn-with-memory.ts
   - /workspace/MEMORY.md
   - /workspace/USER.md
   - /workspace/SOUL.md
   - /workspace/projects/orchestrator/CREATIVE_AGENT_IMAGEBOT_TEMPLATE.md

✅ Verify memory is readable:
   - grep -c "CopyBot" /workspace/MEMORY.md
   - Expected: ≥ 1 match

✅ Verify project structure:
   - mkdir -p /workspace/projects/orchestrator/agents/imagebot/shared
```

### Phase 2: Spawn ImageBot (Live Run)

**Command:**
```bash
# This is pseudo-code; actual spawn happens in agent session
sessions_spawn({
  runtime: "subagent",
  mode: "run",
  label: "imagebot-hr-saas-2026-03-11-e2e-test",
  task: <task definition above>,
  attachments: [
    { name: "MEMORY.md", content: <read workspace MEMORY.md> },
    { name: "USER.md", content: <read workspace USER.md> },
    { name: "SOUL.md", content: <read workspace SOUL.md> },
    { name: "CREATIVE_AGENT_IMAGEBOT_TEMPLATE.md", content: <read from projects> }
  ],
  timeoutSeconds: 900
});
```

### Phase 3: Monitor Execution (Real-Time)

**What to expect:**
```
T+0min:    ImageBot spawned, reads context
T+1min:    Checks checkpoint (should be empty, fresh start)
T+1-2min:  Generates images 1-5 (Speed theme)
           Writes checkpoint after image #5
T+3-5min:  Generates images 6-10 (Cost + Quality themes)
           Writes checkpoint after image #10
T+7-12min: Generates images 11-15 (Integration + Social Proof themes)
           Final validation
T+12-14min: Writes manifest.json, RECOVERY.md, updates memory
T+14min:   ✅ Complete
```

### Phase 4: Verify Checkpoint Files

**After ImageBot completes:**
```bash
# Check checkpoint structure
ls -la /workspace/projects/orchestrator/agents/imagebot/
  ├─ STATE.json          (current progress)
  ├─ MANIFEST.json       (all 15 image URLs)
  └─ RECOVERY.md         (how to resume)

# Verify STATE.json
jq '.progress.completed' /workspace/projects/orchestrator/agents/imagebot/STATE.json
Expected: 15

# Verify MANIFEST.json
jq '.summary.completed' /workspace/projects/orchestrator/agents/imagebot/MANIFEST.json
Expected: 15

# Verify all URLs are valid
jq -r '.images[].url' /workspace/projects/orchestrator/agents/imagebot/MANIFEST.json | \
  head -1 | xargs curl -I
Expected: HTTP/1.1 200 OK
```

### Phase 5: Test Resume (Simulate Crash)

**Simulate crash at image 10:**
```bash
# Manually edit STATE.json to pretend we crashed
cat > /workspace/projects/orchestrator/agents/imagebot/STATE.json << 'EOF'
{
  "sessionId": "imagebot-hr-saas-2026-03-11-e2e-test-resume",
  "status": "in_progress",
  "progress": { "completed": 10, "total": 15, "pending": 5 },
  "recovery": { "canResume": true, "resumePoint": "image #11" },
  "checkpointData": {
    "completedImages": [...first 10 images...],
    "nextIndex": 11,
    "budgetUsed": 0.40,
    "budgetRemaining": 0.20
  }
}
EOF

# Re-spawn ImageBot with recovery context
sessions_spawn({
  label: "imagebot-hr-saas-2026-03-11-e2e-test-resume",
  task: "Resume ImageBot from checkpoint (image #11). Complete images 11-15.",
  attachments: [
    { name: "STATE.json", content: <from checkpoint> },
    { name: "MANIFEST.json", content: <existing 10 images> },
    { name: "RECOVERY.md", content: <recovery instructions> },
    { name: "MEMORY.md", content: <project context> }
  ]
});

# Expected: Skips 1-10, generates 11-15, saves $0.40
```

### Phase 6: Verify Memory Updates

**After completion:**
```bash
# Check daily log
grep -A5 "ImageBot Completion" /workspace/memory/2026-03-11.md
Expected: Status ✅, 15/15 images, $0.60 cost, ready for upload

# Check MEMORY.md (long-term)
grep "ImageBot" /workspace/MEMORY.md
Expected: Updated status in Creative Agent section
```

### Phase 7: Review Output Files

**Brad's manual review:**
```
/workspace/projects/orchestrator/agents/imagebot/
├─ MANIFEST.json (15 image URLs)
├─ STATE.json (final checkpoint)
└─ RECOVERY.md (completion summary)

Download manifest, spot-check 3 image URLs (click in browser)
Expected: All render correctly, 1024×1024 PNG, HR SaaS themed
```

### Phase 8: Update Project Status

**After approval, update CREATIVE_AGENT_IMPLEMENTATION.md:**
```markdown
**✅ COMPLETE (2026-03-11 22:25 PDT):**
- [x] ImageBot MVP: 15 DALL-E images (5 themes × 3 each)
  - All themes: Speed, Cost, Quality, Integration, Social Proof ✅
  - All validated: Format, size, compliance ✅
  - Total cost: $0.60 ✅
  - Manifest ready: imagebot_output.json ✅
  - Checkpoint system verified ✅
  - Resume tested & working ✅

**Next (Today/Tomorrow):**
- [ ] Creative Agent orchestrator (spawn CopyBot + ImageBot in parallel)
- [ ] GCS upload setup
- [ ] Approval gating workflow
```

---

## Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Images generated | 15 | ? |
| All validated | 100% | ? |
| Cost | $0.60 | ? |
| Checkpoints created | STATE + MANIFEST + RECOVERY | ? |
| Resume functionality | Skips 1-10, generates 11-15 | ? |
| Memory updated | Daily log + MEMORY.md | ? |
| Time to completion | <15 min | ? |

---

## Rollback Plan (If Issues)

**If ImageBot fails:**
1. Check STATE.json for last safe point
2. Read RECOVERY.md for instructions
3. Options:
   - Resume from checkpoint (saves $0.40, 9 min)
   - Restart fresh ($0.60, 15 min)
   - Debug specific image (manual DALL-E call)

**If checkpoints corrupt:**
1. Check git history (committed)
2. Reconstruct from memory logs
3. Manual re-generation as last resort

---

## Ready to Execute

All systems in place. Ready to spawn ImageBot E2E test.

**Next Step:** Brad confirms, we spawn ImageBot with full context + checkpointing.

---

_Last Updated: 2026-03-11 15:20 PDT_  
_Test Status: Ready to execute_  
_Estimated Duration: 15 min execution + 5 min verification = 20 min total_
