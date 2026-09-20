"""Self-test for the classifier-evidence rule guard.

Delete `scripts/check_classifier_evidence_rule.py` and this module errors on
import. Delete the rule from AGENTS.md, or the checkbox from the PR template,
and `test_the_repository_satisfies_the_rule_guard` goes red.

The guard classifies "rule present / rule missing", so it is itself subject to
the rule it protects: the fixtures below are the real AGENTS.md and the real PR
template, mutated one requirement at a time.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "check_classifier_evidence_rule.py"

_spec = importlib.util.spec_from_file_location("check_classifier_evidence_rule", MODULE_PATH)
assert _spec and _spec.loader
MODULE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = MODULE
_spec.loader.exec_module(MODULE)

AGENTS = REPO_ROOT / "AGENTS.md"
PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"


class ClassifierEvidenceRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _copy(self, source: Path, name: str, *, drop: str | None = None) -> Path:
        text = source.read_text(encoding="utf-8")
        if drop is not None:
            self.assertIn(drop, text, f"fixture drift: {drop!r} is no longer in {source.name}")
            text = text.replace(drop, "")
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_repository_satisfies_the_rule_guard(self) -> None:
        self.assertEqual(MODULE.run(AGENTS, PR_TEMPLATE), 0)

    def test_removing_the_rule_heading_fails(self) -> None:
        agents = self._copy(AGENTS, "AGENTS.md", drop=MODULE.RULE_HEADING)
        self.assertEqual(MODULE.run(agents, PR_TEMPLATE), 1)

    def test_removing_the_independent_oracle_clause_fails(self) -> None:
        agents = self._copy(AGENTS, "AGENTS.md", drop="independently of the thing under test")
        self.assertEqual(MODULE.run(agents, PR_TEMPLATE), 1)

    def test_removing_the_incident_citation_fails(self) -> None:
        agents = self._copy(AGENTS, "AGENTS.md", drop="57,128")
        self.assertEqual(MODULE.run(agents, PR_TEMPLATE), 1)

    def test_removing_the_pr_template_checkbox_fails(self) -> None:
        template = self._copy(
            PR_TEMPLATE,
            "pull_request_template.md",
            drop="established independently of the tool under test",
        )
        self.assertEqual(MODULE.run(AGENTS, template), 1)

    def test_a_missing_file_is_a_failure_not_a_pass(self) -> None:
        self.assertEqual(MODULE.run(self.tmp / "nope.md", PR_TEMPLATE), 1)

    def test_every_declared_requirement_is_individually_load_bearing(self) -> None:
        """No requirement may be satisfied by accident somewhere else in the file.

        A substring that also appears outside the rule would make its entry
        decoration — the guard would stay green with the rule deleted.
        """
        for label, needle in MODULE.RULE_REQUIREMENTS:
            with self.subTest(label=label):
                agents = self._copy(AGENTS, "AGENTS.md", drop=needle)
                self.assertEqual(
                    MODULE.run(agents, PR_TEMPLATE),
                    1,
                    f"AGENTS.md requirement {label!r} is not load-bearing",
                )
        for label, needle in MODULE.PR_TEMPLATE_REQUIREMENTS:
            with self.subTest(label=label):
                template = self._copy(PR_TEMPLATE, "pull_request_template.md", drop=needle)
                self.assertEqual(
                    MODULE.run(AGENTS, template),
                    1,
                    f"PR template requirement {label!r} is not load-bearing",
                )


if __name__ == "__main__":
    unittest.main()
