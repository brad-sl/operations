#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py
"""
Phase 6 Daily Trading Intelligence Briefing — Crypto Analyst

This script produces the canonical daily briefing delivered via cron/Telegram.

Telegram structure (decision_brief_v1 — Brad 2026-08-25):
- BOTTOM LINE (go/no-go plain English)
- Do now / Book / Stance / Wounds / What's next
- Needs your call (only if new proposals)
Side effects still: backlog JSON, MASTER append, intel_strategic_brief.json, weekly assessment

Proposals:
- Get unique IDs (ANALYST-YYYYMMDD-NNN) that flow from generation through backlog, acceptance, Kanban, and deployment.
- No duplication: IDs and content are deduplicated on every run.
- Automatically ingested into MASTER_TASK_TRACKING.md under Analyst Proposed Backlog (only new IDs).
- Also persisted to data/state/analyst_proposed_backlog.json for clean tracking.

Run by the twice-daily cron. Real data only.
"""

import json
import re
import hashlib
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

# Canonical bootstrap per DATA_FLOW_AND_LOCATIONS.md + paths.py
# This eliminates fragile manual resolution and hardcodes that cause
# "No module named phase6.core" or script-not-found in Hermes no_agent crons.
# Permanent for rebalance notifications stability (t_12d58fd1).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from phase6.core.paths import PROJECT_ROOT as PATHS_PROJECT_ROOT, get_project_root, load_project_dotenv

load_project_dotenv()

# Robust root resolution for both project runs and Hermes no_agent cron copies
# (the latter executes the copy at ~/.hermes/... while workdir may be project root or /home)
# Prefer canonical project; verify by presence of key module file so stale /home/phase6 does not win.
CANONICAL_ROOT = PATHS_PROJECT_ROOT

def _resolve_project_root() -> Path:
    candidates = [CANONICAL_ROOT, Path.cwd().resolve()]
    # Walk up from __file__ (works for copies in ~/.hermes/scripts/...)
    try:
        here = Path(__file__).resolve()
        for _ in range(6):
            if (here / "phase6" / "core" / "sentiment_scorer.py").exists():
                if here not in candidates:
                    candidates.append(here)
                break
            if here.parent == here:
                break
            here = here.parent
    except Exception:
        pass

    for p in candidates:
        if (p / "phase6" / "core" / "sentiment_scorer.py").exists():
            return p
    return CANONICAL_ROOT

PROJECT_ROOT = _resolve_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

# also keep original relative for source-tree runs (non-harmful)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
except Exception:
    pass

from phase6.core.sentiment_scorer import load_latest_sentiment_for_basket, DEFAULT_UNIVERSE
from phase6.core.signal_generator import SignalGenerator
from phase6.core.sl_risk_scorer import get_all_sl_risks

import importlib.util


