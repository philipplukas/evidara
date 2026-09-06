"""Self-test for scripts/bump_contract_version.py.

The script exists because the two contract version numbers are enforced by two
different gates that do not mention each other, and getting one without the other
is this repo's most repeated contract mistake — three PRs from one lane missed the
top-level bump in a single day (2026-09-03).

So the thing worth testing is not "does it increment"; it is that it cannot
confuse the two numbers. The top-level `version:` and the indented
`apis.platform_control.version:` are both `version:` keys in one file, and a
careless pattern matches the wrong one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
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


class TopLevelVersionPatternTests(unittest.TestCase):
    """The pattern must not match the nested `apis.<name>.version`.

    Guard: drop the `^` anchor / MULTILINE and this fails, because the indented
    key matches first and the script would silently bump the wrong number — the
    exact confusion it was written to remove.
    """

    MANIFEST = (
        "# comment mentioning version\n"
        'version: "2.36.0"\n'
        "apis:\n"
        "  platform_control:\n"
        '    version: "0.25.0"\n'
    )

    def test_matches_the_top_level_key_only(self) -> None:
        match = MODULE._TOP_LEVEL_VERSION.search(self.MANIFEST)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("value"), "2.36.0")

    def test_finds_exactly_one_top_level_version(self) -> None:
        self.assertEqual(len(MODULE._TOP_LEVEL_VERSION.findall(self.MANIFEST)), 1)

    def test_the_real_manifest_has_exactly_one_top_level_version(self) -> None:
        """Run against the repo's actual manifest, not a fixture.

        A fixture would keep passing if the real file grew a second top-level
        `version:` — at which point the script would bump whichever came first.
        """
        text = MODULE.MANIFEST.read_text(encoding="utf-8")
        self.assertEqual(len(MODULE._TOP_LEVEL_VERSION.findall(text)), 1)

    def test_api_version_constant_is_found_in_the_real_module(self) -> None:
        text = MODULE.OPENAPI_MODULE.read_text(encoding="utf-8")
        matches = MODULE._API_VERSION_CONST.findall(text)
        self.assertEqual(len(matches), 1, "API_VERSION must be assigned exactly once")


if __name__ == "__main__":
    unittest.main()
