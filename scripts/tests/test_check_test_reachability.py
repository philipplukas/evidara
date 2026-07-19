"""Self-test for `scripts/check_test_reachability.py`.

A reachability check that is only ever exercised against a repo it reports as
clean proves nothing — it would pass identically if it found no test files at
all. So every case below asserts BOTH directions: the check must flag the
unreachable file AND stay quiet about the reachable one.

Run as part of `python -m unittest discover -s scripts/tests -p "test_*.py"`.
"""

from __future__ import annotations

import importlib
import io
import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import check_test_reachability as checker  # noqa: E402


class GlobTranslationTests(unittest.TestCase):
    def test_double_star_spans_directories(self):
        pattern = checker.glob_to_regex("src/**/*.test.{ts,tsx}")
        self.assertTrue(pattern.match("src/lib/highlight.test.ts"))
        self.assertTrue(pattern.match("src/a/b/c/thing.test.tsx"))
        self.assertTrue(pattern.match("src/top.test.ts"))
        self.assertFalse(pattern.match("e2e/smoke.spec.ts"))
        self.assertFalse(pattern.match("src/lib/highlight.ts"))

    def test_single_star_does_not_cross_a_slash(self):
        pattern = checker.glob_to_regex("src/*.test.ts")
        self.assertTrue(pattern.match("src/a.test.ts"))
        self.assertFalse(pattern.match("src/lib/a.test.ts"))

    def test_literal_prefix_stops_at_first_glob(self):
        self.assertEqual(checker.literal_prefix("src/**/*.test.ts"), "src")
        self.assertEqual(checker.literal_prefix("../../styles/ui/**/*.test.ts"), "../../styles/ui")
        self.assertEqual(checker.literal_prefix("*.test.ts"), ".")


