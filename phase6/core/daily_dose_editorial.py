"""
Editorial review for Daily Dose cards (pre-publication).

Brad sample review 2026-08-03:
  - Drop vague / redundant explainers when the event is already covered
  - Drop roundups / "what happened today" filler
  - Prefer active-voice headlines
  - One card per event cluster in the published top-N

Brad dial-in 2026-08-04:
  - Diversity: max 2 pure BTC-tape items in the published shortlist
  - Tone: positive but honest when things go sideways (no gloom-porn)

Brad 2026-08-13:
  - Removed per-bullet "why it matters on this platform" lines from dose output
  - Basket-pair diversity: cap BTC-only cards; spread primary pairs across core basket
  - TG links: domain label markdown-linked to article URL (no raw long URLs)

Not a trading filter — human readability only. Never a trade signal.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

# Default diversity caps by story lane (published shortlist)
DEFAULT_LANE_CAPS: Dict[str, int] = {
    "btc_tape": 2,  # pure price/tape noise around BTC
}

# Basket-pair diversity (shortlist / rank pool)
DEFAULT_MAX_BTC_ONLY = 2  # cards whose tickers are empty or only BTC-USD
DEFAULT_MAX_PER_PRIMARY = 2  # max cards sharing same primary pair label

# Hard drops (irrelevant / filler)
REJECT_TITLE = [
    r"^here'?s what happened\b",
    r"\bwhat happened in crypto today\b",
    r"\btop \d+\b.*\b(today|this week)\b",
    r"\b\d+ things to know\b",
    r"\bfive things to know\b",
    r"\bweekly roundup\b",
    r"\bdaily recap\b",
    r"\bin case you missed\b",
    r"\bnewsletter\b",
    r"\bprice prediction\b",
    r"\bwill bitcoin (hit|reach|go)\b",
]

# Soft drops unless nothing else fills top-N
SOFT_REJECT_TITLE = [
    r"^what is an?\b",
    r"^what are\b",
    r"^how to\b",
    r"^why .+ matters\b",
    r"^explained:?\b",
    r"\bbeginner'?s guide\b",
    r"\beverything you need to know\b",
]

# Shared event keys → tighter than Jaccard title overlap
EVENT_KEY_PATTERNS = [
    (r"coldcard", "evt:coldcard"),
    (r"blackrock.+(liquidat|sell|sold|etf)|liquidat.+blackrock", "evt:blackrock_flow"),
    (r"\bstrategy\b.+(sell|sold|sale|bitcoin)|microstrategy.+(sell|sold)", "evt:strategy_btc"),
    (r"clarity act", "evt:clarity_act"),
    (r"yen (intervention|carry)", "evt:yen"),
    (r"sec\b.+(etf|approv|lawsuit)|etf.+\bsec\b", "evt:sec_etf"),
    (r"goldman.+(neos|yield|income etf)|neos.+(goldman|buyout|buy-?out)", "evt:goldman_neos"),
    (r"occ\b.+(charter|bank)|bank charter", "evt:occ_charter"),
]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s$%]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def reject_reason(title: str) -> Optional[str]:
    t = _norm(title)
    for pat in REJECT_TITLE:
        if re.search(pat, t, re.I):
            return f"reject_roundup:{pat[:24]}"
    return None


def soft_reject_reason(title: str) -> Optional[str]:
    t = _norm(title)
    for pat in SOFT_REJECT_TITLE:
        if re.search(pat, t, re.I):
            return f"soft_explainer:{pat[:24]}"
    return None


def event_keys(title: str, summary: str = "", tags: Optional[List[str]] = None) -> List[str]:
    blob = f"{title} {summary}"
    keys = []
    for pat, key in EVENT_KEY_PATTERNS:
        if re.search(pat, blob, re.I):
            keys.append(key)
    # tag-based fallbacks
    tags = tags or []
    if "hack" in tags or "exploit" in tags:
        if re.search(r"coldcard|wallet|cold storage", blob, re.I):
            if "evt:coldcard" not in keys:
                keys.append("evt:coldcard")
    if re.search(r"\bhashdex\b", blob, re.I) and re.search(r"\b(etf|shut|close|closing)\b", blob, re.I):
        if "evt:hashdex_etf" not in keys:
            keys.append("evt:hashdex_etf")
    if re.search(r"first u\.?s\.? spot bitcoin etf", blob, re.I) and re.search(
        r"\b(close|closing|shut)\b", blob, re.I
    ):
        # same story family as Hashdex wind-down coverage
        if "evt:hashdex_etf" not in keys:
            keys.append("evt:hashdex_etf")
    return keys


def to_active_voice(title: str) -> Tuple[str, List[str]]:
    """Heuristic active-voice cleanup. Returns (title, edit_notes)."""
    notes: List[str] = []
    t = (title or "").strip()
    original = t

    # Strip live-updates chrome but keep substance (Brad kept #3)
    m = re.match(r"^live updates:\s*(.+)$", t, re.I)
    if m:
        t = m.group(1).strip()
        t = t[0].upper() + t[1:] if t else t
        notes.append("strip_live_updates_prefix")

    # "Says CEO of X: quote" / "‘quote,’ Says CEO of X"
    m = re.match(r"^[‘'\"“](.+?)[’'\"”],?\s*[Ss]ays\s+(.+)$", t)
    if m:
        quote, who = m.group(1).strip(), m.group(2).strip()
        # who often "CEO of Bitcoin Treasury Company Strategy"
        who = re.sub(r"^CEO of (?:Bitcoin Treasury Company\s+)?", "Strategy CEO: ", who, flags=re.I)
        if not who.lower().startswith("strategy"):
            who = re.sub(r"^(.*)$", r"\1:", who)
        t = f"{who} {quote}"
        if not t.endswith((".", "!", "?")):
            pass
        notes.append("quote_to_active")

    # "X Forced to Y" -> "X Ys"
    m = re.match(r"^(.+?)\s+[Ff]orced to\s+(\w+)(.+)$", t)
    if m:
        subj, verb, rest = m.group(1).strip(), m.group(2).strip().lower(), m.group(3)
        # crude 3sg
        if verb.endswith("e"):
            verb_act = verb + "s"
        elif verb.endswith("y"):
            verb_act = verb[:-1] + "ies"
        else:
            verb_act = verb + "s"
        t = f"{subj} {verb_act}{rest}"
        notes.append("forced_to_active")

    # "X is/are/was/were VERBed by Y" -> "Y VERBs X" (simple)
    m = re.match(
        r"^(.+?)\s+(?:is|are|was|were)\s+(\w+ed|sold|bought|cut|hit)\s+by\s+(.+)$",
        t,
        re.I,
    )
    if m:
        obj, verb, subj = m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()
        t = f"{subj} {verb} {obj}"
        t = t[0].upper() + t[1:]
        notes.append("passive_by_flip")

    # "X Reveals Y" already active — leave
    # Collapse whitespace / smart quotes noise
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

    if t != original:
        notes.append("title_edited")
    return t, notes


# --- Story lanes + diversity (Brad 2026-08-04) ---

_TAPE_TITLE = re.compile(
    r"\b("
    r"flirts with|tests? \$?\d|touches? \$?\d|hovers? (near|around)|"
    r"opens? (august|september|the (week|month))|"
    r"stocks (start|open|rally)|as stocks\b|"
    r"(bitcoin|btc|ether|eth)\s+(rise|rises|fall|falls|drop|drops|decline|declines|slip|slips|surge|surges)|"
    r"(rise|rises|fall|falls|drop|drops|decline|declines)\s+as\b|"
    r"price (action|levels?)|spot tape|thin volume"
    r")\b",
    re.I,
)

_GLOOM = re.compile(
    r"\b(bloodbath|apocalypse|catastrophe|collapse|doomed|armageddon|"
    r"panic selling|total wipeout|everything is over)\b",
    re.I,
)


def classify_story_lane(card: Dict[str, Any]) -> str:
    """
    Coarse lane for diversity caps.
    btc_tape = pure price/mood around BTC (and copycat tape) without a distinct event.
    """
    title = str(card.get("title") or "")
    summary = str(card.get("summary") or "")
    blob = f"{title} {summary}"
    tags = [str(t).lower() for t in (card.get("event_tags") or [])]
    tickers = [str(t).upper() for t in (card.get("tickers") or [])]
    keys = [str(k) for k in (card.get("event_keys") or [])]

    if "hack" in tags or "exploit" in tags or "evt:coldcard" in keys:
        return "security"
    if re.search(r"\b(hack|exploit|stolen|theft|breach|coldcard|air-?gapped)\b", blob, re.I):
        return "security"

    if "evt:strategy_btc" in keys or "evt:blackrock_flow" in keys:
        return "institution_flow"
    if "liquidation" in tags or "institution" in tags or "treasury_co" in tags:
        if re.search(r"\b(etf|ibit|fund|tokenized|mmf|money market)\b", blob, re.I) and not re.search(
            r"\b(liquidat|sells?|sold|sale|flow|outflow|inflow)\b", blob, re.I
        ):
            return "product_structure"
        return "institution_flow"

    if "etf" in tags or re.search(
        r"\b(etf|tokenized|money market fund|listing|delist|shut .+ etf|fund launch)\b", blob, re.I
    ):
        return "product_structure"

    if re.search(r"\b(fed|rates?|cpi|macro|yen|carry trade|recession)\b", blob, re.I):
        return "macro"
    if re.search(
        r"\b(sec|clarity act|cftc|congress|commissioner|regulation|regulatory|bill)\b",
        blob,
        re.I,
    ):
        return "regulatory"

    # Pure tape / level-watching
    btc_only = tickers == ["BTC-USD"] or (
        "BTC-USD" in tickers and len(tickers) == 1
    ) or (
        re.search(r"\bbitcoin\b|\bbtc\b", title, re.I)
        and not re.search(r"\b(ethereum|ether|solana|xrp|eth\b|sol\b)\b", title, re.I)
        and not tickers
    )
    if _TAPE_TITLE.search(title) or _TAPE_TITLE.search(summary[:180]):
        if btc_only or "BTC-USD" in tickers or re.search(r"\bbitcoin\b|\bbtc\b", title, re.I):
            # If there's a real named flow/security event, don't call it tape
            if not any(k.startswith("evt:") for k in keys):
                return "btc_tape"

    if any(t in tickers for t in ("ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD")):
        if "BTC-USD" not in tickers:
            return "alt_specific"

    return "other"


def soften_tone(text: str) -> str:
    """Keep honest; strip gloom-porn phrasing (titles/summaries if needed)."""
    t = (text or "").strip()
    t = _GLOOM.sub("rough stretch", t)
    t = re.sub(r"\bpanic\b", "stress", t, flags=re.I)
    t = re.sub(r"\bcrash(es|ed|ing)?\b", "sharp move", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def ensure_story_lane(card: Dict[str, Any]) -> Dict[str, Any]:
    """Attach story_lane for diversity caps. Does not add platform-why copy."""
    c = dict(card)
    c["story_lane"] = classify_story_lane(c)
    # Drop legacy field so publish/TG never re-surface old why lines
    c.pop("why_it_matters_platform", None)
    return c


def _norm_tickers(card: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for t in card.get("tickers") or []:
        s = str(t).strip().upper()
        if not s:
            continue
        if not s.endswith("-USD") and re.fullmatch(r"[A-Z0-9]{2,10}", s):
            s = f"{s}-USD"
        if s not in out:
            out.append(s)
    return out


def is_btc_only_card(card: Dict[str, Any]) -> bool:
    """True when card is BTC-only or untagged (treated as BTC-macro default)."""
    tickers = _norm_tickers(card)
    if not tickers:
        return True
    return set(tickers) == {"BTC-USD"}


def primary_basket_pair(card: Dict[str, Any]) -> str:
    """
    Primary pair label for diversity.
    Prefer first non-BTC basket hit; else BTC-USD; else 'none'.
    """
    tickers = _norm_tickers(card)
    for t in tickers:
        if t != "BTC-USD":
            return t
    if "BTC-USD" in tickers:
        return "BTC-USD"
    return "none"


def apply_lane_diversity(
    cards: Sequence[Dict[str, Any]],
    *,
    top_n: int = 5,
    lane_caps: Optional[Dict[str, int]] = None,
    dropped: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Keep rank order; enforce per-lane caps (default max 2 btc_tape)."""
    caps = dict(DEFAULT_LANE_CAPS)
    if lane_caps:
        caps.update(lane_caps)
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    drop_log = dropped if dropped is not None else []

    for c in cards:
        if len(out) >= top_n:
            break
        card = dict(c)
        lane = card.get("story_lane") or classify_story_lane(card)
        card["story_lane"] = lane
        n = counts.get(lane, 0)
        cap = caps.get(lane)
        if cap is not None and n >= cap:
            drop_log.append(
                {
                    "id": str(card.get("id") or ""),
                    "title": str(card.get("title") or "")[:80],
                    "reason": f"diversity_cap:{lane}>={cap}",
                }
            )
            continue
        counts[lane] = n + 1
        out.append(card)
    return out


