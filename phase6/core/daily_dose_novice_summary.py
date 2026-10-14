"""Economical AI editorial — one short paragraph per selected dose card.

Phase 2 after selection is locked (publish top-N or winning A/B arm).

Voice: friendly, approachable, encouraging — plain English for everyday
readers who follow markets. Avoid trade jargon unless needed; if used,
add a short parenthetical definition. Never call the reader a novice/beginner.

One disclaimer for the whole post (footer), not after every card.

Shadow-first. Does NOT overwrite live TG dose until Brad GO + wiring.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.adapters.judgment_jev import resolve_api_key
from phase6.core.paths import PROJECT_ROOT, load_trading_basket

METHOD = "daily_dose_plain_summary_v4_shadow"
SCHEMA_VERSION = 4

# Post-level only (never append per card).
POST_DISCLAIMER = (
    "For context only — not investment advice and not a trade signal. "
    "Does not change the live Daily Dose delivery."
)

# Keep prompt small — title + short summary + tickers only (economical).
MAX_SUMMARY_CHARS = 320
MAX_TITLE_CHARS = 140
MAX_OUT_CHARS = 520  # tight: 2–3 fact sentences, no tutorial coda

DEFAULT_LATEST = PROJECT_ROOT / "data" / "state" / "daily_dose_novice_summary_latest.json"
DEFAULT_HISTORY = PROJECT_ROOT / "data" / "state" / "daily_dose_novice_summary_history.jsonl"
DEFAULT_POST = PROJECT_ROOT / "data" / "state" / "daily_dose_novice_summary_post.txt"

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a wire-service rewrite desk. Output ONLY factual news copy. "
    "Tone: plain, friendly, calm — never hype, never alarmist, never tutorial. "
    "Never call the reader a novice, beginner, or amateur. "
    "Plain English. If you must use ETF, listing, exploit, outflow, SPAC, or "
    "liquidation, add a brief parenthetical definition once. "
    "The headline is already shown above the body — NEVER restate or paraphrase it. "
    "Do not repeat the headline's actor+action or its primary dollar figure. "
    "1–2 complete sentences of NEW facts only (details not already in the headline). "
    "Prefer: venue, product type, timing, mechanism, secondary amounts, related coins, "
    "or what happens next if stated in the source. "
    "If the blurb adds almost nothing beyond the headline, write ONE short new-detail "
    "sentence — do not pad by rephrasing the title. "
    "HARD STOP after the last fact sentence. Forbidden phrases and patterns: "
    "keep an eye, stay informed, valuable insights, consider positions, "
    "reminder, navigating, broader trends, investor confidence, market dynamics, "
    "highlighting … commitment/interest/vulnerabilities, noteworthy as it reflects, "
    "raising concerns, drawn attention, growing acceptance, opens up new opportunities, "
    "signals shifts, for users and investors. "
    "No buy/sell/hold, no price targets, no forecasts, no emojis, no bullets, "
    "no title rewrite, no disclaimer, no moral, no lesson."
)

_USER_TMPL = """Headline (already shown to reader — do NOT restate): {title}
Source blurb: {summary}
Related coins: {tickers}
Watchlist context: {basket}
Currently held (if any): {held}

Write 1–2 fact sentences of NEW details only. No third sentence.
Body must NOT open with or paraphrase the headline (who/what/how much already there).
Pull extras from the blurb: venue, product (e.g. ETF), timing, mechanism, secondary
numbers, related coins, testing/rollout, custody path, conditions.
If blurb ≈ headline, one short new-detail sentence is enough — never rephrase the title.
Rules:
- Friendly plain English; no hype; not a tutorial
- Do not label the reader novice/beginner
- Jargon only if needed, with a short parenthetical once
- Facts only from blurb/headline extras — invent nothing
- No buy/sell/hold, targets, forecasts
- Never end with commentary (ban: noteworthy / highlights / reflects / concerns /
  attention / opportunities / acceptance / confidence / dynamics / keep an eye)
