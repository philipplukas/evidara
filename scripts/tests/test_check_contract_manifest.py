from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
import os


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_contract_manifest.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "contract_manifest"
SPEC = importlib.util.spec_from_file_location("check_contract_manifest", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContractManifestValidationTests(unittest.TestCase):
    def assert_main_result(self, fixture_name: str, expected_result: int) -> None:
        root = FIXTURES_DIR / fixture_name
        original_cwd = Path.cwd()
        try:
            os.chdir(root)
            self.assertEqual(MODULE.main(), expected_result)
        finally:
            os.chdir(original_cwd)

    def test_main_passes_when_manifest_matches_contract_files(self) -> None:
        self.assert_main_result("valid", 0)

    def test_main_fails_when_api_version_does_not_match_openapi_file(self) -> None:
        self.assert_main_result("api-version-mismatch", 1)


if __name__ == "__main__":
    unittest.main()
