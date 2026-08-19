#!/usr/bin/env python3
"""Isolation: daily dose edit package + publish gate (no network)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_publish import (  # noqa: E402
    build_edited_package,
    format_publish_text,
    publish_gate_errors,
    select_items,
    telegram_send_allowed,
    write_edited,
    write_publish_ready,
)


def main() -> int:
    latest = {
        "generated_at": "2026-08-03T12:00:00+00:00",
        "thin_day": False,
        "items": [
            {
                "id": "a1",
                "title": "Strategy sells $395M Bitcoin",
                "source": "cryptoslate.com",
                "url": "https://cryptoslate.com/a1-long-path",
                "tickers": ["BTC-USD"],
                "event_tags": ["treasury_co"],
                "summary": "Strategy sold bitcoin for preferred support",
            },
            {
                "id": "a2",
                "title": "Coldcard exploit day five",
                "source": "www.coindesk.com",
                "url": "https://www.coindesk.com/a2-long",
                "tickers": ["BTC-USD", "ETH-USD"],
                "event_tags": ["hack", "exploit"],
                "summary": "coldcard wallet hack continues",
            },
            {
                "id": "a3",
                "title": "Filler roundup should drop",
                "source": "cointelegraph.com",
                "url": "https://example.com/a3",
                "tickers": [],
            },
            {
                "id": "a4",
                "title": "BlackRock liquidates BTC",
                "source": "u.today",
                "url": "https://u.today/a4",
                "tickers": ["BTC-USD"],
                "event_tags": ["liquidation", "institution"],
            },
            {
                "id": "a5",
                "title": "Solana ETF structure update",
                "source": "decrypt.co",
                "url": "https://decrypt.co/a5-sol-etf",
                "tickers": ["SOL-USD"],
                "event_tags": ["etf"],
            },
            {
                "id": "a6",
                "title": "Bitcoin flirts with $64,000 as stocks open higher",
                "source": "coindesk.com",
                "url": "https://www.coindesk.com/a6",
                "tickers": ["BTC-USD"],
            },
            {
                "id": "a7",
                "title": "Bitcoin tests $63,000 into the close",
                "source": "coindesk.com",
                "url": "https://www.coindesk.com/a7",
                "tickers": ["BTC-USD"],
            },
            {
                "id": "a8",
                "title": "Bitcoin hovers near $62,500",
                "source": "x",
                "url": "https://example.com/a8",
                "tickers": ["BTC-USD"],
            },
            {
                "id": "a9",
                "title": "Ethereum staking inflows climb",
                "source": "blockworks.co",
                "url": "https://blockworks.co/eth-stake",
                "tickers": ["ETH-USD"],
            },
        ],
        "meta": {"method": "test", "basket": ["BTC-USD", "SOL-USD", "ETH-USD"]},
    }

    got = select_items(latest["items"], drop_ids=["a3"], top_n=5)
    assert len(got) <= 5
    assert all(i["id"] != "a3" for i in got)
    assert all(not i.get("why_it_matters_platform") for i in got)
    tape = sum(1 for i in got if i.get("story_lane") == "btc_tape")
    assert tape <= 2, [(i["id"], i.get("story_lane")) for i in got]
    btc_only = sum(
        1 for i in got if set(i.get("tickers") or []) == {"BTC-USD"} or not i.get("tickers")
    )
    assert btc_only <= 2, [(i["id"], i.get("tickers")) for i in got]

    pkg = build_edited_package(
        latest,
        status="APPROVED",
        reviewer="content-editor",
        notes="isolation basket diversity + domain links",
        drop_ids=["a3"],
        top_n=5,
        title_overrides={"a4": "BlackRock sells $122M Bitcoin as clients cut losses"},
    )
    assert pkg["editorial_review"]["status"] == "APPROVED"
    assert len(pkg["items"]) <= 5
    assert "a3" not in [i["id"] for i in pkg["items"]]
    assert pkg["editorial_review"]["checklist"]["diversity_btc_tape_max_2"] is True
    assert pkg["editorial_review"]["checklist"]["diversity_btc_only_max_2"] is True
    assert pkg["meta"].get("why_framing") == "retired"
    assert pkg["meta"].get("link_style") == "domain_markdown"
    assert publish_gate_errors(pkg) == []

    bad = build_edited_package(latest, status="REVISE", reviewer="ed", top_n=3)
    assert publish_gate_errors(bad)
    assert "APPROVED" in publish_gate_errors(bad)[0]

    text = format_publish_text(pkg)
    assert "Not a trade signal" in text
    assert "Why it matters on this platform" not in text
    assert (
        "[cryptoslate.com](" in text
        or "[coindesk.com](" in text
        or "[decrypt.co](" in text
        or "[blockworks.co](" in text
    )
    assert "Filler roundup" not in text
    for line in text.splitlines():
        if line.strip().startswith("http"):
            raise AssertionError(f"raw URL line should be hidden in domain link: {line}")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        edited = td_path / "edited.json"
        ready = td_path / "ready.txt"
        write_edited(pkg, edited)
        data = json.loads(edited.read_text())
        assert data["editorial_review"]["status"] == "APPROVED"
        write_publish_ready(text, ready)
        assert ready.is_file() and "Daily dose" in ready.read_text()

        flag = td_path / "ok.flag"
        ok, reason = telegram_send_allowed(
            env_flag="PUBLISH_TELEGRAM_TEST_NEVER",
            brad_ok_flag_path=flag,
            cli_allow=False,
        )
        assert not ok and "cli" in reason

    print("PASS test_isolation_daily_dose_publish")
    print("  items", [i["id"] for i in pkg["items"]])
    print("  lanes", [i.get("story_lane") for i in pkg["items"]])
    print("  primaries", [i.get("primary_pair") for i in pkg["items"]])
    print("  sample:\n", "\n".join(text.splitlines()[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
