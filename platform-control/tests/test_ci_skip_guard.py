"""Both directions of the "CI may not skip" guard (#690).

The guard is only worth having if it fires in CI and stays out of the way
locally. A guard that fails developers' runs would be turned off; one that never
fires in CI is the silent-green problem it was written to fix.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from ci_skip_guard import ALLOWED_SKIPS, format_report, is_allowed_skip

GUARD_MODULE = Path(__file__).resolve().parent / "ci_skip_guard.py"


class TestAllowlist:
    def test_unlisted_reason_is_not_allowed(self) -> None:
        assert not is_allowed_skip("Docker-backed Postgres is unavailable: boom")

    def test_listed_reason_matches_as_substring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Skip reasons interpolate exceptions and paths, so matching is by
        # substring; assert that explicitly rather than trusting it.
        monkeypatch.setitem(ALLOWED_SKIPS, "requires a live LLM", "example")
        assert is_allowed_skip("requires a live LLM (DI_EVAL_LIVE unset)")

    def test_allowlist_entries_carry_a_justification(self) -> None:
        for reason, justification in ALLOWED_SKIPS.items():
            assert justification.strip(), f"allowlist entry {reason!r} has no justification"

    def test_report_names_the_offending_tests(self) -> None:
        report = format_report(["  tests/test_x.py::test_y\n    skipped because: no docker"])
        assert "tests/test_x.py::test_y" in report
        assert "#690" in report


class TestGuardEndToEnd:
    """Drives a real pytest run so the hook wiring is exercised, not just the logic."""

    @staticmethod
    def _run(tmp_path: Path, *, ci: bool) -> subprocess.CompletedProcess:
        (tmp_path / "ci_skip_guard.py").write_text(GUARD_MODULE.read_text())
        (tmp_path / "conftest.py").write_text(
            textwrap.dedent("""
            from ci_skip_guard import CiSkipGuard

            def pytest_configure(config):
                config.pluginmanager.register(CiSkipGuard(), "ci-skip-guard")
            """)
        )
        (tmp_path / "test_sample.py").write_text(
            textwrap.dedent("""
            import pytest

            def test_passes():
                assert True

            def test_skips():
                pytest.skip("Docker-backed Postgres is unavailable: nope")
            """)
        )
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": str(tmp_path)}
        if ci:
            env["CI"] = "true"
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )

    def test_fails_the_run_when_ci_skips(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=True)
        assert result.returncode != 0, (
            "a non-allowlisted skip in CI must fail the run:\n" + result.stdout
        )
        assert "not allowlisted" in result.stdout

    def test_stays_silent_for_the_same_skip_outside_ci(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=False)
        assert result.returncode == 0, (
            "the escape hatch must still work for offline developers:\n" + result.stdout
        )
        assert "not allowlisted" not in result.stdout
