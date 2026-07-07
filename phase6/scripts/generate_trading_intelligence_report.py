#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py
"""
Phase 6 Daily Trading Intelligence Briefing — Crypto Analyst

This script produces the canonical daily briefing delivered via cron/Telegram.

Structure (as designed):
- Header + Persona
- Current State (basket, per-pair signals, coverage, runner state, Polymarket)
- Honest Assessment (mandatory)
- Evolution Notes
- Strategic Modification Proposals (structured: ID, title, description, benefits, risks, priority/effort/category)
- Decision Approval Required (simple reply options at the bottom)

Proposals:
- Get unique IDs (ANALYST-YYYYMMDD-NNN) that flow from generation through backlog, acceptance, Kanban, and deployment.
- No duplication: IDs and content are deduplicated on every run.
- Automatically ingested into MASTER_TASK_TRACKING.md under Analyst Proposed Backlog (only new IDs).
- Also persisted to data/state/analyst_proposed_backlog.json for clean tracking.

Run by the twice-daily cron. Real data only.
"""

import json
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


def generate_strategic_proposals(sl_risks, coverage, total_pairs, poly, learnings, state, existing_ids, opt_brief=None, leaderboard=None):
    """
    Derive strategic modification proposals.
    Assigns stable IDs.
    Dedupes against existing_ids.
    """
    candidates = []
    try:
        from phase6.research.analyst_narrative import optimization_proposal_candidates

        candidates.extend(optimization_proposal_candidates(opt_brief, leaderboard))
    except Exception:
        pass

    heuristics = learnings.get("heuristics", {})
    known_weaknesses = heuristics.get("known_weaknesses", [])

    # Candidate 1: SL pre-flight
    high_risk_count = sum(1 for r in sl_risks.values() if r.get("level") in ("HIGH", "CRITICAL"))
    if high_risk_count > 0 or any("preview" in str(w).lower() or "stop" in str(w).lower() for w in known_weaknesses):
        candidates.append({
            "title": "Add pre-flight settlement poll + product-specific tick handling to SL layer",
            "description": "Before attaching stop-limit orders, poll for settled balance and apply per-product tick size / precision rules. Use the existing SL risk scorer to decide aggressiveness.",
            "benefits": "Reduce PREVIEW_INSUFFICIENT_FUND and PREVIEW_INVALID_STOP_PRICE_PRECISION failures by 60-80%. Faster and more reliable re-attachment after buys. Improves SL reliability on low-priced assets (SOL, ADA, etc.).",
            "risks": "Slight increase in rebalance latency (mitigation: 2-3s timeout + async). Risk of over-waiting on stable pairs (mitigation: skip poll for low-risk pairs). Coinbase-side rules may still apply in rare cases.",
            "priority": "High",
            "effort": "Medium",
            "category": "SL / Platform"
        })

    # Candidate 2: Regime-aware allocation
    risk_on = poly.get("risk_on_bias", 0.5)
    if risk_on > 0.65 or risk_on < 0.35:
        direction = "risk-on tilt (favor momentum pairs)" if risk_on > 0.65 else "risk-off tilt (favor defensive / higher conviction)"
        candidates.append({
            "title": f"Wire Polymarket regime bias into allocator as soft constraint ({direction})",
            "description": "Pass the current risk_on_bias from Polymarket as a multiplier or filter into RotationStrategy / rebalance_plan. Bias allocation toward or away from higher-vol names accordingly.",
            "benefits": "Better macro alignment. Capture more upside in risk-on regimes and reduce drawdown in risk-off. Uses live external signal that is already being fetched daily.",
            "risks": "Polymarket can be noisy or manipulated on low-liquidity markets (mitigation: smooth with 3-day average + minimum confidence threshold). Could increase churn (mitigation: combine with existing min_score_delta and cooldowns).",
            "priority": "Medium",
            "effort": "Medium",
            "category": "Allocator / Skills"
        })

    # Candidate 3: Data coverage
    if coverage < total_pairs - 1:
        candidates.append({
            "title": "Strengthen pre-rebalance data refresh + fallback for partial coverage",
            "description": "Before running allocator, ensure all basket pairs have fresh RSI + sentiment. Add a short blocking refresh or use last-known with explicit 'stale' flag. Consider lightweight on-demand pull for missing pairs.",
            "benefits": "Higher signal quality for allocator decisions. Fewer 'MISSING' or 'RSI-ONLY' states. Reduces risk of deploying on incomplete information.",
            "risks": "Slight delay to rebalance window (mitigation: parallel refreshes + 10-15s hard cap). API rate limits (mitigation: respect existing backoff).",
            "priority": "Medium",
            "effort": "Low-Medium",
            "category": "Data / Runner"
        })

    # Candidate 4: Close the learnings loop
    # Only propose if NOT yet deployed/gated (check new heuristic key + config flag)
    allocator_active = heuristics.get("allocator_heuristics_active") or "apply_analyst_heuristics" in str(heuristics)
    if not allocator_active and ("paper_trade_validation" in str(heuristics) or not any("allocator" in str(h).lower() for h in heuristics.values())):
        candidates.append({
            "title": "Close the loop: make analyst learnings + heuristics influence allocator parameters",
            "description": "Load key heuristics (e.g. prefer_rotation_when) and recent evolution notes at allocator start. Apply as dynamic config overrides (e.g. adjust min_score_delta or rotation bias based on recent SL failure patterns).",
            "benefits": "System actually learns. Reduces repeated mistakes (e.g. post-buy SL timing). Turns the analyst from observer into active participant in decision quality.",
            "risks": "Over-fitting to recent noise (mitigation: weight recent learnings lightly + require confirmation across 2-3 cycles). Complexity creep (mitigation: start with 1-2 simple rules).",
            "priority": "High",
            "effort": "Medium",
            "category": "Allocator / Analyst Evolution"
        })

    # Fallback if too few
    if len(candidates) < 2:
        candidates.append({
            "title": "Add lightweight 'strategic brief' artifact before each scheduled rebalance",
            "description": "Have the intelligence report produce a short JSON 'brief' (regime bias, high-SL-risk pairs, top proposals) that the runner can optionally load as context or constraints.",
            "benefits": "Pre-rebalance strategic context without heavy coupling. Makes daily briefings directly actionable for the allocator.",
            "risks": "Another artifact to maintain (mitigation: keep it tiny and optional).",
            "priority": "Medium",
            "effort": "Low",
            "category": "Runner / Analyst"
        })

    # Dedup candidates by title (prevent accidental repeats in one run)
    seen = set()
    unique_cands = []
    for c in candidates:
        t = c.get("title")
        if t not in seen:
            seen.add(t)
            unique_cands.append(c)
    candidates = unique_cands

    # Assign IDs and filter duplicates
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
    """Analyst follow-up on deployed suggestions (48-hour observation rule).
    
    User directive (2026-06-24): Stick with 48h rule. Adequate to verify the change didn’t blow anything up.
    Not long enough to validate effectiveness (especially in ranging/sideways markets).
    Daily status reviews (these intelligence reports) are expected to judge and make adjustments.
    """
    print("\n=== Analyst Follow-up on Deployed Suggestions (48h Observation Rule) ===")
    print("Rule: 48-hour minimum observation window after any deployment.")
    print("Purpose: Verify nothing blew up. Daily reports will assess and drive tweaks.")
    print("Note: 48h is deliberately short for safety checks — insufficient for full effectiveness validation in low-volatility/ranging markets.")
    
    now = datetime.now(timezone.utc)
    deployed = [p for p in backlog.get("proposals", []) if p.get("deployed") or p.get("accepted")]
    
    if not deployed:
        print("No deployed/accepted suggestions found for follow-up.")
        return
    
    inside_window = []
    for p in sorted(deployed, key=lambda x: x.get("deployed", x.get("accepted", "")), reverse=True)[:5]:
        pid = p.get("id", "?")
        title = p.get("title", "")
        dep_str = p.get("deployed") or p.get("accepted", "")
        
        try:
            if "T" in dep_str:
                dep_time = datetime.fromisoformat(dep_str.replace("Z", "+00:00"))
            else:
                dep_time = datetime.strptime(dep_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            elapsed = (now - dep_time).total_seconds() / 3600
            elapsed_str = f"{elapsed:.1f}h"
            within_48h = elapsed < 48
        except Exception:
            elapsed_str = "unknown"
            within_48h = True  # conservative
        
        status = "INSIDE 48h WINDOW — observe only" if within_48h else "48h window closed — eligible for review/adjustment"
        if within_48h:
            inside_window.append(pid)
        
        print(f"\n- {pid}: {title[:70]}")
        print(f"  Deployed: {dep_str}")
        print(f"  Elapsed: {elapsed_str} | {status}")
        
        # Lightweight current-state validation
        if "heuristics" in title.lower() or "close the loop" in title.lower() or "analyst learnings" in title.lower():
            heurs = learnings.get("heuristics", {})
            gate = heurs.get("allocator_heuristics_active", "unknown")
            print(f"  Current gate: apply_analyst_heuristics / {gate}")
            high_risk = [k for k, v in sl_risks.items() if str(v.get("level", "")).upper() in ("HIGH", "CRITICAL")]
            print(f"  High SL-risk pairs right now: {high_risk[:3]} (monitor for allocator conservatism effect)")
            print("  Validation ask for daily review: Check runner logs for 'Learnings adjustments' in the last rebalance. Compare SL preview/attach success rate on tagged pairs vs pre-deployment baseline.")
        
        elif "pre-flight" in title.lower() or "settlement" in title.lower():
            print("  Validation ask: Compare recent SL attach success vs historical failure rate in logs.")
        
        if within_48h:
            print("  Action: No further related changes. Wait for 48h + next daily review.")
    
    if inside_window:
        print(f"\nItems still inside 48h window: {inside_window}")
        print("Daily status reviews should note any early signals but withhold major adjustments until window closes.")
    
    print("\nUser principle: '48 hour rule for observation. Adequate to verify that the change didn’t blow anything up. It’s not long enough if the market is ranging sideways to validate effectiveness. Daily status reviews will be able to judge and make adjustments.'")
    print("Analyst will surface elapsed time and window status in every report.")


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

    if added:
        print(f"New proposals added to MASTER: {added}")


def main():
    print("=== Phase 6 Daily Trading Intelligence Briefing — Crypto Analyst ===")
    print(f"Date: {date.today().isoformat()}")
    print(f"Generated: {datetime.utcnow().isoformat()} UTC")
    print()
    print("Persona: Truth-seeking, direct, no fluff. Cite run_id + metrics. Production P&L before scenario hype. Occasional dry humor.")
    print()

    basket = load_basket()
    print(f"Basket: {len(basket)} pairs → {basket}")
    print()

    latest = load_latest_sentiment_for_basket(basket=basket)
    rsi_cache = load_rsi_cache()
    state = load_runner_state()
    learnings = load_learnings()
    sg = SignalGenerator()

    price_map = {}  # populated from live prices in production runs
    sl_risks = get_all_sl_risks(basket, price_map)

    # === Per-Pair Narrative Decisions (slim, emoji + decision only) ===
    print("=== Per-Pair Narrative Decisions ===")
    full_count = 0
    for pair in basket:
        rsi_val = latest.get("rsi", {}).get(pair)
        sent_val = latest.get("sentiment", {}).get(pair, 0.0)
        cache_entry = rsi_cache.get(pair, {})
        rsi_src = "cache (fresh, longer-term)" if cache_entry.get("fresh") else "scorer/db"

        has_rsi = rsi_val is not None and abs(rsi_val) > 0.1
        has_stoch = cache_entry.get("stoch_k") is not None
        has_sent = abs(sent_val) > 0.001

        if (has_rsi or has_stoch) and has_sent:
            full_count += 1
            status = "FULL"
        elif has_rsi or has_stoch:
            status = "RSI+STOCH-ONLY" if has_stoch else "RSI-ONLY"
        elif has_sent:
            status = "SENT-ONLY"
        else:
            status = "MISSING"

        signal = sg.generate_signal(pair, rsi_val or 50.0, sentiment=sent_val or 0.0)

        slr = sl_risks.get(pair, {"level": "unknown", "risk_score": 0.0})
        risk_level = str(slr.get("level", "unknown")).lower()

        if signal.signal == "BUY":
            if risk_level in ("low", "unknown"):
                emoji = "📈🚀"
                narrative = "Positive setup supports adding on rotation."
            else:
                emoji = "📈🔥"
                narrative = "Bullish signal but elevated SL risk — size small or wait for better confirmation."
        elif signal.signal == "SELL":
            emoji = "📉"
            narrative = "Negative setup — consider reducing or avoiding new exposure."
        else:
            emoji = "👉"
            narrative = "Monitor."

        stoch_str = ""
        if cache_entry.get("stoch_k") is not None:
            stoch_str = f" | StochK={cache_entry['stoch_k']}"
        if emoji == "👉":
            print(f"{pair}: {emoji} SL: {slr['level']}{stoch_str}.")
        else:
            print(f"{pair}: {emoji} {signal.reason}. SL: {slr['level']}{stoch_str}.")
        print(f"    {narrative}")

    print("=== Coverage ===")
    print(f"FULL coverage pairs: {full_count} / {len(basket)} (RSI or Stoch + Sent; using 100pt longer-term window + StochRSI)")
    print()

    print("=== Runner State ===")
    print(f"Last rebalance: {state.get('last_rebalance_date')}")
    print(f"Strategy: rotation_catch_wave (Phase 6 allocator + platform executor)")
    print()

    print("=== Polymarket Regime Bias ===")
    print(f"Risk-on bias: {poly.get('risk_on_bias')}")
    print(f"Source: {poly.get('source')}")
    if poly.get("num_markets") is not None:
        print(f"Markets used: {poly.get('num_markets')} | Total vol: {poly.get('total_vol', 0):,.0f} | Confidence: {poly.get('confidence')}")
    if poly.get("events"):
        print("Sample events:", poly["events"][:2])
    print(f"Note: {poly.get('note')}")
    print()

    # === Trade Influence Stack Model ===
    print("=== Trade Influence Stack (conceptual + current) ===")
    print("X sentiment: fast tactical (full ~15min, half-life ~60min, decays sharply after 2-4h). Per-pair.")
    print("Reddit: confirmatory medium (peak influence ~30min, slower decay). Fallback only when real data.")
    print("Polymarket: strategic regime / tilt (slower persistence, HL ~8h proposed, volume-boosted). Global filter/sizing.")
    print()
    # Inline (model defined in polymarket_overlay)
    biasv = float(poly.get("risk_on_bias", 0.5))
    confv = float(poly.get("confidence", 0.5))
    tvolv = float(poly.get("total_vol", 0))
    dirv = abs(biasv - 0.5) * 2 * confv
    vboost = min(1.5, 1.0 + (tvolv / 50_000_000)) if tvolv > 0 else 1.0
    effv = min(1.0, dirv * vboost)
    print(f"Polymarket effective influence (fresh): {effv:.4f} (directional={dirv:.4f}, vol_boost={vboost:.3f})")
    print("  Model: |bias-0.5|*2*conf * vol_boost (regime HL~8h). Global tilt/filter, not per-pair trigger.")
    print()


    # === PM Tie-Breaker Analysis (instrumentation for measurement) ===
    print("=== PM as Tie-Breaker / Tilt ===")
    try:
        from phase6.core.trade_ledger import TradeLedger
        ledger = TradeLedger(base_dir=PROJECT_ROOT)
        recent_decisions = []
        dec_path = PROJECT_ROOT / "data/state/decision_context_log.jsonl"
        if dec_path.exists():
            with open(dec_path) as fh:
                for line in fh.readlines()[-5:]:
                    try:
                        d = __import__("json").loads(line)
                        recent_decisions.append(d)
                    except: pass
        if recent_decisions:
            last = recent_decisions[-1]
            print(f"Last decision tiebreaker: {last.get('pm_used_as_tiebreaker')} | PM bias: {last.get('pm_bias')} | X_neutral: {last.get('x_neutral')} | Reddit_neutral: {last.get('reddit_neutral')}")
            print(f"  Other factors: {last.get('other_factors')}")
            print(f"  Regime mult applied: {last.get('regime_mult_applied')}")
        else:
            print("No recent decision_context logs yet (instrumentation ramping up).")
    except Exception as e:
        print(f"Tie-breaker log read skipped: {e}")

    print("PM influence model treats this as slow regime tilt (HL~8h). Primary value as tie-breaker when X/Reddit neutral.")
    print()


    # === Automated Retrospective Analyzer (for daily analyst status) ===
    print()
    print("=== PM Tilt Retrospective Analyzer ===")
    try:
        # Make the dedicated script importable
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "phase6/scripts"))
        from analyze_pm_tilt_retrospective import run_pm_tilt_analysis
        analysis = run_pm_tilt_analysis(window_hours=6)

        print(f"Data: decisions={analysis['data_summary']['decisions_loaded']}, rebalances={analysis['data_summary']['rebalances_loaded']}, trades={analysis['data_summary']['trades_loaded']}")
        print(f"Tie-breaker activations detected: {analysis['tiebreaker_activations']}")
        print(f"Rebalances near tie-breakers: {analysis['rebalance_buckets']['tied_count']} | baseline: {analysis['rebalance_buckets']['baseline_count']}")

        lift = analysis.get("lift_metrics", {})
        if lift.get("lift"):
            print(f"Lift vs baseline: {lift['lift']}")

        factors = analysis.get("other_factors_correlation", {})
        if factors.get("total_tiebreaker_activations"):
            print(f"Other factors in activations: price_declining_rate={factors.get('price_declining_rate')}, volume_spike_rate={factors.get('volume_spike_rate')}")

        # Surface top suggestions directly in the brief
        suggestions = analysis.get("tuning_suggestions", [])[:2]
        if suggestions:
            print("\nAuto-generated tuning suggestions (review for proposals):")
            for s in suggestions:
                print(f"  - [{s.get('priority','?').upper()}] {s.get('title')}: {s.get('suggestion')[:120]}...")

        # Save the full analysis for the analyst to reference
        try:
            (PROJECT_ROOT / "data/state/pm_tilt_retrospective_analysis.json").write_text(json.dumps(analysis, indent=2))
        except:
            pass
    except Exception as e:
        print(f"PM tilt retrospective analyzer skipped: {e}")

    print()
    print("PM influence model treats this as slow regime tilt (HL~8h). Primary value as tie-breaker when X/Reddit neutral.")
    # === Tuning Protocol for Crypto Analyst ===
    print("=== Tuning Protocol (PM Tilt) ===")
    print("1. Review output from PM Tilt Retrospective Analyzer (run automatically here) + logs.")
    print("2. Bucket by 'pm_used_as_tiebreaker=True' vs baseline.")
    print("3. Compute lift on: rotation win rate, capital deployed when tilted, SL hit rate, overall PnL attribution.")
    print("4. Propose variations in next brief (e.g. ANALYST-...-TUNE-PM): different neutrality thresholds, additional other_factors (volume, funding rate, etc.), effect sizes.")
    print("5. Analyst includes 'Proposed PM Tilt Variation' in strategic proposals when data suggests improvement.")
    print()
    # === Log full influence stack snapshot (for 2-4wk impact analysis) ===
    try:
        base = PROJECT_ROOT
        sys.path.insert(0, str(base / "phase6/core"))
        from trade_ledger import TradeLedger
        from sentiment_scorer import load_sentiment_scores, _load_reddit_from_db, get_aged_sentiment_scores

        sys.path.insert(0, str(Path.home() / ".hermes/skills"))
        from crypto_analyst.polymarket_overlay import get_polymarket_regime_bias, get_polymarket_influence

        ledger = TradeLedger(base_dir=base)
        x_sent = load_sentiment_scores()
        reddit_sent = _load_reddit_from_db(list(x_sent.keys()) if x_sent else ["BTC-USD"])
        aged = get_aged_sentiment_scores(half_life_minutes=60)
        pm_poly = get_polymarket_regime_bias()
        inf = get_polymarket_influence(pm_poly)

        snapshot = {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "polymarket": pm_poly,
            "influence": inf,
            "x_sentiment": {k: round(v,4) for k,v in (x_sent or {}).items()},
            "reddit_sentiment": {k: round(v,4) for k,v in (reddit_sent or {}).items()},
            "aged_sentiment": {k: round(v,4) for k,v in (aged or {}).items()}
        }
        ledger.log_influence_stack(snapshot)
        print(f"[STACK] Logged influence snapshot (polymarket bias={pm_poly.get('risk_on_bias')})")
    except Exception as e:
        print(f"[STACK] Snapshot log skipped: {e}")


    # === Optimization results (scenario vs production) ===
    try:
        from phase6.research.optimization_brief import format_optimization_section, load_leaderboard

        lb = load_leaderboard()
        if lb:
            opt_text, opt_brief = format_optimization_section(lb)
            print(opt_text)
            print()
        else:
            lb = None
            opt_brief = None
    except Exception as e:
        print(f"=== Optimization results ===\n(skipped: {e})\n")
        opt_brief = None
        lb = None

    # === Honest Assessment (mandatory, data-driven) ===
    print("=== Honest Assessment ===")
    try:
        from phase6.research.analyst_narrative import format_honest_assessment

        for line in format_honest_assessment(
            full_coverage_count=full_count,
            total_pairs=len(basket),
            sl_risks=sl_risks,
            opt_brief=opt_brief,
            leaderboard=lb,
        ):
            print(line)
    except Exception as e:
        print(f"(assessment fallback: {e})")
        if full_count >= len(basket) - 2:
            print("Coverage is genuinely good. SL layer remains a weak link.")
        else:
            print("Coverage still patchy.")
    print()

    # === Evolution Notes ===
    print("=== Evolution Notes ===")
    recent = learnings.get("learnings", [])[-1] if learnings.get("learnings") else {}
    if recent:
        print(f"Last thesis: {recent.get('thesis', 'N/A')}")
        print(f"Outcome: {recent.get('outcome', 'N/A')}")
        print(f"Previous evolution: {recent.get('evolution_note', 'N/A')}")
    print()

    try:
        from phase6.research.analyst_narrative import build_evolution_note

        new_evolution = build_evolution_note(
            full_coverage_count=full_count,
            total_pairs=len(basket),
            opt_brief=opt_brief,
            leaderboard=lb,
        )
    except Exception:
        new_evolution = {
            "thesis": "Platform + allocator should deliver better-timed rotation.",
            "outcome": f"Allocator active. {full_count} FULL signals.",
            "evolution_note": "Run regime scorecard; shadow before live knobs.",
        }
    learnings = add_evolution_note(learnings, new_evolution)
    print(f"New note recorded: {new_evolution['evolution_note']}")
    print()

    # === Strategic Modification Proposals ===
    existing_proposals = load_existing_proposals()
    existing_ids = {p.get("id") for p in existing_proposals if p.get("id")}

    proposals = generate_strategic_proposals(
        sl_risks=sl_risks,
        coverage=full_count,
        total_pairs=len(basket),
        poly=poly,
        learnings=learnings,
        state=state,
        existing_ids=existing_ids,
        opt_brief=opt_brief,
        leaderboard=lb,
    )

    print("=== Strategic Modification Proposals ===")
    if not proposals:
        print("No new strategic modifications proposed this cycle.")
    else:
        for p in proposals:
            print(f"\n**{p['id']}** — {p['title']}")
            print(f"Description: {p['description']}")
            print(f"Benefits: {p['benefits']}")
            print(f"Risks + Mitigations: {p['risks']}")
            print(f"Priority: {p['priority']} | Effort: {p['effort']} | Category: {p['category']}")

    print()

    # Persist (deduped)
    try:
        all_proposals = existing_proposals + [p for p in proposals if p["id"] not in existing_ids]
        PROPOSALS_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(PROPOSALS_JSON, "w") as f:
            json.dump({"proposals": all_proposals[-50:]}, f, indent=2)
        print(f"Proposals persisted (deduped) to {PROPOSALS_JSON}")
    except Exception as e:
        print(f"Warning: proposals JSON: {e}")

    # Feed to canonical proposed backlog (with IDs)
    try:
        backlog = load_proposed_backlog()
        existing_backlog_ids = {p.get("id") for p in backlog.get("proposals", [])}
        new_for_backlog = [p for p in proposals if p["id"] not in existing_backlog_ids]
        for p in new_for_backlog:
            p["status"] = "proposed"
            p["generated"] = datetime.utcnow().isoformat()
        backlog["proposals"] = backlog.get("proposals", []) + new_for_backlog
        save_proposed_backlog(backlog)
        if new_for_backlog:
            print(f"Added to analyst_proposed_backlog.json: {[p['id'] for p in new_for_backlog]}")
    except Exception as e:
        print(f"Warning: backlog: {e}")

    # Feed to MASTER (only new IDs)
    try:
        feed_proposals_to_master_backlog(proposals)
    except Exception as e:
        print(f"Warning: MASTER backlog: {e}")

    # Build and persist lightweight strategic brief for the runner (implements ANALYST-20260627-016)
    try:
        BRIEF_CACHE = PROJECT_ROOT / "data/state/intel_strategic_brief.json"
        brief = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "risk_on_bias": round(float(poly.get("risk_on_bias", 0.5)), 3),
            "polymarket": {
                "risk_on_bias": round(float(poly.get("risk_on_bias", 0.5)), 3),
                "num_markets": int(poly.get("num_markets", 0)),
                "total_vol": float(poly.get("total_vol", 0)),
                "confidence": float(poly.get("confidence", 0.0))
            },
            "coverage": {"full": int(full_count), "total": len(basket)},
            "high_sl_risk_pairs": [p for p, r in sl_risks.items() if str(r.get("level", "")).upper() in ("HIGH", "CRITICAL")],
            "top_proposals": [{"id": p.get("id"), "title": p.get("title"), "priority": p.get("priority")} for p in proposals[:3]],
            "last_rebalance": state.get("last_rebalance_date"),
            "optimization": opt_brief,
            "note": "Use as soft context for next rebalance. Regenerated on each intelligence cycle."
        }
        BRIEF_CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(brief, open(BRIEF_CACHE, "w"), indent=2)
        print(f"Strategic brief saved to {BRIEF_CACHE}")
    except Exception as e:
        print(f"Warning: brief save skipped: {e}")

    # === Decision Approval Required (bottom of briefing) ===
    print("\n=== Decision Approval Required ===")
    if proposals:
        for i, p in enumerate(proposals, 1):
            print(f"{i}. {p['id']}: {p['title']}")
            print(f"   Benefits: {p['benefits'][:120]}...")
            print(f"   Risks: {p['risks'][:120]}...")
        print()
        print("Reply with one of:")
        print("- proceed with 1")
        print("- proceed with 2")
        print("- proceed with 1 and 2")
        print("- both")
        print("- wait")
        print("- clarification needed")
        print("- none")
        print()
        print("Example: \"proceed with 1\" or \"proceed with both\"")
    else:
        print("No new proposals this cycle.")

    print()
    if "SOL" in basket:
        print("(SOL continues its tradition of making everyone look smart for 12 minutes and then changing its mind. Classic.)")
    print()
    # === Analyst Follow-up on Deployed Suggestions (recurring validation) ===
    try:
        backlog = load_proposed_backlog()
        generate_followup_validation(learnings, backlog, sl_risks, proposals)
    except Exception as e:
        print(f"[Follow-up] Skipped (non-fatal): {e}")

    print("Report complete. Real data. Evidence over narrative.")
    print("Crypto Analyst — learning, one honest cycle at a time.")


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
