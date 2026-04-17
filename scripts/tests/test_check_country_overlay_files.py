"""Tests for the generalized country-overlay validator.

Exercises the validator against the real `country-overlays/` and
`contracts/` + `platform-control/seeds/` data shipped in the repo, plus
a temp-dir negative case that omits required authorities.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_country_overlay_files.py"
SPEC = importlib.util.spec_from_file_location("check_country_overlay_files", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


REPO_ROOT = Path(__file__).resolve().parents[2]


class RealOverlayCheckTests(unittest.TestCase):
    """Validator runs green against all shipped overlays.

    If these fail, it means a shipped overlay drifted from the shared
    vocabularies or schema — which is exactly what the validator is for.
    Fixing the overlay (not the test) is the right response.
    """

    def test_at_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="AT", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"AT validation errors: {errors}")

    def test_ch_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="CH", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"CH validation errors: {errors}")

    def test_it_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="IT", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"IT validation errors: {errors}")

    def test_eu_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="EU", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"EU validation errors: {errors}")

    def test_de_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="DE", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"DE validation errors: {errors}")

    def test_fr_overlay_passes(self) -> None:
        exit_code, errors = MODULE.evaluate(country="FR", root=REPO_ROOT)
        self.assertEqual(exit_code, 0, f"FR validation errors: {errors}")


class NegativeCaseTests(unittest.TestCase):
    """Verify the validator actually catches the drift classes it claims to."""

    def _write_yaml(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _scaffold_minimal_root(self, root: Path, country: str) -> None:
        iso_lower = country.lower()
        overlay_root = root / "country-overlays" / iso_lower
        self._write_yaml(
            overlay_root / "overlay.yaml",
            {
                "version": 1,
                "country_code": country,
                "jurisdiction_overlay": {
                    "canonical_codes": [country],
                    "hierarchy_paths": [iso_lower, f"{iso_lower}/federal"],
                },
            },
        )
        self._write_yaml(overlay_root / "user-content.yaml", {"version": 1, "country_code": country, "filters": {"jurisdiction": {"label": "X"}}})
        self._write_yaml(overlay_root / "operator-content.yaml", {"version": 1, "country_code": country})
        self._write_yaml(overlay_root / "reference-data.yaml", {
            "version": 1,
            "country_code": country,
            "jurisdiction_id": f"jur_{iso_lower}",
            "authority_ids": [f"auth_{iso_lower}_test"],
        })

        vocab_dir = root / "contracts" / "vocabularies"
        vocab_dir.mkdir(parents=True, exist_ok=True)
        (vocab_dir / "jurisdiction.json").write_text(
            '{"properties":{"values":{"properties":{"' + country + '":{}}}}}',
            encoding="utf-8",
        )
        (vocab_dir / "subdivisions.json").write_text('{"values":{}}', encoding="utf-8")
        (vocab_dir / "source-family.json").write_text('{"values":{"law":{}}}', encoding="utf-8")
        (vocab_dir / "court-level.json").write_text('{"values":{"' + country + '":{}}}', encoding="utf-8")
        (vocab_dir / "language.json").write_text('{"values":{"de":{},"en":{}}}', encoding="utf-8")

        schema_dir = root / "contracts" / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        (schema_dir / "country-overlay.schema.json").write_text(
            '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object"}',
            encoding="utf-8",
        )

        seeds_dir = root / "platform-control" / "seeds" / "reference"
        self._write_yaml(
            seeds_dir / "jurisdictions.yaml",
            {"version": 1, "items": [{"jurisdiction_id": f"jur_{iso_lower}", "slug": iso_lower}]},
        )
        # Seeds include the scaffold's cited authority so the
        # overlay-reference check passes; negative tests override this as
        # needed to trigger specific drift classes.
        self._write_yaml(
            seeds_dir / "authorities.yaml",
            {
                "version": 1,
                "items": [
                    {
                        "authority_id": f"auth_{iso_lower}_test",
                        "jurisdiction_id": f"jur_{iso_lower}",
                        "slug": f"{iso_lower}-test",
                        "name": "Test",
                    }
                ],
            },
        )

    def test_missing_required_authorities_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # AT requires auth_at_ris, auth_at_ogh, auth_at_vfgh, auth_at_vwgh
            self._scaffold_minimal_root(root, "AT")
            exit_code, errors = MODULE.evaluate(country="AT", root=root)
            self.assertEqual(exit_code, 1)
            self.assertTrue(any("auth_at_ris" in e for e in errors), errors)

    def test_invalid_hierarchy_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._scaffold_minimal_root(root, "CH")
            # Re-write overlay with an invalid hierarchy_path
            bad_overlay = root / "country-overlays" / "ch" / "overlay.yaml"
            self._write_yaml(
                bad_overlay,
                {
                    "version": 1,
                    "country_code": "CH",
                    "jurisdiction_overlay": {
                        "canonical_codes": ["CH"],
                        "hierarchy_paths": ["CH/FEDERAL", "ch/cantons/zh"],
                    },
                },
            )
            exit_code, errors = MODULE.evaluate(country="CH", root=root)
            self.assertEqual(exit_code, 1)
            self.assertTrue(any("invalid hierarchy_path" in e for e in errors), errors)

    def test_authority_id_not_in_seeds_fails(self) -> None:
        """Overlay may not reference an authority that doesn't exist in seeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._scaffold_minimal_root(root, "CH")
            # Overlay cites an authority not in seeds.
            self._write_yaml(
                root / "country-overlays" / "ch" / "reference-data.yaml",
                {
                    "version": 1,
                    "country_code": "CH",
                    "jurisdiction_id": "jur_ch",
                    "authority_ids": ["auth_ch_test", "auth_ch_ghost"],
                },
            )
            # Seeds only have auth_ch_test.
            self._write_yaml(
                root / "platform-control" / "seeds" / "reference" / "authorities.yaml",
                {
                    "version": 1,
                    "items": [
                        {
                            "authority_id": "auth_ch_test",
                            "jurisdiction_id": "jur_ch",
                            "slug": "ch-test",
                            "name": "Test",
                        }
                    ],
                },
            )
            exit_code, errors = MODULE.evaluate(country="CH", root=root)
            self.assertEqual(exit_code, 1)
            self.assertTrue(
                any("auth_ch_ghost" in e and "unknown" in e for e in errors),
                errors,
            )

    def test_authority_jurisdiction_mismatch_fails(self) -> None:
        """Overlay may not reference an authority whose seed jurisdiction disagrees."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._scaffold_minimal_root(root, "CH")
            self._write_yaml(
                root / "country-overlays" / "ch" / "reference-data.yaml",
                {
                    "version": 1,
                    "country_code": "CH",
                    "jurisdiction_id": "jur_ch",
                    "authority_ids": ["auth_foreign"],
                },
            )
            # auth_foreign is defined but under a different jurisdiction.
            self._write_yaml(
                root / "platform-control" / "seeds" / "reference" / "authorities.yaml",
                {
                    "version": 1,
                    "items": [
                        {
                            "authority_id": "auth_foreign",
                            "jurisdiction_id": "jur_at",
                            "slug": "foreign",
                            "name": "Foreign",
                        }
                    ],
                },
            )
            exit_code, errors = MODULE.evaluate(country="CH", root=root)
            self.assertEqual(exit_code, 1)
            self.assertTrue(
                any("jur_at" in e and "auth_foreign" in e for e in errors),
                errors,
            )

    def test_unknown_language_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._scaffold_minimal_root(root, "IT")
            overlay_path = root / "country-overlays" / "it" / "overlay.yaml"
            self._write_yaml(
                overlay_path,
                {
                    "version": 1,
                    "country_code": "IT",
                    "jurisdiction_overlay": {
                        "canonical_codes": ["IT"],
                        "hierarchy_paths": ["it", "it/federal"],
                    },
                    "language_defaults": {
                        "primary": "it",
                        "supported": ["it", "xx"],
                    },
                },
            )
            exit_code, errors = MODULE.evaluate(country="IT", root=root)
            self.assertEqual(exit_code, 1)
            self.assertTrue(any("unknown language 'xx'" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
