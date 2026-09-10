from __future__ import annotations

import importlib.util
from pathlib import Path
import contextlib
import io
import tempfile
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

VALID_CHANGESET = MODULE.cs.Changeset(
    path="contracts/changes/x-abcd1234.yaml",
    bump="minor",
    additive=True,
    summary="The coverage ledger gains a refusal count on the response.",
)


@contextlib.contextmanager
def _clean_tree():
    """No malformed changesets in the tree, and nothing uncommitted."""
    with (
        patch.object(MODULE.cs, "validate_all", return_value=[]),
        patch.object(MODULE, "uncommitted_locked_paths", return_value=[]),
    ):
        yield


class ContractChangesetGuardTests(unittest.TestCase):
    def test_passes_when_a_locked_change_ships_a_changeset(self) -> None:
        with (
            _clean_tree(),
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=[
                    "contracts/api/legal-search.openapi.yaml",
                    "contracts/changes/x-abcd1234.yaml",
                ],
            ),
            patch.object(MODULE, "declared_changesets", return_value=[VALID_CHANGESET.path]),
            patch.object(MODULE.cs, "parse", return_value=VALID_CHANGESET),
        ):
            with _capture() as (out, _err):
                self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 0)
        self.assertIn("changeset(s) declared", out.getvalue())

    def test_fails_when_a_locked_change_ships_no_changeset(self) -> None:
        """THE guard. Delete the `if not declared` branch and this goes red.

        Without it a contract surface can change with nothing declaring what
        changed — which is the entire protection the old version-bump rule
        provided.
        """
        with (
            _clean_tree(),
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/events/example.event.json"],
            ),
        ):
            with _capture() as (_out, err):
                self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 2)
        self.assertIn("no changeset was added", err.getvalue())

    def test_a_changeset_deleted_but_not_present_does_not_count(self) -> None:
        """Guard: the `Path(path).is_file()` filter in `declared_changesets`.

        The release commit deletes changesets, so they appear in a diff range
        without existing. Counting a deletion as a declaration would let a
        branch that removed someone else's changeset satisfy the gate.
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "contracts" / "changes" / "gone.yaml")
            with patch.object(MODULE.cs, "is_changeset_path", return_value=True):
                self.assertEqual(MODULE.declared_changesets([missing]), [])

    def test_declared_changesets_ignores_non_changeset_paths(self) -> None:
        self.assertEqual(
            MODULE.declared_changesets(["contracts/api/x.yaml", "contracts/manifest.yaml"]),
            [],
        )

    def test_a_malformed_changeset_fails_even_with_no_locked_change(self) -> None:
        """Guard: the unconditional `cs.validate_all()` call.

        Remove it and a broken changeset sits in the tree until the release step
        trips over it — the gate would have been silent about work it could see.
        """
        with (
            patch.object(
                MODULE.cs,
                "validate_all",
                return_value=["contracts/changes/bad.yaml: `bump` must be one of minor, patch"],
            ),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=[]),
            patch.object(MODULE, "changed_files_between", return_value=[]),
        ):
            with _capture() as (_out, err):
                self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 2)
        self.assertIn("Invalid contract changeset", err.getvalue())

    def test_concurrent_pr_is_unaffected_by_what_main_released(self) -> None:
        """The #913 property, asserted directly.

        The old gate read `contracts/manifest.yaml` from the TIP of the base
        branch and required the branch's value to differ. So PR B, rebased after
        PR A landed the same successor, went red over work that was already
        correct. The verdict must now depend on the branch alone.

        Inverting this means reintroducing a base-branch read; there is none to
        mock, which is exactly the assertion.
        """
        self.assertFalse(
            hasattr(MODULE, "load_manifest_version_from_git"),
            "a base-branch version read is what serialised contract PRs (#913)",
        )
        self.assertFalse(
            hasattr(MODULE, "load_manifest_version_from_file"),
            "the gate must not compare manifest versions at all",
        )

        # And behaviourally: same inputs, whatever main happens to be at.
        with (
            _clean_tree(),
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=[
                    "contracts/api/legal-search.openapi.yaml",
                    "contracts/changes/b-99999999.yaml",
                ],
            ),
            patch.object(MODULE, "declared_changesets", return_value=[VALID_CHANGESET.path]),
            patch.object(MODULE.cs, "parse", return_value=VALID_CHANGESET),
        ):
            with _capture():
                self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 0)

    def test_the_manifest_alone_no_longer_satisfies_the_gate(self) -> None:
        """A hand-edited manifest version is not a declaration any more.

        If it were, the shared scalar would still be the path of least
        resistance and #913 would be unfixed in practice.
        """
        with (
            _clean_tree(),
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/api/x.yaml", "contracts/manifest.yaml"],
            ),
        ):
            with _capture() as (_out, _err):
                self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 2)

    def test_reports_uncommitted_locked_paths_as_not_evaluated(self) -> None:
        """A dirty working tree must never present as a clean pass.

        The guard compares COMMITS, which is right in CI (clean checkout) and a
        trap locally: an edited-but-uncommitted `contracts/api/*` produced
        "No locked contract files changed; guard skipped", which reads as a pass
        over work the guard never looked at. Observed for real on the first
        local run against a genuine contract change (#890).
        """
        with (
            patch.object(MODULE.cs, "validate_all", return_value=[]),
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

    def test_an_uncommitted_changeset_is_also_reported(self) -> None:
        """Guard: `WATCHED_PREFIXES` including the changeset directory.

        Without it, a developer who wrote the changeset but did not commit it is
        told to write one — a correct verdict for the wrong reason, over a tree
        the guard did not fully examine.
        """
        with patch.object(MODULE, "run", return_value=""):
            pass
        with patch.object(MODULE.subprocess, "run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "?? contracts/changes/new-1234abcd.yaml\n"
            self.assertEqual(
                MODULE.uncommitted_locked_paths(),
                ["contracts/changes/new-1234abcd.yaml"],
            )

    def test_clean_tree_keeps_the_original_skip_wording(self) -> None:
        """CI behaviour must be untouched: clean checkout, nothing pending."""
        with (
            _clean_tree(),
            patch.object(MODULE, "changed_files_between", return_value=[]),
        ):
            with _capture() as (out, err):
                exit_code = MODULE.evaluate("origin/main", "HEAD")

        self.assertEqual(exit_code, 0)
        self.assertIn("guard skipped", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_uncommitted_path_already_in_the_commit_range_is_not_double_reported(self) -> None:
        with (
            patch.object(MODULE.cs, "validate_all", return_value=[]),
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/api/x.yaml", "contracts/changes/x-abcd1234.yaml"],
            ),
            patch.object(MODULE, "uncommitted_locked_paths", return_value=["contracts/api/x.yaml"]),
            patch.object(MODULE, "declared_changesets", return_value=[VALID_CHANGESET.path]),
            patch.object(MODULE.cs, "parse", return_value=VALID_CHANGESET),
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
        self.assertEqual(
            run_mock.call_args_list[0].args[0],
            ["git", "diff", "--name-only", "origin/main...HEAD"],
        )
        self.assertEqual(
            run_mock.call_args_list[1].args[0],
            ["git", "diff", "--name-only", "origin/main..HEAD"],
        )


if __name__ == "__main__":
    unittest.main()
