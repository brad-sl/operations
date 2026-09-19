"""Daily Dose Jev ranker — shadow compare vs RSS composite rank.

Measure-only. Does NOT overwrite daily_dose_latest / publish_ready / TG body.
Does NOT touch allocator, tryout, or sentiment scores.

Flow:
  RSS → baseline rank pool → Jev judges each card → Jev top-N
  vs baseline top-N → overlap board + crumbs.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.adapters.judgment_jev import OpenRouterJevAdapter, mock_from_fixture
from phase6.core.paths import (
    DAILY_DOSE_JEV_BUDGET,
    DAILY_DOSE_JEV_COMPARE,
    DAILY_DOSE_JEV_CRUMBS,
    DAILY_DOSE_JEV_LATEST,
    DAILY_DOSE_JEV_PREVIEW,
    DAILY_DOSE_LATEST,
    PROJECT_ROOT,
    load_trading_basket,
)
from phase6.core.rss_feeds import DEFAULT_FEEDS, RssItem, fetch_all_feeds, load_pair_keywords
from phase6.domain.ports.judgment import JudgmentPort, JudgmentResult
from phase6.scripts.run_daily_dose import (
    DEFAULT_TOP_N,
    DEFAULT_WINDOW_H,
    format_telegram,
    rank_items,
)

METHOD = "daily_dose_jev_ranker_v1_shadow"
SCHEMA_VERSION = 1

# Keep if keep_noul high and noise low; boost book materiality + coffee test.
W_KEEP = 0.40
W_MATERIAL = 0.25
W_COFFEE = 0.20
W_BOOK = 0.15
# Penalties applied multiplicatively-ish via subtraction after clamp
NOISE_PENALTY = 0.35
PRICED_PENALTY = 0.20


def headline_questions() -> Dict[str, Any]:
    """Atomic typed questions — briefing filter, not trade entry.

    Schema matches lab Decision API shape: type + instructions + criteria
    (noul uses true/false criteria records — bare string criteria → HTTP 400).
    """
    return {
        "keep_in_brief": {
            "type": "noul",
            "instructions": (
                "Should this headline appear in a short morning crypto operator brief? "
                "Prefer concrete events (ETF/flow, regulation, hack, listing, major protocol) "
                "over roundups, price-level watching, vague explainers, or pure hype."
            ),
            "criteria": {
                "true": "Concrete, newsworthy, operator-relevant; belongs in top brief",
                "false": "Roundup, filler, vague explainer, hype, or not brief-worthy",
            },
        },
        "material_to_book": {
            "type": "noul",
            "instructions": (
                "Is this material to a liquid CEX book trading major alts + BTC/ETH "
                "(not meme degen only)? Higher if it can move held or basket names in state."
            ),
            "criteria": {
                "true": "Likely matters to liquid majors / basket names or book risk",
                "false": "Peripheral meme/noise with little book relevance",
            },
        },
        "noise_or_shill": {
            "type": "noul",
            "instructions": (
                "Is this noise, shill, recycled roundup, or engagement bait with little new fact?"
            ),
            "criteria": {
                "true": "Mostly noise, shill, roundup, or bait",
                "false": "Substantive reporting or primary event",
            },
        },
        "already_priced": {
            "type": "noul",
            "instructions": (
                "Does this look like a story the market already fully digested "
                "(old narrative, pure level-watching, stale macro rehash)?"
            ),
            "criteria": {
                "true": "Already priced / stale / pure tape-watching",
                "false": "Still fresh or newly material information",
            },
        },
        "coffee_worthy": {
            "type": "noul",
            "instructions": (
                "Would a busy operator skim this as worth 5 seconds over coffee "
                "(clear who/what/so-what), not doom-scroll filler?"
            ),
            "criteria": {
                "true": "Clear, skim-worthy, high information density",
                "false": "Not worth the skim; low density or filler",
            },
        },
    }


def card_state(card: Dict[str, Any], *, basket: Sequence[str], held: Sequence[str]) -> Dict[str, Any]:
    return {
        "task": "daily_dose_headline_filter",
        "not_a_trade_signal": True,
        "title": card.get("title") or "",
        "summary": (card.get("summary") or "")[:280],
        "source": card.get("source") or "",
        "tickers": list(card.get("tickers") or []),
        "event_tags": list(card.get("event_tags") or []),
        "baseline_composite": (card.get("scores") or {}).get("composite"),
        "basket": list(basket)[:24],
        "held_pairs": list(held)[:16],
        "url_host_hint": str(card.get("url") or "")[:80],
    }


def _noul(result: JudgmentResult, name: str, default: float = 0.0) -> float:
    a = result.answers.get(name)
    if a is None or a.noul is None:
        return default
    return max(0.0, min(1.0, float(a.noul)))


def jev_score_from_result(result: JudgmentResult) -> Dict[str, Any]:
    keep = _noul(result, "keep_in_brief", 0.0)
    material = _noul(result, "material_to_book", 0.0)
    noise = _noul(result, "noise_or_shill", 0.5)
    priced = _noul(result, "already_priced", 0.5)
    coffee = _noul(result, "coffee_worthy", 0.0)
    raw = (
        W_KEEP * keep
        + W_MATERIAL * material
        + W_COFFEE * coffee
        + W_BOOK * material  # book weight rides material
        - NOISE_PENALTY * noise
        - PRICED_PENALTY * priced
    )
    score = max(0.0, min(1.0, raw + 0.15))  # small floor shift so mid-keep isn't crushed
    confs = []
    for name in headline_questions():
        a = result.answers.get(name)
        if a and a.confidence is not None:
            confs.append(float(a.confidence))
    conf = sum(confs) / len(confs) if confs else None
    return {
        "jev_score": round(score, 4),
        "keep_in_brief": round(keep, 4),
        "material_to_book": round(material, 4),
        "noise_or_shill": round(noise, 4),
        "already_priced": round(priced, 4),
        "coffee_worthy": round(coffee, 4),
        "confidence_mean": round(conf, 4) if conf is not None else None,
        "latency_ms": int(result.latency_ms or 0),
        "ok": bool(result.ok),
        "error": result.error or "",
        "model": result.model,
    }


@dataclass
class DoseJevConfig:
    window_h: float = DEFAULT_WINDOW_H
    baseline_pool: int = 24
    top_n: int = 5
    max_judge: int = 20
    max_calls_per_day: int = 80
    dry_run: bool = False
    from_latest_only: bool = False
    model: str = "~typesafe/jev-latest"
    write_crumbs: bool = True
    budget_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_BUDGET)
    crumbs_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_CRUMBS)
    latest_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_LATEST)
    compare_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_COMPARE)
    preview_path: Path = field(default_factory=lambda: DAILY_DOSE_JEV_PREVIEW)


def _day_key(now: Optional[datetime] = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d")


def load_budget(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"day": _day_key(), "calls": 0}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("day") != _day_key():
            return {"day": _day_key(), "calls": 0}
        return d
    except (OSError, json.JSONDecodeError):
        return {"day": _day_key(), "calls": 0}


def save_budget(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def try_held_pairs() -> List[str]:
    p = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"
    if not p.is_file():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    held: List[str] = []
    for key in ("trading_positions", "active_positions", "positions"):
        rows = d.get(key)
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            pair = str(r.get("pair") or r.get("product_id") or r.get("symbol") or "").upper()
            if pair and pair not in held:
                held.append(pair)
    return held[:24]


def load_baseline_cards_from_latest() -> List[Dict[str, Any]]:
    if not DAILY_DOSE_LATEST.is_file():
        return []
    try:
        d = json.loads(DAILY_DOSE_LATEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = d.get("items") or []
    return [dict(x) for x in items if isinstance(x, dict)]


def build_baseline_pool(
    *,
    cfg: DoseJevConfig,
    fixture_items: Optional[List[RssItem]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Return (pool_for_jev, meta, baseline_top_n_cards)."""
    now = datetime.now(timezone.utc)
    basket = load_trading_basket()
    kws = load_pair_keywords(PROJECT_ROOT)
    feed_stats: List[Dict[str, Any]] = []

    if cfg.from_latest_only and fixture_items is None:
        cards = load_baseline_cards_from_latest()
        meta = {
            "source": "daily_dose_latest",
            "candidates_in_window": len(cards),
            "thin_day": len(cards) < 3,
        }
        baseline_top = cards[: cfg.top_n]
        pool = cards[: cfg.max_judge]
        return pool, meta, baseline_top

    if fixture_items is not None:
        raw = fixture_items
        feed_stats = [{"url": "fixture", "n": len(raw), "ok": True}]
    else:
        raw, feed_stats = fetch_all_feeds(DEFAULT_FEEDS)

    ranked, rank_meta = rank_items(
        raw,
        basket=basket,
        kws=kws,
        now=now,
        window_h=cfg.window_h,
        top_n=max(cfg.baseline_pool, cfg.top_n),
        open_positions=None,
    )
    # rank_items already applies diversity into top_n=pool size
    baseline_top = ranked[: cfg.top_n]
    pool = ranked[: cfg.max_judge]
    meta = {
        "source": "rss_rank",
        "feed_stats_ok": sum(1 for f in feed_stats if f.get("ok") or f.get("n", 0) > 0),
        "feeds_total": len(feed_stats),
        **rank_meta,
    }
    return pool, meta, baseline_top


