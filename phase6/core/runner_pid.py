"""Phase 6 runner PID file helpers (P2-04 cron + start-script alignment)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

from phase6.core.paths import LOGS_DIR, STATE_DIR

# Historical layouts: start script used logs/; cron once used data/state/.
RUNNER_PID_CANDIDATE_PATHS: tuple[Path, ...] = (
    LOGS_DIR / "phase6_runner.pid",
    STATE_DIR / "phase6_runner.pid",
    Path("phase6_live.pid"),
)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("latin-1", errors="ignore")
    except OSError:
        return False
    return "phase6.core.phase6_runner" in cmdline.replace("\x00", " ")


def pgrep_runner_pids() -> List[int]:
    """PIDs of live `python -m phase6.core.phase6_runner` processes."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", r"python.* -m phase6\.core\.phase6_runner"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    pids: List[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = int(line)
            if _pid_alive(pid):
                pids.append(pid)
    return sorted(set(pids))


def read_pid_file(path: Path) -> Optional[int]:
    try:
        raw = path.read_text().strip()
        return int(raw)
    except (OSError, ValueError):
        return None


def find_live_runner_pid(*, exclude_pid: Optional[int] = None) -> Optional[int]:
    """Return a live runner PID from pidfiles or pgrep (first match)."""
    for path in RUNNER_PID_CANDIDATE_PATHS:
        pid = read_pid_file(path)
        if pid is None or pid == exclude_pid:
            continue
        if _pid_alive(pid):
            return pid
    for pid in pgrep_runner_pids():
        if pid != exclude_pid:
            return pid
    return None


def write_runner_pid(pid: Optional[int] = None) -> None:
    pid = pid or os.getpid()
    for path in RUNNER_PID_CANDIDATE_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{pid}\n")


def clear_runner_pid(pid: Optional[int] = None) -> None:
    """Remove pidfiles that point at this PID (or any stale file if pid omitted)."""
    for path in RUNNER_PID_CANDIDATE_PATHS:
        try:
            if not path.exists():
                continue
            if pid is None:
                path.unlink()
                continue
            on_disk = read_pid_file(path)
            if on_disk == pid:
                path.unlink()
        except OSError:
            pass


def is_runner_running() -> bool:
    return find_live_runner_pid() is not None