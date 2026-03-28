# Stop-Slop Quick Reference

**What it does:** Removes AI-generated prose patterns from marketing copy (ads, headlines, descriptions, blog posts)

**Quality threshold:** 8/10 (average across 5 dimensions)

---

## 🚫 Banned Phrases (Remove Immediately)

```
• let's explore          • journey              • leverage
• it's important to      • paradigm             • harness
• at the end of day      • synergy              • ecosystem
• in fact                • tap into             • unleash
• arguably               • unlock               • transform
• taking it to next      • revolutionary       • groundbreaking
```

---

## ❌ Structural Anti-Patterns

| Anti-Pattern | Bad Example | Good Example |
|--------------|-------------|--------------|
| **Binary contrast** | Not just a tool, but a partner | Purpose-built for remote teams |
| **Passive voice** | Budgets are optimized | We optimize your budget |
| **Wh- starters** | What if you could...? | Increase your sales by 40% |
| **Dramatic fragmentation** | Speed. Reliability. Trust. | Fast, reliable, trustworthy |
| **False agency** | The tool understands your needs | Customize settings to your workflow |

---

## ✅ Better Copy (5 Dimensions)

| Dimension | ✅ Good | ❌ Bad |
|-----------|---------|--------|
| **Directness** | "Boost sales 40%" | "You might want to consider..." |
| **Rhythm** | Varied sentence lengths | All sentences same length |
| **Trust** | Clear & simple | Jargon & over-explanation |
| **Authenticity** | Human tone, no clichés | Corporate speak |
| **Density** | No filler words | "Very," "really," "quite" |

---

## 🧪 Test Your Copy

```bash
cd ~/.openclaw/workspace/operations/orchestration

# Run full test suite
node dist/test-stop-slop.js

# Test one phrase (in TypeScript REPL)
npx ts-node -e "
import StopSlopFilter from './StopSlopFilter.ts';
const f = new StopSlopFilter();
console.log(f.formatReport('Your copy here'));
"
```

---

## 📊 Scoring Example

**Copy:** "Unlock Your Artistic Potential Today"

**Output:**
```
Directness:    9/10 (clear intent)
Rhythm:        8/10 (good flow)
Trust:         9/10 (respects reader)
Authenticity:  8/10 (mostly human, but "unlock" is cliché)
Density:       8/10 (no filler)
─────────────────────
AVERAGE:       8/10 ✅ PASS

⚠️ Issues:
• Remove cliché: "unlock"
```

---

## 🤖 Automated Checks

**Creative Optimizer runs automatically:**
- **When:** Fridays at 6 PM PT
- **Where:** Admin Agent workflow
- **What it checks:** All ad copy (headlines, descriptions, callouts, primary text)
- **Action:** Flags quality < 8/10, suggests fixes

---

## 📝 Platform Limits (with quality check)

| Platform | Field | Max | Quality Dims |
|----------|-------|-----|--------------|
| Google Ads | Headline | 30 chars | Directness, Trust |
| Google Ads | Description | 90 chars | All 5 |
| Google Ads | Callout | 25 chars | Density |
| Meta | Primary text | 125 chars | Authenticity, Density |
| Meta | Headline | 40 chars | Directness |

---

## 💡 Quick Fixes

| Issue | Fix |
|-------|-----|
| "Let's explore..." | Make a statement instead |
| "The tool understands" | "Adjust settings to..." |
| Passive voice | Convert to active voice |
| "Very," "really," "quite" | Delete filler words |
| ALL CAPS WORDS | Use normal case (unless brand voice) |
| Em dashes overuse | Replace with periods or commas |

---

## 📦 Files in This Workspace

```
operations/orchestration/
├── StopSlopFilter.ts              ← Core implementation
├── stop-slop-rules.md             ← Rules reference
├── test-stop-slop.ts              ← Test suite
├── STOP_SLOP_INTEGRATION.md       ← Setup guide
├── STOP_SLOP_DEPLOYMENT_REPORT.md ← Test results
└── STOP_SLOP_CHEATSHEET.md        ← This file
```

---

## 🎯 Integration Points

1. **Creative Optimizer** (automatic, Friday 6 PM PT)
   - Validates all ad copy before upload
   - Flags quality < 8/10
   - Suggests improvements

2. **Creative Agent** (during campaign creation)
   - CopyBot generates copy
   - Stop-Slop filter validates
   - Only approved copy uploads to Google Ads/Meta

3. **Manual usage** (test anytime)
   - Run test suite
   - Check specific copy
   - Get improvement suggestions

---

## 📞 Commands

```bash
# Test suite
node dist/test-stop-slop.js

# Evaluate one phrase
npx ts-node -e "import StopSlopFilter from './StopSlopFilter.ts'; const f=new StopSlopFilter(); console.log(f.formatReport('Your copy'));"

# Recompile after edits
npx tsc StopSlopFilter.ts test-stop-slop.ts --outDir dist --lib es2020 --module commonjs --target es2020

# Check compilation
npm list ts-node typescript
```

---

**Status:** ✅ Production Ready  
**Test Coverage:** 4/4 passing  
**Last Updated:** 2026-03-18 17:15 PT  
**Author:** Admin Agent Workflow  
**License:** MIT (original: https://github.com/hardikpandya/stop-slop)
