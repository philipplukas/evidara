"""Self-test for scripts/bump_contract_version.py.

The script exists because the two contract version numbers are enforced by two
different gates that do not mention each other, and getting one without the other
is this repo's most repeated contract mistake — three PRs from one lane missed the
top-level bump in a single day (2026-09-03).

Since #913 the two numbers move at different TIMES, which is the thing worth
testing here: this script writes a changeset and may move
`apis.platform_control.version`, and it must never touch the manifest's top-level
`version`. That key is now written only by `release_contract_version.py`; a second
writer would put the shared scalar back in every contract PR and reintroduce the
conflict the changeset removes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "bump_contract_version.py"
SPEC = importlib.util.spec_from_file_location("bump_contract_version", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BumpTests(unittest.TestCase):
    def test_minor_resets_patch(self) -> None:
        self.assertEqual(MODULE.bump("2.36.4", "minor"), "2.37.0")

    def test_patch_keeps_minor(self) -> None:
        self.assertEqual(MODULE.bump("2.36.4", "patch"), "2.36.5")

    def test_rejects_an_unknown_part(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.bump("2.36.4", "major")


class ChangesetAuthoringTests(unittest.TestCase):
    SUMMARY = "The coverage ledger gains a refusal count on the response."

    def test_the_written_changeset_parses(self) -> None:
        """Round trip: what this writes must be what the gate accepts.

        Two files describing one format is how they drift; this asserts they do
        not, against the real parser rather than a copy of its rules.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.yaml"
            MODULE.write_changeset(path, "minor", True, self.SUMMARY)
            record = MODULE.cs.parse(path)
        self.assertEqual(record.bump, "minor")
        self.assertTrue(record.additive)
        self.assertIn("refusal count", record.summary)

    def test_breaking_round_trips_as_not_additive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.yaml"
            MODULE.write_changeset(path, "patch", False, self.SUMMARY)
            self.assertFalse(MODULE.cs.parse(path).additive)

    def test_filenames_are_unique_for_identical_summaries(self) -> None:
        """Guard: the random suffix in `changeset_filename`.

        Two PRs choosing the same descriptive name would collide on one path —
        an add/add conflict, i.e. exactly the failure the changeset removes,
        moved to a different file.
        """
        names = {MODULE.changeset_filename(self.SUMMARY, None) for _ in range(50)}
        self.assertEqual(len(names), 50)

    def test_slug_is_derived_from_the_summary(self) -> None:
        self.assertTrue(
            MODULE.changeset_filename(self.SUMMARY, None).startswith("the-coverage-ledger")
        )


class SingleWriterTests(unittest.TestCase):
    def test_this_script_does_not_write_the_top_level_manifest_version(self) -> None:
        """Guard: single-writer discipline for the shared scalar.

        This script used to bump `contracts/manifest.yaml`'s top-level `version`
        directly. That is the line every contract PR contended for. If it comes
        back here, #913 is unfixed no matter what the gate accepts.
        """
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "_TOP_LEVEL_VERSION",
            source,
            "only release_contract_version.py may write the top-level version",
        )

    def test_api_version_constant_is_found_in_the_real_module(self) -> None:
        text = MODULE.OPENAPI_MODULE.read_text(encoding="utf-8")
        matches = MODULE._API_VERSION_CONST.findall(text)
        self.assertEqual(len(matches), 1, "API_VERSION must be assigned exactly once")

    def test_the_api_block_pattern_finds_the_nested_key_in_the_real_manifest(self) -> None:
        """The `--api` mirror must still locate `apis.platform_control.version`.

        A pattern that stopped matching would make `--api` a silent no-op on the
        manifest half, leaving `check_contract_manifest.py` red with no hint why.
        """
        import re

        text = MODULE.MANIFEST.read_text(encoding="utf-8")
        pattern = re.compile(
            r'(?P<head>^  platform_control:.*?^    version:\s*")(?P<value>\d+\.\d+\.\d+)(?P<tail>")',
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(text)
        self.assertIsNotNone(match)
        self.assertNotEqual(
            match.group("value"),
            MODULE.cs.next_version("0.0.0", "patch"),
            "sanity: a real version was matched",
        )


if __name__ == "__main__":
    unittest.main()
