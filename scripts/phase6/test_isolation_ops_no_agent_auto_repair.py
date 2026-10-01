#!/usr/bin/env python3
"""Isolation: ops_no_agent_auto_repair classification + wrapper rewrite (no live cron)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core import ops_no_agent_auto_repair as m  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_bare_python_requests(self):
        self.assertTrue(
            m.is_bare_python_error(
                "ModuleNotFoundError: No module named 'requests'\n  File ..."
            )
        )

    def test_hermes_cli_not_bare_cron(self):
        self.assertFalse(
            m.is_bare_python_error(
                "ModuleNotFoundError: No module named 'hermes_cli'"
            )
        )

    def test_classify_job(self):
        job = {
            "name": "phase6-x",
            "last_error": "ModuleNotFoundError: No module named 'requests'",
            "script": "run_x.sh",
        }
        self.assertEqual(m.classify_job(job), "bare_python")


class TestWrapperNeeds(unittest.TestCase):
    def test_bash_bare_needs_pin(self):
        text = "#!/usr/bin/env bash\ncd /x\nexec python3 scripts/foo.py\n"
        p = Path("/tmp/fake.sh")
        self.assertTrue(m.wrapper_needs_venv_pin(text, p))

    def test_bash_venv_ok(self):
        text = (
            "#!/usr/bin/env bash\n"
            'PY="$ROOT/.venv/bin/python3"\n'
            'exec "$PY" scripts/foo.py\n'
        )
        p = Path("/tmp/fake.sh")
        self.assertFalse(m.wrapper_needs_venv_pin(text, p))

    def test_activate_then_python3_needs_pin(self):
        text = "source .venv/bin/activate\nexec python3 scripts/foo.py\n"
        self.assertTrue(m.wrapper_needs_venv_pin(text, Path("/tmp/x.sh")))

    def test_py_bootstrap_ok(self):
        text = "import os\nVENV = Path('x')\nos.execv(str(VENV), [])\n"
        self.assertFalse(m.wrapper_needs_venv_pin(text, Path("/tmp/x.py")))


class TestRewrite(unittest.TestCase):
    def test_apply_bash_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_rsi_event_x_probe.sh"
            p.write_text("#!/usr/bin/env bash\nexec python3 scripts/x.py\n")
            with patch.object(m, "ROOT", Path(td)):
                # still write relative project_rel that may not exist — OK for unit
                act = m.apply_wrapper_repair(p, "run_rsi_event_x_probe.sh", dry_run=False)
            self.assertEqual(act.status, "repaired")
            body = p.read_text()
            self.assertIn(".venv/bin/python3", body)
            self.assertNotIn("exec python3 ", body)

    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_x.sh"
            old = "#!/usr/bin/env bash\nexec python3 foo.py\n"
            p.write_text(old)
            act = m.apply_wrapper_repair(p, "run_x.sh", dry_run=True)
            self.assertEqual(act.status, "dry_run")
            self.assertEqual(p.read_text(), old)


class TestRegistryClose(unittest.TestCase):
    def test_candidates(self):
        actions = [
            {
                "class_id": "bare_python",
                "status": "repaired",
                "verify_ok": True,
                "job_name": "phase6-x",
                "job_id": "abc",
                "detail": "ok",
            },
            {
                "class_id": "hung_runner",
                "status": "repaired",
                "job_name": "",
                "detail": "restart",
            },
        ]
        c = m.registry_close_candidates(actions)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["cron_name"], "phase6-x")

    def test_bash_bare_python_no3_needs_pin(self):
        # Covers goldilocks-style bare "python " (not python3) + heredoc python
        text = """#!/usr/bin/env bash
cd /x
{
  python scripts/phase6/run_foo.py
} >> log 2>&1
python - <<'PY' >> log
print(1)
PY
"""
        self.assertTrue(m.wrapper_needs_venv_pin(text, Path("/tmp/fake.sh")))


if __name__ == "__main__":
    unittest.main()