def _load_polymarket():
    try:
        # Robust resolution for project runs, Hermes script copies under ~/.hermes,
        # and different cwds. Absolute project path is canonical fallback.
        candidates = [
            PROJECT_ROOT / "hermes/skills/crypto_analyst/polymarket_overlay.py",
            (Path(__file__).parent.parent.parent / "hermes/skills/crypto_analyst/polymarket_overlay.py"
             if "__file__" in globals() else Path.cwd() / "hermes/skills/crypto_analyst/polymarket_overlay.py"),
            Path.home() / ".hermes/skills/crypto_analyst/polymarket_overlay.py",
            (PROJECT_ROOT / "hermes/skills/crypto_analyst/polymarket_overlay.py"),
            (PROJECT_ROOT / "hermes/skills/crypto_analyst/polymarket_overlay.py"),
        ]
        skill_path = None
        for p in candidates:
            if p.exists():
                skill_path = p
                break
        if skill_path is None:
            raise FileNotFoundError("polymarket_overlay.py not found in candidates")
        spec = importlib.util.spec_from_file_location(
            "polymarket_overlay", str(skill_path)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Use the analyst-recommended optimal regime config by default (ANALYST-20260627-023)
        optimal_config = {
            "bullish_threshold": 0.05,
            "bearish_threshold": -0.25,
            "min_vol": 5000,
            "clamp_min": 0.15,
            "clamp_max": 0.85,
        }
        return mod.get_polymarket_regime_bias(config=optimal_config)
    except Exception as e:
        return {"risk_on_bias": 0.5, "source": "polymarket (error)", "events": [], "note": str(e)}


poly = _load_polymarket()

ANALYST_PERSONA = """You are the Crypto Analyst. Wry, direct, allergic to hype. 
Honest assessments are mandatory. Occasional dry humor when it actually helps the point.
Focus on what the live allocator, platform executor, and SL layer are actually doing.
When assessing SL risk or reversal potential, explicitly use both plain RSI **and** StochRSI (%K) from the longer-term (100-point) cache. Low Stoch %K (especially <20-30) indicates oversold extremes in the recent window and should drive higher reversal risk / tighter adaptive SLs."""

LEARNINGS_PATH = PROJECT_ROOT / "data/state/analyst_learnings.json"
CONFIG_PATH = PROJECT_ROOT / "config/trading_config_phase6.json"
STATE_PATH = PROJECT_ROOT / "data/state/phase6_runner_state.json"
RSI_CACHE_PATH = PROJECT_ROOT / "data/state/rsi_cache.json"
PROPOSALS_JSON = PROJECT_ROOT / "data/state/analyst_strategic_proposals.json"
PROPOSED_BACKLOG = PROJECT_ROOT / "data/state/analyst_proposed_backlog.json"


def load_learnings():
    try:
        with open(LEARNINGS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"learnings": [], "heuristics": {}}


def save_learnings(data):
    with open(LEARNINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_basket():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        pairs = cfg.get("global_settings", {}).get("pairs", [])
        if not pairs:
            pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool", DEFAULT_UNIVERSE)
        return pairs[:11]
    except Exception:
        return DEFAULT_UNIVERSE[:11]


def load_runner_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"last_rebalance_date": "unknown", "last_updated": "unknown"}


def load_rsi_cache():
    try:
        with open(RSI_CACHE_PATH) as f:
            return json.load(f).get("rsi", {})
    except Exception:
        return {}


def get_analyst_voice():
    return ANALYST_PERSONA


def add_evolution_note(learnings, new_note):
    """Append a new evolution note from this cycle."""
    learnings["learnings"].append({
        "cycle": datetime.utcnow().strftime("%Y-%m-%d"),
        "thesis": new_note.get("thesis", ""),
        "outcome": new_note.get("outcome", ""),
        "evolution_note": new_note.get("evolution_note", ""),
        "date": datetime.utcnow().isoformat()
    })
    learnings["learnings"] = learnings["learnings"][-20:]
    save_learnings(learnings)
    return learnings


def _today_id_prefix() -> str:
    return date.today().strftime("%Y%m%d")


def generate_proposal_id(seq: int) -> str:
    """Unique ID that flows through the entire lifecycle: proposal → backlog → Kanban → deployment."""
    return f"ANALYST-{_today_id_prefix()}-{seq:03d}"


def normalize_proposal_title(title: str) -> str:
    """Stable title key for cross-run dedup (ENG-S7-01)."""
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def proposal_semantic_hash(title: str, category: str = "") -> str:
    """Short hash for logging / MASTER cross-check."""
    payload = f"{normalize_proposal_title(category)}|{normalize_proposal_title(title)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def collect_known_proposal_titles(*, include_strategic_json: bool = True) -> set:
    """Titles already proposed or deployed — do not mint new IDs for the same idea."""
    known = set()
    for p in load_existing_proposals():
        t = p.get("title")
        if t:
            known.add(normalize_proposal_title(t))
    try:
        backlog = load_proposed_backlog()
        for p in backlog.get("proposals", []):
            t = p.get("title")
            if t:
                known.add(normalize_proposal_title(t))
    except Exception:
        pass
    return known


def collect_deployed_proposal_titles() -> set:
    """Titles with accepted/deployed lifecycle — suppress from Decision Approval section."""
    deployed = set()
    try:
        backlog = load_proposed_backlog()
        for p in backlog.get("proposals", []):
            status = str(p.get("status") or "").lower()
            if p.get("deployed") or p.get("accepted") or status in ("accepted", "deployed", "done"):
                t = p.get("title")
                if t:
                    deployed.add(normalize_proposal_title(t))
    except Exception:
        pass
    return deployed


def load_existing_proposals():
    """Load previously generated proposals for deduplication."""
    try:
        data = json.loads(PROPOSALS_JSON.read_text())
        return data.get("proposals", [])
    except Exception:
        return []


def load_proposed_backlog():
    try:
        return json.loads(PROPOSED_BACKLOG.read_text())
    except Exception:
        return {"proposals": []}


def save_proposed_backlog(data):
    PROPOSED_BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSED_BACKLOG, "w") as f:
        json.dump(data, f, indent=2)


