"""CI hook for the golden ``metadata_eval`` harness (see ``metadata_eval.py``)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import metadata_eval as metadata_eval_module


class MetadataEvalHarnessTests(unittest.TestCase):
    def test_metadata_eval_fixtures_pass(self) -> None:
        rows = metadata_eval_module.run_rows(fixture_filter=None)
        self.assertTrue(rows, "expected at least one golden fixture with metadata_eval.expect")
        bad = [r for r in rows if not r.passed]
        self.assertEqual(
            bad,
            [],
            "\n".join(f"{r.fixture} ({r.jurisdiction_id}): {r.failures}" for r in bad),
        )


if __name__ == "__main__":
    unittest.main()
