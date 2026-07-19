"""Enforces parity between scripts/check-legal-search.sh and its CI workflow.

#688: `.github/workflows/legal-search.yml` never invoked
`scripts/check-legal-search.sh`, yet three separate places claimed they were the
same checks — AGENTS.md ("scripts/ is the shared entry point"), the workflow's
own header, and the pre-commit hook literally named "same script as CI". They
had already drifted: the script ran `openapi:lint`/`openapi:check` as extra
frontend steps.

CI does not shell out to the script on purpose — it splits api and frontend into
parallel jobs with per-surface npm caches, which one serial script would give up.
So parity is asserted here instead of by shared invocation. That closes #688's
real complaint: "a claim of parity, and no mechanism enforcing it."

Compared per surface: the set of `npm run <script>` commands. `npm ci` and the
hygiene job are out of scope (the latter has its own entry point and CI job).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-legal-search.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "legal-search.yml"

# Jobs whose `npm run` steps constitute the legal-search quality gate. The e2e
# jobs are excluded: they need browsers, a webServer and admin deps, so they are
# deliberately CI-only and are covered by scripts/check-e2e-spec-coverage.sh.
GATE_JOBS = {"api": "legal-search/api", "frontend": "legal-search/frontend"}


def script_commands() -> dict[str, set[str]]:
    """`npm run` commands in the script, keyed by the surface last `cd`-ed into."""
    commands: dict[str, set[str]] = {surface: set() for surface in GATE_JOBS}
    surface = None
    for line in SCRIPT.read_text().splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        if "legal-search/api" in line and line.startswith("cd "):
            surface = "api"
        elif "legal-search/frontend" in line and line.startswith("cd "):
            surface = "frontend"
        match = re.match(r"npm run ([a-z0-9:-]+)", line)
        if match and surface:
            commands[surface].add(match.group(1))
    return commands


def workflow_commands() -> dict[str, set[str]]:
    """`npm run` commands in each gate job, keyed by job name."""
    text = WORKFLOW.read_text()
    commands: dict[str, set[str]] = {}
    for job, working_dir in GATE_JOBS.items():
        # Slice from this job's header to the next top-level job (2-space indent).
        start = re.search(rf"^  {job}:$", text, re.MULTILINE)
        if start is None:
            raise AssertionError(f"job '{job}' not found in {WORKFLOW}")
        rest = text[start.end() :]
        end = re.search(r"^  [a-z][a-z0-9-]*:$", rest, re.MULTILINE)
        body = rest[: end.start()] if end else rest

        assert working_dir in body, f"job '{job}' no longer works in {working_dir}"
        commands[job] = set(re.findall(r"npm run ([a-z0-9:-]+)", body))
    return commands


class LegalSearchParityTest(unittest.TestCase):
    def test_script_and_workflow_run_the_same_gates(self) -> None:
        from_script = script_commands()
        from_workflow = workflow_commands()

        for surface in GATE_JOBS:
            self.assertEqual(
                from_script[surface],
                from_workflow[surface],
                f"\nscripts/check-legal-search.sh and .github/workflows/legal-search.yml "
                f"disagree on the '{surface}' surface.\n"
                f"  script only:   {sorted(from_script[surface] - from_workflow[surface])}\n"
                f"  workflow only: {sorted(from_workflow[surface] - from_script[surface])}\n"
                f"A gate added to one must be added to the other (AGENTS.md), or the "
                f"parity claims in the workflow header and .pre-commit-config.yaml "
                f"become false again (#688).",
            )

    def test_each_surface_actually_runs_something(self) -> None:
        """A parity test over two empty sets would pass while gating nothing."""
        for surface, commands in script_commands().items():
            self.assertIn(
                "check", commands, f"the '{surface}' surface must at least run `npm run check`"
            )


if __name__ == "__main__":
    unittest.main()