# Stable stems: if any known title contains the stem, treat as already proposed.
# Stops re-minting the same shipped heuristics with tiny wording drift.
_KNOWN_TITLE_STEMS = (
    "pre-flight settlement poll",
    "pre-rebalance data refresh",
    "polymarket regime bias into allocator",
    "analyst learnings + heuristics influence allocator",
    "strategic brief' artifact before each scheduled rebalance",
    "tighten scenario pack toward positive sharpe",
    "run regime quad scorecard before next shadow",
    "align ohlcv data window with production go-live",
)


def title_already_known(title: str, known_title_keys: set) -> bool:
    """True if exact key or a durable stem already lives in backlog/deployed history."""
    key = normalize_proposal_title(title)
    if not key:
        return True
    if key in known_title_keys:
        return True
    for known in known_title_keys:
        if key in known or known in key:
            return True
    for stem in _KNOWN_TITLE_STEMS:
        if stem in key and any(stem in k for k in known_title_keys):
            return True
    return False


def _offer_candidate(candidates: list, cand: dict, known_title_keys: set) -> bool:
    """Append only genuinely new titles. Returns True if offered."""
    title = cand.get("title") or ""
    if title_already_known(title, known_title_keys):
        return False
    candidates.append(cand)
    return True


def generate_strategic_proposals(
    sl_risks,
    coverage,
    total_pairs,
    poly,
    learnings,
    state,
    existing_ids,
    known_title_keys=None,
    opt_brief=None,
    leaderboard=None,
):
    """
    Derive strategic modification proposals.
    Assigns stable IDs.
    ENG-S7-01: never re-mint titles already in backlog/deployed (quiet skip, no spam).
    """
    known_title_keys = set(known_title_keys or set())
    candidates = []
    try:
        from phase6.research.analyst_narrative import optimization_proposal_candidates

        for c in optimization_proposal_candidates(opt_brief, leaderboard):
            _offer_candidate(candidates, c, known_title_keys)
    except Exception:
        pass

    heuristics = learnings.get("heuristics", {})
    known_weaknesses = heuristics.get("known_weaknesses", [])

    # Candidate 1: SL pre-flight (only if not already proposed/shipped)
    high_risk_count = sum(1 for r in sl_risks.values() if r.get("level") in ("HIGH", "CRITICAL"))
    if high_risk_count > 0 or any("preview" in str(w).lower() or "stop" in str(w).lower() for w in known_weaknesses):
        _offer_candidate(
            candidates,
            {
                "title": "Add pre-flight settlement poll + product-specific tick handling to SL layer",
                "description": "Before attaching stop-limit orders, poll for settled balance and apply per-product tick size / precision rules. Use the existing SL risk scorer to decide aggressiveness.",
                "benefits": "Reduce PREVIEW_INSUFFICIENT_FUND and PREVIEW_INVALID_STOP_PRICE_PRECISION failures by 60-80%. Faster and more reliable re-attachment after buys. Improves SL reliability on low-priced assets (SOL, ADA, etc.).",
                "risks": "Slight increase in rebalance latency (mitigation: 2-3s timeout + async). Risk of over-waiting on stable pairs (mitigation: skip poll for low-risk pairs). Coinbase-side rules may still apply in rare cases.",
                "priority": "High",
                "effort": "Medium",
                "category": "SL / Platform",
            },
            known_title_keys,
        )

    # Candidate 2: Regime-aware allocation — stable title (no direction suffix; stem-deduped)
    risk_on = poly.get("risk_on_bias", 0.5)
    if risk_on > 0.65 or risk_on < 0.35:
        direction = (
            "risk-on tilt (favor momentum pairs)"
            if risk_on > 0.65
            else "risk-off tilt (favor defensive / higher conviction)"
        )
        _offer_candidate(
            candidates,
            {
                "title": "Wire Polymarket regime bias into allocator as soft constraint",
                "description": (
                    f"Pass the current risk_on_bias from Polymarket as a multiplier or filter into "
                    f"RotationStrategy / rebalance_plan ({direction}). Bias allocation toward or away "
                    f"from higher-vol names accordingly."
                ),
                "benefits": "Better macro alignment. Capture more upside in risk-on regimes and reduce drawdown in risk-off. Uses live external signal that is already being fetched daily.",
                "risks": "Polymarket can be noisy or manipulated on low-liquidity markets (mitigation: smooth with 3-day average + minimum confidence threshold). Could increase churn (mitigation: combine with existing min_score_delta and cooldowns).",
                "priority": "Medium",
                "effort": "Medium",
                "category": "Allocator / Skills",
            },
            known_title_keys,
        )

    # Candidate 3: Data coverage
    if coverage < total_pairs - 1:
        _offer_candidate(
            candidates,
            {
                "title": "Strengthen pre-rebalance data refresh + fallback for partial coverage",
                "description": "Before running allocator, ensure all basket pairs have fresh RSI + sentiment. Add a short blocking refresh or use last-known with explicit 'stale' flag. Consider lightweight on-demand pull for missing pairs.",
                "benefits": "Higher signal quality for allocator decisions. Fewer 'MISSING' or 'RSI-ONLY' states. Reduces risk of deploying on incomplete information.",
                "risks": "Slight delay to rebalance window (mitigation: parallel refreshes + 10-15s hard cap). API rate limits (mitigation: respect existing backoff).",
                "priority": "Medium",
                "effort": "Low-Medium",
                "category": "Data / Runner",
            },
            known_title_keys,
        )

    # Candidate 4: Close the learnings loop
    allocator_active = heuristics.get("allocator_heuristics_active") or "apply_analyst_heuristics" in str(heuristics)
    if not allocator_active and (
        "paper_trade_validation" in str(heuristics)
        or not any("allocator" in str(h).lower() for h in heuristics.values())
    ):
        _offer_candidate(
            candidates,
            {
                "title": "Close the loop: make analyst learnings + heuristics influence allocator parameters",
                "description": "Load key heuristics (e.g. prefer_rotation_when) and recent evolution notes at allocator start. Apply as dynamic config overrides (e.g. adjust min_score_delta or rotation bias based on recent SL failure patterns).",
                "benefits": "System actually learns. Reduces repeated mistakes (e.g. post-buy SL timing). Turns the analyst from observer into active participant in decision quality.",
                "risks": "Over-fitting to recent noise (mitigation: weight recent learnings lightly + require confirmation across 2-3 cycles). Complexity creep (mitigation: start with 1-2 simple rules).",
                "priority": "High",
                "effort": "Medium",
                "category": "Allocator / Analyst Evolution",
            },
            known_title_keys,
        )

    # Fallback if too few (skip ideas already shipped or already in backlog)
    brief_path = PROJECT_ROOT / "data/state/intel_strategic_brief.json"
    if len(candidates) < 2 and not brief_path.exists():
        _offer_candidate(
            candidates,
            {
                "title": "Add lightweight 'strategic brief' artifact before each scheduled rebalance",
                "description": "Have the intelligence report produce a short JSON 'brief' (regime bias, high-SL-risk pairs, top proposals) that the runner can optionally load as context or constraints.",
                "benefits": "Pre-rebalance strategic context without heavy coupling. Makes daily briefings directly actionable for the allocator.",
                "risks": "Another artifact to maintain (mitigation: keep it tiny and optional).",
                "priority": "Medium",
                "effort": "Low",
                "category": "Runner / Analyst",
            },
            known_title_keys,
        )

    # In-run title uniqueness (defense in depth; known titles already filtered at offer time)
    seen = set()
    unique_cands = []
    for c in candidates:
        key = normalize_proposal_title(c.get("title"))
        if not key or key in seen or title_already_known(c.get("title"), known_title_keys):
            continue
        seen.add(key)
        unique_cands.append(c)
    candidates = unique_cands

    # Assign IDs
    proposals = []
    seq = 1
    for cand in candidates[:4]:
        pid = generate_proposal_id(seq)
        while pid in existing_ids:
            seq += 1
            pid = generate_proposal_id(seq)
        cand["id"] = pid
        proposals.append(cand)
        seq += 1

    return proposals

