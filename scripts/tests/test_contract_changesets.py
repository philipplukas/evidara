"""Self-test for the contract changeset format and the release computation.

Each test names the guard clause it holds. Delete that clause and the named test
goes red — that is the whole point of the file (AGENTS.md: a guard ships with a
test that fails when the guard is removed).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: `@dataclass` resolves `cls.__module__` through
    # sys.modules on 3.13 and raises AttributeError without this. Omitting it
    # made the file pass only when some earlier test had already imported
    # `contract_changesets` by name — green under discovery, red when run alone,
    # which is precisely the state a mutation test cannot see through.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CS = _load("contract_changesets")
RELEASE = _load("release_contract_version")


VALID = (
    "bump: minor\n"
    "additive: true\n"
    "summary: >-\n"
    "  The coverage ledger gains a refusal count on the response.\n"
)


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "contracts" / "changes").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, body: str) -> Path:
        path = self.root / "contracts" / "changes" / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_accepts_a_well_formed_changeset(self) -> None:
        record = CS.parse(self._write("a.yaml", VALID))
        self.assertEqual(record.bump, "minor")
        self.assertTrue(record.additive)

    def test_rejects_an_unknown_bump(self) -> None:
        """Guard: the `bump not in VALID_BUMPS` check.

        `major` is not offered, and a typo must not fall through to the release
        step, where `next_version` would raise mid-write.
        """
        path = self._write("a.yaml", VALID.replace("minor", "major"))
        with self.assertRaises(ValueError) as ctx:
            CS.parse(path)
        self.assertIn("bump", str(ctx.exception))

    def test_rejects_a_non_boolean_additive(self) -> None:
        """Guard: the `isinstance(additive, bool)` check.

        A missing `additive` must fail rather than default. "Additive" is the
        claim a consumer relies on; an absent one silently reading as true is
        the declared-and-empty shape AGENTS.md calls out.
        """
        path = self._write("a.yaml", "bump: minor\nsummary: >-\n  a long enough summary here\n")
        with self.assertRaises(ValueError):
            CS.parse(path)

    def test_rejects_a_placeholder_summary(self) -> None:
        """Guard: the MIN_SUMMARY_CHARS floor.

        The gate this replaced accepted any changed digit and never looked at
        prose. Requiring a summary is only worth anything if `wip` is refused.
        """
        path = self._write("a.yaml", "bump: patch\nadditive: true\nsummary: wip\n")
        with self.assertRaises(ValueError) as ctx:
            CS.parse(path)
        self.assertIn("summary", str(ctx.exception))

    def test_rejects_a_non_mapping(self) -> None:
        path = self._write("a.yaml", "- just\n- a list\n")
        with self.assertRaises(ValueError):
            CS.parse(path)

    def test_validate_all_reports_every_broken_file(self) -> None:
        """Guard: `validate_all` iterating the whole directory.

        The gate calls this unconditionally, so a malformed changeset cannot sit
        in the tree until the release step trips over it.
        """
        self._write("good.yaml", VALID)
        self._write("bad.yaml", "bump: nonsense\n")
        self._write("worse.yaml", "bump: patch\nadditive: true\nsummary: no\n")
        errors = CS.validate_all(self.root)
        self.assertEqual(len(errors), 2, errors)

    def test_readme_is_not_mistaken_for_a_changeset(self) -> None:
        (self.root / "contracts" / "changes" / "README.md").write_text("# docs", encoding="utf-8")
        self.assertEqual(CS.validate_all(self.root), [])


class AggregateTests(unittest.TestCase):
    @staticmethod
    def _cs(bump: str) -> object:
        return CS.Changeset(path="x", bump=bump, additive=True, summary="s" * 30)

    def test_minor_dominates_patch(self) -> None:
        """Guard: the `any(c.bump == 'minor')` rule.

        Flip it to "the first one wins" and a real minor change released
        alongside a typo fix is published as a patch — a stronger claim of
        compatibility than the change supports.
        """
        self.assertEqual(CS.aggregate_bump([self._cs("patch"), self._cs("minor")]), "minor")
        self.assertEqual(CS.aggregate_bump([self._cs("minor"), self._cs("patch")]), "minor")

    def test_all_patch_stays_patch(self) -> None:
        self.assertEqual(CS.aggregate_bump([self._cs("patch"), self._cs("patch")]), "patch")

    def test_empty_is_an_error_not_a_default(self) -> None:
        with self.assertRaises(ValueError):
            CS.aggregate_bump([])

    def test_next_version_resets_patch_on_minor(self) -> None:
        self.assertEqual(CS.next_version("2.41.4", "minor"), "2.42.0")
        self.assertEqual(CS.next_version("2.41.4", "patch"), "2.41.5")


class ReleaseTests(unittest.TestCase):
    MANIFEST = (
        "# 2.40.0: an older note\n"
        'version: "2.41.0"\n'
        "apis:\n"
        "  platform_control:\n"
        '    version: "0.30.0"\n'
    )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "contracts" / "changes").mkdir(parents=True)
        self.manifest = self.root / "contracts" / "manifest.yaml"
        self.manifest.write_text(self.MANIFEST, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, body: str) -> None:
        (self.root / "contracts" / "changes" / name).write_text(body, encoding="utf-8")

    def test_release_bumps_consumes_and_records(self) -> None:
        self._write("a.yaml", VALID)
        self._write("b.yaml", VALID.replace("minor", "patch"))
        self.assertEqual(RELEASE.release(self.root, self.manifest), 0)

        text = self.manifest.read_text(encoding="utf-8")
        self.assertIn('version: "2.42.0"', text, "minor must dominate patch")
        self.assertIn("# 2.42.0:", text, "the changelog note must be written")
        self.assertIn("coverage ledger", text, "the summary prose must survive into the manifest")
        self.assertEqual(CS.discover(self.root), [], "consumed changesets must be deleted")

    def test_top_level_pattern_matches_only_the_unindented_key(self) -> None:
        """Guard: the `^` anchor in `_TOP_LEVEL_VERSION`.

        Both keys are spelled `version:` in one file. Weaken the anchor and this
        finds two.
        """
        self.assertEqual(RELEASE._TOP_LEVEL_VERSION.findall(self.MANIFEST), ["2.41.0"])

    def test_release_leaves_the_nested_api_version_alone(self) -> None:
        """Guard: `_TOP_LEVEL_VERSION`'s `^` anchor.

        Both keys are `version:` in one file. Drop the anchor and the release
        step rewrites `apis.platform_control.version`, breaking the equality
        `check_contract_manifest.py` asserts against the generated spec.
        """
        self._write("a.yaml", VALID)
        RELEASE.release(self.root, self.manifest)
        self.assertIn('    version: "0.30.0"', self.manifest.read_text(encoding="utf-8"))

    def test_release_refuses_when_nothing_is_pending(self) -> None:
        """Guard: the empty-pending refusal.

        A no-op that exits 0 would let a release script report success having
        published nothing — the abstention shape this repo keeps shipping.
        """
        self.assertNotEqual(RELEASE.release(self.root, self.manifest), 0)
        self.assertIn('version: "2.41.0"', self.manifest.read_text(encoding="utf-8"))

    def test_release_refuses_on_an_invalid_changeset(self) -> None:
        """Guard: the `validate_all` call at the top of `release`.

        Without it a broken changeset is skipped or crashes halfway through a
        partially written manifest.
        """
        self._write("a.yaml", VALID)
        self._write("bad.yaml", "bump: nope\n")
        self.assertEqual(RELEASE.release(self.root, self.manifest), 2)
        self.assertIn('version: "2.41.0"', self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(CS.discover(self.root)), 2, "nothing may be consumed on refusal")

    def test_check_does_not_write(self) -> None:
        self._write("a.yaml", VALID)
        self.assertEqual(RELEASE.check(self.root), 0)
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), self.MANIFEST)
        self.assertEqual(len(CS.discover(self.root)), 1)


class RealRepoTests(unittest.TestCase):
    """Run against the repo's actual files, not a fixture.

    A fixture keeps passing if the real manifest grows a second top-level
    `version:`, at which point the release step rewrites whichever came first.
    """

    def test_the_real_manifest_has_exactly_one_top_level_version(self) -> None:
        text = (SCRIPTS.parent / "contracts" / "manifest.yaml").read_text(encoding="utf-8")
        self.assertEqual(len(RELEASE._TOP_LEVEL_VERSION.findall(text)), 1)

    def test_every_committed_changeset_is_valid(self) -> None:
        self.assertEqual(CS.validate_all(SCRIPTS.parent), [])

    def test_release_script_is_the_only_writer_of_the_top_level_version(self) -> None:
        """Guard: single-writer discipline.

        The conflict #913 is about comes back the moment a second tool edits
        that key. `bump_contract_version.py` in particular used to, and its
        docstring now says it must not.
        """
        offenders = []
        for path in sorted(SCRIPTS.glob("*.py")):
            if path.name in ("release_contract_version.py",):
                continue
            if "_TOP_LEVEL_VERSION" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"only the release step may write the top-level version")


if __name__ == "__main__":
    unittest.main()