- No emojis, bullets, or disclaimer
- End the last sentence with a period and STOP
"""

# Tutorial / soft-advice codas the model loves — strip if they sneak in.
_WRAPUP_RE = re.compile(
    r"(?i)^(?:"
    r"keeping an eye\b.*|"
    r"keep an eye\b.*|"
    r"staying (?:aware|informed|vigilant)\b.*|"
    r"stay (?:aware|informed|vigilant)\b.*|"
    r"it(?:'s| is) a reminder\b.*|"
    r"this (?:is a )?reminder\b.*|"
    r".*\bvaluable insights?\b.*|"
    r".*\bconsider (?:their |your )?(?:own )?positions?\b.*|"
    r".*\bnavigat(?:e|ing) the (?:ever-)?changing\b.*|"
    r".*\bbroader (?:crypto )?(?:landscape|market|trends)\b.*|"
    r".*\bfor anyone (?:keeping an eye|following|tracking)\b.*|"
    r".*\bworth (?:keeping an eye|paying attention)\b.*|"
    r".*\bcan help you (?:stay|make)\b.*|"
    r".*\bsignal(?:s|ing)? (?:shifts in )?investor confidence\b.*|"
    r".*\bencourage others to consider\b.*|"
    r".*\bhighlights? (?:the )?(?:complexities|ongoing (?:volatility|vulnerabilities|interest)|growing interest)\b.*|"
    r".*\braising (?:questions|concerns)\b.*|"
    r".*\bimplications it may have\b.*|"
    r".*\binvestor sentiment\b.*|"
    r".*\bcould enhance (?:accessibility|visibility|adoption)\b.*|"
    r".*\bmarking a significant step\b.*|"
    r".*\breflects (?:a larger trend|ongoing interest|institutional)\b.*|"
    r".*\bnoteworthy as it\b.*|"
    r".*\bcould influence market dynamics\b.*|"
    r".*\bhighlighting (?:the )?(?:growing interest|fidelity|vulnerabilities)\b.*|"
    r".*\bdrawn attention\b.*|"
    r".*\braising concerns among users\b.*|"
    r".*\bneed for enhanced security\b.*|"
    r".*\bgrowing acceptance and integration\b.*|"
    r".*\bopens up new opportunities\b.*|"
    r".*\bmarks an important step\b.*|"
    r".*\bmarking an important step\b.*|"
    r".*\bis an important step\b.*"
    r")$"
)

@dataclass
class NoviceSummaryConfig:
    model: str = DEFAULT_MODEL
    dry_run: bool = True  # default safe: mock / template only
    max_cards: int = 5
    latest_path: Path = field(default_factory=lambda: DEFAULT_LATEST)
    history_path: Path = field(default_factory=lambda: DEFAULT_HISTORY)
    post_path: Path = field(default_factory=lambda: DEFAULT_POST)
    write_history: bool = True
    write_post: bool = True


def _clip(s: str, n: int) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


def _split_sentences(t: str) -> List[str]:
    """Split on sentence end punctuation, not decimal points in amounts ($92.9)."""
    t = re.sub(r"\s+", " ", (t or "").strip())
    if not t:
        return []
    # Protect common decimals / tickers briefly
    protected: List[str] = []

    def _park(m: re.Match[str]) -> str:
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    # $1.2 / 92.9 / 0.5% style
    tmp = re.sub(r"\$?\d+\.\d+%?", _park, t)
    parts = re.findall(r"[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$", tmp)
    out: List[str] = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        s = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], s)
        out.append(s)
    return out


def _clip_paragraph(s: str, n: int) -> str:
    """Prefer full sentences under the budget; never leave a mid-sentence ellipsis."""
    t = re.sub(r"\s+", " ", (s or "").strip())
    if len(t) <= n:
        if t and t[-1] not in ".!?":
            t += "."
        return t
    parts = _split_sentences(t)
    keep: List[str] = []
    size = 0
    for p in parts:
        add = (1 if keep else 0) + len(p)
        if size + add > n:
            break
        keep.append(p)
        size += add
    if keep:
        out = " ".join(keep).strip()
        if out[-1] not in ".!?":
            out += "."
        return out
    cut = t[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return cut


def _pretty_ticks(ticks: Sequence[Any]) -> str:
    out: List[str] = []
    for t in ticks:
        s = str(t).replace("-USD", "").strip()
        if s and s not in out:
            out.append(s)
    return ", ".join(out[:8]) if out else "—"


def build_prompt(card: Dict[str, Any], *, basket: Sequence[str], held: Sequence[str]) -> Dict[str, str]:
    title = _clip(str(card.get("title") or card.get("title_display") or ""), MAX_TITLE_CHARS)
    summary = _clip(str(card.get("summary") or ""), MAX_SUMMARY_CHARS)
    ticks = card.get("tickers") or []
    if isinstance(ticks, str):
        ticks = [ticks]
    tick_s = _pretty_ticks(ticks)
    basket_s = _pretty_ticks(list(basket)[:16]) or "—"
    held_s = _pretty_ticks(list(held)[:16]) if held else "none listed"
    user = _USER_TMPL.format(
        title=title,
        summary=summary or "(no blurb)",
        tickers=tick_s,
        basket=basket_s,
        held=held_s,
    )
    return {"system": _SYSTEM, "user": user}


def mock_summary(card: Dict[str, Any], *, basket: Sequence[str], held: Sequence[str]) -> str:
    """Deterministic stand-in when dry_run / no LLM — new details only, no title echo."""
    blurb = _clip(str(card.get("summary") or ""), 200)
    ticks = card.get("tickers") or []
    if isinstance(ticks, str):
        ticks = [ticks]
    tick_s = _pretty_ticks(ticks) or "major coins"
    if blurb:
        # Prefer blurb as body; never paste the headline again.
        return _clean_summary_text(
            f"{blurb} Related coins named include {tick_s}.",
            card=card,
        )
    return _clean_summary_text(
        f"Related coins named in the report include {tick_s}.",
        card=card,
    )


def _strip_inline_disclaimer(text: str) -> str:
    """Guardrail: models sometimes append advice disclaimers per card."""
    t = (text or "").strip()
    parts = _split_sentences(t)
    keep: List[str] = []
    drop_re = re.compile(
        r"(not (investment|financial|trading) advice|not a trade signal|"
        r"not a (buy|sell)|do your own research|nfa\b|this is not advice|"
        r"for educational purposes only)",
        re.I,
    )
    for p in parts:
        if not p:
            continue
        if drop_re.search(p) and len(p) < 180:
            continue
        keep.append(p)
    out = " ".join(keep).strip()
    return out or t


def _strip_wrapup_sentences(text: str) -> str:
    """Drop tutorial / soft-advice coda sentences; keep fact body."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return t
    parts = _split_sentences(t)
    if not parts:
        return t
    kept: List[str] = []
    for i, p in enumerate(parts):
        if _WRAPUP_RE.match(p):
            continue
        low = p.lower()
        if i == len(parts) - 1 and any(
            low.startswith(s)
            for s in (
                "keeping an eye",
                "keep an eye",
                "staying ",
                "stay ",
                "it's a reminder",
                "it is a reminder",
                "this is a reminder",
                "this reminder",
                "the situation highlights",
                "the increase in holdings reflects",
                "this movement in the market highlights",
                "this incident has drawn attention",
                "the exploit highlights",
                "the move could enhance",
                "the move is noteworthy",
                "the move highlights",
                "this listing is significant",
                "this increase comes amid",
                "fidelity's move is noteworthy",
                "this incident is noteworthy",
                "the exploit has drawn attention",
            )
        ):
            continue
        # Soft pad anywhere (not only last)
        if any(
            x in low
            for x in (
                "valuable insight",
                "keep an eye",
                "keeping an eye",
                "investor sentiment surrounding",
                "raising questions about market sentiment",
                "raising concerns among users",
                "could influence market dynamics",
                "highlighting fidelity's commitment",
                "highlighting the growing interest",
                "highlights vulnerabilities",
                "opens up new opportunities for users and investors",
                "growing acceptance and integration of digital assets",
                "reflects a larger trend of institutional",
                "need for enhanced security measures",
                "drawn attention to the need",
                "continues to expand its portfolio",
                "which also includes other",
                "among other cryptocurrencies",
                "marks an important step",
                "marking an important step",
                "is an important step",
            )
        ):
            continue
        kept.append(p)
    if not kept:
        kept = parts[:1]
    # Cap at 2 fact sentences after stripping soft pads
    kept = kept[:2]
    out = " ".join(kept).strip()
    if out and out[-1] not in ".!?":
        out += "."
    return out


