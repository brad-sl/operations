"""Deterministic trader-facing message composition — NO AI / NO LLM.

Contract (Brad / platform scale):
  • Every dashboard, IM (Telegram/etc.), and email line is composed by **script**.
  • Inputs = structured facts only (numbers, codes, pair lists).
  • Output = plain text from fixed templates.
  • Same facts → same bytes (deterministic).
  • Fast: pure CPU, no network, no model calls.
  • Accurate: never invent holdings, regimes, or prices — only format what was passed in.
  • Scalable: O(reasons) string joins; safe for 1k accounts per cycle.

AI agents may *change templates in git*; they must not sit in the live message path.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

# Explicit ban-list for live path audits / greps
COMPOSER_NO_AI = True
COMPOSER_ENGINE = "template_v1"


def _pair_short(pair: str) -> str:
    p = str(pair or "").strip()
    if p.endswith("-USD"):
        return p[: -len("-USD")]
    if p.endswith("-USDC"):
        return p[: -len("-USDC")]
    return p


def _join_pairs(pairs: Sequence[str], *, limit: int = 6) -> str:
    shorts = [_pair_short(p) for p in pairs if p][:limit]
    if not shorts:
        return ""
    body = ", ".join(shorts)
    if len(pairs) > limit:
        body += "…"
    return body


def _pct(v: Any, *, signed: bool = True, digits: int = 1) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if signed:
        return f"{x:+.{digits}f}%"
    return f"{x:.{digits}f}%"


def render_reason_line(reason: Mapping[str, Any], *, channel: str = "dashboard") -> str:
    """One bullet. Prefer precomposed title/detail (from facts layer); never call a model."""
    title = str(reason.get("title") or reason.get("code") or "").strip()
    detail = str(reason.get("detail") or "").strip()
    # Strip markdown leftovers if any
    detail = detail.replace("**", "")
    if not title:
        return detail
    if not detail:
        return title
    if channel in ("telegram", "sms", "push"):
        # Slightly tighter for IM
        if len(detail) > 220:
            detail = detail[:217].rstrip() + "…"
        return f"• {title} — {detail}"
    if channel == "email":
        return f"<li><strong>{_escape_html(title)}</strong> — {_escape_html(detail)}</li>"
    # dashboard / default plain
    return f"{title} — {detail}"


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compose_why_cash_channels(why: Mapping[str, Any]) -> Dict[str, Any]:
    """Build channel payloads from a why_idle / why_cash facts dict.

    Expected keys (all optional except we degrade gracefully):
      headline, reasons[{title,detail,code,severity}], heat, posture, cream, book, scale_faq
    """
    headline = str(why.get("headline") or "Account status update.").strip()
    reasons: List[Mapping[str, Any]] = list(why.get("reasons") or [])
    heat = why.get("heat") if isinstance(why.get("heat"), dict) else {}
    posture = why.get("posture") if isinstance(why.get("posture"), dict) else {}
    cream = why.get("cream") if isinstance(why.get("cream"), dict) else {}
    book = why.get("book") if isinstance(why.get("book"), dict) else {}
    faq = str(why.get("scale_faq") or "").strip()

    # --- dashboard (structured; UI binds fields) ---
    dash_reasons = [
        {
            "code": r.get("code"),
            "title": r.get("title"),
            "detail": r.get("detail"),
            "severity": r.get("severity"),
            "line": render_reason_line(r, channel="dashboard"),
        }
        for r in reasons
    ]

    # --- telegram / plain IM ---
    tg_lines = [headline, ""]
    for r in reasons[:6]:
        tg_lines.append(render_reason_line(r, channel="telegram"))
    # compact footer facts (still plain language)
    btc_h = heat.get("btc_change_24h_pct")
    park = posture.get("park")
    cream_n = cream.get("shadow_would_buy_count")
    footer_bits = []
    if btc_h is not None:
        footer_bits.append(f"Bitcoin today {_pct(btc_h)}")
    if park is True:
        footer_bits.append("plan: holding cash")
    elif park is False:
        footer_bits.append("plan: open to careful buys")
    if cream_n is not None:
        footer_bits.append(f"buy checklist open: {int(cream_n)}")
    held = book.get("held_pairs") or []
    if held:
        footer_bits.append("held: " + _join_pairs([str(p) for p in held], limit=5))
    if footer_bits:
        tg_lines.append("")
        tg_lines.append(" · ".join(footer_bits))
    if faq:
        tg_lines.append("")
        tg_lines.append(faq)
    telegram_text = "\n".join(tg_lines).strip() + "\n"

    # --- email (simple HTML body; subject separate) ---
    subject = headline if len(headline) <= 90 else headline[:87].rstrip() + "…"
    li = "\n".join(render_reason_line(r, channel="email") for r in reasons[:8])
    email_html = (
        f"<p>{_escape_html(headline)}</p>\n"
        f"<ul>\n{li}\n</ul>\n"
        + (f"<p><em>{_escape_html(faq)}</em></p>\n" if faq else "")
    )
    email_text = telegram_text  # plain multipart twin

    # --- short push / SMS ---
    sms = headline
    if len(sms) > 160:
        sms = sms[:157].rstrip() + "…"

    return {
        "engine": COMPOSER_ENGINE,
        "no_ai": COMPOSER_NO_AI,
        "deterministic": True,
        "dashboard": {
            "headline": headline,
            "reasons": dash_reasons,
            "scale_faq": faq,
        },
        "telegram": {
            "text": telegram_text,
            "parse_mode": None,  # plain text — no HTML entity surprises
            "disable_web_page_preview": True,
        },
        "email": {
            "subject": subject,
            "text": email_text,
            "html": email_html,
        },
        "push": {"body": sms},
        "sms": {"body": sms},
    }


def compose_from_why_idle(why: Mapping[str, Any]) -> Dict[str, Any]:
    """Alias — facts dict from market_posture_explain.build_why_idle."""
    return compose_why_cash_channels(why)


def compose_bear_tp_channels(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Bear profit-take shadow → dashboard / IM / email (no AI).

    Expected keys from bear_profit_take_shadow.run_bear_profit_take_cycle:
      plain_english, regime, status, new_episodes, n_new_episodes,
      proceeds_destination, rebuy_block_hours, orders_placed
    """
    pe = str(result.get("plain_english") or "").strip()
    reg = str(result.get("regime") or "unknown")
    status = str(result.get("status") or "")
    n_new = int(result.get("n_new_episodes") or 0)
    dest = str(result.get("proceeds_destination") or "cash")
    block_h = int(result.get("rebuy_block_hours") or 72)

    if status == "idle_wrong_regime":
        headline = (
            "Profit ladder is on standby — it only arms in a clear down-market regime."
        )
    elif status == "off":
        headline = "Bear profit-take playbook is turned off."
    elif n_new > 0:
        headline = (
            "Down-market playbook (shadow only): we'd take some profit on strength. "
            "No real sell placed."
        )
    else:
        headline = (
            "Down-market watch is on. No new partial take-profit levels hit this check."
        )

    if pe:
        headline = pe if len(pe) < 220 else headline

    reasons: List[Dict[str, Any]] = []
    for ep in list(result.get("new_episodes") or [])[:6]:
        if ep.get("kind") and ep.get("kind") != "ladder_scale_out":
            continue
        pair = _pair_short(str(ep.get("pair") or ""))
        try:
            r = float(ep.get("r") or 0) * 100.0
            frac = float(ep.get("sell_frac") or 0) * 100.0
            usd = float(ep.get("would_exit_usd") or 0)
        except (TypeError, ValueError):
            r, frac, usd = 0.0, 0.0, 0.0
        reasons.append(
            {
                "code": "ladder_scale_out",
                "title": f"Would trim {pair}",
                "detail": (
                    f"Up about {r:.1f}% from your entry — rules say sell ~{frac:.0f}% "
                    f"(about ${usd:.0f}), keep a leftover bag, park proceeds in {dest}, "
                    f"and don't rush back in for ~{block_h}h."
                ),
                "severity": "primary",
            }
        )

    if not reasons:
        reasons.append(
            {
                "code": "bear_standby" if status == "idle_wrong_regime" else "bear_watch",
                "title": "No new trim this cycle",
                "detail": (
                    f"Regime={reg}. Ladder arms only in a down market; "
                    "partial sells are rule-based, not a short."
                ),
                "severity": "secondary",
            }
        )

    faq = (
        "In a long down market we prefer taking some profit on temporary green days "
        "instead of hoping for a perfect top — and we don't short."
    )
    facts = {
        "headline": headline,
        "reasons": reasons,
        "heat": {},
        "posture": {"park": True},
        "cream": {},
        "book": {},
        "scale_faq": faq,
    }
    out = compose_why_cash_channels(facts)
    out["feature"] = "bear_profit_take"
    out["orders_placed"] = bool(result.get("orders_placed"))
    return out


def assert_no_ai_imports() -> None:
    """Lightweight self-check for isolation tests (not a full security sandbox)."""
    import sys

    banned = (
        "openai",
        "anthropic",
        "litellm",
        "langchain",
        "hermes_tools",
        "groq",
    )
    bad = [n for n in banned if n in sys.modules]
    if bad:
        raise RuntimeError(f"AI modules loaded in composer process: {bad}")
