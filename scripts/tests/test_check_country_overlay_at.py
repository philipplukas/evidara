from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_country_overlay_at.py"
SPEC = importlib.util.spec_from_file_location("check_country_overlay_at", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


class AustriaOverlayCheckTests(unittest.TestCase):
    def test_evaluate_passes_for_consistent_overlay_and_seed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            overlay_root = root / "country-overlays" / "at"
            _write_yaml(
                overlay_root / "overlay.yaml",
                {
                    "version": 1,
                    "country_code": "AT",
                    "jurisdiction_overlay": {"canonical_codes": ["AT"]},
                },
            )
            _write_yaml(overlay_root / "user-content.yaml", {"version": 1, "country_code": "AT"})
            _write_yaml(
                overlay_root / "operator-content.yaml", {"version": 1, "country_code": "AT"}
            )
            _write_yaml(
                overlay_root / "reference-data.yaml", {"version": 1, "country_code": "AT"}
            )
            (root / "contracts" / "vocabularies").mkdir(parents=True, exist_ok=True)
            (root / "contracts" / "vocabularies" / "jurisdiction.json").write_text(
                '{"values":{"AT":{"label":"Österreich"}}}', encoding="utf-8"
            )
            _write_yaml(
                root / "platform-control" / "seeds" / "reference" / "jurisdictions.yaml",
                {"version": 1, "items": [{"jurisdiction_id": "jur_at", "slug": "at"}]},
            )
            _write_yaml(
                root / "platform-control" / "seeds" / "reference" / "authorities.yaml",
                {
                    "version": 1,
                    "items": [
                        {"authority_id": "auth_at_ris", "jurisdiction_id": "jur_at"},
                        {"authority_id": "auth_at_ogh", "jurisdiction_id": "jur_at"},
                        {"authority_id": "auth_at_vfgh", "jurisdiction_id": "jur_at"},
                        {"authority_id": "auth_at_vwgh", "jurisdiction_id": "jur_at"},
                    ],
                },
            )
            exit_code, errors = MODULE.evaluate(
                overlay_file=overlay_root / "overlay.yaml",
                user_content_file=overlay_root / "user-content.yaml",
                operator_content_file=overlay_root / "operator-content.yaml",
                reference_data_file=overlay_root / "reference-data.yaml",
                jurisdiction_vocab_file=root / "contracts" / "vocabularies" / "jurisdiction.json",
                seed_jurisdictions_file=root
                / "platform-control"
                / "seeds"
                / "reference"
                / "jurisdictions.yaml",
                seed_authorities_file=root
                / "platform-control"
                / "seeds"
                / "reference"
                / "authorities.yaml",
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(errors, [])

    def test_evaluate_fails_when_austria_seed_entries_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            overlay_root = root / "country-overlays" / "at"
            _write_yaml(
                overlay_root / "overlay.yaml",
                {
                    "version": 1,
                    "country_code": "AT",
                    "jurisdiction_overlay": {"canonical_codes": ["AT"]},
                },
            )
            _write_yaml(overlay_root / "user-content.yaml", {"version": 1, "country_code": "AT"})
            _write_yaml(
                overlay_root / "operator-content.yaml", {"version": 1, "country_code": "AT"}
            )
            _write_yaml(
                overlay_root / "reference-data.yaml", {"version": 1, "country_code": "AT"}
            )
            (root / "contracts" / "vocabularies").mkdir(parents=True, exist_ok=True)
            (root / "contracts" / "vocabularies" / "jurisdiction.json").write_text(
                '{"values":{"AT":{"label":"Österreich"}}}', encoding="utf-8"
            )
            _write_yaml(
                root / "platform-control" / "seeds" / "reference" / "jurisdictions.yaml",
                {"version": 1, "items": [{"jurisdiction_id": "jur_ch", "slug": "ch"}]},
            )
            _write_yaml(
                root / "platform-control" / "seeds" / "reference" / "authorities.yaml",
                {"version": 1, "items": [{"authority_id": "auth_ch_fedlex", "jurisdiction_id": "jur_ch"}]},
            )
            exit_code, errors = MODULE.evaluate(
                overlay_file=overlay_root / "overlay.yaml",
                user_content_file=overlay_root / "user-content.yaml",
                operator_content_file=overlay_root / "operator-content.yaml",
                reference_data_file=overlay_root / "reference-data.yaml",
                jurisdiction_vocab_file=root / "contracts" / "vocabularies" / "jurisdiction.json",
                seed_jurisdictions_file=root
                / "platform-control"
                / "seeds"
                / "reference"
                / "jurisdictions.yaml",
                seed_authorities_file=root
                / "platform-control"
                / "seeds"
                / "reference"
                / "authorities.yaml",
            )
            self.assertEqual(exit_code, 1)
            self.assertTrue(any("jur_at" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