def mock_answers_for_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic offline answers from baseline composite + title cues."""
    title = (card.get("title") or "").lower()
    comp = float((card.get("scores") or {}).get("composite") or 0.5)
    noise = 0.85 if any(w in title for w in ("roundup", "what happened", "meme", "onlyfans")) else 0.2
    keep = max(0.05, min(0.95, comp * (1.0 - 0.5 * noise)))
    material = max(0.05, min(0.95, comp * 0.9))
    if any(w in title for w in ("sec", "etf", "hack", "outage", "blackrock")):
        material = min(0.95, material + 0.15)
        keep = min(0.95, keep + 0.1)
    return {
        "keep_in_brief": {"type": "noul", "noul": keep, "confidence": 0.7},
        "material_to_book": {"type": "noul", "noul": material, "confidence": 0.65},
        "noise_or_shill": {"type": "noul", "noul": noise, "confidence": 0.7},
        "already_priced": {"type": "noul", "noul": 0.3 if "watch" not in title else 0.7, "confidence": 0.55},
        "coffee_worthy": {"type": "noul", "noul": keep * 0.9, "confidence": 0.6},
    }


def judge_pool(
    pool: List[Dict[str, Any]],
    *,
    cfg: DoseJevConfig,
    port: Optional[JudgmentPort] = None,
    basket: Optional[Sequence[str]] = None,
    held: Optional[Sequence[str]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    basket = list(basket or load_trading_basket())
    held = list(held or try_held_pairs())
    questions = headline_questions()
    budget = load_budget(cfg.budget_path)
    calls_left = max(0, int(cfg.max_calls_per_day) - int(budget.get("calls") or 0))

    adapter: Optional[JudgmentPort] = None
    if not cfg.dry_run:
        adapter = port or OpenRouterJevAdapter(
            model=cfg.model,
            title="phase6-daily-dose-jev",
        )

    judged: List[Dict[str, Any]] = []
    calls = 0
    errors = 0
    lat_sum = 0

    for card in pool:
        if calls >= cfg.max_judge:
            break
        if not cfg.dry_run and calls >= calls_left:
            break

        state = card_state(card, basket=basket, held=held)
        if cfg.dry_run and port is None:
            result = mock_from_fixture(mock_answers_for_card(card))
        elif port is not None and cfg.dry_run:
            result = port.decide(state, questions, model="mock")
        else:
            assert adapter is not None
            result = adapter.decide(state, questions, model=cfg.model)

        calls += 1
        js = jev_score_from_result(result)
        if not result.ok:
            errors += 1
        lat_sum += int(js.get("latency_ms") or 0)

        out = dict(card)
        out["jev"] = js
        out["jev_answers"] = {
            k: ({"type": a.type, **a.raw} if a else None)
            for k, a in ((n, result.answers.get(n)) for n in questions)
        }
        judged.append(out)

        if cfg.write_crumbs:
            crumb = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "id": card.get("id"),
                "title": (card.get("title") or "")[:140],
                "tickers": card.get("tickers"),
                "baseline_composite": (card.get("scores") or {}).get("composite"),
                "jev": js,
                "method": METHOD,
                "dry_run": cfg.dry_run,
            }
            cfg.crumbs_path.parent.mkdir(parents=True, exist_ok=True)
            with cfg.crumbs_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(crumb, ensure_ascii=False) + "\n")

    if not cfg.dry_run and calls:
        budget["calls"] = int(budget.get("calls") or 0) + calls
        budget["day"] = _day_key()
        save_budget(cfg.budget_path, budget)

    judged.sort(
        key=lambda c: (
            float((c.get("jev") or {}).get("jev_score") or 0.0),
            float((c.get("scores") or {}).get("composite") or 0.0),
        ),
        reverse=True,
    )
    stats = {
        "judged": len(judged),
        "calls": calls,
        "errors": errors,
        "latency_ms_sum": lat_sum,
        "latency_ms_mean": int(lat_sum / calls) if calls else 0,
        "budget_calls_today": int(load_budget(cfg.budget_path).get("calls") or 0),
        "dry_run": cfg.dry_run,
    }
    return judged, stats


def compare_lists(
    baseline_top: List[Dict[str, Any]],
    jev_top: List[Dict[str, Any]],
) -> Dict[str, Any]:
    b_ids = [c.get("id") for c in baseline_top if c.get("id")]
    j_ids = [c.get("id") for c in jev_top if c.get("id")]
    b_set, j_set = set(b_ids), set(j_ids)
    inter = b_set & j_set
    union = b_set | j_set
    jaccard = (len(inter) / len(union)) if union else 0.0
    return {
        "baseline_ids": b_ids,
        "jev_ids": j_ids,
        "overlap_ids": sorted(str(x) for x in inter),
        "only_baseline": sorted(str(x) for x in (b_set - j_set)),
        "only_jev": sorted(str(x) for x in (j_set - b_set)),
        "jaccard": round(jaccard, 4),
        "n_baseline": len(b_ids),
        "n_jev": len(j_ids),
        "n_overlap": len(inter),
    }


def titles_by_id(cards: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    return {str(c.get("id")): str(c.get("title") or "")[:120] for c in cards if c.get("id")}


def render_compare_md(payload: Dict[str, Any]) -> str:
    cmp_ = payload.get("compare") or {}
    b_items = payload.get("baseline_top") or []
    j_items = payload.get("jev_top") or []
    id_title = titles_by_id(list(b_items) + list(j_items) + list(payload.get("judged") or []))
    lines = [
        f"# Daily Dose Jev ranker compare ({payload.get('generated_at', '')})",
        "",
        f"**Method:** `{payload.get('method')}` · **NOT a trade signal** · shadow only",
        f"**Jaccard overlap top-{payload.get('top_n')}:** {cmp_.get('jaccard')} "
        f"({cmp_.get('n_overlap')}/{cmp_.get('n_baseline')} baseline ids)",
        f"**Judged:** {(payload.get('judge_stats') or {}).get('judged')} · "
        f"errors={(payload.get('judge_stats') or {}).get('errors')} · "
        f"mean_lat_ms={(payload.get('judge_stats') or {}).get('latency_ms_mean')}",
        "",
        "## Baseline top",
    ]
    for i, c in enumerate(b_items, 1):
        sc = (c.get("scores") or {}).get("composite")
        lines.append(f"{i}. [{sc}] {c.get('title', '')[:100]}")
    lines.append("")
    lines.append("## Jev top")
    for i, c in enumerate(j_items, 1):
        j = c.get("jev") or {}
        lines.append(
            f"{i}. [jev={j.get('jev_score')} keep={j.get('keep_in_brief')} "
            f"noise={j.get('noise_or_shill')}] {c.get('title', '')[:100]}"
        )
    lines.append("")
    lines.append("## Only Jev kept (vs baseline top)")
    for iid in cmp_.get("only_jev") or []:
        lines.append(f"- {id_title.get(iid, iid)}")
    if not cmp_.get("only_jev"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Only baseline kept (Jev deprioritized)")
    for iid in cmp_.get("only_baseline") or []:
        lines.append(f"- {id_title.get(iid, iid)}")
    if not cmp_.get("only_baseline"):
        lines.append("- (none)")
    lines.append("")
    lines.append(
        "_Expand platform-relevance only after multi-day skim says Jev quality is better._"
    )
    lines.append("")
    return "\n".join(lines)


def run_ranker(
    *,
    cfg: Optional[DoseJevConfig] = None,
    port: Optional[JudgmentPort] = None,
    fixture_items: Optional[List[RssItem]] = None,
) -> Dict[str, Any]:
    cfg = cfg or DoseJevConfig()
    now = datetime.now(timezone.utc)
    basket = load_trading_basket()
    held = try_held_pairs()

    pool, pool_meta, baseline_top = build_baseline_pool(cfg=cfg, fixture_items=fixture_items)
    judged, judge_stats = judge_pool(
        pool, cfg=cfg, port=port, basket=basket, held=held
    )
    jev_top = judged[: cfg.top_n]
    cmp_ = compare_lists(baseline_top, jev_top)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": METHOD,
        "generated_at": now.isoformat(),
        "top_n": cfg.top_n,
        "not_a_trade_signal": True,
        "shadow_only": True,
        "publishes_to_telegram": False,
        "overwrites_daily_dose_latest": False,
        "basket": list(basket)[:24],
        "held_pairs": held,
        "pool_meta": pool_meta,
        "judge_stats": judge_stats,
        "compare": cmp_,
        "baseline_top": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "tickers": c.get("tickers"),
                "scores": c.get("scores"),
                "url": c.get("url"),
            }
            for c in baseline_top
        ],
        "jev_top": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "tickers": c.get("tickers"),
                "scores": c.get("scores"),
                "jev": c.get("jev"),
                "url": c.get("url"),
            }
            for c in jev_top
        ],
        "judged": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "tickers": c.get("tickers"),
                "baseline_composite": (c.get("scores") or {}).get("composite"),
                "jev": c.get("jev"),
            }
            for c in judged
        ],
        "note": (
            "Shadow ranker. Live TG still uses RSS+editorial pipeline. "
            "Promote Jev order only after Brad likes multi-day compare quality."
        ),
    }

    preview = format_telegram(jev_top, payload["generated_at"], thin=len(jev_top) < 3)
    # Tag preview so nobody confuses with production dose
    preview = (
        "🧪 Jev shadow brief (NOT published · NOT a trade signal)\n"
        + preview.replace("Not a trade signal · RSS rank + editorial v4",
                          "Not a trade signal · Jev shadow rank v1")
    )
    compare_md = render_compare_md(payload)

    cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cfg.compare_path.write_text(compare_md, encoding="utf-8")
    cfg.preview_path.write_text(preview, encoding="utf-8")

    return payload
