"""Tiny lexicon polarity — no TextBlob/NLTK/NumPy.

Used when TextBlob import fails on this host (NumPy baseline mismatch).
Good enough for RSS/last30 shadow probes; not a research-grade NLP stack.
"""
from __future__ import annotations

import re
from typing import Iterable

# compact crypto/news-ish lexicon (pos/neg)
_POS = {
    "surge",
    "surges",
    "surging",
    "rally",
    "rallies",
    "bull",
    "bullish",
    "soar",
    "soars",
    "soaring",
    "gain",
    "gains",
    "gaining",
    "jump",
    "jumps",
    "jumping",
    "breakout",
    "breakouts",
    "ath",
    "record",
    "high",
    "higher",
    "upside",
    "optimism",
    "optimistic",
    "adopt",
    "adoption",
    "approve",
    "approved",
    "approval",
    "inflow",
    "inflows",
    "buy",
    "buying",
    "accumulate",
    "accumulation",
    "strong",
    "strength",
    "recovery",
    "recover",
    "green",
    "moon",
    "pump",
    "pumps",
    "win",
    "wins",
    "winner",
    "positive",
    "growth",
    "grow",
    "boost",
    "boosts",
    "upgrade",
    "upgrades",
}
_NEG = {
    "crash",
    "crashes",
    "crashing",
    "dump",
    "dumps",
    "dumping",
    "bear",
    "bearish",
    "plunge",
    "plunges",
    "plunging",
    "drop",
    "drops",
    "dropping",
    "fall",
    "falls",
    "falling",
    "selloff",
    "sell-off",
    "outflow",
    "outflows",
    "hack",
    "hacked",
    "exploit",
    "exploited",
    "ban",
    "banned",
    "lawsuit",
    "sue",
    "sues",
    "fraud",
    "scam",
    "fear",
    "panic",
    "liquidat",  # prefix-ish handled via startswith below
    "weak",
    "weakness",
    "downside",
    "lower",
    "loss",
    "losses",
    "decline",
    "declines",
    "declining",
    "risk",
    "risks",
    "warning",
    "warns",
    "collapse",
    "collapses",
    "negative",
    "red",
    "slash",
    "slashes",
    "cut",
    "cuts",
}


def simple_polarity(text: str) -> float:
    if not text:
        return 0.0
    toks = re.findall(r"[a-z0-9']+", text.lower())
    if not toks:
        return 0.0
    pos = neg = 0
    for t in toks:
        if t in _POS:
            pos += 1
            continue
        if t in _NEG or t.startswith("liquidat"):
            neg += 1
            continue
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / float(total)))


def try_textblob_polarity(text: str) -> float:
    """Prefer TextBlob when importable; else lexicon."""
    try:
        from textblob import TextBlob  # type: ignore

        blob = TextBlob(text or "")
        sent = getattr(blob, "sentiment", None)
        if sent is None:
            return simple_polarity(text or "")
        pol = getattr(sent, "polarity", None)
        if pol is None:
            return simple_polarity(text or "")
        return float(pol)
    except Exception:
        return simple_polarity(text or "")
