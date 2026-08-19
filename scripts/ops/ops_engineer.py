#!/usr/bin/env python3
"""
Operations Engineer Agent (Low-Cost, Competent)

Owns smooth running of actively running processes (starting with Phase 6 trading runner + monitors).

Core mandate (per role definition):
- Monitor logs for error conditions and alert.
- Diagnose issues accurately (state vs claim, root cause, not symptoms).
- Open Trouble Tickets (GitHub via gh CLI when auth'd; always durable record in MASTER_TASK_TRACKING.md).
- Escalate to Orchestration Agent / human (Telegram) when necessary.
- Verify that resolved tickets are actually fixed post-deploy.

Design for low cost + competence:
- 95%+ deterministic rules + log/state inspection (no LLM on every tick).
- LLM only for optional nice ticket body drafting on *new* troubles (cheap model).
- Heavy use of real tool output (ps, tail logs, json state, pgrep, journal if available).
- Strict "verify with tools" discipline.
- Idempotent: tracks seen troubles in a small state file to avoid duplicate tickets.
- Supports --verify <ticket> for post-deploy confirmation.

Run manually or via cron (recommended: every 10-15 min as Hermes cron with no_agent or cheap model).
"""

import os
import sys
import json
import subprocess
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

# === CONFIG (easy to extend for more processes) ===
PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
LOGS_DIR = PROJECT_ROOT / "logs"
STATE_DIR = PROJECT_ROOT / "data" / "state"
OPS_STATE = Path.home() / ".hermes" / "ops_engineer_state.json"  # seen troubles, last checks
MASTER_TASKS = PROJECT_ROOT / "docs" / "MASTER_TASK_TRACKING.md"

# Processes / monitors we own
TARGETS = {
    "phase6_runner": {
        "pgrep_pattern": r"phase6\.core\.phase6_runner|phase6_runner\.py",
        "log": LOGS_DIR / "phase6_runner_error.log",
        "main_log": LOGS_DIR / "phase6_runner.log",
        "state_file": STATE_DIR / "phase6_runner_state.json",
        "service": "phase6-runner",
    },
    "phase6_monitor": {
        "pgrep_pattern": r"monitor_phase6_runner\.py",
        "log": LOGS_DIR / "monitor.log",  # may be general
    },
}

# Known bad patterns (expand as we learn more from real incidents)
ERROR_PATTERNS = [
    {
        "id": "REBALANCE_STALE_36H",
        "severity": "WARNING",
        "regex": r"No rebalance detected in the last 36 hours",
        "diagnosis": "last_rebalance_date in phase6_runner_state.json is >~36h old. Rebalance window (09:00) likely missed or crashed before state update.",
        "common_root": "Coinbase client broken (missing get_accounts), unverified holdings causing ValueError in reserve/CR-03 paths, or calendar check + no persist.",
    },
    {
        "id": "UNVERIFIED_FLOAT_ERROR",
        "severity": "CRITICAL",
        "regex": r"could not convert string to float: 'Unverified or error'",
        "diagnosis": "LivePortfolioManager returned verified=False sentinel (error string) and rebalance/reserve code did float() or .get() on it.",
        "common_root": "exchange_client.get_holdings_verified always fails because coinbase_wrapper_FIXED lacks get_accounts() (or 401s on /brokerage/accounts).",
    },
    {
        "id": "NO_GET_ACCOUNTS",
        "severity": "CRITICAL",
        "regex": r"no attribute 'get_accounts'|Failed to fetch live balance/holdings",
        "diagnosis": "CoinbaseWrapper_FIXED (the live one) is missing get_accounts implementation that exchange_client + LPM depend on.",
        "common_root": "Incomplete port of wrapper during auth/order fixes. Holdings always unverified=True in live mode.",
    },
    {
        "id": "COINBASE_401",
        "severity": "HIGH",
        "regex": r"401 Unauthorized|Unauthorized",
        "diagnosis": "JWT / API key rejected by Coinbase Advanced Trade endpoints (accounts, orders/historical/batch).",
        "common_root": "API key permissions insufficient (needs accounts:read, orders:read/trade), wrong key format, or PEM newlines.",
    },
    {
        "id": "RUNNER_NOT_RUNNING",
        "severity": "CRITICAL",
        "regex": None,  # special cased via pgrep
        "diagnosis": "Target process not visible via pgrep.",
        "common_root": "systemd crash loop, OOM, unhandled exception at startup, or manual stop.",
    },
    {
        "id": "CYCLE_ERRORS_SPIKE",
        "severity": "HIGH",
        "regex": r"Cycle error:",
        "diagnosis": "Repeated exceptions inside _run_cycle (caught but logged). Rebalance or critical path may be silently degraded.",
        "common_root": "See accompanying traceback (often the unverified or 401 cases above).",
    },
]

# Telegram (reuse existing pattern from monitors)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[OPS] Telegram not configured — printing instead")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        import requests
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"[OPS] Telegram failed: {e}")

def run_cmd(cmd: list[str], timeout=15) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return out.strip()
    except Exception as e:
        return f"ERROR: {e}"

