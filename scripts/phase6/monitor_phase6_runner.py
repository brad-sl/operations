#!/usr/bin/env python3
"""
Phase 6 Runner Monitoring Agent

Duties:
- Check if the main Phase6Runner is running
- Verify last rebalance timestamp is recent (respect daily 9am schedule + grace)
- Detect excessive errors in logs
- Send alerts via Telegram on issues

Mitigation Strategies:
- Auto-restart runner if down (optional)
- Trigger manual rebalance if overdue
- Escalate to human via Telegram if critical

Escalation Path:
1. Warning → Telegram alert
2. Critical → Telegram + log to file
3. Persistent failure → Human intervention required
"""

import os
import sys
import time
import signal
import subprocess
import requests
import json
from datetime import datetime, timedelta, time as dt_time
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUNNER_LOG = "logs/phase6_runner.log"
STATE_FILE = "data/state/phase6_live_state.json"  # prefer live state (updated for accuracy)

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[MONITOR] Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"[MONITOR] Telegram send failed: {e}")

def is_process_alive(pid: int) -> bool:
    """Check if a PID is currently running (portable, no ps)."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        return False

def get_runner_pids() -> list:
    """Return list of PIDs for *actual running* phase6 runners.
    Very strict filter to avoid false positives from:
    - monitor's own python process or subprocess
    - investigation python -c commands that contain the search string
    - bash launchers
    Only count processes launched with the real '-m phase6.core.phase6_runner' pattern.
    """
    pids = []
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            # Strict: must have the actual module launch with -m
            if ("-m phase6.core.phase6_runner" in line 
                and "python" in line 
                and "grep" not in line 
                and " -c " not in line 
                and "monitor_phase6_runner" not in line.lower()
                and "bash" not in line.lower()):
                parts = line.split()
                if len(parts) > 1 and parts[1].isdigit():
                    pids.append(parts[1])
        # Strict pgrep fallback: exact launch pattern
        result = subprocess.run(["pgrep", "-f", "-m phase6.core.phase6_runner"], capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            if line.strip() and line.strip().isdigit():
                pid = line.strip()
                try:
                    with open(f"/proc/{pid}/cmdline", "r") as f:
                        cmd = f.read().replace("\x00", " ")
                    if "-m phase6.core.phase6_runner" in cmd and "python" in cmd and "monitor" not in cmd.lower():
                        pids.append(pid)
                except:
                    pass
    except Exception as e:
        print(f"[MONITOR] ps/pgrep error: {e}")
    unique = sorted(set([p for p in pids if p]))
    return unique


def _proc_cmdline(pid: str) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "r") as f:
            return f.read().replace("\x00", " ")
    except OSError:
        return ""


def remediate_duplicate_runners(pids: list) -> tuple:
    """Keep canonical .venv runner; SIGTERM extras (e.g. systemd /usr/bin/python3)."""
    if len(pids) < 2:
        return (pids[0] if pids else None, [])

    scored = []
    for pid in pids:
        cmd = _proc_cmdline(pid)
        score = 0
        if ".venv" in cmd or "venv/bin/python" in cmd:
            score += 10
        if cmd.startswith("/usr/bin/python3") or " /usr/bin/python3 " in cmd:
            score -= 5
        scored.append((score, pid, cmd))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    keep = scored[0][1]
    killed = []
    for _, pid, cmd in scored[1:]:
        try:
            os.kill(int(pid), signal.SIGTERM)
            killed.append(pid)
            print(f"[MONITOR] Terminated duplicate runner pid={pid} cmd={cmd[:120]!r}")
        except OSError as e:
            print(f"[MONITOR] Failed to kill duplicate pid={pid}: {e}")
    time.sleep(2)
    return keep, killed

def is_runner_running() -> bool:
    pids = get_runner_pids()
    return len(pids) > 0

def check_last_rebalance() -> bool:
    """Returns True if healthy (suppress alert).
    Supports daily_rebalance_times list for 2x daily (9am & 9pm).
    Uses latest target for grace period check.
    """
    if not os.path.exists(STATE_FILE):
        return False
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        last = state.get("last_rebalance_date")
        if not last:
            # Fallback to runner_state (more authoritative for date)
            try:
                with open("data/state/phase6_runner_state.json") as rf:
                    rs = json.load(rf)
                last = rs.get("last_rebalance_date")
            except:
                pass
        if not last:
            return False
        last_date = datetime.fromisoformat(last).date()
        now = datetime.now()
        today = now.date()

        # Load real schedule - support list for 2x daily
        rebalance_times = ["09:00", "21:00"]
        try:
            with open("config/trading_config_phase6.json") as cf:
                cfg = json.load(cf)
            rebalance_times = cfg.get("scheduler", {}).get("daily_rebalance_times", [cfg.get("scheduler", {}).get("daily_rebalance_time", "09:00")])
        except Exception:
            pass
        # Use the latest time for today's window check
        latest_time_str = sorted(rebalance_times)[-1]
        target = dt_time.fromisoformat(latest_time_str)
        grace_delta = timedelta(hours=1)

        if last_date == today:
            return True
        days = (today - last_date).days
        if days <= 0:
            return True
        if days == 1:
            # Yesterday's last; today's latest window + grace not yet passed -> healthy
            target_dt = datetime.combine(today, target) + grace_delta
            if now < target_dt:
                return True
            else:
                return False
        # >1 day stale
        return False
    except Exception:
        return False

def check_pid_files() -> list:
    """Report stale or mismatched pid files vs live processes."""
    issues = []
    pid_files = ["logs/phase6_runner.pid", "phase6_live.pid"]
    live_pids = set(get_runner_pids())
    for pf in pid_files:
        if not os.path.exists(pf):
            # try absolute project path fallback (cron may run with different cwd)
            abs_pf = f"/home/brad/projects/crypto-trading-bot/{pf}"
            if os.path.exists(abs_pf):
                pf = abs_pf
            else:
                continue
        try:
            with open(pf) as f:
                pid_str = f.read().strip()
            if pid_str:
                pid = int(pid_str)
                if not is_process_alive(pid):
                    issues.append(f"Stale pidfile {pf}: {pid} (not running)")
                elif str(pid) not in live_pids and live_pids:
                    issues.append(f"pidfile {pf}={pid} not matching live pids {live_pids}")
        except Exception as e:
            issues.append(f"Bad/unreadable pidfile {pf}: {e}")
    return issues

def main():
    print(f"[MONITOR] Phase 6 Monitoring Agent started at {datetime.now()}")

    pids = get_runner_pids()
    count = len(pids)
    if count == 0:
        msg = "🚨 CRITICAL: Phase 6 Runner is NOT running!"
        print(msg)
        pid_issues = check_pid_files()
        if pid_issues:
            print("[MONITOR] PID issues:", "; ".join(pid_issues))
        # Auto-restart canonical launcher (singleton-safe)
        start_sh = os.path.join(os.getcwd(), "scripts/phase6/start_phase6_runner.sh")
        project_root = os.getcwd()
        if not os.path.isfile(start_sh):
            project_root = "/home/brad/projects/crypto-trading-bot"
            start_sh = os.path.join(project_root, "scripts/phase6/start_phase6_runner.sh")
        if os.path.isfile(start_sh):
            try:
                proc = subprocess.run(
                    ["bash", start_sh],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                print("[MONITOR] Auto-restart attempt:", out.strip()[:500])
                time.sleep(3)
                if get_runner_pids():
                    send_telegram("✅ Phase 6 Runner auto-restarted by monitor.")
                    print("[MONITOR] Auto-restart succeeded")
                    return
            except Exception as e:
                print(f"[MONITOR] Auto-restart failed: {e}")
        send_telegram(msg)
        return
    elif count > 1:
        keep, killed = remediate_duplicate_runners(pids)
        remaining = get_runner_pids()
        if killed and len(remaining) <= 1:
            msg = (
                f"⚠️ Duplicate Phase 6 runner(s) auto-terminated: {killed}. "
                f"Kept canonical PID {keep or remaining[0] if remaining else '?'}. "
                "Root cause: systemd phase6-runner.service conflicts with start_phase6_runner.sh — "
                "run once: sudo systemctl disable --now phase6-runner.service"
            )
        else:
            msg = (
                f"🚨 CRITICAL: MULTIPLE Phase 6 Runners detected ({len(remaining)} PIDs: {remaining}). "
                "Duplicate process risk — disable systemd: sudo systemctl disable --now phase6-runner.service"
            )
        print(msg)
        send_telegram(msg)
        pids = remaining
        count = len(pids)

    pid_issues = check_pid_files()
    if pid_issues:
        print("[MONITOR] PID file issues detected: " + "; ".join(pid_issues))

    if not check_last_rebalance():
        rebalance_times = ["09:00", "21:00"]
        try:
            with open("config/trading_config_phase6.json") as cf:
                cfg = json.load(cf)
            rebalance_times = cfg.get("scheduler", {}).get("daily_rebalance_times", [cfg.get("scheduler", {}).get("daily_rebalance_time", "09:00")])
        except:
            pass
        times_str = ", ".join(rebalance_times) + " PT"
        msg = f"⚠️ WARNING: Rebalance window missed for configured daily time ({times_str} + 1h grace; last_rebalance stale)"
        print(msg)
        send_telegram(msg)

    # Signal data-quality: defer streak + basket coverage (once per fingerprint / cooldown)
    try:
        root = os.getcwd()
        if not os.path.isdir(os.path.join(root, "phase6")):
            root = "/home/brad/projects/crypto-trading-bot"
        if root not in sys.path:
            sys.path.insert(0, root)
        from phase6.core.signal_dq_monitor import evaluate_signal_dq, format_coverage_kpi

        dq = evaluate_signal_dq(
            log_path=os.path.join(root, "logs/phase6_runner.log"),
            state_path=os.path.join(root, "data/state/signal_dq_monitor.json"),
            min_streak=3,
            cooldown_minutes=60,
        )
        print(f"[MONITOR] {dq.message}")
        if dq.coverage:
            print(f"[MONITOR] {format_coverage_kpi(dq.coverage)}")
        if dq.should_alert:
            send_telegram(dq.message)
            print(f"[MONITOR] SIGNAL-DQ alert sent level={dq.level}")
        # Soft warn on incomplete coverage even without defer streak (no Telegram spam)
        elif dq.coverage and not dq.coverage.complete:
            print(
                f"[MONITOR] coverage incomplete missing_rsi={dq.coverage.missing_rsi} "
                f"missing_sent={dq.coverage.missing_sent}"
            )
    except Exception as e:
        print(f"[MONITOR] signal DQ check failed: {e}")

    print(f"[MONITOR] Health check passed (runners={count})")

if __name__ == "__main__":
    main()