def _repair_truncated_lead(text: str, card: Dict[str, Any]) -> str:
    """Fix rare model glitches that start mid-amount (e.g. '9 million from wallets…')."""
    t = (text or "").strip()
    if not t:
        return t
    broken = bool(
        re.match(r"^(?:\$?\d[\d,]*(?:\.\d+)?\s+)?(?:million|billion|thousand)\b", t, re.I)
        or re.match(r"^\d[\d,]*\s+million\b", t, re.I)
        or re.match(r"^\$?\d[\d,]*(?:\.\d+)?\s+million\b", t, re.I)
    )
    if broken:
        blurb = _clip(str(card.get("summary") or ""), 220)
        ticks = card.get("tickers") or []
        if isinstance(ticks, str):
            ticks = [ticks]
        tick_s = _pretty_ticks(ticks) or "major coins"
        # Prefer blurb extras — never fall back to pasting the headline into the body.
        if blurb:
            blurb2 = re.sub(
                r"(?i)^here'?s everything you need to know about\s+",
                "",
                blurb,
            ).strip()
            blurb2 = blurb2[:1].upper() + blurb2[1:] if blurb2 else blurb2
            return f"{blurb2} Related coins named in the report include {tick_s}."
        return f"Related coins named in the report include {tick_s}."
    return t