def apply_basket_pair_diversity(
    cards: Sequence[Dict[str, Any]],
    *,
    top_n: int = 5,
    max_btc_only: Optional[int] = None,
    max_per_primary: Optional[int] = None,
    dropped: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Keep rank order; spread core-basket primary pairs.
    Caps pure BTC-only cards so ETH/SOL/XRP/… stories can surface.
    """
    if max_btc_only is None:
        max_btc_only = DEFAULT_MAX_BTC_ONLY if top_n <= 8 else max(DEFAULT_MAX_BTC_ONLY, top_n // 3)
    if max_per_primary is None:
        max_per_primary = DEFAULT_MAX_PER_PRIMARY if top_n <= 8 else max(DEFAULT_MAX_PER_PRIMARY, top_n // 4)

    out: List[Dict[str, Any]] = []
    drop_log = dropped if dropped is not None else []
    btc_only_n = 0
    primary_counts: Dict[str, int] = {}
    taken_ids: set = set()

    def try_take(pool: Sequence[Dict[str, Any]], *, allow_btc_only: bool) -> None:
        nonlocal btc_only_n
        for c in pool:
            if len(out) >= top_n:
                return
            oid = str(c.get("id") or "")
            if oid and oid in taken_ids:
                continue
            card = dict(c)
            btc_only = is_btc_only_card(card)
            if btc_only and not allow_btc_only:
                continue
            if btc_only and btc_only_n >= max_btc_only:
                drop_log.append(
                    {
                        "id": oid,
                        "title": str(card.get("title") or "")[:80],
                        "reason": f"diversity_cap:btc_only>={max_btc_only}",
                    }
                )
                continue
            primary = primary_basket_pair(card)
            if primary_counts.get(primary, 0) >= max_per_primary:
                drop_log.append(
                    {
                        "id": oid,
                        "title": str(card.get("title") or "")[:80],
                        "reason": f"diversity_cap:primary:{primary}>={max_per_primary}",
                    }
                )
                continue
            card["primary_pair"] = primary
            card["btc_only"] = btc_only
            out.append(card)
            if oid:
                taken_ids.add(oid)
            primary_counts[primary] = primary_counts.get(primary, 0) + 1
            if btc_only:
                btc_only_n += 1

    # Pass 1: non-BTC-only first (still rank-ordered within that set)
    try_take(cards, allow_btc_only=False)
    # Pass 2: fill remaining slots (BTC allowed under cap)
    try_take(cards, allow_btc_only=True)
    return out


def apply_shortlist_diversity(
    cards: Sequence[Dict[str, Any]],
    *,
    top_n: int = 5,
    lane_caps: Optional[Dict[str, int]] = None,
    max_btc_only: Optional[int] = None,
    max_per_primary: Optional[int] = None,
    dropped: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Lane caps then basket-pair caps (order-preserving within each stage)."""
    drop_log = dropped if dropped is not None else []
    # Wider intermediate so basket pass has room after lane drops
    mid_n = max(top_n * 3, top_n)
    after_lane = apply_lane_diversity(
        cards, top_n=mid_n, lane_caps=lane_caps, dropped=drop_log
    )
    return apply_basket_pair_diversity(
        after_lane,
        top_n=top_n,
        max_btc_only=max_btc_only,
        max_per_primary=max_per_primary,
        dropped=drop_log,
    )


def domain_label(source: str = "", url: str = "") -> str:
    """Human domain for display (strip www.)."""
    host = (source or "").strip()
    if not host and url:
        try:
            host = urlparse(url).netloc or ""
        except Exception:
            host = ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "source"


def md_source_link(source: str = "", url: str = "") -> str:
    """
    Telegram markdown: [coindesk.com](https://…/article).
    Falls back to bare domain if no URL.
    """
    label = domain_label(source, url)
    u = (url or "").strip()
    if u:
        return f"[{label}]({u})"
    return label


def format_tickers_display(tickers: Optional[Sequence[str]]) -> str:
    """Compact ticker list for TG (ETH-USD,SOL-USD → ETH,SOL)."""
    if not tickers:
        return "—"
    parts = []
    for t in tickers:
        s = str(t).strip().upper()
        if s.endswith("-USD"):
            s = s[:-4]
        if s and s not in parts:
            parts.append(s)
    return ",".join(parts) if parts else "—"


def ensure_platform_why(
    card: Dict[str, Any],
    *,
    override: Optional[str] = None,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Backward-compat shim — lane only; platform-why lines retired 2026-08-13."""
    _ = override, refresh
    return ensure_story_lane(card)


def editorial_pass(
    ranked: List[Dict[str, Any]],
    top_n: int = 8,
    fill_soft: bool = True,
    lane_caps: Optional[Dict[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Filter + rewrite ranked cards for publication.
    Keeps order preference from ranker; enforces one-per-event-key,
    lane diversity (max 2 btc_tape), and basket-pair diversity
    (max 2 BTC-only; spread primary pairs). No per-bullet platform-why.
    """
    dropped: List[Dict[str, str]] = []
    hard_ok: List[Dict[str, Any]] = []
    soft_pool: List[Dict[str, Any]] = []

    for card in ranked:
        title = card.get("title") or ""
        rr = reject_reason(title)
        if rr:
            dropped.append({"id": card.get("id", ""), "title": title[:80], "reason": rr})
            continue
        sr = soft_reject_reason(title)
        card = dict(card)
        keys = event_keys(title, card.get("summary") or "", card.get("event_tags") or [])
        card["event_keys"] = keys
        new_title, notes = to_active_voice(title)
        card["title_original"] = title
        card["title"] = new_title
        card = ensure_story_lane(card)
        if notes:
            card.setdefault("why", []).append("edit:" + ",".join(notes[:3]))
            ed = dict(card.get("editorial") or {})
            ed_notes = list(ed.get("notes") or [])
            for n in notes:
                if n not in ed_notes:
                    ed_notes.append(n)
            ed["notes"] = ed_notes
            ed.setdefault("title_original", title)
            card["editorial"] = ed
        else:
            card.setdefault("editorial", {"notes": [], "title_original": title})
        if sr:
            card.setdefault("why", []).append(sr)
            soft_pool.append(card)
        else:
            hard_ok.append(card)

    def take_unique(pool: List[Dict[str, Any]], n: int, used_keys: set) -> List[Dict[str, Any]]:
        out = []
        used_ids = set()
        for c in pool:
            if len(out) >= n:
                break
            # event key exclusivity
            ckeys = c.get("event_keys") or []
            if ckeys and any(k in used_keys for k in ckeys):
                dropped.append(
                    {
                        "id": c.get("id", ""),
                        "title": (c.get("title") or "")[:80],
                        "reason": "dup_event:" + ",".join(ckeys),
                    }
                )
                continue
            oid = c.get("id")
            if oid in used_ids:
                continue
            out.append(c)
            used_ids.add(oid)
            for k in ckeys:
                used_keys.add(k)
        return out

    # Pull a wider unique pool, then diversity-cut to top_n
    pool_n = max(top_n * 4, 16)
    used: set = set()
    unique = take_unique(hard_ok, pool_n, used)
    if fill_soft and len(unique) < pool_n:
        unique.extend(take_unique(soft_pool, pool_n - len(unique), used))

    selected = apply_shortlist_diversity(
        unique,
        top_n=top_n,
        lane_caps=lane_caps,
        dropped=dropped,
    )
    selected = [ensure_story_lane(c) for c in selected]

    lane_counts: Dict[str, int] = {}
    primary_counts: Dict[str, int] = {}
    btc_only_n = 0
    for c in selected:
        ln = str(c.get("story_lane") or "other")
        lane_counts[ln] = lane_counts.get(ln, 0) + 1
        pp = primary_basket_pair(c)
        c["primary_pair"] = pp
        primary_counts[pp] = primary_counts.get(pp, 0) + 1
        if is_btc_only_card(c):
            btc_only_n += 1
            c["btc_only"] = True
        else:
            c["btc_only"] = False

    meta = {
        "editorial_method": "v4_basket_pair_diversity_domain_links_2026-08-13",
        "dropped_n": len(dropped),
        "dropped_sample": dropped[:12],
        "hard_ok_n": len(hard_ok),
        "soft_pool_n": len(soft_pool),
        "published_n": len(selected),
        "lane_caps": dict(lane_caps or DEFAULT_LANE_CAPS),
        "lane_counts": lane_counts,
        "primary_pair_counts": primary_counts,
        "btc_only_n": btc_only_n,
        "max_btc_only": DEFAULT_MAX_BTC_ONLY,
        "why_it_matters": "retired",
        "tone": "positive_honest",
    }
    return selected, meta
