#!/usr/bin/env npx ts-node
/**
 * Quick test script for StopSlopFilter
 * Usage: npx ts-node test-stop-slop.ts
 */

import StopSlopFilter from './StopSlopFilter';

const filter = new StopSlopFilter();

// Test cases: Real vs improved copy
const testCases = [
  {
    name: "Uncorked Canvas Search Headline",
    bad: "Unlock Your Artistic Potential Today",
    good: "Create Beautiful Art in Minutes",
  },
  {
    name: "PMax Description",
    bad: "At the end of the day, our platform helps you transform your creative journey",
    good: "Turn your ideas into finished artwork, faster and easier",
  },
  {
    name: "Meta Callout",
    bad: "It's Important to Note: Revolutionary Features",
    good: "Ship faster. No setup needed.",
  },
  {
    name: "Blog Post Opener",
    bad: "Let's explore how groundbreaking AI technology is revolutionizing the art world",
    good: "AI is changing how artists work. Here's what you need to know.",
  },
];

console.log("🧪 STOP-SLOP FILTER TEST SUITE\n");
console.log("=" + "=".repeat(70));

testCases.forEach((test, index) => {
  console.log(`\n📝 TEST ${index + 1}: ${test.name}\n`);

  console.log("❌ BAD VERSION:");
  const badScore = filter.evaluate(test.bad);
  console.log(`"${test.bad}"`);
  console.log(filter.formatReport(test.bad, 60));

  console.log("\n✅ GOOD VERSION:");
  const goodScore = filter.evaluate(test.good);
  console.log(`"${test.good}"`);
  console.log(filter.formatReport(test.good, 60));

  console.log("─".repeat(72) + "\n");
});

console.log("📊 SUMMARY");
console.log("=" + "=".repeat(70));
console.log(`
Total tests: ${testCases.length}
Each test shows BAD (AI-like) vs GOOD (human-like) versions.
Quality threshold: 40/50 (pass), below 40 (fail/revise).

Next steps:
1. Try your own copy: filter.evaluate("your text here")
2. Integrate into Creative Agent workflow
3. Run Creative Optimizer every Friday at 6 PM PT
4. Audit existing campaigns for AI-slop patterns
`);
