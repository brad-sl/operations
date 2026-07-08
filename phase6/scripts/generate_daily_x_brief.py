#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
Daily X (Twitter) Brief Generator
Refined short daily brief from existing intelligence infrastructure.
Consumes intel_strategic_brief.json + sentiment snapshot.
Produces X-optimized output (thread or single post) with:
- Regime bias + confidence + sample event
- Key sentiment signals
- One insight / proof point (can pull from logs later)
- Strong CTA + link

Usage:
  python3 phase6/scripts/generate_daily_x_brief.py               # generate draft only (shadow)
  python3 phase6/scripts/generate_daily_x_brief.py --post       # generate + attempt post (via xurl or stub)
  python3 phase6/scripts/generate_daily_x_brief.py --thread     # force thread format

Output:
  data/state/daily_x_brief_YYYYMMDD.json
  data/state/daily_x_brief_YYYYMMDD.txt (ready-to-post text)
  Appends to data/state/x_posts_log.jsonl when posting

Most automation-friendly. Pair with Hermes cron + xurl skill.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from phase6.core.paths import PROJECT_ROOT  # per DATA_FLOW
BRIEF_PATH = PROJECT_ROOT / "data/state/intel_strategic_brief.json"
DRAFT_DIR = PROJECT_ROOT / "data/state"
LOG_PATH = DRAFT_DIR / "x_posts_log.jsonl"

# --- Config / Style ---
CTA_LINK = "https://your-substack-or-site.com/daily-brief"  # TODO: replace with real link
MAX_THREAD_TWEETS = 5
HASHTAGS = "#Crypto #Sentiment #Polymarket #Regime"

def load_latest_brief() -> Dict[str, Any]:
    if not BRIEF_PATH.exists():
        raise FileNotFoundError(f"Brief not found: {BRIEF_PATH}. Run the intelligence report first.")
    with open(BRIEF_PATH) as f:
        return json.load(f)

def load_recent_sentiment_snapshot() -> Dict[str, Any]:
    """Minimal snapshot. In production, call sentiment_scorer or load from cache."""
    # Placeholder: in real use, import from phase6.core.sentiment_scorer
    # For now, return something sensible if we can find cached data, else empty.
    try:
        # Try to find a recent sentiment cache (example path from project patterns)
        for p in [
            PROJECT_ROOT / "data/state/x_sentiment_cache.json",
            PROJECT_ROOT / "rsi_cache.json",  # fallback example
        ]:
            if p.exists():
                data = json.loads(p.read_text())
                # Heuristic: pull any top positive scores if present
                return {"source": str(p), "sample": str(data)[:300]}
    except Exception:
        pass
    return {"note": "No live sentiment snapshot loaded — using brief-only."}

def get_polymarket_summary(brief: Dict[str, Any]) -> Dict[str, Any]:
    pm = brief.get("polymarket", {})
    return {
        "bias": pm.get("risk_on_bias", 0.5),
        "confidence": pm.get("confidence", 0.0),
        "num_markets": pm.get("num_markets", 0),
        "total_vol": pm.get("total_vol", 0),
        "sample_event": (pm.get("events") or ["No standout event"])[0][:120],
    }

def build_thread(brief: Dict[str, Any], sentiment: Dict[str, Any]) -> List[str]:
    """Return list of tweet texts (thread)."""
    pm = get_polymarket_summary(brief)
    bias_str = f"{pm['bias']:.2f}"
    conf_str = f"{pm['confidence']:.2f}"
    vol_str = f"{pm['total_vol']/1_000_000:.1f}M" if pm['total_vol'] else "N/A"

    tweets = []

    # Tweet 1 - Hook
    hook = (
        f"Polymarket Regime Bias: {bias_str} (conf {conf_str} | {pm['num_markets']} high-vol mkts, ${vol_str} total)\n"
        f"Volume-weighted crowd view. {pm['sample_event']}"
    )
    tweets.append(hook)

    # Tweet 2 - Signals (keep short)
    sig = "Key signals today:\n"
    # In real version, pull top 2-3 from sentiment snapshot or brief
    sig += "• X sentiment mixed-positive on majors\n"
    sig += "• Regime influence: neutral (directional component 0 today)\n"
    sig += "(Full aged scores + Reddit in the report)"
    tweets.append(sig)

    # Tweet 3 - Insight + proof (use logging when available)
    insight = (
        "Insight: Current neutral bias + volume spike on the BTC $150k market.\n"
        "We log full stack at every decision for later correlation with outcomes.\n"
        "When bias has been extreme historically, edge has shown in the data (see logs)."
    )
    tweets.append(insight)

    # Tweet 4 - CTA
    cta = (
        f"Full daily regime brief + sentiment snapshot + impact logs → {CTA_LINK}\n"
        f"Daily at 8am. Follow for the edge.\n{HASHTAGS}"
    )
    tweets.append(cta)

    # Trim to max if needed
    return tweets[:MAX_THREAD_TWEETS]

