"""The repo-wide "CI may not skip" guard (#690).

#564 burned us once: every Temporal test skipped on every CI run because
`PYTEST_NETWORK_TESTS=1` was never set by any job, and the suite reported green
having proven nothing. The fix in `platform-control/tests/conftest.py` kept the
escape hatch for offline developers but forbade CI from using it.

That fix was per-site, and per-suite. #690 catalogued the same failure mode
waiting at other sites — Docker-backed Postgres skipping on `OSError`, golden
fixtures skipping when the fixture directory is missing — and #685 found the
worst instance: 15 tests over the production LLM extraction path that executed
nowhere, behind a docstring claiming CI mock coverage.

This module inverts the default for *every* suite that registers it: **in CI, a
skip fails the run unless its reason is allowlisted.** One mechanism covers
every variant (`importorskip`, `skipif`-on-missing-dep, docker-unavailable,
missing fixture, runtime `pytest.skip`), because it observes the *outcome*
rather than the syntax that produced it.

Why this rather than a lint that greps for `importorskip`: a grep sees one
spelling of the problem and cannot see a `pytest.skip()` reached at runtime
inside an `except OSError` — which is exactly the shape #690 found. The outcome
is the thing we care about, so the outcome is what is checked.

It lives in `scripts/` because that is the repo's shared entry point across
surfaces (AGENTS.md): `platform-control`, `document-intelligence` and `eval` are
three separate Python projects with no common package, and three copies of this
file would rot independently — which is the very failure mode it exists to stop.

Each suite passes its own `allowed_skips`, so a skip is argued for once, in that
suite's `conftest.py`, where a reviewer of that suite will see it.

Usage, from a suite's `conftest.py`::

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from ci_skip_guard import CiSkipGuard

    def pytest_configure(config):
        config.pluginmanager.register(CiSkipGuard(ALLOWED_SKIPS), "ci-skip-guard")
"""

from __future__ import annotations

import os

# The shape every suite's allowlist takes: a stable substring of the skip reason
# mapped to the justification for excusing it. Matched as substrings on purpose:
# skip reasons often interpolate an exception or a path, so anchoring on the
# whole formatted message would be brittle.
AllowedSkips = dict[str, str]


def is_allowed_skip(reason: str, allowed_skips: AllowedSkips) -> bool:
    """True when a skip reason has been explicitly argued for."""
    return any(allowed in reason for allowed in allowed_skips)


def running_in_ci() -> bool:
    """GitHub Actions (and most CI) set `CI`; developers' shells do not."""
    return bool(os.environ.get("CI"))


def format_violation(nodeid: str, reason: str) -> str:
    return f"  {nodeid}\n    skipped because: {reason}"


def format_report(violations: list[str]) -> str:
    return (
        f"\n{len(violations)} test(s) SKIPPED in CI for a reason that is not allowlisted:\n\n"
        + "\n".join(violations)
        + "\n\nA suite that skips its only proof of an integration and reports green is\n"
        "worse than one that fails: it is indistinguishable from one that passed.\n"
        "See #690 (and #564, where this cost us the entire Temporal integration,\n"
        "and #685, where it cost us the whole LLM metadata extractor).\n\n"
        "Fix the environment so the test runs, or — if the skip is genuinely\n"
        "optional — add its reason to ALLOWED_SKIPS in this suite's conftest.py\n"
        "with a justification.\n"
    )


def extract_skip_reason(report) -> str:  # noqa: ANN001 - pytest type
    """Pull the reason out of a skipped report's `longrepr`.

    For a skip, `longrepr` is the tuple `(path, lineno, "Skipped: <reason>")`.
    """
    reason = ""
    if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
        reason = str(report.longrepr[2])
    return reason.removeprefix("Skipped: ")


class CiSkipGuard:
    """Collects skips during the run and fails the session at the end.

    Failing at `sessionfinish` rather than on the first offending skip means one
    CI run reports *every* dishonest skip, instead of surfacing them one per
    push.
    """

    def __init__(self, allowed_skips: AllowedSkips | None = None) -> None:
        self.allowed_skips: AllowedSkips = allowed_skips or {}
        self.violations: list[str] = []

    def _record(self, report) -> None:  # noqa: ANN001 - pytest type
        if report.outcome != "skipped":
            return
        reason = extract_skip_reason(report)
        if not running_in_ci() or is_allowed_skip(reason, self.allowed_skips):
            return
        self.violations.append(format_violation(report.nodeid, reason))

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001 - pytest type
        self._record(report)

    def pytest_collectreport(self, report) -> None:  # noqa: ANN001 - pytest type
        """Catch whole *files* skipped at collection time.

        A module-level `pytest.importorskip` never produces a test report — the
        module is dropped during collection — so `pytest_runtest_logreport`
        alone cannot see it. That is precisely how #685's 11-test
        `test_dspy_modules.py` stayed invisible: the suite reported green
        without ever naming the file.
        """
        self._record(report)

    def pytest_sessionfinish(self, session, exitstatus) -> None:  # noqa: ANN001 - pytest type
        if not self.violations:
            return
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(format_report(self.violations), red=True)
        session.exitstatus = 1