def _norm_words(s: str) -> List[str]:
    return re.findall(r"[a-z0-9$%]+", (s or "").lower())


def _token_jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def _strip_title_amount_clauses(sentence: str, title: str) -> str:
    """Remove inline clauses that only restate the headline's primary $ figure."""
    s = (sentence or "").strip()
    if not s or not title:
        return s
    amounts = set(re.findall(r"\d+(?:\.\d+)?", title))
    if not amounts:
        return s
    # Coin-ish tokens from title (skip pure numbers / million)
    stop = {
        "a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "as", "is",
        "buys", "buy", "bought", "purchase", "purchases", "million", "billion",
        "thousand", "after", "over", "into", "with", "from", "by", "set", "launch",
        "launches", "another", "spot", "etf", "seeks", "seeks", "brings",
    }
    coins = [
        w for w in _norm_words(title)
        if w not in stop and not re.fullmatch(r"\d+(?:\.\d+)?", w) and len(w) > 2
    ]
    coin_alt = "|".join(re.escape(c) for c in coins[:6]) if coins else r"[a-z]{3,12}"
    amt_alt = "|".join(re.escape(a) for a in sorted(amounts, key=len, reverse=True))
    # ", with the firm adding approximately $20 million worth of Solana…"
    # "…adding approximately $20 million worth of Solana to its holdings"
    patterns = [
        rf"(?i)(?:,|\s+with\s+(?:the\s+)?(?:firm|fund|company|manager)\s+)?\s*"
        rf"(?:adding|added|add|purchased|purchase|bought|buying|includes?|including)\s+"
        rf"(?:a\s+total\s+of\s+|approximately\s+|about\s+|roughly\s+|nearly\s+)?"
        rf"\$?(?:{amt_alt})(?:\s*million|\s*billion)?\s*"
        rf"(?:worth\s+of\s+)?(?:{coin_alt})(?:\s*\([a-z]{{2,6}}\))?"
        rf"(?:\s+to\s+its\s+holdings)?",
        rf"(?i),\s*with\s+(?:the\s+)?(?:firm|fund|company)\s+"
        rf"(?:adding|already\s+adding)[^.]{{0,80}}"
        rf"\$?(?:{amt_alt})[^.]{{0,40}}(?:{coin_alt})",
        rf"(?i)\s+with\s+(?:the\s+)?firm\s+adding\s+approximately\s+"
        rf"\$?(?:{amt_alt})\s*million\s+worth\s+of\s+(?:{coin_alt})"
        rf"(?:\s+to\s+its\s+holdings)?",
    ]
    out = s
    for pat in patterns:
        out2 = re.sub(pat, "", out).strip(" ,;")
        out2 = re.sub(r"\s{2,}", " ", out2)
        out2 = re.sub(r"\s+,", ",", out2)
        out2 = re.sub(r",\s*\.", ".", out2)
        out2 = re.sub(r"\.\s*\.", ".", out2)
        out = out2
    # Soft strategy pad tacked on
    out = re.sub(
        r"(?i)\s*The ETF is part of .{0,80}expand its cryptocurrency offerings\.?\s*$",
        "",
        out,
    ).strip()
    out = re.sub(
        r"(?i)\s*This launch adds to the growing interest in .{0,60}\.?\s*$",
        "",
        out,
    ).strip()
    if out and out[-1] not in ".!?":
        # If we stripped mid-sentence trailing junk, close cleanly
        if len(out) > 12:
            out = out.rstrip(",;:") + "."
    return out