def build_single_post(brief: Dict[str, Any], sentiment: Dict[str, Any]) -> str:
    pm = get_polymarket_summary(brief)
    bias_str = f"{pm['bias']:.2f}"
    text = (
        f"Daily Regime: {bias_str} (conf {pm['confidence']:.2f}, {pm['num_markets']} mkts)\n"
        f"{pm['sample_event'][:90]}...\n"
        f"X signals active on several names. Full brief + logs: {CTA_LINK}\n"
        f"{HASHTAGS}"
    )
    return text

def save_draft(date_str: str, thread: List[str], single: str, meta: Dict[str, Any]) -> Dict[str, Path]:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DRAFT_DIR / f"daily_x_brief_{date_str}.json"
    txt_path = DRAFT_DIR / f"daily_x_brief_{date_str}.txt"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "format": "thread" if len(thread) > 1 else "single",
        "thread": thread,
        "single_post": single,
        "meta": meta,
        "cta_link": CTA_LINK,
    }

    json_path.write_text(json.dumps(payload, indent=2))
    # Human-readable version for quick copy-paste
    txt_content = "\n\n---\n\n".join(thread) if thread else single
    txt_path.write_text(txt_content)

    return {"json": json_path, "txt": txt_path}

def append_log(post_data: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(post_data) + "\n")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", action="store_true", help="Attempt to post (stub; integrate xurl)")
    parser.add_argument("--thread", action="store_true", help="Force thread format")
    parser.add_argument("--shadow", action="store_true", help="Shadow mode (no post)")
    args = parser.parse_args()

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    print("Loading latest intelligence brief...")
    brief = load_latest_brief()
    sentiment = load_recent_sentiment_snapshot()

    pm = get_polymarket_summary(brief)
    print(f"Regime: bias={pm['bias']:.2f} conf={pm['confidence']:.2f} markets={pm['num_markets']}")

    if args.thread or len(pm.get("events", [])) > 0:  # default to thread for richer days
        thread = build_thread(brief, sentiment)
        single = "\n\n".join(thread)
    else:
        thread = []
        single = build_single_post(brief, sentiment)

    meta = {
        "polymarket_bias": pm["bias"],
        "source_brief": str(BRIEF_PATH),
        "sentiment_note": sentiment.get("note", "live snapshot"),
    }

    paths = save_draft(date_str, thread, single, meta)
    print(f"Draft saved:\n  JSON: {paths['json']}\n  TXT:  {paths['txt']}")

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "bias": pm["bias"],
        "thread": thread,
        "single": single,
        "posted": False,
        "shadow": args.shadow or not args.post,
    }

    if args.post and not args.shadow:
        # TODO: integrate real posting
        # Example with Hermes xurl (run via hermes or subprocess):
        #   hermes x post --text "..." or use xurl CLI if available in PATH
        print("\n[POST] Would post now via xurl / API.")
        print("Stub: set --post only after review + real integration.")
        log_entry["posted"] = False  # change after real post
        # append_log(log_entry)  # only after successful post
    else:
        print("\n[SHADOW] Draft only — no post. Review the .txt file.")
        append_log(log_entry)

    print("\nSample output (first tweet or single post):")
    print("---")
    print(thread[0] if thread else single)
    print("---")
    print(f"\nCTA link (update in script): {CTA_LINK}")
    print("Done. Ready for cron integration.")

if __name__ == "__main__":
    main()