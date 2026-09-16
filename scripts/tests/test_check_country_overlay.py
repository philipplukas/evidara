from __future__ import annotations

import unittest

from scripts.check_country_overlay import (
    _known_jurisdiction_ids,
    _validate_template,
    evaluate,
)


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


class TemplateJurisdictionIsDeclaredAndReal(unittest.TestCase):
    """`jurisdiction_id` decides whether registering a source is an API call or a
    repo edit, so a wrong one is worse than an absent one: absent fails closed
    ("no template serves this jurisdiction"), while a typo claims to serve a
    jurisdiction that cannot ever match.
    """

    BASE = {
        "provider": "fedlex_sparql",
        "seed_urls": ["https://fedlex.data.admin.ch/eli/cc/1999/404"],
    }

    def _validate(self, **overrides):
        payload = {**self.BASE, **overrides}
        return _validate_template("ch", "fedlex_sparql_probe", payload)

    def test_a_real_jurisdiction_is_accepted(self) -> None:
        self.assertEqual(self._validate(jurisdiction_id="jur_ch_federal"), [])

    def test_an_unknown_jurisdiction_is_rejected(self) -> None:
        errors = self._validate(jurisdiction_id="jur_ch_atlantis")
        self.assertEqual(len(errors), 1)
        self.assertIn("not in", errors[0])
        self.assertIn("jur_ch_atlantis", errors[0])

    def test_a_typo_on_a_real_canton_is_rejected(self) -> None:
        """The failure mode this guard is for: plausible, and silently unmatched."""
        errors = self._validate(jurisdiction_id="jur_ch_zh_")
        self.assertEqual(len(errors), 1)

    def test_an_absent_jurisdiction_is_allowed(self) -> None:
        """Three shipped templates have no jurisdiction in the seed to point at."""
        self.assertEqual(self._validate(), [])

    def test_an_empty_jurisdiction_is_rejected_rather_than_read_as_absent(self) -> None:
        errors = self._validate(jurisdiction_id="   ")
        self.assertEqual(len(errors), 1)
        self.assertIn("non-empty", errors[0])

    def test_every_declared_jurisdiction_in_the_shipped_templates_exists(self) -> None:
        """Guards the committed YAML, not just the validator."""
        for country in ("AT", "CH", "DE", "FR", "IT", "EU"):
            self.assertEqual(evaluate(country), [], f"{country} overlay")

    def test_the_seed_actually_loaded(self) -> None:
        """If the seed path broke, every id would be 'unknown' and the guard would
        reject everything — or, read the other way, a guard comparing against an
        empty set proves nothing. Assert the set is populated and has a known id."""
        self.assertIn("jur_ch_federal", _known_jurisdiction_ids())
        self.assertGreater(len(_known_jurisdiction_ids()), 100)
