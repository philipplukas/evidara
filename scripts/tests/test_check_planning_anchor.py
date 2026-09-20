"""Self-test for the planning-anchor guard.

Delete `scripts/check_planning_anchor.py` and every test in this module errors on
import — which is the point: the guard is not allowed to disappear quietly, the
way the pointer it guards did.

The cases cover the three outcomes separately, because the failure this guard
exists for is precisely a check that reports success without having established
anything (AGENTS.md: "PASS, FAIL and DID-NOT-RUN are three outcomes, not two").
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "check_planning_anchor.py"

_spec = importlib.util.spec_from_file_location("check_planning_anchor", MODULE_PATH)
assert _spec and _spec.loader
MODULE = importlib.util.module_from_spec(_spec)
# Register before executing: `@dataclass` resolves annotations through
# `sys.modules[cls.__module__]`, which is None for a module that is not there.
sys.modules[_spec.name] = MODULE
_spec.loader.exec_module(MODULE)


class FindAnchorTests(unittest.TestCase):
    def test_reads_the_issue_number_from_the_pointer_line(self) -> None:
        text = (
            "### Planning anchor\n\n"
            "**#628 (M13) closed 2026-07-19.** Its successor is **#958**, below.\n\n"
            "**Current anchor: #958 — the corpus states what is true, or refuses.**\n"
        )
        self.assertEqual(MODULE.find_anchor(text), 958)

    def test_other_issue_numbers_in_the_file_are_not_mistaken_for_the_anchor(self) -> None:
        # CLAUDE.md names dozens of issues; only the pointer line is the anchor.
        text = (
            "Do not scope work against #628 — read its closing comments.\n"
            "**Current anchor: #958 — the corpus states what is true.**\n"
            "The predecessor M1-M6 roadmap (#279) closed 2026-04-20.\n"
        )
        self.assertEqual(MODULE.find_anchor(text), 958)

    def test_a_deleted_pointer_is_malformed_not_a_pass(self) -> None:
        with self.assertRaises(MODULE.MalformedAnchor):
            MODULE.find_anchor("### Planning anchor\n\nSee the roadmap.\n")

    def test_two_pointers_are_malformed(self) -> None:
        text = "**Current anchor: #958 — a.**\n\n**Current anchor: #731 — b.**\n"
        with self.assertRaises(MODULE.MalformedAnchor):
            MODULE.find_anchor(text)


class EvaluateTests(unittest.TestCase):
    def test_a_closed_anchor_fails(self) -> None:
        outcome = MODULE.evaluate(731, "CLOSED", "philipplukas/evidara")
        self.assertEqual(outcome.status, "FAIL")
        self.assertEqual(outcome.exit_code, 1)
        self.assertIn("#731", outcome.message)

    def test_an_open_anchor_passes(self) -> None:
        outcome = MODULE.evaluate(958, "OPEN", "philipplukas/evidara")
        self.assertEqual(outcome.status, "PASS")
        self.assertEqual(outcome.exit_code, 0)

    def test_an_unresolvable_state_is_did_not_run_not_pass(self) -> None:
        outcome = MODULE.evaluate(958, None, "philipplukas/evidara")
        self.assertEqual(outcome.status, "DID-NOT-RUN")
        self.assertIn("was NOT checked", outcome.message)


class MainTests(unittest.TestCase):
    """End-to-end over the CLI, with the network transports stubbed out."""

    def setUp(self) -> None:
        self._real_resolve = MODULE.resolve_state
        self.addCleanup(setattr, MODULE, "resolve_state", self._real_resolve)

    def _write_anchor(self, body: str) -> Path:
        import tempfile

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "CLAUDE.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_cli_fails_on_a_closed_anchor(self) -> None:
        MODULE.resolve_state = lambda number, repo: "CLOSED"  # type: ignore[assignment]
        path = self._write_anchor("**Current anchor: #731 — done.**\n")
        self.assertEqual(MODULE.main(["--anchor-file", str(path)]), 1)

    def test_cli_passes_on_an_open_anchor(self) -> None:
        MODULE.resolve_state = lambda number, repo: "OPEN"  # type: ignore[assignment]
        path = self._write_anchor("**Current anchor: #958 — live.**\n")
        self.assertEqual(MODULE.main(["--anchor-file", str(path)]), 0)

    def test_cli_abstains_without_a_transport_and_escalates_on_demand(self) -> None:
        MODULE.resolve_state = lambda number, repo: None  # type: ignore[assignment]
        path = self._write_anchor("**Current anchor: #958 — live.**\n")
        self.assertEqual(MODULE.main(["--anchor-file", str(path)]), 0)
        self.assertEqual(
            MODULE.main(["--anchor-file", str(path), "--require-network"]),
            3,
            "--require-network must distinguish 'did not run' from 'passed'",
        )

    def test_cli_rejects_a_file_with_no_pointer(self) -> None:
        MODULE.resolve_state = lambda number, repo: "OPEN"  # type: ignore[assignment]
        path = self._write_anchor("### Planning anchor\n\nnothing here\n")
        self.assertEqual(MODULE.main(["--anchor-file", str(path)]), 2)


class RepositoryAnchorTests(unittest.TestCase):
    """The real CLAUDE.md must carry a parseable pointer at all times."""

    def test_claude_md_carries_exactly_one_anchor(self) -> None:
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        number = MODULE.find_anchor(text)
        self.assertGreater(number, 0)


if __name__ == "__main__":
    unittest.main()