def generate_followup_validation(learnings, backlog, sl_risks, recent_proposals):
    """Only surface deployments still inside the 48h observation window."""
    now = datetime.now(timezone.utc)
    deployed = [p for p in backlog.get("proposals", []) if p.get("deployed") or p.get("accepted")]
    rows = []

    for p in sorted(deployed, key=lambda x: x.get("deployed", x.get("accepted", "")), reverse=True)[:8]:
        dep_str = p.get("deployed") or p.get("accepted", "")
        try:
            if "T" in dep_str:
                dep_time = datetime.fromisoformat(dep_str.replace("Z", "+00:00"))
            else:
                dep_time = datetime.strptime(dep_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            elapsed_h = (now - dep_time).total_seconds() / 3600
        except Exception:
            continue
        if elapsed_h >= 48:
            continue
        rows.append((p.get("id", "?"), p.get("title", "")[:60], elapsed_h))

    if not rows:
        return
    print("\n=== Watch list (48h post-deploy) ===")
    for pid, title, elapsed_h in rows:
        print(f"  {pid}: {title} — {elapsed_h:.0f}h (observe only)")


def feed_proposals_to_master_backlog(new_proposals):
    """Append only new proposals (by ID) to MASTER. No duplication."""
    if not new_proposals:
        return

    master_path = PROJECT_ROOT / "docs/MASTER_TASK_TRACKING.md"
    if not master_path.exists():
        return

    # Load existing IDs to avoid dupes
    try:
        existing_content = master_path.read_text()
    except Exception:
        existing_content = ""

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    added = []

    for p in new_proposals:
        pid = p.get("id")
        if pid and pid in existing_content:
            continue  # already ingested

        block = f"\n**{pid}** — {p['title']}\n"
        block += f"Status: Proposed — Awaiting Review/Acceptance\n"
        block += f"Description: {p['description']}\n"
        block += f"Benefits: {p['benefits']}\n"
        block += f"Risks + Mitigations: {p['risks']}\n"
        block += f"Priority: {p['priority']} | Effort: {p['effort']} | Category: {p['category']}\n"
        block += f"Source: Daily Intelligence Briefing {timestamp}\n\n"

        with open(master_path, "a") as f:
            f.write(block)

        added.append(pid)

    # Quiet: MASTER append is a side effect; TG body must stay decision-only
    return added


def _run_background_analyst_jobs(basket, sent_scores):
    """PM retrospective + influence stack ledger (no routine console noise)."""
    try:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT / "phase6/scripts"))
        from analyze_pm_tilt_retrospective import run_pm_tilt_analysis

        analysis = run_pm_tilt_analysis(window_hours=6)
        (PROJECT_ROOT / "data/state/pm_tilt_retrospective_analysis.json").write_text(
            json.dumps(analysis, indent=2)
        )
        # Event artifact on disk only — do not print to Telegram stdout
        _ = analysis.get("tiebreaker_activations", 0)
    except Exception:
        pass

    try:
        import sys

        from phase6.core.trade_ledger import TradeLedger
        from phase6.core.sentiment_scorer import _load_reddit_from_db, get_aged_sentiment_scores

        sys.path.insert(0, str(Path.home() / ".hermes/skills"))
        from crypto_analyst.polymarket_overlay import get_polymarket_regime_bias, get_polymarket_influence

        ledger = TradeLedger(base_dir=PROJECT_ROOT)
        aged = get_aged_sentiment_scores(
            half_life_minutes=60, raw_scores=sent_scores, universe=basket
        )
        pm_poly = get_polymarket_regime_bias()
        inf = get_polymarket_influence(pm_poly)
        reddit_sent = _load_reddit_from_db(basket)
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "polymarket": pm_poly,
            "influence": inf,
            "x_sentiment": {k: round(v, 4) for k, v in (sent_scores or {}).items()},
            "reddit_sentiment": {k: round(v, 4) for k, v in (reddit_sent or {}).items()},
            "aged_sentiment": {k: round(v, 4) for k, v in (aged or {}).items()},
        }
        ledger.log_influence_stack(snapshot)
    except Exception:
        pass


