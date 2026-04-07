from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_contract_version_bump.py"
SPEC = importlib.util.spec_from_file_location("check_contract_version_bump", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContractVersionBumpGuardTests(unittest.TestCase):
    def test_evaluate_passes_when_locked_contract_changes_and_manifest_version_bumped(self) -> None:
        with (
            patch.object(
                MODULE,
                "changed_files_between",
                return_value=["contracts/api/legal-search.openapi.yaml", "contracts/manifest.yaml"],
            ),
            patch.object(MODULE, "load_manifest_version_from_file", return_value="1.2.0"),
            patch.object(MODULE, "load_manifest_version_from_git", return_value="1.1.0"),
        ):
            self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 0)

    def test_evaluate_fails_when_locked_contract_changes_without_manifest_update(self) -> None:
        with patch.object(
            MODULE,
            "changed_files_between",
            return_value=["contracts/events/example.event.json"],
        ):
            self.assertEqual(MODULE.evaluate("origin/main", "HEAD"), 2)

    def test_changed_files_between_falls_back_to_two_dot_without_merge_base(self) -> None:
        with patch.object(
            MODULE,
            "run",
            side_effect=[
                RuntimeError("fatal: origin/main...HEAD: no merge base"),
                "contracts/api/legal-search.openapi.yaml\n",
            ],
        ) as run_mock:
            changed = MODULE.changed_files_between("origin/main", "HEAD")

        self.assertEqual(changed, ["contracts/api/legal-search.openapi.yaml"])
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(run_mock.call_args_list[0].args[0], ["git", "diff", "--name-only", "origin/main...HEAD"])
        self.assertEqual(run_mock.call_args_list[1].args[0], ["git", "diff", "--name-only", "origin/main..HEAD"])


if __name__ == "__main__":
    unittest.main()
