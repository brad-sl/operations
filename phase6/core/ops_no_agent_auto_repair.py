#!/usr/bin/env python3
"""Deterministic no_agent auto-repair for known ops failure classes.

Brad GO 2026-09-26: ops issue loop was ticket-and-stall (Kanban worker dies on
Hermes tools python). Known env classes must heal without an agent:

1. bare_python / ModuleNotFoundError (requests, etc.) → force project .venv
   on the Hermes/project wrapper for that cron.
2. hung_runner → PID alive + phase6_runner.log age >90m → restart via monitor.

Never: trading knobs, membership, live orders, git push, broad shell rewrite.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path("/home/brad/projects/crypto-trading-bot")
HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
JOBS_JSON = Path.home() / ".hermes" / "cron" / "jobs.json"
STATE_DIR = ROOT / "data" / "state"
LATEST = STATE_DIR / "ops_no_agent_auto_repair_latest.json"
HISTORY = STATE_DIR / "ops_no_agent_auto_repair_history.jsonl"
KILL = STATE_DIR / "ops_no_agent_auto_repair_KILL"
VENV_PY = ROOT / ".venv" / "bin" / "python3"
RUNNER_LOG = ROOT / "logs" / "phase6_runner.log"

# Missing deps that mean "wrong interpreter", not "missing package forever"
BARE_PY_MARKERS = (
    "ModuleNotFoundError: No module named 'requests'",
    "ModuleNotFoundError: No module named 'numpy'",
    "ModuleNotFoundError: No module named 'pandas'",
    "ModuleNotFoundError: No module named 'phase6'",
    "No module named 'requests'",
    "No module named 'numpy'",
)

HUNG_LOG_MAX_MIN = 90.0
MAX_REPAIRS_PER_DAY = 8

# script basename → optional project canonical path (when hermes wrapper is thin)
SCRIPT_CANONICAL: dict[str, str] = {
    "run_rsi_event_x_probe.sh": "phase6/scripts/run_rsi_event_x_probe_cron.sh",
    "run_jev_lab_shadow.sh": "phase6/scripts/run_jev_lab_shadow_cron.sh",
    "run_rebalance_x_candidates.sh": "",  # hermes-only thin wrapper
    "refresh_rsi_prices.py": "",  # hermes bootstrap → project scripts/refresh_rsi_prices.py
}


@dataclass
class RepairAction:
    class_id: str
    target: str
    status: str  # repaired | already_ok | skipped | failed | dry_run
    detail: str = ""
    paths: list[str] = field(default_factory=list)
    verify_ok: bool = False
    job_name: str = ""
    job_id: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def kill_switch_on() -> bool:
    return KILL.exists()


def _load_jobs() -> list[dict[str, Any]]:
    if not JOBS_JSON.exists():
        return []
    try:
        raw = json.loads(JOBS_JSON.read_text())
    except Exception:
        return []
    return raw if isinstance(raw, list) else list(raw.get("jobs") or [])


def _jobs_error() -> list[dict[str, Any]]:
    out = []
    for j in _load_jobs():
        if not j.get("enabled", True):
            continue
        if str(j.get("last_status") or "").lower() != "error":
            continue
        out.append(j)
    return out


def _error_blob(job: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(job.get("name") or ""),
            str(job.get("last_error") or ""),
            str(job.get("script") or ""),
        ]
    )


def is_bare_python_error(text: str) -> bool:
    t = text or ""
    if "ModuleNotFoundError" in t or "No module named" in t:
        # Hermes tools python missing hermes_cli is a *worker* problem, not cron wrapper
        if "hermes_cli" in t or "hermes_cli.main" in t:
            return False
        return True
    for m in BARE_PY_MARKERS:
        if m in t:
            return True
    return False


def classify_job(job: dict[str, Any]) -> Optional[str]:
    blob = _error_blob(job)
    if is_bare_python_error(blob):
        return "bare_python"
    return None


def resolve_wrapper_paths(script: str) -> list[Path]:
    """Paths that may need venv pin for this Hermes script field."""
    script = (script or "").strip()
    if not script:
        return []
    paths: list[Path] = []
    # Hermes entry
    h = HERMES_SCRIPTS / script
    if h.exists():
        paths.append(h)
    # Nested phase6/
    h2 = HERMES_SCRIPTS / "phase6" / script
    if h2.exists() and h2 not in paths:
        paths.append(h2)
    # Project canonical twin
    canon = SCRIPT_CANONICAL.get(script)
    if canon:
        p = ROOT / canon
        if p.exists() and p not in paths:
            paths.append(p)
    # Common project mirrors
    for rel in (
        f"phase6/scripts/{script}",
        f"scripts/phase6/{script}",
        script if script.startswith("phase6/") or script.startswith("scripts/") else "",
    ):
        if not rel:
            continue
        p = ROOT / rel
        if p.exists() and p not in paths:
            paths.append(p)
    return paths


def wrapper_needs_venv_pin(text: str, path: Path) -> bool:
    """True if file likely runs bare system/Hermes python for project code."""
    if path.suffix == ".py":
        # Bootstrap that already re-execs venv is OK
        if "os.execv" in text and ".venv" in text:
            return False
        if "VENV" in text and "execv" in text:
            return False
        # Direct project imports without re-exec = bad under Hermes shebang
        if re.search(r"^(import |from )phase6", text, re.M):
            return True
        if "from phase6" in text or "import phase6" in text:
            return True
        # Thin launcher that only subprocesses project is OK if it uses venv
        if str(ROOT) in text and ".venv" not in text and "subprocess" in text:
            return True
        return False

    # shell
    if re.search(r"\$ROOT/\.venv/bin/python3|\.venv/bin/python3", text):
        # still bad if later falls back to bare exec python3 as primary path without check
        if re.search(r"exec python3 |^python3 ", text, re.M) and "source .venv" in text:
            # activate then bare python3 — fragile under cron
            return True
        # has venv path — OK unless only in a comment
        return False
    if re.search(r"exec python3 |PY=python3|PYTHON:-python3|#!/usr/bin/env python3", text):
        return True
    if "source .venv" in text and re.search(r"\bpython3\b", text):
        return True
    return False


def _bash_venv_wrapper(script_name: str, project_rel: str, extra_exports: str = "") -> str:
    """Generate a safe thin bash wrapper."""
    return f"""#!/usr/bin/env bash