def main():
    """
    Telegram body = decision-first plain English (see decision_brief.py).
    Ops/JSON artifacts still built for runner + MASTER; not dumped raw to TG.
    """
    from phase6.core.sentiment_scorer import load_sentiment_scores
    from phase6.core.basket_signal_coverage import assess_pair_signal_coverage
    from phase6.research.decision_brief import format_decision_brief

    basket = load_basket()
    sent_scores = load_sentiment_scores(universe=basket)
    latest = load_latest_sentiment_for_basket(basket=basket, sentiment_scores=sent_scores)
    state = load_runner_state()
    learnings = load_learnings()
    sg = SignalGenerator()
    sl_risks = get_all_sl_risks(basket, {})

    cov = assess_pair_signal_coverage(basket=basket, sentiment_scores=sent_scores)
    full_count = int(cov.get("full_count", 0))

    # Structured signals for decision brief (BUY/SELL only drive "Do now")
    signal_rows = []
    for pair in basket:
        rsi_val = latest.get("rsi", {}).get(pair)
        sent_val = latest.get("sentiment", {}).get(pair, 0.0)
        signal = sg.generate_signal(pair, rsi_val or 50.0, sentiment=sent_val or 0.0)
        slr = sl_risks.get(pair, {"level": "unknown"})
        signal_rows.append(
            {
                "pair": pair,
                "signal": signal.signal,
                "reason": (signal.reason or "")[:72],
                "sl_level": slr.get("level"),
            }
        )

    same_session = None
    same_session_3d = None
    try:
        from phase6.core.same_session_sl import summarize as _ss_sl

        same_session = _ss_sl(persist=True)  # default ~30d health metric on disk
        same_session_3d = _ss_sl(persist=False, lookback_days=3.0)
    except Exception:
        pass

    # Background side effects (PM tilt file, influence stack) — quiet on TG
    _run_background_analyst_jobs(basket, sent_scores)

    lb = None
    opt_brief = None
    try:
        from phase6.research.optimization_brief import build_daily_opt_brief, load_leaderboard

        lb = load_leaderboard()
        _opt_text, opt_brief = build_daily_opt_brief(lb)
        # Keep verbose opt_text off Telegram (decision_brief uses opt_brief JSON)
        del _opt_text
    except Exception as e:
        opt_brief = {"deployment_hint": f"hold — wealth block skipped ({type(e).__name__})"}

    # Honest assessment still computed for weekly artifact / evolution — not printed
    try:
        from phase6.research.analyst_narrative import (
            format_honest_assessment,
            build_evolution_note,
            persist_weekly_assessment,
        )

        assessment_lines = format_honest_assessment(
            full_coverage_count=full_count,
            total_pairs=len(basket),
            sl_risks=sl_risks,
            opt_brief=opt_brief,
            leaderboard=lb,
        )
        new_evolution = build_evolution_note(
            full_coverage_count=full_count,
            total_pairs=len(basket),
            opt_brief=opt_brief,
            leaderboard=lb,
        )
        try:
            persist_weekly_assessment(assessment_lines, new_evolution, opt_brief)
        except Exception:
            pass
    except Exception:
        assessment_lines = []
        new_evolution = {
            "thesis": "Platform + allocator should deliver better-timed rotation.",
            "outcome": f"Allocator active. {full_count} FULL signals.",
            "evolution_note": "Keep gates; paper-trial OPT winners before live settings.",
        }
    learnings = add_evolution_note(learnings, new_evolution)

    # Prospects (persist + optional TG "Needs your call")
    existing_proposals = load_existing_proposals()
    existing_ids = {p.get("id") for p in existing_proposals if p.get("id")}
    known_title_keys = collect_known_proposal_titles()

    proposals = generate_strategic_proposals(
        sl_risks=sl_risks,
        coverage=full_count,
        total_pairs=len(basket),
        poly=poly,
        learnings=learnings,
        state=state,
        existing_ids=existing_ids,
        known_title_keys=known_title_keys,
        opt_brief=opt_brief,
        leaderboard=lb,
    )

    # Persist (deduped, quiet)
    try:
        all_proposals = existing_proposals + [p for p in proposals if p["id"] not in existing_ids]
        PROPOSALS_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(PROPOSALS_JSON, "w") as f:
            json.dump({"proposals": all_proposals[-50:]}, f, indent=2)
    except Exception:
        pass

    try:
        backlog = load_proposed_backlog()
        existing_backlog_ids = {p.get("id") for p in backlog.get("proposals", [])}
        new_for_backlog = [p for p in proposals if p["id"] not in existing_backlog_ids]
        for p in new_for_backlog:
            p["status"] = "proposed"
            p["generated"] = datetime.utcnow().isoformat()
        backlog["proposals"] = backlog.get("proposals", []) + new_for_backlog
        save_proposed_backlog(backlog)
    except Exception:
        pass

    try:
        feed_proposals_to_master_backlog(proposals)
    except Exception:
        pass

    try:
        BRIEF_CACHE = PROJECT_ROOT / "data/state/intel_strategic_brief.json"
        brief = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "risk_on_bias": round(float(poly.get("risk_on_bias", 0.5)), 3),
            "polymarket": {
                "risk_on_bias": round(float(poly.get("risk_on_bias", 0.5)), 3),
                "num_markets": int(poly.get("num_markets", 0)),
                "total_vol": float(poly.get("total_vol", 0)),
                "confidence": float(poly.get("confidence", 0.0)),
            },
            "coverage": {"full": int(full_count), "total": len(basket)},
            "high_sl_risk_pairs": [
                p
                for p, r in sl_risks.items()
                if str(r.get("level", "")).upper() in ("HIGH", "CRITICAL")
            ],
            "top_proposals": [
                {"id": p.get("id"), "title": p.get("title"), "priority": p.get("priority")}
                for p in proposals[:3]
            ],
            "last_rebalance": state.get("last_rebalance_date"),
            "optimization": opt_brief,
            "note": "Soft context for next rebalance.",
            "format": "decision_brief_v1",
        }
        BRIEF_CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(brief, open(BRIEF_CACHE, "w"), indent=2)
    except Exception:
        pass

    # 48h post-deploy watch stays off TG unless you want it later (still available via backlog tools)

    body = format_decision_brief(
        basket=basket,
        full_count=full_count,
        last_rebalance=str(state.get("last_rebalance_date") or "?"),
        poly=poly,
        sl_risks=sl_risks,
        signals=signal_rows,
        opt_brief=opt_brief,
        same_session=same_session,
        same_session_3d=same_session_3d,
        proposals=proposals,
        next_focus=str(new_evolution.get("evolution_note") or ""),
    )
    print(body)


