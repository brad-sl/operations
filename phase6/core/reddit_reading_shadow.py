"""Shadow Reddit scores via Hermes bundled reddit-reading skill.

Uses ~/.hermes/skills/social-media/reddit-reading/scripts/reddit.py
(anonymous Atom by default; OAuth if REDDIT_CLIENT_ID/SECRET set).

SHADOW ONLY — does not write live sentiment_cache.json or clear buy gates.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket

REDDIT_PY = (
    Path.home()
    / ".hermes"
    / "skills"
    / "social-media"
    / "reddit-reading"
    / "scripts"
    / "reddit.py"
)
OUT_CACHE = PROJECT_ROOT / "data" / "state" / "sentiment_cache_reddit_reading.json"
OUT_REPORT = PROJECT_ROOT / "reports" / "REDDIT_READING_SHADOW_LATEST.md"
HISTORY = PROJECT_ROOT / "data" / "state" / "reddit_reading_shadow_history.jsonl"

# Keep short: anonymous Atom ≈ 1 req/min/IP
SUBS_GENERAL = ["CryptoCurrency", "CryptoMarkets"]
# Only hit pair subs when OAuth (or caller passes --deep)
SUBS_BY_PAIR = {
    "BTC-USD": ["Bitcoin"],
    "ETH-USD": ["ethereum"],
    "SOL-USD": ["solana"],
    "XRP-USD": ["Ripple"],
    "DOGE-USD": ["dogecoin"],
    "ADA-USD": ["cardano"],
    "AVAX-USD": ["Avax"],
    "LINK-USD": ["Chainlink"],
    "UNI-USD": ["UniSwap"],
}

HALF_LIFE_H = 36.0
EPS = 1e-9

try:
    from textblob import TextBlob

    HAS_TB = True
except ImportError:
    HAS_TB = False


def _polarity(text: str) -> float:
    if not text:
        return 0.0
    if HAS_TB:
        try:
            return float(TextBlob(text).sentiment.polarity)
        except Exception:
            pass
    # cheap fallback lexicon
    t = text.lower()
    pos = sum(
        1
        for w in (
            "bull",
            "moon",
            "rally",
            "breakout",
            "pump",
            "surge",
            "ath",
            "buy",
            "accumulate",
            "undervalued",
        )
        if w in t
    )
    neg = sum(
        1
        for w in (
            "bear",
            "crash",
            "dump",
            "scam",
            "hack",
            "rug",
            "ban",
            "sell",
            "collapse",
            "fraud",
        )
        if w in t
    )
    if pos == neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(3.0, pos + neg)))


def _load_keywords() -> Dict[str, List[str]]:
    path = PROJECT_ROOT / "config" / "sentiment_keywords.json"
    out: Dict[str, List[str]] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pairs = data.get("pairs") or data
            for pair, cfg in pairs.items():
                if not isinstance(cfg, dict):
                    continue
                terms = [str(t) for t in (cfg.get("reddit") or [])]
                terms.append(pair.split("-")[0])
                seen, clean = set(), []
                for t in terms:
                    tl = t.lower()
                    if tl not in seen:
                        seen.add(tl)
                        clean.append(t)
                out[str(pair)] = clean
        except Exception:
            pass
    return out


def _run_reddit(args: List[str], timeout: int = 120) -> Any:
    if not REDDIT_PY.is_file():
        raise FileNotFoundError(f"reddit-reading skill missing: {REDDIT_PY}")
    cmd = [sys.executable, str(REDDIT_PY), "--json", *args]
    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()})},
    )
    err = (cp.stderr or "").strip()
    if err:
        # rate-limit sleep messages are expected on stderr
        for line in err.splitlines()[-3:]:
            print(f"  [reddit stderr] {line}", file=sys.stderr)
    if cp.returncode != 0:
        raise RuntimeError(f"reddit.py rc={cp.returncode}: {(cp.stderr or '')[:300]}")
    out = (cp.stdout or "").strip()
    if not out:
        return []
    return json.loads(out)


def doctor() -> Dict[str, Any]:
    if not REDDIT_PY.is_file():
        return {"ok": False, "error": f"missing {REDDIT_PY}"}
    try:
        # doctor prints plain, not always json — run without --json first path
        cmd = [sys.executable, str(REDDIT_PY), "doctor"]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        text = (cp.stdout or "") + "\n" + (cp.stderr or "")
        # try parse as json lines
        report: Dict[str, Any] = {"raw": text.strip()[:800], "rc": cp.returncode}
        for line in text.splitlines():
            if ":" in line and not line.strip().startswith("{"):
                k, _, v = line.partition(":")
                report[k.strip()] = v.strip()
        # also try json doctor if supported
        try:
            j = _run_reddit(["doctor"], timeout=60)
            if isinstance(j, dict):
                report.update(j)
        except Exception:
            pass
        report["ok"] = cp.returncode == 0
        report["skill_path"] = str(REDDIT_PY)
        return report
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _entry_text(e: Dict[str, Any]) -> str:
    title = e.get("title") or e.get("name") or ""
    body = e.get("body") or e.get("summary") or e.get("selftext") or e.get("content") or ""
    return f"{title}. {body}".strip()


def _entry_ts(e: Dict[str, Any]) -> Optional[float]:
    for k in ("created_utc", "created", "published", "updated", "timestamp"):
        v = e.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            # atom sometimes ms
            f = float(v)
            if f > 1e12:
                f /= 1000.0
            return f
        s = str(v).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            continue
    return None


def _recency_w(ts: Optional[float], now_ts: float) -> float:
    if not ts:
        return 0.45
    age_h = max(0.0, (now_ts - float(ts)) / 3600.0)
    if age_h > HALF_LIFE_H * 2.5:
        return 0.0
    return float(0.5 ** (age_h / HALF_LIFE_H))


def _score_posts(posts: List[Dict[str, Any]], now_ts: float) -> Tuple[float, int, float]:
    obs: List[Tuple[float, float]] = []
    for p in posts:
        text = _entry_text(p)
        pol = _polarity(text)
        if abs(pol) < 1e-9:
            continue
        w = _recency_w(_entry_ts(p), now_ts)
        ups = float(p.get("score") or p.get("ups") or 0.0)
        if ups > 0:
            w *= 1.0 + min(2.0, math.log1p(ups) / 5.0)
        if w > 0:
            obs.append((pol, w))
    if not obs:
        return 0.0, 0, 0.0
    wsum = sum(w for _, w in obs)
    sent = sum(p * w for p, w in obs) / max(wsum, 1e-12)
    conf = min(1.0, len(obs) / 12.0)
    sent = max(-1.0, min(1.0, sent * (0.35 + 0.65 * conf)))
    return round(sent, 4), len(obs), round(conf, 4)


def _mentions(text: str, terms: List[str]) -> bool:
    tl = text.lower()
    for t in terms:
        tok = t.lower()
        if len(tok) <= 2:
            if re.search(rf"\b{re.escape(tok)}\b", tl):
                return True
        elif tok in tl:
            return True
    return False


def collect(*, deep: bool = False, limit: int = 20) -> Dict[str, Any]:
    """Fetch Reddit listings via skill and score basket pairs. Shadow only."""
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    doc = doctor()
    backend = str(doc.get("active_backend") or "unknown")
    oauth = bool(doc.get("oauth_credentials") in (True, "True", "true", "1"))
    if not oauth and deep:
        # deep still allowed but warn — will be slow
        print("deep without OAuth: ~1 req/min — this will take several minutes", file=sys.stderr)

    basket = [str(p) for p in (load_trading_basket() or [])]
    kws = _load_keywords()
    for p in basket:
        kws.setdefault(p, [p.split("-")[0]])

    all_posts: List[Dict[str, Any]] = []
    fetch_log: List[Dict[str, Any]] = []

    subs = list(SUBS_GENERAL)
    if deep or oauth:
        for p in basket:
            for s in SUBS_BY_PAIR.get(p) or []:
                if s not in subs:
                    subs.append(s)

    for i, sub in enumerate(subs):
        t0 = time.time()
        try:
            rows = _run_reddit(["sub", sub, "--sort", "hot", "--limit", str(limit)], timeout=180)
            if isinstance(rows, dict):
                rows = rows.get("entries") or rows.get("posts") or rows.get("data") or []
            if not isinstance(rows, list):
                rows = []
            for r in rows:
                if isinstance(r, dict):
                    r = dict(r)
                    r["_sub"] = sub
                    all_posts.append(r)
            fetch_log.append(
                {
                    "sub": sub,
                    "n": len(rows),
                    "sec": round(time.time() - t0, 2),
                    "ok": True,
                }
            )
        except Exception as e:
            fetch_log.append(
                {
                    "sub": sub,
                    "n": 0,
                    "sec": round(time.time() - t0, 2),
                    "ok": False,
                    "error": str(e)[:160],
                }
            )
        # polite gap even if OAuth (anonymous needs the window)
        if i + 1 < len(subs) and not oauth:
            time.sleep(2)

    # Score per pair
    sentiment: Dict[str, Any] = {}
    for pair in basket:
        terms = kws.get(pair) or [pair.split("-")[0]]
        matched = [
            p
            for p in all_posts
            if _mentions(_entry_text(p), terms)
            or (p.get("_sub") or "").lower()
            in {s.lower() for s in (SUBS_BY_PAIR.get(pair) or [])}
        ]
        # general-sub posts only count if term hit
        sent, n, conf = _score_posts(matched, now_ts)
        sentiment[pair] = {
            "sentiment_score": sent,
            "sentiment": sent,
            "n_posts": n,
            "confidence": conf,
            "source": "reddit_reading",
        }

    payload = {
        "timestamp": now.isoformat(),
        "schema_version": 1,
        "status": "ok" if any(fetch_log and f.get("ok") for f in fetch_log) else "fail",
        "source": "hermes_reddit_reading",
        "backend": backend,
        "oauth": oauth,
        "drives_gates": False,
        "sentiment": sentiment,
        "meta": {
            "skill": str(REDDIT_PY),
            "subs": subs,
            "deep": deep,
            "n_posts_raw": len(all_posts),
            "fetch_log": fetch_log,
            "doctor": {k: doc.get(k) for k in ("active_backend", "oauth_credentials", "ok", "anonymous_feed")},
            "has_textblob": HAS_TB,
            "note": "SHADOW only — display/cross-check; not live buy gates",
        },
    }

    OUT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OUT_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": payload["timestamp"],
                        "backend": backend,
                        "oauth": oauth,
                        "n_posts": len(all_posts),
                        "nz": sum(
                            1
                            for v in sentiment.values()
                            if abs(float(v.get("sentiment") or 0)) > EPS
                        ),
                    }
                )
                + "\n"
            )
    except Exception:
        pass

    # short report
    lines = [
        "# Reddit-reading shadow (Hermes skill)",
        "",
        f"- as_of: `{payload['timestamp']}`",
        f"- backend: **{backend}** · oauth={oauth}",
        f"- posts: {len(all_posts)} · subs: {', '.join(subs)}",
        f"- drives_gates: **false**",
        "",
        "| Pair | Sent | n | conf |",
        "|------|------|---|------|",
    ]
    for pair, e in sentiment.items():
        lines.append(
            f"| {pair} | {e['sentiment']:+.3f} | {e['n_posts']} | {e['confidence']:.2f} |"
        )
    lines += [
        "",
        f"Cache: `{OUT_CACHE}`",
        "",
        "OAuth optional: free script app at reddit.com/prefs/apps → "
        "`REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` in `~/.hermes/.env` "
        "(app credentials only — **no user login**).",
    ]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Reddit-reading shadow collector")
    ap.add_argument("--deep", action="store_true", help="Also hit pair-specific subs (slow without OAuth)")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)
    if args.doctor:
        print(json.dumps(doctor(), indent=2, default=str))
        return 0
    out = collect(deep=bool(args.deep), limit=int(args.limit))
    nz = sum(
        1
        for v in (out.get("sentiment") or {}).values()
        if abs(float(v.get("sentiment") or 0)) > EPS
    )
    print(
        f"reddit_reading_shadow ok backend={out.get('backend')} "
        f"posts={out.get('meta', {}).get('n_posts_raw')} nz_pairs={nz} → {OUT_CACHE}"
    )
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
