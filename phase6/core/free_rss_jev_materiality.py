"""Free/RSS Jev materiality shadow — reweight aux text before scoring.

Measure-only. Does NOT write live sentiment_cache.json.
Does NOT change tryout floors, aging, or X primary.

Flow:
  RSS headlines (same feeds as free path)
    → pair-tag + TextBlob polarity + recency weight (baseline)
    → Jev judges unique titles (material / noise / priced / durable)
    → pair score = Σ polarity × recency × jev_weight / Σ weights
    → optional free hybrid merge (RSS_jev + funding + F&G) → shadow cache
    → compare board vs raw free / raw RSS / X

Reliability target: less junk polarity in aux eng — not “as good as X.”
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.adapters.judgment_jev import OpenRouterJevAdapter, mock_from_fixture
from phase6.core.paths import (
    FREE_JEV_BUDGET,
    FREE_JEV_COMPARE,
    FREE_JEV_CRUMBS,
    FREE_JEV_LATEST,
    FREE_JEV_RSS_CACHE,
    FREE_JEV_SENTIMENT_CACHE,
    FREE_SENTIMENT_CACHE,
    FNG_CACHE,
    FUNDING_SENTIMENT_CACHE,
    PHASE6_LIVE_STATE,
    PROJECT_ROOT,
    RSS_SENTIMENT_CACHE,
    SENTIMENT_CACHE,
    X_SENTIMENT_CACHE,
    load_trading_basket,
)
from phase6.domain.ports.judgment import JudgmentPort, JudgmentResult

METHOD = "free_rss_jev_materiality_v1_shadow"
SCHEMA_VERSION = 1

# Same hybrid weights as refresh_sentiment_free.py
PAIR_BETA = {
    "BTC-USD": 1.0,
    "ETH-USD": 1.0,
    "SOL-USD": 0.7,
    "XRP-USD": 0.7,
    "DOGE-USD": 0.5,
    "ADA-USD": 0.5,
    "AVAX-USD": 0.5,
    "LINK-USD": 0.6,
    "UNI-USD": 0.5,
    "ARB-USD": 0.4,
    "OP-USD": 0.4,
}

# Import RSS helpers from production free path (no second firehose)
import fetch_rss_sentiment as rss_mod  # noqa: E402


def materiality_questions() -> Dict[str, Any]:
    """Sentiment-aux quality — not trade entry, not coffee brief."""
    return {
        "material_to_book": {
            "type": "noul",
            "instructions": (
                "Is this headline material to liquid CEX crypto (BTC/ETH/majors/alts book), "
                "not peripheral meme-only noise? Prefer ETF/flow, regulation, hacks, listings, "
                "protocol events over vague roundups."
            ),
            "criteria": {
                "true": "Likely matters to liquid majors / basket risk or flows",
                "false": "Peripheral, meme-only, or not book-relevant",
            },
        },
        "noise_or_shill": {
            "type": "noul",
            "instructions": (
                "Is this noise, shill, recycled roundup, scam-alert theater, or engagement bait "
                "with little new fact for traders?"
            ),
            "criteria": {
                "true": "Mostly noise, shill, roundup, scam bait, or filler",
                "false": "Substantive reporting or primary event",
            },
        },
        "already_priced": {
            "type": "noul",
            "instructions": (
                "Does this look already fully digested (stale macro rehash, pure price-level "
                "watching, old narrative with no new catalyst)?"
            ),
            "criteria": {
                "true": "Already priced / stale / pure tape-watching",
                "false": "Still fresh or newly material",
            },
        },
        "durable_vs_spike": {
            "type": "noul",
            "instructions": (
                "If this moves sentiment, is it more durable narrative/flow than a one-hour "
                "spike or clickbait pump?"
            ),
            "criteria": {
                "true": "Durable narrative or structural flow",
                "false": "Spike, hype candle, or short-lived bait",
            },
        },
    }


def _noul(result: JudgmentResult, name: str, default: float = 0.0) -> float:
    a = result.answers.get(name)
    if a is None or a.noul is None:
        return default
    return max(0.0, min(1.0, float(a.noul)))


def jev_weight_from_result(result: JudgmentResult) -> Dict[str, Any]:
    """Map judgment → multiplicative weight on polarity observation.

    weight ≈ material × (1 - noise) × (1 - 0.5*priced) × (0.55 + 0.45*durable)
    Unjudged / failed → neutral 1.0 (do not invent).
    """
    if not result.ok:
        return {
            "jev_weight": 1.0,
            "material_to_book": None,
            "noise_or_shill": None,
            "already_priced": None,
            "durable_vs_spike": None,
            "ok": False,
            "error": result.error or "not_ok",
            "latency_ms": int(result.latency_ms or 0),
            "model": result.model,
        }
    material = _noul(result, "material_to_book", 0.5)
    noise = _noul(result, "noise_or_shill", 0.5)
    priced = _noul(result, "already_priced", 0.5)
    durable = _noul(result, "durable_vs_spike", 0.5)
    w = (
        max(0.05, material)
        * max(0.05, 1.0 - noise)
        * max(0.25, 1.0 - 0.5 * priced)
        * (0.55 + 0.45 * durable)
    )
    w = max(0.05, min(1.5, w))
    confs = []
    for name in materiality_questions():
        a = result.answers.get(name)
        if a and a.confidence is not None:
            confs.append(float(a.confidence))
    conf = sum(confs) / len(confs) if confs else None
    return {
        "jev_weight": round(w, 4),
        "material_to_book": round(material, 4),
        "noise_or_shill": round(noise, 4),
        "already_priced": round(priced, 4),
        "durable_vs_spike": round(durable, 4),
        "confidence_mean": round(conf, 4) if conf is not None else None,
        "ok": True,
        "error": "",
        "latency_ms": int(result.latency_ms or 0),
        "model": result.model,
    }


def headline_state(title: str, text: str, pairs: Sequence[str]) -> Dict[str, Any]:
    return {
        "task": "free_rss_materiality_filter",
        "not_a_trade_signal": True,
        "not_live_sentiment_primary": True,
        "title": title[:240],
        "summary": (text or "")[:280],
        "pair_hits": list(pairs)[:12],
    }


@dataclass
class FreeJevConfig:
    max_judge: int = 24
    max_calls_per_day: int = 96  # ~4/run × 24 if 2h cron
    dry_run: bool = False
    skip_rss_fetch: bool = False  # reuse last in-memory path only via injected hits
    model: str = "~typesafe/jev-latest"
    write_crumbs: bool = True
    merge_free_hybrid: bool = True
    budget_path: Path = field(default_factory=lambda: FREE_JEV_BUDGET)
    crumbs_path: Path = field(default_factory=lambda: FREE_JEV_CRUMBS)
    latest_path: Path = field(default_factory=lambda: FREE_JEV_LATEST)
    compare_path: Path = field(default_factory=lambda: FREE_JEV_COMPARE)
    rss_jev_path: Path = field(default_factory=lambda: FREE_JEV_RSS_CACHE)
    free_jev_path: Path = field(default_factory=lambda: FREE_JEV_SENTIMENT_CACHE)


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
        return {"day": d["day"], "calls": int(d.get("calls") or 0)}
    except Exception:
        return {"day": _day_key(), "calls": 0}


def save_budget(path: Path, budget: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(budget, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pair_score_from_cache(data: Dict[str, Any], pair: str) -> Optional[float]:
    if not data:
        return None
    # free hybrid shape
    sent = data.get("sentiment")
    if isinstance(sent, dict) and pair in sent:
        e = sent[pair]
        if isinstance(e, dict):
            v = e.get("sentiment_score", e.get("sentiment"))
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    e = data.get(pair)
    if isinstance(e, dict):
        v = e.get("sentiment_score", e.get("sentiment"))
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    return None


@dataclass
class HeadlineObs:
    title: str
    text: str
    published: Optional[datetime]
    polarity: float
    recency_w: float
    pairs: List[str]
    uid: str


def collect_headline_obs(
    *,
    basket: Sequence[str],
    now: Optional[datetime] = None,
) -> Tuple[List[HeadlineObs], Dict[str, Any]]:
    """Fetch RSS and build pair-tagged polarity observations (baseline path)."""
    now = now or datetime.now(timezone.utc)
    kws = rss_mod.load_keywords()
    headlines: List[Tuple[str, str, Optional[datetime]]] = []
    feed_stats: List[Dict[str, Any]] = []
    for url in rss_mod.FEEDS:
        got = rss_mod.fetch_feed(url)
        feed_stats.append({"url": url, "n": len(got)})
        headlines.extend(got)

    # title-key → obs
    by_title: Dict[str, HeadlineObs] = {}
    dropped_old = 0
    for title, text, pub in headlines:
        w = rss_mod.recency_weight(pub, now)
        if w <= 0:
            dropped_old += 1
            continue
        pol = rss_mod.polarity(text)
        if abs(pol) < 1e-9:
            continue
        low = text.lower()
        hit_pairs: List[str] = []
        for pair in basket:
            terms = kws.get(pair) or [pair.split("-")[0]]
            for t in terms:
                if re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", low):
                    hit_pairs.append(pair)
                    break
        if not hit_pairs:
            continue
        key = (title or text[:80]).strip().lower()
        if not key:
            continue
        if key in by_title:
            # merge pairs
            existing = by_title[key]
            for p in hit_pairs:
                if p not in existing.pairs:
                    existing.pairs.append(p)
            # keep stronger |pol| * w
            if abs(pol) * w > abs(existing.polarity) * existing.recency_w:
                existing.polarity = pol
                existing.recency_w = w
                existing.published = pub
                existing.text = text
        else:
            by_title[key] = HeadlineObs(
                title=title or text[:120],
                text=text,
                published=pub,
                polarity=float(pol),
                recency_w=float(w),
                pairs=sorted(set(hit_pairs)),
                uid=key[:160],
            )

    meta = {
        "feeds": list(rss_mod.FEEDS),
        "feed_stats": feed_stats,
        "headlines_raw": len(headlines),
        "dropped_old": dropped_old,
        "unique_pair_tagged": len(by_title),
        "half_life_hours": rss_mod.HALF_LIFE_HOURS,
    }
    return list(by_title.values()), meta


def select_for_judge(obs: Sequence[HeadlineObs], max_judge: int) -> List[HeadlineObs]:
    """Prefer high |pol|×recency and multi-pair hits; stable title order secondary."""
    ranked = sorted(
        obs,
        key=lambda o: (
            abs(o.polarity) * o.recency_w * (1.0 + 0.15 * len(o.pairs)),
            len(o.pairs),
            o.title,
        ),
        reverse=True,
    )
    return list(ranked[: max(0, int(max_judge))])


def score_pairs_from_obs(
    obs: Sequence[HeadlineObs],
    weights: Dict[str, float],
    *,
    basket: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """weights keyed by obs.uid; missing → 1.0 (neutral)."""
    pair_obs: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    pair_hits: Dict[str, int] = defaultdict(int)
    pair_judged: Dict[str, int] = defaultdict(int)

    for o in obs:
        jw = float(weights.get(o.uid, 1.0))
        tw = o.recency_w * jw
        if tw <= 0:
            continue
        for pair in o.pairs:
            pair_obs[pair].append((o.polarity, tw))
            pair_hits[pair] += 1
            if o.uid in weights:
                pair_judged[pair] += 1

    out: Dict[str, Dict[str, Any]] = {}
    for pair in basket:
        rows = pair_obs.get(pair) or []
        hits = pair_hits.get(pair) or 0
        if hits < rss_mod.MIN_HITS or not rows:
            out[pair] = {
                "sentiment": 0.0,
                "post_count": 0,
                "confidence": 0.0,
                "weight_sum": 0.0,
                "judged_hits": 0,
                "source": "rss_jev",
            }
            continue
        wsum = sum(w for _, w in rows)
        if wsum < 1e-12:
            sent = 0.0
            conf = 0.0
        else:
            sent = sum(p * w for p, w in rows) / wsum
            conf = min(1.0, (hits / 8.0) * 0.5 + min(1.0, wsum / 3.0) * 0.5)
            sent = sent * (0.35 + 0.65 * conf)
            sent = max(-1.0, min(1.0, sent))
        out[pair] = {
            "sentiment": round(float(sent), 4),
            "post_count": hits,
            "confidence": round(float(conf if hits else 0.0), 4),
            "weight_sum": round(float(wsum), 4),
            "judged_hits": int(pair_judged.get(pair) or 0),
            "source": "rss_jev",
            "half_life_hours": rss_mod.HALF_LIFE_HOURS,
        }
    return out


def merge_free_hybrid_jev(
    rss_jev: Dict[str, Dict[str, Any]],
    *,
    basket: Sequence[str],
    funding: Dict[str, Any],
    fng: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Same rules as refresh_sentiment_free, text leg = RSS_jev."""
    fg_damped = float(fng.get("score_damped") or 0.0)

    def _fund(pair: str) -> float:
        e = funding.get(pair)
        if isinstance(e, dict):
            try:
                return float(e.get("sentiment", e.get("sentiment_score", 0.0)) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    sentiment: Dict[str, Dict[str, Any]] = {}
    for pair in basket:
        a = float((rss_jev.get(pair) or {}).get("sentiment") or 0.0)
        b = _fund(pair)
        components = {
            "text_jev": round(a, 4),
            "funding": round(b, 4),
            "fng_damped": round(fg_damped, 4),
        }
        if abs(a) > 1e-6 and abs(b) > 1e-6:
            score = 0.65 * a + 0.35 * b
            src = "hybrid_rss_jev_funding"
            conf = 0.7
            tier = "A"
        elif abs(a) > 1e-6:
            score = a
            src = "rss_jev"
            conf = 0.45
            tier = "A"
        elif abs(b) > 1e-6:
            score = 0.8 * b
            src = "funding"
            conf = 0.5
            tier = "B"
        else:
            beta = PAIR_BETA.get(pair, 0.4)
            score = fg_damped * beta
            src = "fng" if abs(score) > 1e-6 else "none"
            conf = 0.2 if abs(score) > 1e-6 else 0.0
            tier = "C" if src == "fng" else "Z"
        score = max(-1.0, min(1.0, float(score)))
        sentiment[pair] = {
            "sentiment_score": round(score, 4),
            "source": src,
            "confidence": round(conf, 4),
            "components": components,
            "tier": tier,
            "rss_jev_post_count": int((rss_jev.get(pair) or {}).get("post_count") or 0),
            "rss_jev_judged_hits": int((rss_jev.get(pair) or {}).get("judged_hits") or 0),
        }
    return sentiment


def build_compare(
    *,
    basket: Sequence[str],
    free_jev: Dict[str, Dict[str, Any]],
    rss_jev: Dict[str, Dict[str, Any]],
    judged: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> str:
    free_raw = _load_json(FREE_SENTIMENT_CACHE)
    rss_raw = _load_json(RSS_SENTIMENT_CACHE)
    x_cache = _load_json(X_SENTIMENT_CACHE)
    live = _load_json(SENTIMENT_CACHE)

    lines = [
        f"# Free/RSS Jev materiality compare",
        f"",
        f"- method: `{METHOD}`",
        f"- ts: {meta.get('timestamp')}",
        f"- judged: {meta.get('n_judged')} · ok: {meta.get('n_ok')} · errors: {meta.get('n_err')}",
        f"- budget_day_calls: {meta.get('budget_calls')}/{meta.get('max_calls_per_day')}",
        f"- **SHADOW only** — not live floors, not X replace",
        f"",
        f"## Pair scores (free_jev vs free raw vs RSS raw vs X)",
        f"",
        f"| pair | free_jev | free_raw | rss_jev | rss_raw | X/live | Δ free |",
        f"|------|----------|----------|---------|---------|--------|--------|",
    ]
    for pair in basket:
        fj = free_jev.get(pair) or {}
        v_fj = fj.get("sentiment_score")
        v_fr = _pair_score_from_cache(free_raw, pair)
        v_rj = (rss_jev.get(pair) or {}).get("sentiment")
        v_rr = _pair_score_from_cache(rss_raw, pair)
        v_x = _pair_score_from_cache(x_cache, pair)
        if v_x is None:
            v_x = _pair_score_from_cache(live, pair)
        try:
            dlt = (float(v_fj) - float(v_fr)) if v_fj is not None and v_fr is not None else None
        except (TypeError, ValueError):
            dlt = None

        def fmt(x: Any) -> str:
            if x is None:
                return "—"
            try:
                return f"{float(x):+.3f}"
            except (TypeError, ValueError):
                return "—"

        lines.append(
            f"| {pair} | {fmt(v_fj)} | {fmt(v_fr)} | {fmt(v_rj)} | {fmt(v_rr)} | {fmt(v_x)} | {fmt(dlt)} |"
        )

    # sign agreement free_jev vs X
    agree = disagree = 0
    for pair in basket:
        a = (free_jev.get(pair) or {}).get("sentiment_score")
        b = _pair_score_from_cache(x_cache, pair)
        if b is None:
            b = _pair_score_from_cache(live, pair)
        if a is None or b is None:
            continue
        if abs(float(a)) < 0.02 and abs(float(b)) < 0.02:
            continue
        if (float(a) >= 0) == (float(b) >= 0):
            agree += 1
        else:
            disagree += 1
    lines += [
        f"",
        f"## Sign agreement free_jev vs X ( |s|≥0.02 )",
        f"- agree: **{agree}** · disagree: **{disagree}**",
        f"- N small → no promote claim",
        f"",
        f"## Judged headlines (weight low = downranked noise)",
        f"",
    ]
    for j in sorted(judged, key=lambda x: float(x.get("jev_weight") or 1.0)):
        lines.append(
            f"- w={j.get('jev_weight')} mat={j.get('material_to_book')} noise={j.get('noise_or_shill')} "
            f"priced={j.get('already_priced')} dur={j.get('durable_vs_spike')} · "
            f"{(j.get('title') or '')[:100]}"
        )
    lines.append("")
    return "\n".join(lines)


def run_free_rss_jev(
    *,
    port: Optional[JudgmentPort] = None,
    cfg: Optional[FreeJevConfig] = None,
    obs_override: Optional[List[HeadlineObs]] = None,
) -> Dict[str, Any]:
    cfg = cfg or FreeJevConfig()
    now = datetime.now(timezone.utc)
    basket = load_trading_basket()
    budget = load_budget(cfg.budget_path)
    remaining = max(0, int(cfg.max_calls_per_day) - int(budget.get("calls") or 0))

    if obs_override is not None:
        obs = list(obs_override)
        fetch_meta: Dict[str, Any] = {"mode": "override", "unique_pair_tagged": len(obs)}
    else:
        obs, fetch_meta = collect_headline_obs(basket=basket, now=now)

    to_judge = select_for_judge(obs, min(int(cfg.max_judge), remaining if not cfg.dry_run else int(cfg.max_judge)))
    if port is None:
        if cfg.dry_run:

            class _MockPort:
                def decide(self, state, questions, **kwargs):  # type: ignore[no-untyped-def]
                    return mock_from_fixture(
                        {
                            "material_to_book": {"type": "noul", "noul": 0.55},
                            "noise_or_shill": {"type": "noul", "noul": 0.35},
                            "already_priced": {"type": "noul", "noul": 0.40},
                            "durable_vs_spike": {"type": "noul", "noul": 0.50},
                        }
                    )

            port = _MockPort()  # type: ignore[assignment]
        else:
            port = OpenRouterJevAdapter(model=cfg.model, title="phase6-free-rss-jev")

    weights: Dict[str, float] = {}
    judged_rows: List[Dict[str, Any]] = []
    n_ok = n_err = 0
    questions = materiality_questions()

    for o in to_judge:
        if not cfg.dry_run and remaining <= 0:
            break
        t0 = time.time()
        result = port.decide(state=headline_state(o.title, o.text, o.pairs), questions=questions)
        if result.latency_ms is None:
            result.latency_ms = int((time.time() - t0) * 1000)
        jw = jev_weight_from_result(result)
        weights[o.uid] = float(jw["jev_weight"])
        row = {
            "uid": o.uid,
            "title": o.title[:200],
            "pairs": list(o.pairs),
            "polarity": round(o.polarity, 4),
            "recency_w": round(o.recency_w, 4),
            **jw,
        }
        judged_rows.append(row)
        if jw.get("ok"):
            n_ok += 1
        else:
            n_err += 1
        if not cfg.dry_run:
            budget["calls"] = int(budget.get("calls") or 0) + 1
            remaining = max(0, int(cfg.max_calls_per_day) - int(budget["calls"]))
            if cfg.write_crumbs:
                cfg.crumbs_path.parent.mkdir(parents=True, exist_ok=True)
                with cfg.crumbs_path.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "ts": now.isoformat(),
                                "method": METHOD,
                                **row,
                            },
                            default=str,
                        )
                        + "\n"
                    )

    if not cfg.dry_run:
        save_budget(cfg.budget_path, budget)

    rss_jev = score_pairs_from_obs(obs, weights, basket=basket)
    funding = _load_json(FUNDING_SENTIMENT_CACHE)
    fng = _load_json(FNG_CACHE)
    if cfg.merge_free_hybrid:
        free_jev = merge_free_hybrid_jev(rss_jev, basket=basket, funding=funding, fng=fng)
    else:
        free_jev = {
            p: {
                "sentiment_score": (rss_jev.get(p) or {}).get("sentiment", 0.0),
                "source": "rss_jev",
                "confidence": (rss_jev.get(p) or {}).get("confidence", 0.0),
                "tier": "A",
            }
            for p in basket
        }

    meta = {
        "timestamp": now.isoformat(),
        "method": METHOD,
        "schema_version": SCHEMA_VERSION,
        "live_primary": False,
        "would_write_live_sentiment": False,
        "n_obs": len(obs),
        "n_judged": len(judged_rows),
        "n_ok": n_ok,
        "n_err": n_err,
        "budget_calls": int(budget.get("calls") or 0),
        "max_calls_per_day": cfg.max_calls_per_day,
        "dry_run": cfg.dry_run,
        "fetch": fetch_meta,
        "note": "SHADOW only — runner still uses sentiment_cache.json / X path",
    }

    rss_payload = {
        "timestamp": now.isoformat(),
        "schema_version": 2,
        "meta": {
            **fetch_meta,
            "method": "textblob_recency_jev_weighted",
            "jev_method": METHOD,
            "n_judged": len(judged_rows),
        },
        **rss_jev,
    }
    free_payload = {
        "timestamp": now.isoformat(),
        "schema_version": 3,
        "sentiment": free_jev,
        "meta": meta,
    }
    latest = {
        "meta": meta,
        "judged": judged_rows,
        "rss_jev_pairs": rss_jev,
        "free_jev_pairs": free_jev,
    }

    if not cfg.dry_run or obs_override is not None:
        # isolation may dry_run with override and still want paths injectable — write if paths set
        pass

    # Always write artifacts unless pure unit path with dry_run and no override writes
    write_art = not cfg.dry_run or obs_override is not None
    # For dry_run mock without override, still allow caller to skip disk via dry_run only
    if not cfg.dry_run:
        cfg.rss_jev_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.rss_jev_path.write_text(json.dumps(rss_payload, indent=2), encoding="utf-8")
        cfg.free_jev_path.write_text(json.dumps(free_payload, indent=2), encoding="utf-8")
        cfg.latest_path.write_text(json.dumps(latest, indent=2), encoding="utf-8")
        compare_md = build_compare(
            basket=basket,
            free_jev=free_jev,
            rss_jev=rss_jev,
            judged=judged_rows,
            meta=meta,
        )
        cfg.compare_path.write_text(compare_md, encoding="utf-8")
        latest["compare_path"] = str(cfg.compare_path)
    else:
        compare_md = build_compare(
            basket=basket,
            free_jev=free_jev,
            rss_jev=rss_jev,
            judged=judged_rows,
            meta=meta,
        )

    return {
        "ok": n_err == 0 or n_ok > 0,
        "meta": meta,
        "rss_jev": rss_jev,
        "free_jev": free_jev,
        "judged": judged_rows,
        "compare_md": compare_md,
        "budget": budget,
    }


def telegram_summary(result: Dict[str, Any]) -> str:
    m = result.get("meta") or {}
    return (
        f"free_rss_jev shadow · judged {m.get('n_judged')} ok {m.get('n_ok')} err {m.get('n_err')} · "
        f"budget {m.get('budget_calls')}/{m.get('max_calls_per_day')} · not live"
    )
