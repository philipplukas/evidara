"""Self-test for `scripts/check_adr_numbers.py`.

Asserts both directions — the check must fire on a fresh collision and stay
quiet without one. A guard only ever observed passing is indistinguishable from
a guard that cannot fail (ADR-0040).
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import check_adr_numbers as checker  # noqa: E402


class AdrNumberTests(unittest.TestCase):
    def run_checker(self, filenames, known=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        adr_dir = Path(tmp.name) / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        for name in filenames:
            (adr_dir / name).write_text("# stub\n")

        os.environ["ADR_NUMBERS_REPO_ROOT"] = tmp.name
        try:
            module = importlib.reload(checker)
            module.KNOWN_DUPLICATES = dict(known or {})
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = module.main()
            return code, out.getvalue()
        finally:
            del os.environ["ADR_NUMBERS_REPO_ROOT"]
            importlib.reload(checker)

    def test_two_files_claiming_one_number_fail(self):
        # The real #676-vs-this-PR shape: different filenames, same number,
        # which git would merge without a conflict.
        code, output = self.run_checker(
            ["0038-user-identity.md", "0038-test-result-trust.md", "0037-binary.md"]
        )
        self.assertEqual(code, 1, output)
        self.assertIn("ADR-0038", output)
        self.assertIn("0038-user-identity.md", output)
        self.assertIn("0038-test-result-trust.md", output)

    def test_distinct_numbers_pass(self):
        code, output = self.run_checker(
            ["0038-user-identity.md", "0039-marketing.md", "0040-test-result-trust.md"]
        )
        self.assertEqual(code, 0, output)
        self.assertIn("ADR numbering: OK", output)

    def test_both_filename_conventions_share_a_namespace(self):
        # `0016-...md` and `adr-0016-...md` are the same number.
        code, output = self.run_checker(["0016-cloud-run.md", "adr-0016-design-system.md"])
        self.assertEqual(code, 1, output)
        self.assertIn("ADR-0016", output)

    def test_registered_duplicate_is_tolerated(self):
        code, output = self.run_checker(
            ["0016-cloud-run.md", "adr-0016-design-system.md"],
            known={"0016": "historical renumbering"},
        )
        self.assertEqual(code, 0, output)

    def test_stale_register_entry_fails(self):
        code, output = self.run_checker(
            ["0040-test-result-trust.md"], known={"0016": "no longer duplicated"}
        )
        self.assertEqual(code, 1, output)
        self.assertIn("stale", output)

    def test_empty_directory_fails_loudly(self):
        # A check that silently finds nothing would report every repo clean.
        code, output = self.run_checker([])
        self.assertEqual(code, 1, output)
        self.assertIn("parser is broken", output)

    def test_real_repo_register_matches_reality(self):
        module = importlib.reload(checker)
        by_number = module.collect()
        actual = {n for n, files in by_number.items() if len(files) > 1}
        self.assertEqual(
            actual,
            set(module.KNOWN_DUPLICATES),
            "KNOWN_DUPLICATES has drifted from docs/adr/",
        )


if __name__ == "__main__":
    unittest.main()