if __name__ == "__main__":
    main()

# === Lightweight Report Cache (added 2026-06-24 for token reduction) ===
import hashlib, json, time
from datetime import datetime
from pathlib import Path

REPORT_CACHE = PROJECT_ROOT / "data/state/intel_report_cache.json"
BRIEF_CACHE = PROJECT_ROOT / "data/state/intel_strategic_brief.json"

def _report_cache_key(basket, poly, sl_risks, coverage):
    kd = {
        "d": datetime.utcnow().strftime("%Y-%m-%d"),
        "basket": sorted([str(p) for p in basket]),
        "poly": round(float(poly.get("risk_on_bias", 0.5)), 1),
        "hrisk": sum(1 for r in sl_risks.values() if str(r.get("level","")).upper() in ("HIGH", "CRITICAL")),
        "cov": int(coverage),
    }
    return hashlib.sha256(json.dumps(kd, sort_keys=True).encode()).hexdigest()[:12]

def load_fresh_report_cache(key):
    try:
        if REPORT_CACHE.exists():
            d = json.loads(REPORT_CACHE.read_text())
            if d.get("key") == key and (time.time() - d.get("ts", 0)) < 12*3600:
                return d
    except Exception:
        pass
    return None

def save_report_cache(key, full_text, meta=None):
    REPORT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "key": key,
        "ts": time.time(),
        "generated": datetime.utcnow().isoformat(),
        "text": (full_text or "")[:18000],
        "meta": meta or {}
    }, open(REPORT_CACHE, "w"), indent=2)

def build_and_save_brief(basket, poly, sl_risks, coverage, proposals, state):
    """Compact actionable brief for the runner (addresses ANALYST-20260624-006)."""
    brief = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "risk_on_bias": round(float(poly.get("risk_on_bias", 0.5)), 2),
        "coverage": {"full": int(coverage), "total": len(basket)},
        "high_sl_risk_pairs": [p for p, r in sl_risks.items() if str(r.get("level","")).upper() in ("HIGH", "CRITICAL")],
        "top_proposals": [{"id": p.get("id"), "title": p.get("title"), "priority": p.get("priority")} for p in proposals[:3]],
        "last_rebalance": state.get("last_rebalance_date"),
        "note": "Use as soft context for next rebalance. Regenerated on each intelligence cycle."
    }
    BRIEF_CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(brief, open(BRIEF_CACHE, "w"), indent=2)
    return brief