def _strip_headline_restatement(text: str, card: Dict[str, Any]) -> str:
    """Drop body sentences that mostly rephrase the already-shown headline.

    Title is rendered above the body in format_post — repeating who/what/how much
    is pure redundancy. Keep sentences that add venue, timing, mechanism, etc.
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return t
    title = str(card.get("title") or card.get("title_display") or "").strip()
    if not title:
        return t
    title_words = _norm_words(title)
    # Drop ultra-common glue so "buys / of / the" don't inflate overlap alone.
    stop = {
        "a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "as", "is",
        "has", "have", "had", "its", "it", "this", "that", "with", "from", "by",
        "at", "be", "been", "are", "was", "were", "will", "would", "can", "could",
        "after", "over", "into", "than", "then", "also", "just", "about", "into",
        "which", "also", "other", "like", "within", "already", "recently",
    }
    title_core = [w for w in title_words if w not in stop and len(w) > 1]
    if not title_core:
        title_core = title_words
    # Money figures in the title (e.g. $20 / 20 / 765) — repeating them is title echo.
    title_amounts = set(re.findall(r"\d+(?:\.\d+)?", title))
    title_amounts |= {a.replace(",", "") for a in re.findall(r"\d[\d,]*(?:\.\d+)?", title)}
    # Soft pad that adds no fact
    soft_pad = re.compile(
        r"(?i)\b("
        r"continues to expand(?: its)?(?: portfolio)?"
        r"|expand(?:s|ing)? its portfolio"
        r"|which also includes other"
        r"|among other (?:cryptocurrencies|assets|coins)"
        r"|broader strategy to expand"
        r"|growing interest in"
        r"|significant investment"
        r")\b"
    )
    parts = _split_sentences(t)
    if not parts:
        return t
    kept: List[str] = []
    for i, p in enumerate(parts):
        p = _strip_title_amount_clauses(p, title)
        if not p or len(_norm_words(p)) < 4:
            continue
        if soft_pad.search(p) and len(_norm_words(p)) <= 18:
            if re.match(
                r"(?i)^(the fund |it |the product |the etf )?(continues to expand|expand|is part of)",
                p.strip(),
            ) or "which also includes other" in p.lower() or "broader strategy" in p.lower():
                continue
        pw = _norm_words(p)
        p_core = [w for w in pw if w not in stop and len(w) > 1] or pw
        jac = _token_jaccard(title_core, p_core)
        p_amounts = set(re.findall(r"\d+(?:\.\d+)?", p))
        shared_amt = bool(title_amounts and (title_amounts & p_amounts))
        # Leading sentence that is mostly the title → drop.
        if shared_amt and jac >= 0.35 and i == 0:
            continue
        if i == 0 and jac >= 0.50:
            continue
        if jac >= 0.78:
            continue
        # Later sentence whose only hard fact is the title's $ figure → drop.
        if shared_amt:
            non_title = [w for w in p_core if w not in set(title_core)]
            extra_signal = any(
                w in non_title
                for w in (
                    "etf", "trust", "filing", "filings", "weekly", "custody", "difc",
                    "lmax", "december", "testing", "app", "dao", "pause", "paused",
                    "renew", "migrate", "hong", "kong", "pando", "branch", "collateral",
                    "launch", "launched", "second", "first",
                )
            )
            # Pure amount restatement (even mid-body)
            if re.search(
                r"(?i)(?:total of |approximately |about |roughly )?\$?\d[\d,]*(?:\.\d+)?\s*"
                r"(?:million|billion)?\s*(?:worth of )?(?:solana|bitcoin|ethereum|xrp|ada|link)",
                p,
            ) and not extra_signal:
                continue
            if not extra_signal and len(non_title) <= 6 and i > 0:
                continue
        # Short near-paraphrases with heavy title-core overlap
        if i == 0 and len(p_core) <= max(10, len(title_core) + 4):
            overlap = set(title_core) & set(p_core)
            if len(overlap) >= max(3, int(0.65 * len(title_core))):
                continue
        # Soft trend/region coda with no hard fact
        if re.search(
            r"(?i)following the recent trend|in the region\b|broader (?:market|crypto) (?:trend|move)|"
            r"growing interest in|broader strategy to expand",
            p,
        ):
            continue
        kept.append(p)
    if not kept:
        # Fall back to blurb-only extras when the model only restated the title.
        blurb = _clip(str(card.get("summary") or ""), 220)
        ticks = card.get("tickers") or []
        if isinstance(ticks, str):
            ticks = [ticks]
        tick_s = _pretty_ticks(ticks)
        if blurb:
            blurb2 = re.sub(
                r"(?i)^here'?s everything you need to know about\s+",
                "",
                blurb,
            ).strip()
            blurb2 = _strip_title_amount_clauses(blurb2, title)
            b_core = [w for w in _norm_words(blurb2) if w not in stop and len(w) > 1]
            b_amounts = set(re.findall(r"\d+(?:\.\d+)?", blurb2))
            if (not blurb2) or _token_jaccard(title_core, b_core) >= 0.50 or (
                title_amounts and title_amounts <= b_amounts and len(b_core) <= len(title_core) + 6
            ):
                if tick_s:
                    return f"Related coins named in the report include {tick_s}."
                return blurb2 or (parts[-1] if parts else "")
            return blurb2 if blurb2.endswith((".", "!", "?")) else (blurb2 + ".")
        if tick_s:
            return f"Related coins named in the report include {tick_s}."
        return parts[-1]
    out = " ".join(kept[:2]).strip()
    if out and out[-1] not in ".!?":
        out += "."
    return out


def _clean_summary_text(text: str, card: Optional[Dict[str, Any]] = None) -> str:
    t = _strip_inline_disclaimer(text)
    t = _strip_wrapup_sentences(t)
    if card is not None:
        t = _repair_truncated_lead(t, card)
        t = _strip_wrapup_sentences(t)
        t = _strip_headline_restatement(t, card)
        t = _strip_wrapup_sentences(t)
    return _clip_paragraph(t, MAX_OUT_CHARS)

def _call_openrouter_chat(
    prompt: Dict[str, str],
    *,
    model: str,
    api_key: str,
    card: Optional[Dict[str, Any]] = None,
    timeout_s: float = 45.0,
) -> Dict[str, Any]:
    body = {
        "model": model,
        "temperature": 0.25,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/brad/crypto-trading-bot",
            "X-OpenRouter-Title": "phase6-daily-dose-plain-summary",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw_text = resp.read().decode("utf-8", errors="replace")
        status = getattr(resp, "status", 200)
    payload = json.loads(raw_text)
    choices = payload.get("choices") or []
    text = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        text = str(msg.get("content") or "").strip()
    text = _clean_summary_text(re.sub(r"\s+", " ", text), card=card)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    return {
        "ok": bool(text) and int(status) < 400,
        "text": text,
        "model": str(payload.get("model") or model),
        "status": status,
        "usage": {
            "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "completion_tokens": (usage or {}).get("completion_tokens"),
            "total_tokens": (usage or {}).get("total_tokens"),
        }
        if usage
        else None,
        "raw_error": None,
    }


def _call_llm(
    prompt: Dict[str, str],
    *,
    model: str,
    dry_run: bool,
    card: Dict[str, Any],
    basket: Sequence[str],
    held: Sequence[str],
) -> Dict[str, Any]:
    """Best-effort economical completion. dry_run → mock. Live → OpenRouter chat."""
    if dry_run:
        text = mock_summary(card, basket=basket, held=held)
        return {
            "ok": True,
            "text": _clean_summary_text(text, card=card),
            "model": "mock",
            "dry_run": True,
            "prompt_chars": len(prompt["system"]) + len(prompt["user"]),
        }

    api_key = resolve_api_key()
    if not api_key:
        text = mock_summary(card, basket=basket, held=held)
        return {
            "ok": False,
            "text": _clean_summary_text(text, card=card),
            "model": "mock_fallback",
            "dry_run": False,
            "error": "missing_OPENROUTER_API_KEY",
            "prompt_chars": len(prompt["system"]) + len(prompt["user"]),
        }

    try:
        result = _call_openrouter_chat(prompt, model=model, api_key=api_key, card=card)
        fallback = _clean_summary_text(mock_summary(card, basket=basket, held=held), card=card)
        return {
            "ok": result.get("ok"),
            "text": result.get("text") or fallback,
            "model": result.get("model") or model,
            "dry_run": False,
            "prompt_chars": len(prompt["system"]) + len(prompt["user"]),
            "usage": result.get("usage"),
            "error": None if result.get("ok") else "empty_or_bad_response",
        }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        text = mock_summary(card, basket=basket, held=held)
        return {
            "ok": False,
            "text": _clean_summary_text(text, card=card),
            "model": "mock_fallback",
            "dry_run": False,
            "error": f"HTTPError {e.code}: {err_body}"[:240],
            "prompt_chars": len(prompt["system"]) + len(prompt["user"]),
        }
    except Exception as e:  # noqa: BLE001 — shadow path must never break dose
        text = mock_summary(card, basket=basket, held=held)
        return {
            "ok": False,
            "text": _clean_summary_text(text, card=card),
            "model": "mock_fallback",
            "dry_run": False,
            "error": f"{type(e).__name__}: {e}"[:200],
            "prompt_chars": len(prompt["system"]) + len(prompt["user"]),
        }


def format_post(
    items: Sequence[Dict[str, Any]],
    *,
    dose_day: str = "",
    include_disclaimer: bool = True,
) -> str:
    """Human post: numbered linked titles + plain paragraphs; one footer disclaimer.

    Title line uses Telegram-friendly markdown: [title](url) when url is present.
    """
    day = dose_day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"Daily Dose · plain-language notes · {day}",
        "",
    ]
    for i, it in enumerate(items, 1):
        title = str(it.get("title") or "").strip()
        body = str(it.get("plain_summary") or it.get("novice_summary") or "").strip()
        ticks = _pretty_ticks(it.get("tickers") or [])
        url = str(it.get("url") or it.get("source_url") or "").strip()
        title_line = f"{i}. {_md_title_link(title, url)}"
        lines.append(title_line)
        if ticks and ticks != "—":
            lines.append(f"   ({ticks})")
        lines.append(body)
        lines.append("")
    if include_disclaimer:
        lines.append(POST_DISCLAIMER)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _md_title_link(title: str, url: str) -> str:
    """Telegram markdown link for the headline; bare title if no usable URL."""
    t = (title or "").strip() or "(untitled)"
    u = (url or "").strip()
    if not u or not (u.startswith("http://") or u.startswith("https://")):
        return t
    # Escape bare [ ] in title so the link markup stays valid
    safe = t.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}]({u})"


def summarize_cards(
    cards: Sequence[Dict[str, Any]],
    *,
    cfg: Optional[NoviceSummaryConfig] = None,
    basket: Optional[Sequence[str]] = None,
    held: Optional[Sequence[str]] = None,
    dose_day: str = "",
) -> Dict[str, Any]:
    """Run economical one-paragraph summaries for up to max_cards selected items."""
    cfg = cfg or NoviceSummaryConfig()
    basket = list(basket if basket is not None else load_trading_basket())
    held = list(held or [])
    now = datetime.now(timezone.utc)
    out_items: List[Dict[str, Any]] = []
    for card in list(cards)[: max(0, int(cfg.max_cards))]:
        if not isinstance(card, dict) or not card.get("id"):
            continue
        prompt = build_prompt(card, basket=basket, held=held)
        result = _call_llm(
            prompt,
            model=cfg.model,
            dry_run=cfg.dry_run,
            card=card,
            basket=basket,
            held=held,
        )
        summary_text = str(result.get("text") or "")
        out_items.append(
            {
                "id": card.get("id"),
                "title": card.get("title") or card.get("title_display"),
                "tickers": card.get("tickers") or [],
                "url": card.get("url") or card.get("source_url"),
                "novice_summary": summary_text,  # field name kept for compatibility
                "plain_summary": summary_text,
                "summary_meta": {
                    "ok": result.get("ok"),
                    "model": result.get("model"),
                    "dry_run": result.get("dry_run"),
                    "prompt_chars": result.get("prompt_chars"),
                    "error": result.get("error"),
                    "usage": result.get("usage"),
                },
            }
        )

    day = dose_day or now.astimezone().strftime("%Y-%m-%d")
    post_text = format_post(out_items, dose_day=day, include_disclaimer=True)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": METHOD,
        "generated_at": now.isoformat(),
        "dose_day": day,
        "ok": True,
        "not_a_trade_signal": True,
        "shadow_only": True,
        "publishes_replacement_dose": False,
        "disclaimer": POST_DISCLAIMER,
        "disclaimer_placement": "post_footer_only",
        "n_items": len(out_items),
        "dry_run": cfg.dry_run,
        "model": cfg.model if not cfg.dry_run else "mock",
        "items": out_items,
        "post_text": post_text,
        "phase": "post_selection_editorial",
        "depends_on": "optimal_selection_first_then_summarize",
        "voice": {
            "tone": "friendly_clear_no_hype_no_tutorial",
            "audience_label": "everyday_reader",  # never call out 'novice' in copy
            "jargon": "plain_first_parenthetical_when_needed",
            "wrapup": "stripped_facts_only",
        },
    }

    try:
        cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if cfg.write_post:
            cfg.post_path.write_text(post_text, encoding="utf-8")
        if cfg.write_history:
            hist = {
                "generated_at": payload["generated_at"],
                "dose_day": day,
                "n_items": payload["n_items"],
                "dry_run": payload["dry_run"],
                "model": payload["model"],
                "ids": [x.get("id") for x in out_items],
                "ok_n": sum(1 for x in out_items if (x.get("summary_meta") or {}).get("ok")),
            }
            with cfg.history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(hist, ensure_ascii=False) + "\n")
    except OSError:
        payload["write_error"] = "disk_write_failed"

    return payload


def summarize_from_edited(
    edited_path: Path,
    *,
    cfg: Optional[NoviceSummaryConfig] = None,
    held: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Convenience: load published/edited package items and summarize."""
    if not edited_path.is_file():
        return {
            "ok": False,
            "error": f"missing_edited:{edited_path}",
            "not_a_trade_signal": True,
            "shadow_only": True,
        }
    try:
        d = json.loads(edited_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e), "not_a_trade_signal": True, "shadow_only": True}
    items = d.get("items") or []
    basket = (d.get("meta") or {}).get("basket") or load_trading_basket()
    # Prefer dose day from package if present
    day = ""
    gen = str(d.get("generated_at") or d.get("editorial_review", {}).get("reviewed_at") or "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", gen)
    if m:
        day = m.group(1)
    return summarize_cards(items, cfg=cfg, basket=basket, held=held or [], dose_day=day)