class PlaywrightSelectionTests(unittest.TestCase):
    """The #605 case: `-g` tag filters versus one-file-by-path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.e2e = self.root / "e2e"
        self.e2e.mkdir()
        (self.e2e / "smoke.spec.ts").write_text(
            'test.describe("Frontend smoke", () => {\n'
            '  test("@smoke renders the shell", async ({ page }) => {});\n'
            "});\n"
        )
        (self.e2e / "workspace-panels.spec.ts").write_text(
            'test.describe("Workspace Panels", () => {\n'
            '  test("renders three resizable panels", async ({ page }) => {});\n'
            "});\n"
        )
        (self.e2e / "visual.spec.ts").write_text(
            'test.describe("Visual regressions", () => {\n'
            '  test("desktop shell matches baseline", async ({ page }) => {});\n'
            "});\n"
        )
        self.surface = checker.Surface("playwright", self.root / "playwright.config.ts", self.e2e, [])
        self.addCleanup(self.tmp.cleanup)

    def inv(self, argv):
        return checker.Invocation(cwd=self.root, argv=argv, source="test")

    def test_tag_filter_selects_only_the_tagged_spec(self):
        invocation = self.inv(["playwright", "test", "-g", "@smoke"])
        self.assertTrue(
            checker.playwright_reaches(invocation, self.surface, self.e2e / "smoke.spec.ts")
        )
        # The whole point: an untagged spec is invisible to every tag filter.
        self.assertFalse(
            checker.playwright_reaches(
                invocation, self.surface, self.e2e / "workspace-panels.spec.ts"
            )
        )

    def test_path_argument_selects_only_that_file(self):
        invocation = self.inv(["playwright", "test", "e2e/visual.spec.ts"])
        self.assertTrue(
            checker.playwright_reaches(invocation, self.surface, self.e2e / "visual.spec.ts")
        )
        self.assertFalse(
            checker.playwright_reaches(
                invocation, self.surface, self.e2e / "workspace-panels.spec.ts"
            )
        )

    def test_bare_test_command_selects_everything(self):
        invocation = self.inv(["playwright", "test"])
        for name in ("smoke.spec.ts", "workspace-panels.spec.ts", "visual.spec.ts"):
            self.assertTrue(
                checker.playwright_reaches(invocation, self.surface, self.e2e / name), name
            )


class VitestConfigSelectionTests(unittest.TestCase):
    """`legal-search/api` runs three vitest projects off three configs.

    Modelling only `vitest.config.ts` reported the #697 integration specs as
    unreachable — a false positive, and in the direction that wastes review
    time rather than hiding problems, but wrong either way.
    """

    def surface(self, name, include, exclude=()):
        root = checker.REPO_ROOT / "legal-search" / "api"
        return checker.Surface(
            "vitest", root / name, root, [], include=list(include), exclude=list(exclude)
        )

    def inv(self, argv):
        return checker.Invocation(
            cwd=checker.REPO_ROOT / "legal-search" / "api", argv=argv, source="t"
        )

    def test_config_flag_selects_the_matching_surface_only(self):
        default = self.surface(
            "vitest.config.ts", ["src/**/*.spec.ts"], ["src/**/*.integration.spec.ts"]
        )
        integration = self.surface("vitest.integration.config.ts", ["src/**/*.integration.spec.ts"])
        spec = checker.REPO_ROOT / "legal-search/api/src/modules/search/search.integration.spec.ts"

        bare = self.inv(["vitest", "run"])
        flagged = self.inv(["vitest", "run", "--config", "vitest.integration.config.ts"])

        # The default run excludes it; the --config run collects it.
        self.assertFalse(checker.vitest_reaches(bare, default, spec))
        self.assertTrue(checker.vitest_reaches(flagged, integration, spec))
        # A --config run must NOT be evaluated against the default config.
        self.assertFalse(checker.vitest_reaches(flagged, default, spec))
        self.assertFalse(checker.vitest_reaches(bare, integration, spec))

    def test_config_arg_parsing_handles_both_spellings(self):
        self.assertEqual(checker.vitest_config_arg(self.inv(["vitest", "run"])), "vitest.config.ts")
        self.assertEqual(
            checker.vitest_config_arg(self.inv(["vitest", "run", "--config", "a.config.ts"])),
            "a.config.ts",
        )
        self.assertEqual(
            checker.vitest_config_arg(self.inv(["vitest", "run", "--config=b.config.ts"])),
            "b.config.ts",
        )


class WorkflowParsingTests(unittest.TestCase):
    """The directory a command runs in decides which package.json resolves it."""

    def write_workflow(self, body: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "wf.yml"
        path.write_text(body)
        return path

    def test_job_level_defaults_working_directory_applies_to_steps(self):
        wf = self.write_workflow(
            "jobs:\n"
            "  frontend:\n"
            "    defaults:\n"
            "      run:\n"
            "        working-directory: legal-search/frontend\n"
            "    steps:\n"
            "      - name: Check\n"
            "        run: npm run check\n"
        )
        commands = checker.workflow_commands(wf)
        self.assertIn(
            (checker.REPO_ROOT / "legal-search/frontend", "npm run check"),
            [(cwd, cmd.strip()) for cwd, cmd in commands],
        )

    def test_a_new_job_resets_the_default_directory(self):
        wf = self.write_workflow(
            "jobs:\n"
            "  frontend:\n"
            "    defaults:\n"
            "      run:\n"
            "        working-directory: legal-search/frontend\n"
            "    steps:\n"
            "      - run: npm run check\n"
            "  contracts:\n"
            "    steps:\n"
            "      - run: python scripts/validate_json_schemas.py\n"
        )
        by_cmd = {cmd.strip(): cwd for cwd, cmd in checker.workflow_commands(wf)}
        self.assertEqual(by_cmd["python scripts/validate_json_schemas.py"], checker.REPO_ROOT)

    def test_block_scalar_run_yields_each_line(self):
        wf = self.write_workflow(
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - name: Many\n"
            "        run: |\n"
            "          echo one\n"
            "          pytest tests/\n"
            "      - name: Next\n"
            "        run: echo done\n"
        )
        commands = [cmd.strip() for _, cmd in checker.workflow_commands(wf)]
        self.assertIn("pytest tests/", commands)
        self.assertIn("echo done", commands)


class CommandResolutionTests(unittest.TestCase):
    def collect(self, cwd, line):
        collector = checker.Collector()
        collector.feed_line(cwd, line, "test")
        return [" ".join(i.argv) for i in collector.invocations]

    def test_shell_keyword_prefix_does_not_hide_the_command(self):
        # CI wraps its Playwright steps as `if npm run e2e:smoke; then ...`.
        self.assertEqual(
            self.collect(checker.REPO_ROOT, "if pytest tests/; then"), ["pytest tests/"]
        )

    def test_python_dash_m_and_uv_run_prefixes_are_stripped(self):
        self.assertEqual(self.collect(checker.REPO_ROOT, "python3 -m pytest tests/"), ["pytest tests/"])
        self.assertEqual(self.collect(checker.REPO_ROOT, "uv run pytest -q"), ["pytest -q"])
        self.assertEqual(
            self.collect(checker.REPO_ROOT, "npx playwright test -g @smoke"),
            ["playwright test -g @smoke"],
        )

    def test_env_assignment_prefix_is_stripped(self):
        self.assertEqual(
            self.collect(checker.REPO_ROOT, "CI=1 pytest tests/"), ["pytest tests/"]
        )

    def test_non_test_commands_are_ignored(self):
        self.assertEqual(self.collect(checker.REPO_ROOT, "npm ci"), [])
        self.assertEqual(self.collect(checker.REPO_ROOT, "ruff check ."), [])


class PytestSelectionTests(unittest.TestCase):
    def test_directory_argument_includes_nested_files(self):
        cwd = checker.REPO_ROOT / "document-intelligence"
        inv = checker.Invocation(cwd=cwd, argv=["pytest", "tests/", "-v"], source="t")
        self.assertTrue(pytest_hit(inv, cwd / "tests" / "sub" / "test_a.py"))
        self.assertFalse(pytest_hit(inv, cwd / "other" / "test_b.py"))

    def test_dash_k_value_is_not_mistaken_for_a_path(self):
        inv = checker.Invocation(
            cwd=checker.REPO_ROOT,
            argv=["pytest", "eval/test_eval_pipeline.py", "-k", "test_ris_fixture"],
            source="t",
        )
        self.assertTrue(pytest_hit(inv, checker.REPO_ROOT / "eval" / "test_eval_pipeline.py"))
        self.assertFalse(pytest_hit(inv, checker.REPO_ROOT / "eval" / "test_other.py"))

    def test_unittest_discover_honours_start_dir_and_pattern(self):
        inv = checker.Invocation(
            cwd=checker.REPO_ROOT,
            argv=["unittest", "discover", "-s", "scripts/tests", "-p", "test_*.py"],
            source="t",
        )
        scripts_tests = checker.REPO_ROOT / "scripts" / "tests"
        self.assertTrue(checker.unittest_reaches(inv, scripts_tests / "test_thing.py"))
        self.assertFalse(checker.unittest_reaches(inv, scripts_tests / "helper.py"))
        self.assertFalse(
            checker.unittest_reaches(inv, checker.REPO_ROOT / "eval" / "test_thing.py")
        )


def pytest_hit(inv, path):
    return checker.pytest_reaches(inv, path)


class EndToEndFixtureTests(unittest.TestCase):
    """Drive `main()` over a fixture repo and assert both outcomes."""

    def build_repo(self, tagged_only: bool) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "app" / "e2e").mkdir(parents=True)

        (root / ".github" / "workflows" / "ci.yml").write_text(
            "jobs:\n"
            "  e2e:\n"
            "    defaults:\n"
            "      run:\n"
            "        working-directory: app\n"
            "    steps:\n"
            "      - run: npm run e2e:smoke\n"
        )
        (root / "app" / "package.json").write_text(
            '{"scripts": {"e2e:smoke": "playwright test -g @smoke"}}'
        )
        (root / "app" / "playwright.config.ts").write_text('export default { testDir: "./e2e" };')
        (root / "app" / "e2e" / "tagged.spec.ts").write_text(
            'test("@smoke does a thing", async () => {});'
        )
        if not tagged_only:
            (root / "app" / "e2e" / "untagged.spec.ts").write_text(
                'test("does another thing", async () => {});'
            )
        return root

    def run_checker(self, root: Path) -> tuple[int, str]:
        os.environ["TEST_REACHABILITY_REPO_ROOT"] = str(root)
        try:
            module = importlib.reload(checker)
            module.KNOWN_UNREACHABLE = {}
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = module.main()
            return code, out.getvalue()
        finally:
            del os.environ["TEST_REACHABILITY_REPO_ROOT"]
            importlib.reload(checker)

    def test_untagged_spec_fails_the_check(self):
        code, output = self.run_checker(self.build_repo(tagged_only=False))
        self.assertEqual(code, 1, output)
        self.assertIn("app/e2e/untagged.spec.ts", output)
        # The tagged spec must NOT be reported (note: "untagged" contains
        # "tagged", so this has to anchor on the full path).
        self.assertNotIn("app/e2e/tagged.spec.ts", output)
        self.assertIn("Unreachable: 1", output)

    def test_repo_where_every_spec_is_selected_passes(self):
        code, output = self.run_checker(self.build_repo(tagged_only=True))
        self.assertEqual(code, 0, output)
        self.assertIn("Test reachability: OK", output)


class RegisterIntegrityTests(unittest.TestCase):
    def test_every_registered_entry_has_a_reason(self):
        for path, reason in checker.KNOWN_UNREACHABLE.items():
            self.assertTrue(reason.strip(), f"{path} is registered with no reason")

    def test_registered_paths_exist(self):
        for path in checker.KNOWN_UNREACHABLE:
            self.assertTrue(
                (checker.REPO_ROOT / path).is_file(),
                f"{path} is registered as unreachable but does not exist — delete the entry",
            )


if __name__ == "__main__":
    unittest.main()
