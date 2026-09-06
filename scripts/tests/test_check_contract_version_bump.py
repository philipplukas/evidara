from __future__ import annotations

import importlib.util
from pathlib import Path
import contextlib
import io
import unittest
from unittest.mock import patch


@contextlib.contextmanager
def _capture():
    """Capture stdout and stderr separately — the two carry different verdicts."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_contract_version_bump.py"
SPEC = importlib.util.spec_from_file_location("check_contract_version_bump", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContractVersionBumpGuardTests(unittest.TestCase):
    def test_evaluate_passes_when_locked_contract_changes_and_manifest_version_bumped(self) -> None:
        with (
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/api/legal-search.openapi.yaml", "contracts/manifest.yaml"],
            ),
            patch.object(MODULE, "load_manifest_version_from_file", return_value="1.2.0"),
            patch.object(MODULE, "load_manifest_version_from_git", return_value="1.1.0"),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=[]),
        ):
            self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 0)

    def test_evaluate_fails_when_locked_contract_changes_without_manifest_update(self) -> None:
        with (
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/events/example.event.json"],
            ),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=[]),
        ):
            self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 2)

    def test_reports_uncommitted_locked_paths_as_not_evaluated(self) -> None:
        """A dirty working tree must never present as a clean pass.

        The guard compares COMMITS, which is right in CI (clean checkout) and a
        trap locally: an edited-but-uncommitted `contracts/api/*` produced
        "No locked contract files changed; version bump guard skipped", which
        reads as a pass over work the guard never looked at. Observed for real
        on the first local run against a genuine contract change.
        """
        with (
            patch.object(MODULE, "changed_files_between", return_value=[]),
            patch.object(
                MODULE,
                "uncommitted_locked_paths",
                return_value=["contracts/api/platform-control.openapi.yaml"],
            ),
        ):
            with _capture() as (out, err):
                exit_code = MODULE.evaluate("origin/main", "HEAD")

        self.assertEqual(exit_code, 0, "an unexamined working tree is not a failure")
        self.assertIn("DID-NOT-RUN", out.getvalue())
        self.assertIn("NOT EVALUATED", err.getvalue())
        self.assertIn("platform-control.openapi.yaml", err.getvalue())
        self.assertNotIn(
            "guard skipped",
            out.getvalue(),
            "the wording that reads as a pass must not appear when work was unexamined",
        )

    def test_clean_tree_keeps_the_original_skip_wording(self) -> None:
        """CI behaviour must be untouched: clean checkout, nothing pending."""
        with (
            patch.object(MODULE, "changed_files_between", return_value=[]),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=[]),
        ):
            with _capture() as (out, err):
                exit_code = MODULE.evaluate("origin/main", "HEAD")

        self.assertEqual(exit_code, 0)
        self.assertIn("guard skipped", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_uncommitted_path_already_in_the_commit_range_is_not_double_reported(self) -> None:
        with (
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/api/x.yaml", "contracts/manifest.yaml"],
            ),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=["contracts/api/x.yaml"]),
            patch.object(MODULE, "load_manifest_version_from_file", return_value="1.2.0"),
            patch.object(MODULE, "load_manifest_version_from_git", return_value="1.1.0"),
        ):
            with _capture() as (_out, err):
                exit_code = MODULE.evaluate("origin/main", "HEAD")

        self.assertEqual(exit_code, 0)
        self.assertEqual(err.getvalue(), "", "a committed path must not be reported as pending")

    def test_changed_files_between_falls_back_to_two_dot_without_merge_base(self) -> None:
        with patch.object(
            MODULE,
            "run",
            side_effect=[
                RuntimeError("fatal: origin/main...HEAD: no merge base"),
                "contracts/api/legal-search.openapi.yaml\n",
            ],
        ) as run_mock:
            changed = MODULE.changed_files_between("origin/main", "HEAD")

        self.assertEqual(changed, ["contracts/api/legal-search.openapi.yaml"])
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(run_mock.call_args_list[0].args[0], ["git", "diff", "--name-only", "origin/main...HEAD"])
        self.assertEqual(run_mock.call_args_list[1].args[0], ["git", "diff", "--name-only", "origin/main..HEAD"])


if __name__ == "__main__":
    unittest.main()
