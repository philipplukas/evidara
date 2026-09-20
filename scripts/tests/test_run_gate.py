"""Self-test for `scripts/run-gate.sh`.

Delete the script and every test here fails at `setUpClass` — the guard cannot be
removed without a named test going red.

What these assert is the thing that actually went wrong on 2026-09-19: a gate
piped into `tail` reported `tail`'s exit status. So the tests run the wrapper
*through a pipe* and check that the reported line still says FAIL, and that the
wrapper's own status is the command's, not the pipeline's.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_GATE = REPO_ROOT / "scripts" / "run-gate.sh"


class RunGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not RUN_GATE.exists():
            raise AssertionError(
                f"{RUN_GATE} is missing — the gate wrapper that makes PASS/FAIL/"
                "DID-NOT-RUN honest has been deleted."
            )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_dir = Path(self._tmp.name)

    def run_gate(self, *args: str, pipe_through: str | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ, EVIDARA_GATE_LOG_DIR=str(self.log_dir))
        argv = ["bash", str(RUN_GATE), *args]
        if pipe_through is None:
            return subprocess.run(argv, capture_output=True, text=True, env=env, check=False)
        # Reproduce the incident exactly: the gate's output goes into another
        # command, and that command's exit status is what the shell reports.
        quoted = " ".join(f"'{a}'" for a in argv)
        return subprocess.run(
            ["bash", "-c", f"{quoted} | {pipe_through}"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    # ── PASS ────────────────────────────────────────────────────────────────
    def test_a_succeeding_command_reports_pass_and_exits_zero(self) -> None:
        result = self.run_gate("demo", "--", sys.executable, "-c", "print('ok')")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            result.stdout.strip().splitlines()[-1].startswith("PASS gate=demo exit=0 log="),
            result.stdout,
        )

    # ── FAIL ────────────────────────────────────────────────────────────────
    def test_a_failing_command_reports_fail_and_propagates_its_status(self) -> None:
        result = self.run_gate("demo", "--", sys.executable, "-c", "raise SystemExit(7)")
        self.assertEqual(result.returncode, 7, "the command's own status must survive")
        self.assertTrue(
            result.stdout.strip().splitlines()[-1].startswith("FAIL gate=demo exit=7 log="),
            result.stdout,
        )

    def test_a_failing_command_piped_into_tail_still_reports_fail(self) -> None:
        """The 2026-09-19 incident: `gate | tail` reported tail's 0."""
        result = self.run_gate(
            "demo", "--", sys.executable, "-c", "raise SystemExit(7)", pipe_through="tail -1"
        )
        last_line = result.stdout.strip().splitlines()[-1]
        self.assertTrue(last_line.startswith("FAIL gate=demo exit=7"), last_line)
        self.assertNotIn(
            "PASS",
            result.stdout,
            "a gate laundered through a pager must never be able to print PASS",
        )

    def test_the_pipeline_status_is_still_the_pagers_and_the_line_is_the_evidence(self) -> None:
        """Honesty comes from the printed line, not from the caller's shell.

        `tail` still exits 0 — nothing can change that from inside the wrapper.
        This test pins WHY the final line exists: it is the one artifact a
        careless pipeline cannot rewrite.
        """
        result = self.run_gate(
            "demo", "--", sys.executable, "-c", "raise SystemExit(7)", pipe_through="tail -1"
        )
        self.assertEqual(result.returncode, 0, "sanity: the pager's status is what a shell sees")
        self.assertIn("FAIL", result.stdout)

    # ── DID-NOT-RUN ─────────────────────────────────────────────────────────
    def test_a_missing_prerequisite_is_did_not_run_not_pass(self) -> None:
        result = self.run_gate(
            "demo", "--requires", "path:definitely/not/here", "--", sys.executable, "-c", "pass"
        )
        last_line = result.stdout.strip().splitlines()[-1]
        self.assertTrue(last_line.startswith("DID-NOT-RUN gate=demo exit=none log="), last_line)
        self.assertIn("missing=path:definitely/not/here", last_line)
        self.assertEqual(result.returncode, 2, "DID-NOT-RUN must not be exit 0")

    def test_a_missing_executable_is_did_not_run(self) -> None:
        result = self.run_gate("demo", "--", "evidara-no-such-binary", "--version")
        last_line = result.stdout.strip().splitlines()[-1]
        self.assertTrue(last_line.startswith("DID-NOT-RUN"), last_line)
        self.assertEqual(result.returncode, 2)

    def test_an_npm_gate_without_node_modules_is_did_not_run(self) -> None:
        surface = self.log_dir / "surface"
        surface.mkdir()
        (surface / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        result = self.run_gate("api", "--dir", str(surface), "--", "npm", "run", "check")
        last_line = result.stdout.strip().splitlines()[-1]
        self.assertTrue(last_line.startswith("DID-NOT-RUN gate=api"), last_line)
        self.assertIn("node_modules", last_line)

    def test_a_missing_env_prerequisite_is_did_not_run(self) -> None:
        result = self.run_gate(
            "demo", "--requires", "env:EVIDARA_NOT_SET_ANYWHERE", "--", sys.executable, "-c", "pass"
        )
        self.assertIn("missing=env:EVIDARA_NOT_SET_ANYWHERE", result.stdout)
        self.assertEqual(result.returncode, 2)

    # ── The log ─────────────────────────────────────────────────────────────
    def test_full_output_is_teed_to_a_log_and_the_line_names_it(self) -> None:
        result = self.run_gate(
            "demo", "--", sys.executable, "-c", "print('needle-in-the-output')"
        )
        last_line = result.stdout.strip().splitlines()[-1]
        log_path = Path(last_line.split("log=", 1)[1].split(" ", 1)[0])
        self.assertTrue(log_path.exists(), f"{log_path} was named but not written")
        contents = log_path.read_text(encoding="utf-8")
        self.assertIn("needle-in-the-output", contents)
        self.assertIn("PASS gate=demo", contents)

    def test_it_refuses_a_call_with_no_command(self) -> None:
        result = self.run_gate("demo")
        self.assertEqual(result.returncode, 64, result.stderr)


if __name__ == "__main__":
    unittest.main()
