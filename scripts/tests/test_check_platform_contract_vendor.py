from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_platform_contract_vendor.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "platform_contract_vendor"
SPEC = importlib.util.spec_from_file_location("check_platform_contract_vendor", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PlatformContractVendorTests(unittest.TestCase):
    def assert_main_result(self, fixture_name: str, expected_result: int) -> None:
        root = FIXTURES_DIR / fixture_name
        original_cwd = Path.cwd()
        try:
            os.chdir(root)
            self.assertEqual(MODULE.main(), expected_result)
        finally:
            os.chdir(original_cwd)

    def test_main_passes_when_readme_matches_yaml(self) -> None:
        self.assert_main_result("valid", 0)

    def test_main_fails_when_readme_pin_mismatches_yaml(self) -> None:
        self.assert_main_result("readme-mismatch", 1)

    def test_main_fails_when_readme_missing_pin_line(self) -> None:
        self.assert_main_result("missing-pin", 1)

    def test_main_fails_when_contract_version_not_semver(self) -> None:
        self.assert_main_result("bad-semver", 1)

    def test_main_fails_when_vendor_file_missing(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "**Pinned platform contract:** `0.1.0`\n",
                encoding="utf-8",
            )
            try:
                os.chdir(root)
                self.assertEqual(MODULE.main(), 1)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