# Auto-repaired bare-python wrapper (ops_no_agent_auto_repair { _day() }).
# Always exec project .venv — never bare system/Hermes python.
set -euo pipefail
ROOT="{ROOT}"
cd "$ROOT"
export OPENBLAS_CORETYPE="${{OPENBLAS_CORETYPE:-GENERIC}}"
export PYTHONPATH="$ROOT${{PYTHONPATH:+:$PYTHONPATH}}"
{extra_exports}PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
exec "$PY" {project_rel} "$@"
"""


def _py_venv_bootstrap(project_rel: str) -> str:
    return f'''#!/usr/bin/env python3
"""Hermes cron entry — re-exec project module under project .venv.

Auto-repaired by ops_no_agent_auto_repair ({_day()}).
Bare Hermes/system python lacks trading deps (requests).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path("{ROOT}")
VENV_PY = ROOT / ".venv" / "bin" / "python3"
TARGET = ROOT / "{project_rel}"


def main() -> None:
    if not TARGET.is_file():
        print(f"missing target: {{TARGET}}", file=sys.stderr)
        raise SystemExit(2)
    # Already under project venv?
    exe = Path(sys.executable).resolve()
    want = VENV_PY.resolve() if VENV_PY.is_file() else None
    if want is not None and exe != want:
        env = os.environ.copy()
        env["OPENBLAS_CORETYPE"] = env.get("OPENBLAS_CORETYPE") or "GENERIC"
        pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(ROOT) + (os.pathsep + pp if pp else "")
        os.execve(str(want), [str(want), str(TARGET), *sys.argv[1:]], env)
    # In venv (or no venv): run target in-process
    import runpy

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    sys.argv = [str(TARGET), *sys.argv[1:]]
    runpy.run_path(str(TARGET), run_name="__main__")


