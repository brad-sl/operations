"""
Daily Dose D2 — publisher (disk ship; Telegram gated).

Reads data/state/daily_dose_edited.json
Requires editorial_review.status == APPROVED
Writes data/state/daily_dose_publish_ready.txt

Telegram live send requires ALL of:
  --allow-telegram
  env PUBLISH_TELEGRAM=1
  data/state/daily_dose_brad_telegram_ok.flag exists

With those + --live-telegram: hermes send -t telegram.
Without --live-telegram: stub only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.daily_dose_publish import (  # noqa: E402
    append_publish_history,
    format_publish_text,
    hermes_telegram_send,
    load_edited,
    publish_gate_errors,
    stub_telegram_send,
    telegram_send_allowed,
    write_publish_ready,
)
from phase6.core.paths import (  # noqa: E402
    DAILY_DOSE_BRAD_TG_OK,
    DAILY_DOSE_EDITED,
    DAILY_DOSE_PUBLISH_READY,
)

ENV_TG = "PUBLISH_TELEGRAM"


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose D2 publisher")
    ap.add_argument("--input", type=Path, default=DAILY_DOSE_EDITED)
    ap.add_argument("--output", type=Path, default=DAILY_DOSE_PUBLISH_READY)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--print", action="store_true", dest="do_print")
    ap.add_argument(
        "--allow-telegram",
        action="store_true",
        help="Permit TG path (still needs env + Brad OK flag)",
    )
    ap.add_argument(
        "--live-telegram",
        action="store_true",
        help="Actually hermes-send when gates pass",
    )
    ap.add_argument(
        "--force-live-telegram",
        action="store_true",
        help="Alias of --live-telegram",
    )
    ap.add_argument(
        "--telegram-target",
        default="telegram",
        help="hermes send -t target (default: telegram home)",
    )
    args = ap.parse_args()
    live = bool(args.live_telegram or args.force_live_telegram)

    pkg = load_edited(args.input)
    errs = publish_gate_errors(pkg)
    if errs:
        print("PUBLISH BLOCKED:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2

    text = format_publish_text(pkg, max_bullets=args.top)
    out = write_publish_ready(text, args.output)

    tg_attempted = False
    tg_sent = False
    if args.allow_telegram:
        ok, reason = telegram_send_allowed(
            env_flag=ENV_TG,
            brad_ok_flag_path=DAILY_DOSE_BRAD_TG_OK,
            cli_allow=True,
        )
        tg_attempted = True
        if not ok:
            print(f"Telegram not sent: {reason}")
        elif not live:
            result = stub_telegram_send(text)
            tg_sent = bool(result.get("sent"))
            print(f"Telegram path: allowed but stubbed → {result}")
        else:
            result = hermes_telegram_send(text, target=args.telegram_target)
            tg_sent = bool(result.get("sent"))
            print(f"Telegram live send → {result}")
    else:
        print("Telegram: OFF (default)")

    append_publish_history(
        pkg,
        publish_path=out,
        telegram_attempted=tg_attempted,
        telegram_sent=tg_sent,
    )
    print(f"Publish ready → {out} items={len(pkg.get('items') or [])}")
    if args.do_print:
        print("--- publish_ready ---")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