def is_process_running(pattern: str) -> bool:
    out = run_cmd(["pgrep", "-f", pattern])
    return bool(out.strip() and "ERROR" not in out)

def tail_log(path: Path, lines=200) -> str:
    if not path.exists():
        return ""
    return run_cmd(["tail", f"-{lines}", str(path)])

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except:
        return {}

def load_ops_state() -> dict:
    if not OPS_STATE.exists():
        return {"seen_troubles": {}, "last_run": None}
    try:
        return json.loads(OPS_STATE.read_text())
    except:
        return {"seen_troubles": {}, "last_run": None}

def save_ops_state(state: dict):
    OPS_STATE.parent.mkdir(parents=True, exist_ok=True)
    OPS_STATE.write_text(json.dumps(state, indent=2, default=str))

def append_to_master_tracking(ticket: dict):
    """Append a durable Trouble Ticket record to the master list (user's preferred source of truth)."""
    now = datetime.now().isoformat()
    entry = f"""

---

**OPS ENGINEER — TROUBLE TICKET {ticket['id']}** (opened {now})
**Severity**: {ticket['severity']}
**Title**: {ticket['title']}
**Diagnosis (verified via tools)**: {ticket['diagnosis']}
**Common Root Causes**: {ticket['common_root']}
**Evidence** (recent log snippets + state):
```
{ticket.get('evidence', 'see logs')}
```
**Suggested Next**:
- Restart affected service + clear __pycache__ if code change deployed.
- Verify with: `python scripts/ops/ops_engineer.py --verify {ticket['id']}`
- Escalate to Orchestrator if not resolved in 1 cycle.
**Status**: OPEN (auto-created by ops-engineer)

See full context in logs/ and phase6/core/ related files.
"""
    with open(MASTER_TASKS, "a") as f:
        f.write(entry)
    print(f"[OPS] Appended {ticket['id']} to MASTER_TASK_TRACKING.md")

def try_create_github_ticket(ticket: dict) -> str | None:
    """Attempt real GitHub issue. Returns issue URL or None."""
    title = f"[OPS] {ticket['id']}: {ticket['title']}"
    body = f"""**Automated Trouble Ticket from Operations Engineer Agent**

**Severity**: {ticket['severity']}
**Opened**: {datetime.now().isoformat()}
**Diagnosis**: {ticket['diagnosis']}
**Likely Root Cause**: {ticket['common_root']}

**Verified Evidence** (from live tools at open time):
{ticket.get('evidence', '(see attached logs in follow-up)')}

**Reproduction / Verification**:
- `cd /home/brad/projects/crypto-trading-bot`
- `python scripts/ops/ops_engineer.py --verify {ticket['id']}` (post any fix)
- Check state: `cat data/state/phase6_runner_state.json`
- Recent errors: `tail -100 logs/phase6_runner_error.log`

**Impact**: Phase 6 daily rebalance (and potentially other cycles) not completing reliably. Warnings spamming Telegram.

**Owner**: Operations Engineer (this agent). Escalate to Orchestrator / human if blocked.

*This ticket was auto-filed by the low-cost ops-engineer role. Real data only.*
"""
    labels = "ops,trouble,phase6,monitoring"

    # Try gh CLI first
    cmd = ["gh", "issue", "create", "--repo", "brad-slusher/crypto-trading-bot", "--title", title, "--body", body, "--label", labels]
    result = run_cmd(cmd, timeout=20)
    if "https://github.com" in result or "created" in result.lower():
        print(f"[OPS] GitHub ticket created: {result}")
        return result.strip()
    else:
        print(f"[OPS] gh create failed (likely auth): {result[:200]}")
        # Fallback: print full ticket for manual or future gh
        print("=== FULL TICKET BODY (copy to gh manually) ===")
        print(body)
        return None

def diagnose_target(name: str, cfg: dict, recent_logs: str) -> list[dict]:
    """Return list of active troubles for this target, with diagnosis."""
    troubles = []
    state = load_json(Path(cfg.get("state_file", ""))) if cfg.get("state_file") else {}

    # Process health
    if not is_process_running(cfg.get("pgrep_pattern", name)):
        troubles.append({
            "id": f"{name.upper()}_DOWN",
            "severity": "CRITICAL",
            "title": f"{name} process not running",
            "diagnosis": "pgrep found no matching process.",
            "common_root": "systemd restart loop, uncaught exception, OOM, or explicit stop.",
            "evidence": run_cmd(["ps", "aux", "|", "grep", "-E", cfg.get("pgrep_pattern", "")])[:500],
        })

    # State-based (rebalance staleness)
    if "last_rebalance_date" in state:
        try:
            last = datetime.fromisoformat(state["last_rebalance_date"]).date()
            days = (datetime.now().date() - last).days
            if days >= 2:
                troubles.append({
                    "id": "REBALANCE_STALE_36H",
                    "severity": "WARNING",
                    "title": "No rebalance detected in the last 36+ hours (state stale)",
                    "diagnosis": "last_rebalance_date too old relative to today.",
                    "common_root": ERROR_PATTERNS[0]["common_root"],
                    "evidence": json.dumps(state, indent=2),
                })
        except:
            pass

    # Pattern scan on recent error log
    for pat in ERROR_PATTERNS:
        if pat["regex"] and re.search(pat["regex"], recent_logs, re.I):
            troubles.append({
                "id": pat["id"],
                "severity": pat["severity"],
                "title": pat["id"].replace("_", " "),
                "diagnosis": pat["diagnosis"],
                "common_root": pat["common_root"],
                "evidence": recent_logs[-1500:],  # last chunk
            })

    # Dedup by id within this target
    seen = set()
    unique = []
    for t in troubles:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    return unique