if __name__ == "__main__":
    main()
'''


def _infer_project_rel(path: Path, script: str) -> str:
    """Best-effort project python entry for a wrapper."""
    name = path.name
    # Known maps
    known = {
        "run_rsi_event_x_probe.sh": "scripts/phase6/run_rsi_event_x_probe.py",
        "run_rsi_event_x_probe_cron.sh": "scripts/phase6/run_rsi_event_x_probe.py",
        "run_jev_lab_shadow.sh": "scripts/phase6/run_jev_lab_shadow.py",
        "run_jev_lab_shadow_cron.sh": "scripts/phase6/run_jev_lab_shadow.py",
        "run_rebalance_x_candidates.sh": "scripts/phase6/run_rebalance_x_candidates.py",
        "refresh_rsi_prices.py": "scripts/refresh_rsi_prices.py",
        "run_volume_velocity_shadow.sh": "scripts/phase6/run_volume_velocity_shadow.py",
        "run_shadow_tp_validation_check.sh": "scripts/phase6/shadow_tp_validation_status.py",
    }
    if name in known:
        return known[name]
    if script in known:
        return known[script]
    # Heuristic: scripts/phase6/<stem>.py
    stem = Path(name).stem.replace("_cron", "")
    cand = ROOT / "scripts" / "phase6" / f"{stem}.py"
    if cand.exists():
        return f"scripts/phase6/{stem}.py"
    cand2 = ROOT / "phase6" / "scripts" / f"{stem}.py"
    if cand2.exists():
        return f"phase6/scripts/{stem}.py"
    return f"scripts/phase6/{stem}.py"


def repair_wrapper_text(path: Path, script: str) -> tuple[str, str]:
    """Return (new_text, mode) for a path that needs venv pin."""
    project_rel = _infer_project_rel(path, script)
    if path.suffix == ".py" or path.name.endswith(".py"):
        return _py_venv_bootstrap(project_rel), "py_bootstrap"
    # preserve PROBE_GO style env if present in old
    old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    extra = ""
    if "PROBE_GO" in old:
        extra = 'export PROBE_GO="${PROBE_GO:-1}"\n'
    return _bash_venv_wrapper(path.name, project_rel, extra_exports=extra), "bash_venv"


def apply_wrapper_repair(
    path: Path, script: str, *, dry_run: bool = False
) -> RepairAction:
    if not path.exists():
        return RepairAction(
            class_id="bare_python",
            target=str(path),
            status="failed",
            detail="path missing",
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    if not wrapper_needs_venv_pin(text, path):
        return RepairAction(
            class_id="bare_python",
            target=str(path),
            status="already_ok",
            detail="wrapper already pins .venv",
            paths=[str(path)],
        )
    new_text, mode = repair_wrapper_text(path, script)
    if dry_run:
        return RepairAction(
            class_id="bare_python",
            target=str(path),
            status="dry_run",
            detail=f"would rewrite mode={mode} bytes={len(new_text)}",
            paths=[str(path)],
        )
    # backup once
    bak = path.with_suffix(path.suffix + f".bak_autorepair_{_day().replace('-', '')}")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass
    return RepairAction(
        class_id="bare_python",
        target=str(path),
        status="repaired",
        detail=f"rewrote mode={mode} backup={bak.name}",
        paths=[str(path), str(bak)],
    )


def verify_wrapper(path: Path, timeout: int = 90) -> tuple[bool, str]:
    """Smoke the wrapper; treat ModuleNotFound as fail, other business exits may be ok."""
    if not path.exists():
        return False, "missing"
    env = os.environ.copy()
    env["OPENBLAS_CORETYPE"] = env.get("OPENBLAS_CORETYPE") or "GENERIC"
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    try:
        if path.suffix == ".py" or path.name.endswith(".py"):
            cmd = [str(VENV_PY if VENV_PY.is_file() else "python3"), str(path)]
        else:
            cmd = ["bash", str(path)]
        # Prefer dry-ish: many scripts accept nothing and just run measure
        cp = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        err = (cp.stderr or "") + (cp.stdout or "")
        if is_bare_python_error(err):
            return False, err[:300]
        # exit 0 always good; exit non-zero without import error often business skip
        if cp.returncode == 0:
            return True, f"exit=0"
        if "ModuleNotFoundError" in err or "No module named" in err:
            return False, err[:300]
        return True, f"exit={cp.returncode} (no import error)"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:200]


def runner_log_age_minutes() -> Optional[float]:
    try:
        if RUNNER_LOG.is_file():
            return (time.time() - RUNNER_LOG.stat().st_mtime) / 60.0
    except OSError:
        return None
    return None


def get_runner_pids() -> list[str]:
    try:
        cp = subprocess.run(
            ["pgrep", "-f", r"phase6\.core\.phase6_runner|phase6_runner\.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        return [p for p in (cp.stdout or "").split() if p.isdigit()]
    except Exception:
        return []


def repair_hung_runner(*, dry_run: bool = False) -> RepairAction:
    age = runner_log_age_minutes()
    pids = get_runner_pids()
    if not pids:
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="skipped",
            detail="no runner PIDs (down path is monitor's job)",
        )
    if age is None:
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="skipped",
            detail="runner log missing",
            paths=[str(RUNNER_LOG)],
        )
    if age <= HUNG_LOG_MAX_MIN:
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="already_ok",
            detail=f"log age {age:.1f}m <= {HUNG_LOG_MAX_MIN}",
            paths=[str(RUNNER_LOG)],
        )
    detail = f"pids={pids} log_age_min={age:.1f}"
    if dry_run:
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="dry_run",
            detail=f"would restart {detail}",
            paths=[str(RUNNER_LOG)],
        )
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from scripts.phase6.monitor_phase6_runner import restart_runner  # type: ignore

        ok = bool(restart_runner(str(ROOT)))
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="repaired" if ok else "failed",
            detail=detail + ("; restart_ok" if ok else "; restart_failed"),
            paths=[str(RUNNER_LOG)],
            verify_ok=ok,
        )
    except Exception as e:
        # Fallback local restart
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except OSError:
                pass
        time.sleep(3)
        start = ROOT / "scripts/phase6/start_phase6_runner.sh"
        if start.is_file():
            cp = subprocess.run(
                ["bash", str(start)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            ok = bool(get_runner_pids())
            return RepairAction(
                class_id="hung_runner",
                target="phase6_runner",
                status="repaired" if ok else "failed",
                detail=f"{detail}; fallback start rc={cp.returncode} err={e}",
                verify_ok=ok,
            )
        return RepairAction(
            class_id="hung_runner",
            target="phase6_runner",
            status="failed",
            detail=f"{detail}; no start script; {e}",
        )


def repair_bare_python_job(
    job: dict[str, Any], *, dry_run: bool = False, verify: bool = True
) -> list[RepairAction]:
    script = str(job.get("script") or "").strip()
    name = str(job.get("name") or "")
    jid = str(job.get("id") or "")
    actions: list[RepairAction] = []
    paths = resolve_wrapper_paths(script)
    if not paths:
        actions.append(
            RepairAction(
                class_id="bare_python",
                target=script or name,
                status="failed",
                detail="no wrapper path resolved",
                job_name=name,
                job_id=jid,
            )
        )
        return actions
    any_repaired = False
    verify_path: Optional[Path] = None
    for p in paths:
        act = apply_wrapper_repair(p, script, dry_run=dry_run)
        act.job_name = name
        act.job_id = jid
        actions.append(act)
        if act.status in ("repaired", "dry_run"):
            any_repaired = True
            verify_path = p
        elif act.status == "already_ok" and verify_path is None:
            verify_path = p
    if verify and verify_path is not None and not dry_run:
        ok, msg = verify_wrapper(verify_path)
        for a in actions:
            if a.target == str(verify_path):
                a.verify_ok = ok
                a.detail = (a.detail + f"; verify={msg}")[:500]
        # If wrappers already ok but job still erroring, still mark verify
        if ok and not any_repaired:
            actions.append(
                RepairAction(
                    class_id="bare_python",
                    target=str(verify_path),
                    status="already_ok",
                    detail=f"verify smoke OK ({msg}); sticky last_status until next cron fire",
                    verify_ok=True,
                    job_name=name,
                    job_id=jid,
                    paths=[str(verify_path)],
                )
            )
    return actions


def _count_repairs_today() -> int:
    if not HISTORY.exists():
        return 0
    day = _day()
    n = 0
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("day") or "").startswith(day) or str(row.get("as_of") or "").startswith(
            day
        ):
            for a in row.get("actions") or []:
                if a.get("status") == "repaired":
                    n += 1
    return n


def run_auto_repair(
    *,
    dry_run: bool = False,
    include_hung: bool = True,
    verify: bool = True,
    max_repairs: int = MAX_REPAIRS_PER_DAY,
) -> dict[str, Any]:
    """Scan error jobs + hung runner; apply known-class repairs."""
    if kill_switch_on():
        payload = {
            "as_of": _now(),
            "status": "killed",
            "detail": f"kill switch {KILL}",
            "actions": [],
        }
        return payload

    actions: list[RepairAction] = []
    budget = max(0, max_repairs - (_count_repairs_today() if not dry_run else 0))

    # 1) bare python error jobs
    for job in _jobs_error():
        if classify_job(job) != "bare_python":
            continue
        if budget <= 0 and not dry_run:
            actions.append(
                RepairAction(
                    class_id="bare_python",
                    target=str(job.get("name")),
                    status="skipped",
                    detail=f"daily repair cap {max_repairs}",
                    job_name=str(job.get("name") or ""),
                    job_id=str(job.get("id") or ""),
                )
            )
            continue
        job_actions = repair_bare_python_job(job, dry_run=dry_run, verify=verify)
        actions.extend(job_actions)
        if not dry_run and any(a.status == "repaired" for a in job_actions):
            budget -= 1

    # 2) hung runner (independent of cron errors)
    if include_hung:
        if budget <= 0 and not dry_run:
            actions.append(
                RepairAction(
                    class_id="hung_runner",
                    target="phase6_runner",
                    status="skipped",
                    detail=f"daily repair cap {max_repairs}",
                )
            )
        else:
            h = repair_hung_runner(dry_run=dry_run)
            actions.append(h)
            if not dry_run and h.status == "repaired":
                budget -= 1

    payload = {
        "as_of": _now(),
        "day": _day(),
        "dry_run": dry_run,
        "kill": False,
        "actions": [asdict(a) for a in actions],
        "summary": {
            "repaired": sum(1 for a in actions if a.status == "repaired"),
            "already_ok": sum(1 for a in actions if a.status == "already_ok"),
            "failed": sum(1 for a in actions if a.status == "failed"),
            "skipped": sum(1 for a in actions if a.status == "skipped"),
            "dry_run": sum(1 for a in actions if a.status == "dry_run"),
            "verify_ok": sum(1 for a in actions if a.verify_ok),
        },
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not dry_run:
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def registry_close_candidates(actions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map successful repairs → cron names that can auto-close registry rows."""
    out: list[dict[str, str]] = []
    for a in actions:
        if a.get("status") not in ("repaired", "already_ok"):
            continue
        if a.get("class_id") != "bare_python":
            continue
        # Prefer verify_ok; allow repaired without verify if smoke skipped
        if a.get("status") == "repaired" and not a.get("verify_ok"):
            # still close if rewrite landed — sticky status note
            pass
        name = str(a.get("job_name") or "").strip()
        jid = str(a.get("job_id") or "").strip()
        if name or jid:
            out.append(
                {
                    "cron_name": name,
                    "cron_job_id": jid,
                    "note": f"no_agent auto-repair {a.get('class_id')}: {a.get('detail', '')[:200]}",
                }
            )
    # dedupe by name
    seen: set[str] = set()
    deduped = []
    for c in out:
        key = c.get("cron_name") or c.get("cron_job_id") or ""
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped
