"""Daily Dose locked-pool A/B — fair twin-rank on the same 08:00 freeze.

Shadow only. Does NOT replace TG dose, publish_ready, or trade paths.

A = published editorial top-N (what hit Telegram)
B = Jev re-rank of the *same* candidate freeze (draft pool that fed A)
Card = dual top-N + plain relevance notes for Brad gut mark (better/worse/mixed)

Why locked: early 07:15 Jev on a different RSS slice is not a true A/B.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.daily_dose_jev_ranker import (
    DoseJevConfig,
    compare_lists,
    judge_pool,
    try_held_pairs,
)
from phase6.core.paths import (
    DAILY_DOSE_EDITED,
    DAILY_DOSE_JEV_AB_CARD,
    DAILY_DOSE_JEV_AB_HISTORY,
    DAILY_DOSE_JEV_AB_LATEST,
    DAILY_DOSE_LATEST,
    DAILY_DOSE_PUBLISH_READY,
    load_trading_basket,
)
from phase6.domain.ports.judgment import JudgmentPort

METHOD = "daily_dose_jev_ab_locked_v1"
SCHEMA_VERSION = 1
NOT_TRADE = "NOT a trade signal · shadow A/B only · does not change live dose"

# Cheap title heuristics for plain-English notes (no second LLM).
_THEATER = re.compile(
    r"\b(scam|onlyfans|liquidat|shorts? get|rockets? to|surges? to|"
    r"what happened|roundup|meme)\b",
    re.I,
)
_ESSAY = re.compile(
    r"\b(argues that|op-?ed|essay|privacy without|co-?founder .* says|"
    r"believes that)\b",
    re.I,
)
_FLOW = re.compile(
    r"\b(etf|inflow|outflow|fidelity|blackrock|flows?|sec |cftc|fed )\b",
    re.I,
)
_PRODUCT = re.compile(
    r"\b(upgrade|launch|borrow|listing|mainnet|payments?|block.?time|"
    r"validator|partnership|integration)\b",
    re.I,
)


@dataclass
class DoseAbConfig:
    top_n: int = 5
    max_judge: int = 16
    dry_run: bool = False
    model: str = "~typesafe/jev-latest"
    write_history: bool = True
    latest_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_AB_LATEST)
    card_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_AB_CARD)
    history_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_AB_HISTORY)
    edited_path: Path = field(default_factory=lambda: DAILY_DOSE_EDITED)
    draft_path: Path = field(default_factory=lambda: DAILY_DOSE_LATEST)
    publish_txt_path: Path = field(default_factory=lambda: DAILY_DOSE_PUBLISH_READY)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def load_arm_a(path: Path) -> List[Dict[str, Any]]:
    """Published editorial package items (Telegram order)."""
    d = _load_json(path)
    items = d.get("items") or []
    return [dict(x) for x in items if isinstance(x, dict) and x.get("id")]


def load_freeze_pool(
    draft_path: Path,
    arm_a: Sequence[Dict[str, Any]],
    *,
    max_n: int = 24,
) -> List[Dict[str, Any]]:
    """Same candidate freeze that fed the live dose.

    Prefer full draft (`daily_dose_latest` top-8+). Guarantee every Arm A id
    is present so B re-ranks a superset of what published — never a foreign pool.
    """
    draft = _load_json(draft_path)
    raw = [dict(x) for x in (draft.get("items") or []) if isinstance(x, dict) and x.get("id")]
    by_id: Dict[str, Dict[str, Any]] = {}
    for c in raw:
        by_id[str(c["id"])] = c
    for c in arm_a:
        iid = str(c.get("id") or "")
        if iid and iid not in by_id:
            by_id[iid] = dict(c)
    # Stable order: draft order first, then any A-only appends
    ordered: List[Dict[str, Any]] = []
    seen = set()
    for c in raw:
        iid = str(c["id"])
        if iid not in seen:
            ordered.append(by_id[iid])
            seen.add(iid)
    for c in arm_a:
        iid = str(c.get("id") or "")
        if iid and iid not in seen:
            ordered.append(by_id[iid])
            seen.add(iid)
    return ordered[: max(1, int(max_n))]


def _tickers(card: Dict[str, Any]) -> List[str]:
    t = card.get("tickers") or []
    if isinstance(t, str):
        return [t]
    return [str(x) for x in t if x]


def _title(card: Dict[str, Any]) -> str:
    return str(card.get("title") or card.get("title_original") or "")[:140]


def classify_card(card: Dict[str, Any], *, basket: Sequence[str], held: Sequence[str]) -> Dict[str, Any]:
    title = _title(card)
    ticks = _tickers(card)
    basket_u = {str(p).upper().replace("-USD", "") for p in basket}
    held_u = {str(p).upper().replace("-USD", "") for p in held}
    tick_u = {str(t).upper().replace("-USD", "") for t in ticks}
    on_basket = sorted(tick_u & basket_u)
    on_held = sorted(tick_u & held_u)
    tags: List[str] = []
    if _THEATER.search(title):
        tags.append("theater")
    if _ESSAY.search(title):
        tags.append("essay")
    if _FLOW.search(title):
        tags.append("flow_macro")
    if _PRODUCT.search(title):
        tags.append("product")
    if on_held:
        tags.append("held_pair")
    elif on_basket:
        tags.append("basket_pair")
    else:
        tags.append("off_book")
    # Desk relevance 0-3 rough
    score = 0
    if on_held:
        score += 2
    elif on_basket:
        score += 1
    if "flow_macro" in tags or "product" in tags:
        score += 1
    if "theater" in tags or "essay" in tags:
        score -= 1
    score = max(0, min(3, score))
    return {
        "tags": tags,
        "on_basket": on_basket,
        "on_held": on_held,
        "desk_relevance_0_3": score,
        "title": title,
        "tickers": ticks,
    }


def note_for_move(
    *,
    side: str,
    card: Dict[str, Any],
    cls: Dict[str, Any],
) -> str:
    """One plain line: why this card helped or hurt desk relevance."""
    tags = cls.get("tags") or []
    pairs = cls.get("on_held") or cls.get("on_basket") or []
    pair_s = ",".join(pairs) if pairs else "no-basket"
    if side == "only_b":
        if "product" in tags and pairs:
            return f"B added product/flow on {pair_s} — platform-specific."
        if "flow_macro" in tags:
            return f"B added macro/flow ({pair_s}) — regime tone."
        if pairs:
            return f"B promoted basket name {pair_s}."
        return f"B added off-book or soft card ({pair_s})."
    # only_a = published kept, Jev dropped/deprioritized
    if "theater" in tags:
        return f"B dropped theater/chase on {pair_s} — usually good."
    if "essay" in tags:
        return f"B dropped essay/soft take on {pair_s} — usually good."
    if "flow_macro" in tags:
        return f"B deprioritized flow/macro on {pair_s} — may be a miss."
    if pairs:
        return f"B deprioritized basket {pair_s} vs published."
    return f"B deprioritized {pair_s}."


def build_relevance_notes(
    arm_a: Sequence[Dict[str, Any]],
    arm_b: Sequence[Dict[str, Any]],
    cmp_: Dict[str, Any],
    *,
    basket: Sequence[str],
    held: Sequence[str],
    id_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    only_a = list(cmp_.get("only_baseline") or [])
    only_b = list(cmp_.get("only_jev") or [])
    lines: List[str] = []
    a_scores = []
    b_scores = []
    for c in arm_a:
        cl = classify_card(c, basket=basket, held=held)
        a_scores.append(int(cl["desk_relevance_0_3"]))
    for c in arm_b:
        cl = classify_card(c, basket=basket, held=held)
        b_scores.append(int(cl["desk_relevance_0_3"]))
    for iid in only_b:
        card = id_index.get(str(iid)) or {"id": iid, "title": str(iid)}
        cl = classify_card(card, basket=basket, held=held)
        lines.append(note_for_move(side="only_b", card=card, cls=cl))
    for iid in only_a:
        card = id_index.get(str(iid)) or {"id": iid, "title": str(iid)}
        cl = classify_card(card, basket=basket, held=held)
        lines.append(note_for_move(side="only_a", card=card, cls=cl))

    mean_a = sum(a_scores) / len(a_scores) if a_scores else 0.0
    mean_b = sum(b_scores) / len(b_scores) if b_scores else 0.0
    delta = mean_b - mean_a
    if abs(delta) < 0.15 and not only_a and not only_b:
        auto = "mixed"
        auto_why = "Nearly identical tops; no material rank swap."
    elif delta > 0.25:
        auto = "b_better"
        auto_why = f"B desk-relevance mean {mean_b:.2f} > A {mean_a:.2f}."
    elif delta < -0.25:
        auto = "a_better"
        auto_why = f"A desk-relevance mean {mean_a:.2f} > B {mean_b:.2f}."
    else:
        auto = "mixed"
        auto_why = (
            f"Close means (A {mean_a:.2f} vs B {mean_b:.2f}); "
            "read move notes — flow miss vs theater drop can cancel."
        )

    return {
        "mean_desk_rel_a": round(mean_a, 3),
        "mean_desk_rel_b": round(mean_b, 3),
        "delta_b_minus_a": round(delta, 3),
        "auto_mark": auto,  # heuristic only — Brad gut is SSOT
        "auto_why": auto_why,
        "move_notes": lines,
        "brad_mark": None,  # filled later by operator if desired
        "brad_mark_choices": ["b_better", "a_better", "mixed"],
    }


def slim_card(c: Dict[str, Any], *, include_jev: bool = False) -> Dict[str, Any]:
    out = {
        "id": c.get("id"),
        "title": _title(c),
        "tickers": _tickers(c),
        "primary_pair": c.get("primary_pair"),
        "url": c.get("url") or c.get("source_url"),
        "source": c.get("source"),
        "baseline_composite": (c.get("scores") or {}).get("composite"),
    }
    if include_jev and c.get("jev"):
        j = c["jev"]
        out["jev"] = {
            "jev_score": j.get("jev_score"),
            "keep_in_brief": j.get("keep_in_brief"),
            "material_to_book": j.get("material_to_book"),
            "noise_or_shill": j.get("noise_or_shill"),
            "coffee_worthy": j.get("coffee_worthy"),
        }
    return out


def render_ab_card(payload: Dict[str, Any]) -> str:
    day = payload.get("dose_day") or ""
    cmp_ = payload.get("compare") or {}
    rel = payload.get("relevance") or {}
    lines = [
        f"# Daily Dose locked A/B · {day}",
        "",
        f"**{NOT_TRADE}**",
        f"Freeze: `{payload.get('freeze_source')}` · n={payload.get('freeze_n')} · "
        f"Jaccard={cmp_.get('jaccard')} · judged={((payload.get('judge_stats') or {}).get('judged'))}",
        "",
        f"**Auto mark (heuristic, not Brad):** `{rel.get('auto_mark')}` — {rel.get('auto_why')}",
        f"**Your mark:** reply `dose ab b_better` / `a_better` / `mixed` (optional)",
        "",
        "## A — published (live TG)",
    ]
    for i, c in enumerate(payload.get("arm_a") or [], 1):
        ticks = ",".join(c.get("tickers") or []) or "—"
        lines.append(f"{i}. {c.get('title', '')[:110]}")
        lines.append(f"   {ticks}")
    lines.append("")
    lines.append("## B — Jev on same freeze")
    for i, c in enumerate(payload.get("arm_b") or [], 1):
        j = c.get("jev") or {}
        ticks = ",".join(c.get("tickers") or []) or "—"
        lines.append(
            f"{i}. [jev={j.get('jev_score')} mat={j.get('material_to_book')} "
            f"noise={j.get('noise_or_shill')}] {c.get('title', '')[:100]}"
        )
        lines.append(f"   {ticks}")
    lines.append("")
    lines.append("## Why B moved (plain)")
    notes = rel.get("move_notes") or []
    if not notes:
        lines.append("- No unique moves — tops fully overlap.")
    else:
        for n in notes:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("## Only B (not in published top)")
    for iid in cmp_.get("only_jev") or []:
        t = (payload.get("id_titles") or {}).get(str(iid), str(iid))
        lines.append(f"- {t[:120]}")
    if not cmp_.get("only_jev"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Only A (Jev deprioritized)")
    for iid in cmp_.get("only_baseline") or []:
        t = (payload.get("id_titles") or {}).get(str(iid), str(iid))
        lines.append(f"- {t[:120]}")
    if not cmp_.get("only_baseline"):
        lines.append("- (none)")
    lines.append("")
    lines.append("_Live dose unchanged. No promote without multi-day Brad marks._")
    lines.append("")
    return "\n".join(lines)


def format_tg_card(payload: Dict[str, Any]) -> str:
    """Short operator card for optional TG — not a second full dose."""
    day = payload.get("dose_day") or ""
    cmp_ = payload.get("compare") or {}
    rel = payload.get("relevance") or {}
    lines = [
        f"Dose A/B · {day} · locked freeze",
        "(Shadow compare — NOT a second dose · NOT a trade signal)",
        "",
        f"Overlap {cmp_.get('n_overlap')}/{cmp_.get('n_baseline')} · "
        f"Jaccard {cmp_.get('jaccard')} · auto `{rel.get('auto_mark')}`",
        "",
        "A (published):",
    ]
    for i, c in enumerate((payload.get("arm_a") or [])[:5], 1):
        lines.append(f"  {i}. {(_title(c))[:90]}")
    lines.append("B (Jev same freeze):")
    for i, c in enumerate((payload.get("arm_b") or [])[:5], 1):
        lines.append(f"  {i}. {(_title(c))[:90]}")
    notes = (rel.get("move_notes") or [])[:4]
    if notes:
        lines.append("Why:")
        for n in notes:
            lines.append(f"  · {n}")
    lines.append("")
    lines.append("Mark: dose ab b_better | a_better | mixed")
    return "\n".join(lines)


def run_locked_ab(
    *,
    cfg: Optional[DoseAbConfig] = None,
    port: Optional[JudgmentPort] = None,
    fixture_freeze: Optional[List[Dict[str, Any]]] = None,
    fixture_arm_a: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    cfg = cfg or DoseAbConfig()
    now = datetime.now(timezone.utc)
    basket = load_trading_basket()
    held = try_held_pairs()

    if fixture_arm_a is not None:
        arm_a = [dict(x) for x in fixture_arm_a]
    else:
        arm_a = load_arm_a(cfg.edited_path)
    if not arm_a:
        # Fallback: draft top_n if edit package missing
        draft_items = load_freeze_pool(cfg.draft_path, [], max_n=cfg.top_n)
        arm_a = draft_items[: cfg.top_n]

    if fixture_freeze is not None:
        freeze = [dict(x) for x in fixture_freeze]
        freeze_source = "fixture"
    else:
        freeze = load_freeze_pool(cfg.draft_path, arm_a, max_n=max(cfg.max_judge, cfg.top_n * 2))
        freeze_source = f"{cfg.draft_path.name}+arm_a_ids"

    if not freeze:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "method": METHOD,
            "generated_at": now.isoformat(),
            "ok": False,
            "error": "empty_freeze",
            "not_a_trade_signal": True,
            "shadow_only": True,
            "publishes_replacement_dose": False,
        }
        cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        cfg.card_path.write_text("# Dose A/B\n\nempty freeze — no live dose artifacts?\n", encoding="utf-8")
        return payload

    # Cap judge list but never drop Arm A members
    a_ids = {str(c.get("id")) for c in arm_a if c.get("id")}
    primary = [c for c in freeze if str(c.get("id")) in a_ids]
    rest = [c for c in freeze if str(c.get("id")) not in a_ids]
    pool = (primary + rest)[: cfg.max_judge]
    # If A still missing from pool (shouldn't), force-append
    have = {str(c.get("id")) for c in pool}
    for c in arm_a:
        iid = str(c.get("id") or "")
        if iid and iid not in have:
            pool.append(dict(c))
            have.add(iid)

    jcfg = DoseJevConfig(
        top_n=cfg.top_n,
        max_judge=cfg.max_judge,
        dry_run=cfg.dry_run,
        model=cfg.model,
        from_latest_only=False,
        write_crumbs=True,
    )
    judged, judge_stats = judge_pool(pool, cfg=jcfg, port=port, basket=basket, held=held)
    arm_b = judged[: cfg.top_n]
    cmp_ = compare_lists(arm_a[: cfg.top_n], arm_b)

    id_index: Dict[str, Dict[str, Any]] = {}
    for c in list(freeze) + list(judged) + list(arm_a):
        iid = str(c.get("id") or "")
        if iid:
            id_index[iid] = c
    id_titles = {i: _title(c) for i, c in id_index.items()}

    relevance = build_relevance_notes(
        arm_a[: cfg.top_n],
        arm_b,
        cmp_,
        basket=basket,
        held=held,
        id_index=id_index,
    )

    # Dose day from publish header or generated_at
    dose_day = now.astimezone().strftime("%Y-%m-%d")
    pub = cfg.publish_txt_path
    if pub.is_file():
        try:
            first = pub.read_text(encoding="utf-8").splitlines()[0]
            m = re.search(r"(\d{4}-\d{2}-\d{2})", first)
            if m:
                dose_day = m.group(1)
        except OSError:
            pass

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": METHOD,
        "generated_at": now.isoformat(),
        "dose_day": dose_day,
        "ok": True,
        "not_a_trade_signal": True,
        "shadow_only": True,
        "publishes_replacement_dose": False,
        "overwrites_daily_dose_latest": False,
        "freeze_source": freeze_source,
        "freeze_n": len(freeze),
        "freeze_ids": [str(c.get("id")) for c in freeze],
        "top_n": cfg.top_n,
        "basket": list(basket)[:24],
        "held_pairs": held,
        "judge_stats": judge_stats,
        "compare": cmp_,
        "relevance": relevance,
        "arm_a": [slim_card(c) for c in arm_a[: cfg.top_n]],
        "arm_b": [slim_card(c, include_jev=True) for c in arm_b],
        "id_titles": id_titles,
        "note": (
            "Locked-pool A/B. A is live published top-N. B is Jev on the same "
            "draft freeze (superset including A). Live TG body unchanged."
        ),
    }
    card_md = render_ab_card(payload)
    tg = format_tg_card(payload)
    payload["tg_card"] = tg

    cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cfg.card_path.write_text(card_md, encoding="utf-8")
    if cfg.write_history:
        row = {
            "ts": payload["generated_at"],
            "dose_day": dose_day,
            "jaccard": cmp_.get("jaccard"),
            "auto_mark": relevance.get("auto_mark"),
            "mean_a": relevance.get("mean_desk_rel_a"),
            "mean_b": relevance.get("mean_desk_rel_b"),
            "only_a_n": len(cmp_.get("only_baseline") or []),
            "only_b_n": len(cmp_.get("only_jev") or []),
            "brad_mark": None,
        }
        with cfg.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return payload
