"""Tests for `scripts/check_baseline_stale_base.py`.

Per AGENTS.md ("A classifier is tested against the surface it classifies"), the
fixtures here are real git repositories with real binary blobs at the real
snapshot paths, driven through the real `git` binary — not a mocked history.
The case whose answer is established independently of the guard is
`test_the_incident_that_motivated_this_guard`, which reconstructs the #1054 /
#1051 collision from its actual shape: two branches, one file, the base landing
first.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_baseline_stale_base as guard  # noqa: E402
import check_visual_baseline_provenance as provenance  # noqa: E402

BASELINE = guard.SNAPSHOT_DIRS[1] / "run-detail-v2-chromium-linux.png"
OTHER = guard.SNAPSHOT_DIRS[0] / "empty-state-mobile-linux.png"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class RepoFixture:
    """A throwaway repo with a `main` and a feature branch."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        git(self.path, "init", "-q", "-b", "main")
        git(self.path, "config", "user.email", "t@example.invalid")
        git(self.path, "config", "user.name", "T")
        self.write(BASELINE, b"\x89PNG original")
        self.write(OTHER, b"\x89PNG other-original")
        self.commit("base")

    def write(self, path: Path, data: bytes) -> None:
        target = self.path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message: str) -> None:
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)

    def branch(self, name: str) -> None:
        git(self.path, "checkout", "-q", "-b", name)

    def checkout(self, name: str) -> None:
        git(self.path, "checkout", "-q", name)

    def close(self) -> None:
        self._tmp.cleanup()


class StaleBaseGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = RepoFixture()
        self.addCleanup(self.repo.close)

    def check(self, base: str = "main", head: str = "HEAD") -> list[str]:
        return guard.superseded_baselines(self.repo.path, base, head)

    def test_the_incident_that_motivated_this_guard(self) -> None:
        """#1054 lands on main; #1051 captured the same file from the older base."""
        self.repo.branch("licence")
        self.repo.write(BASELINE, b"\x89PNG captured-from-old-base")
        self.repo.commit("refresh baseline on the licence branch")

        self.repo.checkout("main")
        self.repo.write(BASELINE, b"\x89PNG production-build-no-dev-indicator")
        self.repo.commit("remove the dev indicator")

        self.repo.checkout("licence")
        self.assertEqual(self.check(), [BASELINE.as_posix()])

    def test_a_branch_whose_baseline_the_base_did_not_touch_is_fine(self) -> None:
        self.repo.branch("feature")
        self.repo.write(BASELINE, b"\x89PNG my-change")
        self.repo.commit("refresh baseline")

        self.repo.checkout("main")
        self.repo.write(Path("README.md"), b"unrelated")
        self.repo.commit("unrelated work on main")

        self.repo.checkout("feature")
        self.assertEqual(self.check(), [])

    def test_a_branch_that_changed_no_baseline_is_fine(self) -> None:
        """Even when the base moved a baseline underneath it."""
        self.repo.branch("feature")
        self.repo.write(Path("src.ts"), b"code")
        self.repo.commit("code only")

        self.repo.checkout("main")
        self.repo.write(BASELINE, b"\x89PNG moved-on-main")
        self.repo.commit("baseline moved on main")

        self.repo.checkout("feature")
        self.assertEqual(self.check(), [])

    def test_a_baseline_this_branch_introduced_is_not_stale(self) -> None:
        """The base cannot have superseded a file the branch created."""
        new_file = guard.SNAPSHOT_DIRS[1] / "brand-new-view-chromium-linux.png"
        self.repo.branch("feature")
        self.repo.write(new_file, b"\x89PNG brand-new")
        self.repo.commit("add a new baseline")
        self.assertEqual(self.check(), [])

    def test_each_surface_is_checked_independently(self) -> None:
        """A collision on one surface does not implicate the other's baseline."""
        self.repo.branch("feature")
        self.repo.write(BASELINE, b"\x89PNG admin-change")
        self.repo.write(OTHER, b"\x89PNG frontend-change")
        self.repo.commit("both surfaces")

        self.repo.checkout("main")
        self.repo.write(OTHER, b"\x89PNG frontend-moved-on-main")
        self.repo.commit("only the frontend baseline moved")

        self.repo.checkout("feature")
        self.assertEqual(self.check(), [OTHER.as_posix()])

    def test_a_baseline_deleted_on_the_base_is_reported(self) -> None:
        """Deletion is a change too: re-adding it silently resurrects a retired view."""
        self.repo.branch("feature")
        self.repo.write(BASELINE, b"\x89PNG refreshed")
        self.repo.commit("refresh")

        self.repo.checkout("main")
        (self.repo.path / BASELINE).unlink()
        self.repo.commit("retire the view and its baseline")

        self.repo.checkout("feature")
        self.assertEqual(self.check(), [BASELINE.as_posix()])

    def test_non_png_changes_in_a_snapshot_dir_are_ignored(self) -> None:
        """PROVENANCE.md collides textually, and git can merge text."""
        ledger = guard.SNAPSHOT_DIRS[1] / "PROVENANCE.md"
        self.repo.write(ledger, b"# ledger\n")
        self.repo.commit("add ledger")

        self.repo.branch("feature")
        self.repo.write(ledger, b"# ledger\n\n## my entry\n")
        self.repo.commit("ledger entry")

        self.repo.checkout("main")
        self.repo.write(ledger, b"# ledger\n\n## their entry\n")
        self.repo.commit("their ledger entry")

        self.repo.checkout("feature")
        self.assertEqual(self.check(), [])


class GuardWiringTests(unittest.TestCase):
    def test_snapshot_dirs_match_the_provenance_guard(self) -> None:
        """A directory guarded by one and not the other is the gap both close."""
        self.assertEqual(
            tuple(sorted(d.as_posix() for d in guard.SNAPSHOT_DIRS)),
            tuple(sorted(d.as_posix() for d in provenance.SNAPSHOT_DIRS)),
        )

    def test_a_missing_base_ref_reports_did_not_run_rather_than_passing(self) -> None:
        repo = RepoFixture()
        self.addCleanup(repo.close)
        code = guard.main(
            ["--base", "origin/nonexistent", "--repo-root", str(repo.path)]
        )
        self.assertEqual(code, guard.DID_NOT_RUN)
        self.assertNotEqual(code, 0)

    def test_the_cli_fails_on_the_incident_shape(self) -> None:
        repo = RepoFixture()
        self.addCleanup(repo.close)
        repo.branch("licence")
        repo.write(BASELINE, b"\x89PNG old-base")
        repo.commit("refresh")
        repo.checkout("main")
        repo.write(BASELINE, b"\x89PNG newer")
        repo.commit("newer")
        repo.checkout("licence")
        self.assertEqual(guard.main(["--base", "main", "--repo-root", str(repo.path)]), 1)

    def test_the_cli_passes_a_clean_branch(self) -> None:
        repo = RepoFixture()
        self.addCleanup(repo.close)
        repo.branch("feature")
        repo.write(Path("src.ts"), b"code")
        repo.commit("code")
        repo.checkout("feature")
        self.assertEqual(guard.main(["--base", "main", "--repo-root", str(repo.path)]), 0)


if __name__ == "__main__":
    unittest.main()
