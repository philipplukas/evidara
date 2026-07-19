"""Generalises the #564 "CI may not skip" guard to every skip in this suite.

#564 burned us once: every Temporal test skipped on every CI run because
`PYTEST_NETWORK_TESTS=1` was never set by any job, and the suite reported green
having proven nothing. The fix in `conftest.pytest_collection_modifyitems` was
to keep the escape hatch for offline developers but forbid CI from using it.

That fix is per-site. #690 catalogued the same failure mode waiting at other
sites — Docker-backed Postgres skipping on `OSError`, golden fixtures skipping
when the fixture directory is missing — each of which converts the only proof of
a real integration into a pass, with no signal.

This module inverts the default for the whole suite: **in CI, a skip fails the
run unless its reason is allowlisted.** One mechanism covers every variant
(`importorskip`, `skipif`-on-missing-dep, docker-unavailable, missing fixture,
runtime `pytest.skip`), because it observes the *outcome* rather than the syntax
that produced it.

Why this rather than a lint that greps for `importorskip`: a grep sees one
spelling of the problem and cannot see a `pytest.skip()` reached at runtime
inside an `except OSError` — which is exactly the shape #690 found here. The
outcome is the thing we care about, so the outcome is what is checked.

To allow a genuinely optional skip, add a stable substring to `ALLOWED_SKIPS`
below WITH a reason. The point is not to forbid skips; it is to make each one
argued for once, in one reviewable place, instead of appearing silently.
"""

from __future__ import annotations

import os

# Substrings of skip reasons that are legitimate in CI. Matched as substrings on
# purpose: skip reasons often interpolate an exception or a path, so anchoring on
# the whole formatted message would be brittle.
#
# Empty today, and that is the honest state: a full run of this suite is
# `547 passed, 0 skipped` (#690). Nothing here is optional, so nothing is
# excused. Adding an entry requires saying why, here:
ALLOWED_SKIPS: dict[str, str] = {
    # "requires a live LLM": "DI_EVAL_LIVE evals cost money and need a key.",
}


def is_allowed_skip(reason: str) -> bool:
    """True when a skip reason has been explicitly argued for."""
    return any(allowed in reason for allowed in ALLOWED_SKIPS)


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
        "See #690 (and #564, where this cost us the entire Temporal integration).\n\n"
        "Fix the environment so the test runs, or — if the skip is genuinely\n"
        "optional — add its reason to ALLOWED_SKIPS in tests/ci_skip_guard.py\n"
        "with a justification.\n"
    )


class CiSkipGuard:
    """Collects skips during the run and fails the session at the end.

    Failing at `sessionfinish` rather than on the first offending skip means one
    CI run reports *every* dishonest skip, instead of surfacing them one per
    push.
    """

    def __init__(self) -> None:
        self.violations: list[str] = []

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001 - pytest type
        if report.outcome != "skipped":
            return
        # `report.longrepr` for a skip is (path, lineno, "Skipped: <reason>").
        reason = ""
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2])
        reason = reason.removeprefix("Skipped: ")

        if not running_in_ci() or is_allowed_skip(reason):
            return
        self.violations.append(format_violation(report.nodeid, reason))

    def pytest_sessionfinish(self, session, exitstatus) -> None:  # noqa: ANN001 - pytest type
        if not self.violations:
            return
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(format_report(self.violations), red=True)
        session.exitstatus = 1
