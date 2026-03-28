# ImageBot — What's Still Needed for Image Generation

**Status:** MINIMAL — Only 1 credential needed  
**Time to Ready:** 5-10 minutes  
**Date:** 2026-03-11 17:21 PDT

---

## ✅ Already Have

### Code & Framework
- ✅ `checkpoint-manager.ts` (checkpoint I/O)
- ✅ `spawn-with-memory.ts` (context injection)
- ✅ Full task definition & validation logic
- ✅ Memory continuity & recovery system
- ✅ All business logic for image generation workflow

### Infrastructure
- ✅ OpenClaw Gateway (running, healthy)
- ✅ Project directories (/orchestrator/agents/imagebot/)
- ✅ Memory system (MEMORY.md, checkpoints)

---

## ⏳ What's Missing

### 1. OpenAI API Key (DALLE-3 Access)

**What:** OpenAI API key with DALL-E 3 access  
**Why:** ImageBot calls `dalle3(prompt, {...})` to generate images  
**Cost:** $0.04 per image = $0.60 for 15 images  
**How to Get:**
```bash
1. Go to https://platform.openai.com/account/api-keys
2. Click "Create new secret key"
3. Copy the key
4. Set environment variable: export OPENAI_API_KEY="sk-..."
   (Or pass as parameter to ImageBot spawn)
```

**Time needed:** ~5 minutes (just copy/paste)

---

## How ImageBot Uses It

```typescript
// Inside ImageBot sub-agent spawn:
const image = await dalle3(prompt, {
  size: "1024x1024",
  quality: "standard"  // $0.04 per image
});

// Expected calls per run:
// 15 images × $0.04 = $0.60 total cost
```

---

## That's It!

Everything else is ready:

- ✅ Task definition (full)
- ✅ Checkpoint system (ready)
- ✅ Memory continuity (ready)
- ✅ Validation logic (ready)
- ✅ Infrastructure (healthy)

---

## To Execute ImageBot E2E Test

1. **Get OpenAI API key** (~5 min)
   - Create at https://platform.openai.com/account/api-keys
   - Set environment variable or pass to spawn

2. **Spawn ImageBot**
   ```
   Brad confirms: "Ready to generate images"
   Agent spawns with: OPENAI_API_KEY in environment
   ImageBot runs: ~14 min execution
   Checkpoint system tracks progress
   Outputs: 15 images + manifest
   ```

3. **Verify & Review**
   - Check STATE.json (completed: 15/15)
   - Check MANIFEST.json (all URLs valid)
   - Review images (spot-check 3 URLs)
   - Approve + proceed to next phase

---

## Optional Enhancements (Not Required)

- Google Cloud Storage (GCS) for image hosting (~$0.02/mo)
- Image compliance checker (ImageMagick, FFmpeg)
- Performance tracking dashboard

These are **Phase 2+** items. Not needed for E2E test.

---

## Go/No-Go Decision

**Current:** ⏳ Waiting on OpenAI API key  
**With API key:** ✅ Ready to execute E2E test immediately

---

_Last Updated: 2026-03-11 17:21 PDT_
