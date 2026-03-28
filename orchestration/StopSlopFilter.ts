import { readFileSync } from 'fs';
import { resolve } from 'path';

interface QualityScore {
  directness: number;
  rhythm: number;
  trust: number;
  authenticity: number;
  density: number;
  total: number;
  passed: boolean;
  issues: string[];
  suggestions: string[];
}

class StopSlopFilter {
  private bannedPhrases: string[] = [];
  private forbiddenPatterns: RegExp[] = [];

  constructor() {
    this.initializeBannedPhrases();
    this.initializeForbiddenPatterns();
  }

  private initializeBannedPhrases(): void {
    this.bannedPhrases = [
      "let's explore",
      "it's important to note",
      "in today's world",
      "at the end of the day",
      "it goes without saying",
      "needless to say",
      "as a matter of fact",
      "in fact",
      "arguably",
      "interestingly enough",
      "for all intents and purposes",
      "take it to the next level",
      "transformative",
      "revolutionary",
      "groundbreaking",
      "tap into",
      "unlock",
      "unleash",
      "harness",
      "leverage",
      "journey",
      "paradigm",
      "synergy",
      "ecosystem",
      "in this digital age",
      "in this day and age",
      "on the other hand",
      "that being said",
      "the very core of",
      "fundamentally transform"
    ];
  }

  private initializeForbiddenPatterns(): void {
    this.forbiddenPatterns = [
      /\b(what if|why would|where have|have you ever|ever wondered)\b/gi,
      /\b(might want to|you might consider|one might)\b/gi,
      /—/g, // Em dash overuse
      /\b(always|never|everyone|nobody)\b/gi, // Lazy extremes
      /^[A-Z\s]+$/gm, // ALL CAPS words
    ];
  }

  /**
   * Check for banned phrases (case-insensitive)
   */
  private checkBannedPhrases(text: string): string[] {
    const issues: string[] = [];
    for (const phrase of this.bannedPhrases) {
      if (new RegExp(`\\b${phrase}\\b`, 'gi').test(text)) {
        issues.push(`Remove cliché: "${phrase}"`);
      }
    }
    return issues;
  }

  /**
   * Check for forbidden patterns
   */
  private checkForbiddenPatterns(text: string): string[] {
    const issues: string[] = [];
    if (/\bwh(at|y|ere|o) /gi.test(text)) {
      issues.push('Avoid Wh- sentence starters');
    }
    if (/——/.test(text)) {
      issues.push('Reduce em dash usage');
    }
    if (/!{2,}/.test(text)) {
      issues.push('Max 1 exclamation mark');
    }
    if (/\b(always|never|everyone|nobody)\b/gi.test(text)) {
      issues.push('Replace lazy absolutes (always/never/everyone)');
    }
    return issues;
  }

  /**
   * Check for passive voice indicators
   */
  private checkPassiveVoice(text: string): string[] {
    const issues: string[] = [];
    if (/\b(is|are|was|were)\s+\w+ed\b/g.test(text)) {
      issues.push('Convert passive voice to active');
    }
    if (/by\s+(the|a)\s+\w+$/.test(text)) {
      issues.push('Remove "by the..." passive constructions');
    }
    return issues;
  }

  /**
   * Check for binary contrasts
   */
  private checkBinaryContrasts(text: string): string[] {
    const issues: string[] = [];
    if (/not\s+\w+,\s+but\s+\w+|vs\.|versus/gi.test(text)) {
      issues.push('Avoid binary contrasts (X vs Y, not X but Y)');
    }
    return issues;
  }

  /**
   * Analyze sentence rhythm (length variation)
   */
  private analyzeRhythm(text: string): { score: number; feedback: string } {
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [];
    
    // For very short text (< 2 sentences), don't penalize rhythm
    if (sentences.length < 2) return { score: 8, feedback: 'Too few sentences for detailed rhythm analysis.' };

    const lengths = sentences.map(s => s.split(' ').length);
    const avg = lengths.reduce((a, b) => a + b, 0) / lengths.length;
    const variance = lengths.reduce((sum, len) => sum + Math.pow(len - avg, 2), 0) / lengths.length;
    const stdDev = Math.sqrt(variance);

    // High variance = good rhythm (varied lengths)
    // For short texts, even small variance is OK
    let score = Math.min(10, Math.max(4, stdDev * 1.5)); // Scale conservatively
    if (stdDev < 0.5) {
      return { score: 6, feedback: 'Rhythm is monotonous. Vary sentence length more.' };
    }
    return { score: Math.round(score), feedback: 'Good rhythm variation.' };
  }

