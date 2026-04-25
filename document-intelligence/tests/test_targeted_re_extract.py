"""Coverage for ``processing_runtime.targeted_re_extract`` (issue #427).

The DI side of the rescore loop is intentionally narrow at this stage —
these tests pin the contract so platform-control's workflow doesn't drift
from what the runtime returns.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.processing_runtime import targeted_re_extract


class TargetedReExtractTests(unittest.TestCase):
    def test_default_extractor_echoes_after_payload_and_diffs(self) -> None:
        result = targeted_re_extract(
            target_entity_type="commentary_insight",
            target_entity_id="ci_di_1",
            baseline={"jurisdiction": "DE"},
            correction_payload={"after": {"jurisdiction": "CH"}},
        )
        self.assertEqual(result["target_entity_type"], "commentary_insight")
        self.assertEqual(result["target_entity_id"], "ci_di_1")
        self.assertEqual(result["fields"], {"jurisdiction": "CH"})
        self.assertEqual(
            result["diff"],
            {"jurisdiction": {"before": "DE", "after": "CH"}},
        )
        self.assertEqual(result["outcome"], "changed")
        self.assertIsNotNone(result["extraction_id"])

    def test_default_extractor_unchanged_when_baseline_matches(self) -> None:
        result = targeted_re_extract(
            target_entity_type="commentary_insight",
            target_entity_id="ci_di_2",
            baseline={"jurisdiction": "CH"},
            correction_payload={"after": {"jurisdiction": "CH"}},
        )
        self.assertEqual(result["outcome"], "unchanged")
        self.assertEqual(result["diff"], {})

    def test_default_extractor_returns_empty_when_no_after_payload(self) -> None:
        result = targeted_re_extract(
            target_entity_type="commentary_insight",
            target_entity_id="ci_di_3",
            baseline={"jurisdiction": "CH"},
            correction_payload={},
        )
        self.assertEqual(result["fields"], {})
        # No diff because the new fields are empty.
        self.assertEqual(result["diff"], {})
        self.assertEqual(result["outcome"], "unchanged")
        self.assertIsNone(result["extraction_id"])

    def test_failed_outcome_when_extractor_raises(self) -> None:
        def explode(**_):
            raise RuntimeError("boom")

        result = targeted_re_extract(
            target_entity_type="commentary_insight",
            target_entity_id="ci_di_4",
            baseline={"a": 1},
            correction_payload={"after": {"a": 2}},
            extractor=explode,
        )
        self.assertEqual(result["outcome"], "failed")
        self.assertIn("boom", result["error"])
        self.assertEqual(result["fields"], {})
        self.assertEqual(result["diff"], {})

    def test_custom_extractor_is_invoked_with_named_arguments(self) -> None:
        captured = {}

        def my_extractor(**kwargs):
            captured.update(kwargs)
            return {"jurisdiction": "FR"}

        result = targeted_re_extract(
            target_entity_type="commentary_insight",
            target_entity_id="ci_di_5",
            baseline={"jurisdiction": "DE"},
            correction_payload={"hint": "europe"},
            extractor=my_extractor,
        )
        self.assertEqual(captured["target_entity_type"], "commentary_insight")
        self.assertEqual(captured["target_entity_id"], "ci_di_5")
        self.assertEqual(captured["correction_payload"], {"hint": "europe"})
        self.assertEqual(result["fields"], {"jurisdiction": "FR"})
        self.assertEqual(
            result["diff"],
            {"jurisdiction": {"before": "DE", "after": "FR"}},
        )
        self.assertEqual(result["outcome"], "changed")


if __name__ == "__main__":
    unittest.main()
