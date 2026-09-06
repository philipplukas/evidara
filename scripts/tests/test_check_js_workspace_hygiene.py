"""Self-test for scripts/check-js-workspace-hygiene.sh.

A guard that can INVERT is worse than no guard, because it is trusted. Check 2
and check 2b used to be written as::

    if grep -rl 'pattern' --include='Dockerfile*' . | grep -qv node_modules; then err ...

On empty input (no match anywhere, i.e. the healthy case) `grep -qv` returns 1
under GNU grep but 0 under other implementations (ugrep among them), so the
guard fired exactly when the violation was ABSENT. It reported a Dockerfile that
does not exist in this repo, and nearly caused a PR to "fix" a missing file.

So these tests assert BOTH directions for the content checks: the guard fires
when a violation exists, and is silent when it does not. They drive the script
against a synthetic fixture repo via `JS_HYGIENE_REPO_ROOT`.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-js-workspace-hygiene.sh"

VITEST_CONFIG = """
export default {
  resolve: {
    dedupe: ["react", "react-dom"],
  },
};
"""

NEXT_CONFIG = """
export default {
  turbopack: {
    resolveAlias: {
      clsx: "./node_modules/clsx",
      "lucide-react": "./node_modules/lucide-react",
      "tailwind-merge": "./node_modules/tailwind-merge",
    },
  },
};
"""


def _node_major() -> str | None:
    if shutil.which("node") is None:
        return None
    out = subprocess.run(["node", "-v"], capture_output=True, text=True, check=True)
    return out.stdout.strip().lstrip("v").split(".")[0]


class CheckJsWorkspaceHygieneTest(unittest.TestCase):
    """Drives the real script against fixture trees."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.node_major = _node_major()
        if cls.node_major is None:
            raise unittest.SkipTest("node is not installed; the guard cannot run")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # A minimal tree that satisfies every check, so any failure a test sees
        # is the one it introduced. `.nvmrc` tracks the running node on purpose:
        # check 5 (node matches .nvmrc) is about local-vs-CI drift, not about
        # which node this test happens to run on.
        (self.root / ".nvmrc").write_text(f"{self.node_major}\n")
        for surface in ("legal-search/frontend", "platform-control/admin"):
            path = self.root / surface
            path.mkdir(parents=True)
            (path / "vitest.config.ts").write_text(VITEST_CONFIG)
            (path / "next.config.ts").write_text(NEXT_CONFIG)

    def run_guard(self) -> subprocess.CompletedProcess:
        # Inherit the real environment so the guard resolves the SAME `node` that
        # `_node_major()` measured — overriding PATH here made the guard see the
        # system node while the fixture `.nvmrc` tracked nvm's.
        env = {**os.environ, "JS_HYGIENE_REPO_ROOT": str(self.root)}
        return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)

    def assert_passes(self, message: str) -> None:
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, f"{message}\nstderr:\n{result.stderr}")

    def assert_fails_with(self, needle: str, message: str) -> None:
        result = self.run_guard()
        self.assertEqual(result.returncode, 1, f"{message}\nstdout:\n{result.stdout}")
        self.assertIn(needle, result.stderr, message)

    # --- baseline -----------------------------------------------------------

    def test_clean_tree_passes(self) -> None:
        """The healthy case must be silent. This is the direction that inverted."""
        self.assert_passes("a clean fixture tree must pass the guard")

    # --- check 2: postinstall symlink ---------------------------------------

    def test_postinstall_violation_fires(self) -> None:
        (self.root / "legal-search/frontend/package.json").write_text(
            '{"scripts": {"postinstall": "node scripts/ensure-monorepo-shared-modules.mjs"}}'
        )
        self.assert_fails_with(
            "postinstall", "a re-introduced ensure-monorepo-shared-modules postinstall must fail"
        )

    def test_postinstall_inside_node_modules_is_ignored(self) -> None:
        """A vendored dependency's own postinstall is not our problem."""
        vendored = self.root / "legal-search/frontend/node_modules/some-dep"
        vendored.mkdir(parents=True)
        (vendored / "package.json").write_text(
            '{"scripts": {"postinstall": "node scripts/ensure-monorepo-shared-modules.mjs"}}'
        )
        self.assert_passes("matches under node_modules must not trip the guard")

    # --- check 2b: Dockerfile COPY ------------------------------------------

    def test_dockerfile_violation_fires(self) -> None:
        (self.root / "Dockerfile").write_text(
            "FROM node:22\nCOPY scripts/ensure-monorepo-shared-modules.mjs ./scripts/\n"
        )
        self.assert_fails_with(
            "Dockerfile", "a Dockerfile COPYing the deleted symlink script must fail"
        )

    def test_dockerfile_inside_node_modules_is_ignored(self) -> None:
        vendored = self.root / "legal-search/frontend/node_modules/some-dep"
        vendored.mkdir(parents=True)
        (vendored / "Dockerfile").write_text("COPY scripts/ensure-monorepo-shared-modules.mjs .\n")
        self.assert_passes("a vendored Dockerfile must not trip the guard")

    # --- nested checkouts (.claude/worktrees) -------------------------------

    def test_violation_inside_a_claude_worktree_is_ignored(self) -> None:
        """An agent worktree is a checkout of ANOTHER branch, not this tree.

        `.claude/worktrees/` is gitignored, but `grep -r` does not know that. Every
        worktree still holding a pre-#588 branch reported as a live violation of the
        invariant #588 fixed — so this gate FAILED on a clean working tree locally
        while passing in CI, which checks out fresh and has no worktrees. A gate that
        disagrees with CI in the direction of false alarm is one people stop reading.
        """
        worktree = self.root / ".claude/worktrees/agent-abc/legal-search/frontend"
        worktree.mkdir(parents=True)
        (worktree / "package.json").write_text(
            '{"scripts": {"postinstall": "node scripts/ensure-monorepo-shared-modules.mjs"}}'
        )
        (worktree / "Dockerfile").write_text("COPY scripts/ensure-monorepo-shared-modules.mjs .\n")
        self.assert_passes("a violation inside a nested agent worktree must not trip the guard")

    def test_exclusion_does_not_swallow_a_real_dot_prefixed_path(self) -> None:
        """The exclusion is `.claude/worktrees`, not "anything dot-prefixed".

        Guard against widening it to `/\..*/` — a real violation in a dotted
        directory this repo does track would then pass silently.
        """
        dotted = self.root / ".config/legal-search/frontend"
        dotted.mkdir(parents=True)
        (dotted / "Dockerfile").write_text("COPY scripts/ensure-monorepo-shared-modules.mjs .\n")
        self.assert_fails_with(
            "Dockerfile", "a violation in a tracked dot-directory must still fail"
        )

    # --- check 3: stray legal-search package --------------------------------

    def test_legal_search_package_json_fires(self) -> None:
        (self.root / "legal-search/package.json").write_text("{}")
        self.assert_fails_with(
            "legal-search/ has a package.json", "a package.json at legal-search/ must fail"
        )

    # --- check 4 / 4b: react dedupe and turbopack aliases -------------------

    def test_missing_react_dedupe_fires(self) -> None:
        (self.root / "legal-search/frontend/vitest.config.ts").write_text("export default {};\n")
        self.assert_fails_with("does not dedupe", "a vitest config without react dedupe must fail")

    def test_missing_turbopack_alias_fires(self) -> None:
        (self.root / "platform-control/admin/next.config.ts").write_text("export default {};\n")
        self.assert_fails_with(
            "does not resolveAlias", "a next config without the shared-module aliases must fail"
        )

    # --- check 5: node pin ---------------------------------------------------

    def test_node_version_mismatch_fires(self) -> None:
        (self.root / ".nvmrc").write_text(f"{int(self.node_major) + 2}\n")
        self.assert_fails_with(
            "does not match the pinned Node", "a node major differing from .nvmrc must fail"
        )


if __name__ == "__main__":
    unittest.main()