  /**
   * Rate directness: statements vs questions/suggestions
   */
  private rateDirectness(text: string): number {
    const questions = (text.match(/\?/g) || []).length;
    const suggestions = (text.match(/\b(might|could|should|you may|want to|consider)\b/gi) || []).length;
    const weakStarters = (text.match(/\b(let's|have you|what if|why would)\b/gi) || []).length;

    let score = 9; // Start high
    if (questions > 0) score -= questions * 2;
    if (suggestions > 0) score -= suggestions * 1.5;
    if (weakStarters > 0) score -= weakStarters * 2;
    
    return Math.max(1, Math.min(10, score));
  }

  /**
   * Rate trust: respects reader intelligence, no over-explanation
   */
  private rateTrust(text: string): number {
    let score = 9; // Start high
    if (/\b(advanced|sophisticated|complex)\b/gi.test(text)) score -= 1;
    if (/\b(easy|simple|intuitive)\b/gi.test(text)) score -= 1; // Over-reassuring
    if (/AI-powered|machine learning|algorithm/gi.test(text)) score -= 1; // Jargon
    return Math.max(1, score);
  }

  /**
   * Rate authenticity: human tone vs corporate
   */
  private rateAuthenticity(text: string): number {
    let score = 8;
    if (/synergy|ecosystem|paradigm|leverage/gi.test(text)) score -= 2;
    if (/(?:the\s+)?(?:ultimate|cutting-edge|next-generation)/gi.test(text)) score -= 1;
    if (/\bwe\b|\byou\b/gi.test(text)) score += 1; // Personal pronouns = more human
    return Math.max(1, score);
  }

  /**
   * Rate density: how much can be cut
   */
  private rateDensity(text: string): number {
    let score = 8;
    const filler = /\b(very|really|quite|just|actually|literally|basically)\b/gi;
    if (filler.test(text)) score -= (text.match(filler) || []).length;
    if (/\b(and|or)\b/g.test(text)) score -= 0.5; // Conjunctions can bloat
    return Math.max(1, score);
  }

  /**
   * Main quality check
   */
  public evaluate(text: string): QualityScore {
    const issues: string[] = [];
    const suggestions: string[] = [];

    // Run all checks
    issues.push(...this.checkBannedPhrases(text));
    issues.push(...this.checkForbiddenPatterns(text));
    issues.push(...this.checkPassiveVoice(text));
    issues.push(...this.checkBinaryContrasts(text));

    // Rate each dimension
    const directness = this.rateDirectness(text);
    const { score: rhythm, feedback: rhythmFeedback } = this.analyzeRhythm(text);
    const trust = this.rateTrust(text);
    const authenticity = this.rateAuthenticity(text);
    const density = this.rateDensity(text);

    if (rhythm < 5) suggestions.push(rhythmFeedback);
    if (directness < 7) suggestions.push('Make statements instead of posing questions');
    if (trust < 7) suggestions.push('Avoid corporate jargon and over-explanation');
    if (authenticity < 7) suggestions.push('Use conversational, human language');
    if (density < 7) suggestions.push('Remove filler words and tighten phrasing');

    const total = Math.round((directness + rhythm + trust + authenticity + density) / 5);
    const passed = total >= 8; // 8/10 minimum (80% quality)

    return {
      directness,
      rhythm,
      trust,
      authenticity,
      density,
      total,
      passed,
      issues,
      suggestions,
    };
  }

  /**
   * Format evaluation for readable output
   */
  public formatReport(text: string, maxChars?: number): string {
    const displayText = maxChars ? text.substring(0, maxChars) + '...' : text;
    const score = this.evaluate(text);

    let report = `\n📋 STOP-SLOP EVALUATION\n`;
    report += `Text: "${displayText}"\n\n`;
    report += `📊 DIMENSION SCORES (1-10 each):\n`;
    report += `  Directness:    ${score.directness}/10\n`;
    report += `  Rhythm:        ${score.rhythm}/10\n`;
    report += `  Trust:         ${score.trust}/10\n`;
    report += `  Authenticity:  ${score.authenticity}/10\n`;
    report += `  Density:       ${score.density}/10\n`;
    report += `  ───────────────────────\n`;
    report += `  AVERAGE:       ${score.total}/10 (${score.passed ? '✅ PASS (≥8)' : '❌ FAIL (<8)'})\n\n`;

    if (score.issues.length > 0) {
      report += `⚠️  ISSUES:\n`;
      score.issues.forEach(issue => (report += `  • ${issue}\n`));
      report += '\n';
    }

    if (score.suggestions.length > 0) {
      report += `💡 SUGGESTIONS:\n`;
      score.suggestions.forEach(suggestion => (report += `  • ${suggestion}\n`));
    }

    return report;
  }
}

export default StopSlopFilter;
