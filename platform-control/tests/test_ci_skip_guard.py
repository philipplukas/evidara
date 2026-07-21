"""Both directions of the "CI may not skip" guard (#690).

The guard is only worth having if it fires in CI and stays out of the way
locally. A guard that fails developers' runs would be turned off; one that never
fires in CI is the silent-green problem it was written to fix.

The guard itself now lives in `scripts/ci_skip_guard.py` and is shared by
platform-control, document-intelligence and eval. This suite is its home for
tests: it is the one of the three that is not itself an optional-extras minefield.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from ci_skip_guard import format_report, is_allowed_skip
from conftest import ALLOWED_SKIPS

GUARD_MODULE = Path(__file__).resolve().parents[2] / "scripts" / "ci_skip_guard.py"


class TestAllowlist:
    def test_unlisted_reason_is_not_allowed(self) -> None:
        assert not is_allowed_skip("Docker-backed Postgres is unavailable: boom", {})

    def test_listed_reason_matches_as_substring(self) -> None:
        # Skip reasons interpolate exceptions and paths, so matching is by
        # substring; assert that explicitly rather than trusting it.
        allowed = {"requires a live LLM": "example"}
        assert is_allowed_skip("requires a live LLM (DI_EVAL_LIVE unset)", allowed)

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
    def _run(tmp_path: Path, *, ci: bool, body: str) -> subprocess.CompletedProcess:
        (tmp_path / "ci_skip_guard.py").write_text(GUARD_MODULE.read_text())
        (tmp_path / "conftest.py").write_text(
            textwrap.dedent("""
            from ci_skip_guard import CiSkipGuard

            def pytest_configure(config):
                config.pluginmanager.register(CiSkipGuard({}), "ci-skip-guard")
            """)
        )
        (tmp_path / "test_sample.py").write_text(textwrap.dedent(body))
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

    RUNTIME_SKIP = """
        import pytest

        def test_passes():
            assert True

        def test_skips():
            pytest.skip("Docker-backed Postgres is unavailable: nope")
    """

    # The #685 shape: the module never produces a test report at all, because it is
    # dropped during collection. A guard that only watched `runtest` reports would
    # have reported green over this, which is exactly how 11 tests stayed invisible.
    COLLECTION_SKIP = """
        import pytest

        pytest.importorskip("no_such_module_xyz")

        def test_never_runs():
            assert True
    """

    def test_fails_the_run_when_ci_skips(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=True, body=self.RUNTIME_SKIP)
        assert result.returncode != 0, (
            "a non-allowlisted skip in CI must fail the run:\n" + result.stdout
        )
        assert "not allowlisted" in result.stdout

    def test_stays_silent_for_the_same_skip_outside_ci(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=False, body=self.RUNTIME_SKIP)
        assert result.returncode == 0, (
            "the escape hatch must still work for offline developers:\n" + result.stdout
        )
        assert "not allowlisted" not in result.stdout

    def test_fails_the_run_when_ci_drops_a_whole_module_at_collection(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=True, body=self.COLLECTION_SKIP)
        assert result.returncode != 0, (
            "a module-level importorskip in CI must fail the run — this is #685:\n" + result.stdout
        )
        assert "not allowlisted" in result.stdout
        assert "no_such_module_xyz" in result.stdout

    def test_stays_silent_for_a_collection_skip_outside_ci(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, ci=False, body=self.COLLECTION_SKIP)
        assert "not allowlisted" not in result.stdout
