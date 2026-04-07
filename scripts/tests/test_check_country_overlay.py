from __future__ import annotations

import unittest

from scripts.check_country_overlay import _validate_template, evaluate


class CheckCountryOverlayTests(unittest.TestCase):
    def test_rejects_unknown_country(self) -> None:
        errors = evaluate("ES")
        self.assertEqual(len(errors), 1)
        self.assertIn("Unsupported country", errors[0])

    def test_at_overlay_templates_validate(self) -> None:
        self.assertEqual(evaluate("AT"), [])

    def test_de_overlay_templates_validate(self) -> None:
        self.assertEqual(evaluate("DE"), [])

    def test_ch_overlay_templates_validate(self) -> None:
        self.assertEqual(evaluate("CH"), [])

    def test_fr_overlay_templates_validate(self) -> None:
        self.assertEqual(evaluate("FR"), [])

    def test_it_overlay_templates_validate(self) -> None:
        self.assertEqual(evaluate("IT"), [])

    def test_template_name_must_start_with_provider_prefix(self) -> None:
        errors = _validate_template(
            "at",
            "foo_template",
            {"provider": "ris_ogd", "base_url": "https://example.com"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("must start with 'ris_ogd_'", errors[0])


if __name__ == "__main__":
    unittest.main()