def main():
    print(f"[OPS ENGINEER] Starting at {datetime.now().isoformat()}")
    ops_state = load_ops_state()
    all_troubles = []

    for name, cfg in TARGETS.items():
        log_path = cfg.get("log") or cfg.get("main_log")
        recent = tail_log(Path(log_path)) if log_path else ""
        troubles = diagnose_target(name, cfg, recent)
        for t in troubles:
            t["target"] = name
            all_troubles.append(t)

    # Signal DQ (defer streak / coverage) — deterministic, cooldown inside module
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from phase6.core.signal_dq_monitor import evaluate_signal_dq

        dq = evaluate_signal_dq(
            log_path=LOGS_DIR / "phase6_runner.log",
            state_path=STATE_DIR / "signal_dq_monitor.json",
            min_streak=3,
            cooldown_minutes=60,
        )
        print(f"[OPS] SIGNAL-DQ: {dq.message}")
        if dq.should_alert:
            all_troubles.append(
                {
                    "id": "REBALANCE_DEFER_STREAK",
                    "severity": "WARNING" if dq.level != "critical" else "HIGH",
                    "title": "Rebalance deferred repeatedly (signal data quality)",
                    "diagnosis": dq.message,
                    "common_root": (
                        "Missing RSI/sentiment or refresher failure; "
                        "see phase6.core.signal_dq_monitor + scripts/refresh_rsi_prices.py"
                    ),
                    "evidence": dq.message,
                    "target": "phase6_runner",
                }
            )
    except Exception as e:
        print(f"[OPS] SIGNAL-DQ check failed: {e}")

    if not all_troubles:
        print("[OPS] No active error conditions detected. Systems nominal.")
        ops_state["last_run"] = datetime.now().isoformat()
        save_ops_state(ops_state)
        return

    print(f"[OPS] Detected {len(all_troubles)} trouble condition(s).")

    for t in all_troubles:
        ticket_id = f"OPS-{t['target'].upper()}-{t['id']}-{datetime.now().strftime('%Y%m%d')}"
        if ticket_id in ops_state.get("seen_troubles", {}):
            print(f"[OPS] {ticket_id} already seen — skipping duplicate ticket.")
            continue

        ticket = {
            "id": ticket_id,
            "severity": t["severity"],
            "title": t["title"],
            "diagnosis": t["diagnosis"],
            "common_root": t.get("common_root", ""),
            "evidence": t.get("evidence", ""),
            "target": t["target"],
        }

        # 1. Durable record (always)
        append_to_master_tracking(ticket)

        # 2. GitHub ticket (best effort)
        gh_url = try_create_github_ticket(ticket)
        if gh_url:
            ticket["github_url"] = gh_url

        # 3. Alert human / orchestrator
        alert = f"🚨 {ticket['severity']} OPS TICKET: {ticket['id']}\n{ticket['title']}\nDiagnosis: {ticket['diagnosis']}\nRoot: {ticket['common_root'][:200]}...\nMaster updated. GitHub: {gh_url or 'pending (auth?)'}"
        send_telegram(alert)

        # Mark seen (prevents spam on every tick)
        ops_state.setdefault("seen_troubles", {})[ticket_id] = {
            "opened": datetime.now().isoformat(),
            "github": gh_url,
        }

    ops_state["last_run"] = datetime.now().isoformat()
    save_ops_state(ops_state)
    print("[OPS] Run complete. Troubles recorded + alerted.")

def verify(ticket_id: str):
    """Post-deploy verification: re-scan and report if the condition for this ticket is gone."""
    print(f"[OPS VERIFY] Checking resolution of {ticket_id} at {datetime.now()}")
    # Simple heuristic: re-run main logic and see if that exact id pattern would still fire
    # For real use, parse the ticket id back to patterns and re-check state/logs.
    # Here we just re-diagnose everything and report status.
    main()
    print(f"[OPS VERIFY] Re-scan complete. If the original condition (stale state, unverified float, missing get_accounts, etc.) no longer appears in the output above, the ticket can be closed.")
    print("Recommend: update MASTER_TASK_TRACKING.md with 'VERIFIED FIXED' + date, and close GitHub issue manually or via gh.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        ticket = sys.argv[2] if len(sys.argv) > 2 else "ALL"
        verify(ticket)
    else:
        main()
