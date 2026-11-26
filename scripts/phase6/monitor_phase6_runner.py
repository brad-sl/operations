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

2026-11-25: rebalance miss uses slot SSOT (rebalance_slots_completed), absolute
paths, and 6h TG cooldown — stops false "last_rebalance stale" spam when
phase6_live_state lacks the date field / park days with executed=0.
"""

from __future__ import annotations

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

# Absolute project root — cron/cwd must not break state reads (false "stale rebalance" spam).
PROJECT_ROOT = os.environ.get(
    "PHASE6_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
if not os.path.isdir(os.path.join(PROJECT_ROOT, "phase6")):
    PROJECT_ROOT = "/home/brad/projects/crypto-trading-bot"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUNNER_LOG = os.path.join(PROJECT_ROOT, "logs/phase6_runner.log")
# live_state is for book snapshot — it does NOT carry last_rebalance_date.
# Slot SSOT is phase6_runner_state.json (rebalance_slots_completed).
STATE_FILE = os.path.join(PROJECT_ROOT, "data/state/phase6_live_state.json")
RUNNER_STATE_FILE = os.path.join(PROJECT_ROOT, "data/state/phase6_runner_state.json")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config/trading_config_phase6.json")
REBAL_MISS_ALERT_STATE = os.path.join(
    PROJECT_ROOT, "data/state/monitor_rebalance_miss_alert.json"
)
REBAL_MISS_COOLDOWN_HOURS = 6.0
REBAL_GRACE_HOURS = 1.0

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


def runner_log_age_minutes(log_path: str | None = None) -> float | None:
    """Minutes since last write to phase6_runner.log (None if missing)."""
    candidates = [
        log_path,
        "logs/phase6_runner.log",
        "/home/brad/projects/crypto-trading-bot/logs/phase6_runner.log",
    ]
    for p in candidates:
        if not p:
            continue
        try:
            if os.path.isfile(p):
                age = (time.time() - os.path.getmtime(p)) / 60.0
                return float(age)
        except OSError:
            continue
    return None


def is_runner_log_fresh(max_age_min: float = 90.0) -> bool:
    """PID-alive is not enough — hung runners freeze the log while still pgrep-able.

    Cycle interval is ~30m; 90m (~3 missed cycles) = hung threshold.
    """
    age = runner_log_age_minutes()
    if age is None:
        return False
    return age <= max_age_min


def restart_runner(project_root: str | None = None) -> bool:
    """Canonical singleton restart via start_phase6_runner.sh. Returns True if PIDs live after."""
    project_root = project_root or os.getcwd()
    start_sh = os.path.join(project_root, "scripts/phase6/start_phase6_runner.sh")
    if not os.path.isfile(start_sh):
        project_root = "/home/brad/projects/crypto-trading-bot"
        start_sh = os.path.join(project_root, "scripts/phase6/start_phase6_runner.sh")
    if not os.path.isfile(start_sh):
        print("[MONITOR] restart_runner: start script missing")
        return False
    try:
        # Soft-stop hung PIDs first so start script doesn't refuse as duplicate
        for pid in get_runner_pids():
            try:
                os.kill(int(pid), signal.SIGTERM)
                print(f"[MONITOR] SIGTERM hung/old runner pid={pid}")
            except OSError as e:
                print(f"[MONITOR] SIGTERM pid={pid} failed: {e}")
        time.sleep(3)
        for pid in get_runner_pids():
            try:
                os.kill(int(pid), signal.SIGKILL)
                print(f"[MONITOR] SIGKILL stubborn runner pid={pid}")
            except OSError:
                pass
        time.sleep(1)
        proc = subprocess.run(
            ["bash", start_sh],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        print("[MONITOR] Restart attempt:", out.strip()[:500])
        time.sleep(3)
        return bool(get_runner_pids())
    except Exception as e:
        print(f"[MONITOR] restart_runner failed: {e}")
        return False


def load_rebalance_times(config_path: str = CONFIG_FILE) -> list:
    """Return configured daily rebalance HH:MM list (PT wall clock on host)."""
    rebalance_times = ["09:00", "21:00"]
    try:
        with open(config_path) as cf:
            cfg = json.load(cf)
        sched = cfg.get("scheduler", {}) or {}
        times = sched.get("daily_rebalance_times")
        if isinstance(times, list) and times:
            rebalance_times = [str(t).strip() for t in times if str(t).strip()]
        elif sched.get("daily_rebalance_time"):
            rebalance_times = [str(sched.get("daily_rebalance_time")).strip()]
    except Exception:
        pass
    return rebalance_times or ["09:00", "21:00"]


def evaluate_rebalance_health(
    *,
    now: datetime,
    rebalance_times: list,
    completed_slots: list,
    last_rebalance_date: str | None = None,
    grace_hours: float = REBAL_GRACE_HOURS,
) -> tuple:
    """Pure check: True=healthy (no alert), False=overdue.

    Prefer per-slot keys in rebalance_slots_completed (e.g. '2026-11-25|09:00').
    Only the most recent full day of due slots (len(times), min 2) must be present —
    runner slot lists are truncated, so requiring 3 calendar days of history false-alarms.
    Date-only last_rebalance_date is fallback only when slot list is empty.
    """
    grace_delta = timedelta(hours=float(grace_hours))
    times = [str(t).strip() for t in (rebalance_times or []) if str(t).strip()]
    if not times:
        times = ["09:00", "21:00"]
    completed = set(str(x) for x in (completed_slots or []) if x is not None)

    if completed:
        due: list = []
        # Look back enough calendar days to collect recent due windows.
        for day_offset in range(0, 5):
            day = now.date() - timedelta(days=day_offset)
            for tstr in times:
                try:
                    target = dt_time.fromisoformat(tstr)
                except ValueError:
                    continue
                deadline = datetime.combine(day, target) + grace_delta
                if now < deadline:
                    continue
                key = f"{day.isoformat()}|{tstr}"
                due.append((deadline, key))
        due.sort(key=lambda x: x[0], reverse=True)
        need_n = max(len(times), 2)
        need = due[:need_n]
        missed = [key for _, key in need if key not in completed]
        if missed:
            return False, f"missed_slots={missed}"
        return True, "slots_ok"

    # Fallback: no slot history — date-only (legacy). Use *latest* daily time + grace.
    if not last_rebalance_date:
        return False, "no_slots_no_last_date"
    try:
        last_date = datetime.fromisoformat(str(last_rebalance_date)).date()
    except Exception:
        return False, "bad_last_date"
    today = now.date()
    if last_date == today or (today - last_date).days <= 0:
        return True, "date_today_fallback"
    days = (today - last_date).days
    latest = sorted(times)[-1]
    try:
        target = dt_time.fromisoformat(latest)
    except ValueError:
        target = dt_time(21, 0)
    if days == 1:
        target_dt = datetime.combine(today, target) + grace_delta
        if now < target_dt:
            return True, "date_yest_pre_latest_grace"
        return False, "date_yest_post_grace"
    return False, f"date_stale_days={days}"


def check_last_rebalance(now: datetime | None = None) -> tuple:
    """Returns (healthy: bool, detail: str). Absolute paths; slot SSOT."""
    now = now or datetime.now()
    times = load_rebalance_times()
    completed: list = []
    last = None
    try:
        with open(RUNNER_STATE_FILE) as rf:
            rs = json.load(rf)
        completed = list(rs.get("rebalance_slots_completed") or [])
        last = rs.get("last_rebalance_date")
    except Exception as e:
        return False, f"runner_state_unreadable:{e}"
    return evaluate_rebalance_health(
        now=now,
        rebalance_times=times,
        completed_slots=completed,
        last_rebalance_date=last,
        grace_hours=REBAL_GRACE_HOURS,
    )


def maybe_alert_rebalance_miss(msg: str, fingerprint: str) -> bool:
    """Telegram once per fingerprint within REBAL_MISS_COOLDOWN_HOURS. Returns True if sent."""
    now = datetime.now()
    try:
        prev = {}
        if os.path.exists(REBAL_MISS_ALERT_STATE):
            with open(REBAL_MISS_ALERT_STATE) as f:
                prev = json.load(f) or {}
        last_fp = str(prev.get("fingerprint") or "")
        last_ts = prev.get("sent_at")
        if last_fp == fingerprint and last_ts:
            try:
                sent = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                if sent.tzinfo is not None:
                    sent = sent.replace(tzinfo=None)
                age_h = (now - sent).total_seconds() / 3600.0
                if age_h < REBAL_MISS_COOLDOWN_HOURS:
                    print(
                        f"[MONITOR] rebalance-miss alert suppressed "
                        f"(cooldown {age_h:.1f}h/{REBAL_MISS_COOLDOWN_HOURS}h fp={fingerprint})"
                    )
                    return False
            except Exception:
                pass
        send_telegram(msg)
        os.makedirs(os.path.dirname(REBAL_MISS_ALERT_STATE), exist_ok=True)
        with open(REBAL_MISS_ALERT_STATE, "w") as f:
            json.dump(
                {
                    "sent_at": now.isoformat(),
                    "fingerprint": fingerprint,
                    "message": msg[:500],
                },
                f,
                indent=2,
            )
            f.write("\n")
        return True
    except Exception as e:
        print(f"[MONITOR] rebalance-miss cooldown write failed: {e}; sending anyway")
        send_telegram(msg)
        return True

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
        if restart_runner():
            send_telegram("✅ Phase 6 Runner auto-restarted by monitor.")
            print("[MONITOR] Auto-restart succeeded")
            return
        send_telegram(msg)
        return

    # PID alive but log frozen = hung runner (2026-09-25 class: 2d zombie, monitor green)
    log_age = runner_log_age_minutes()
    if log_age is not None and log_age > 90.0:
        msg = (
            f"🚨 CRITICAL: Phase 6 Runner HUNG — pid(s)={pids} but "
            f"logs/phase6_runner.log stale {log_age:.0f}m (threshold 90m). Auto-restarting."
        )
        print(msg)
        send_telegram(msg)
        if restart_runner():
            send_telegram("✅ Phase 6 hung runner auto-restarted by monitor.")
            print("[MONITOR] Hung-runner auto-restart succeeded")
            return
        send_telegram("🚨 Hung runner restart FAILED — needs manual GO restart.")
        return

    if count > 1:
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

    healthy, detail = check_last_rebalance()
    if not healthy:
        rebalance_times = load_rebalance_times()
        times_str = ", ".join(rebalance_times) + " PT"
        msg = (
            f"⚠️ WARNING: Rebalance window missed for configured daily time "
            f"({times_str} + {int(REBAL_GRACE_HOURS)}h grace; {detail})"
        )
        print(msg)
        # Cooldown so 15m monitor does not spam TG on one sticky miss fingerprint.
        maybe_alert_rebalance_miss(msg, fingerprint=str(detail)[:240])
    else:
        print(f"[MONITOR] rebalance schedule OK ({detail})")

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
