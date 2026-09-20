"""Self-test for the API_VERSION single-owner lane guard.

Delete `scripts/check_api_version_lane.py` and this module errors on import.
Delete the lane section from `docs/process/parallel-work-streams.md`, or move
`API_VERSION` out of the module the rule names, and a named test goes red.

The fixtures are the real doc and a real copy of the real repo layout, mutated
one fact at a time — the rule's whole job is to stay true of the code, so a
synthetic doc would not test it.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "check_api_version_lane.py"

_spec = importlib.util.spec_from_file_location("check_api_version_lane", MODULE_PATH)
assert _spec and _spec.loader
MODULE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = MODULE
_spec.loader.exec_module(MODULE)

DOC = REPO_ROOT / "docs" / "process" / "parallel-work-streams.md"


class ApiVersionLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _fake_repo(self, *, api_version_lines: int = 1) -> Path:
        """A minimal tree carrying every path the lane section names."""
        root = self.tmp / "repo"
        section = MODULE.extract_section(DOC.read_text(encoding="utf-8"), MODULE.SECTION_HEADING)
        assert section is not None
        for path in set(MODULE._BACKTICKED_PATH.findall(section)):
            target = root / path
            if path.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("placeholder\n", encoding="utf-8")

        module = root / MODULE.OPENAPI_MODULE
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text(
            "".join(f'API_VERSION = "0.3{n}.0"\n' for n in range(api_version_lines)),
            encoding="utf-8",
        )
        manifest = root / MODULE.MANIFEST
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("apis:\n  platform_control:\n    version: \"0.33.0\"\n", encoding="utf-8")
        return root

    def _doc_without(self, needle: str) -> Path:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn(needle, text, f"fixture drift: {needle!r} is no longer in the doc")
        path = self.tmp / "parallel-work-streams.md"
        path.write_text(text.replace(needle, ""), encoding="utf-8")
        return path

    # ── The repository satisfies the guard ──────────────────────────────────
    def test_the_repository_satisfies_the_lane_guard(self) -> None:
        self.assertEqual(MODULE.run(REPO_ROOT, DOC), 0)

    def test_the_fixture_repo_is_itself_acceptable(self) -> None:
        # Otherwise every negative case below could be passing for the wrong reason.
        self.assertEqual(MODULE.run(self._fake_repo(), DOC), 0)

    # ── The rule must exist ─────────────────────────────────────────────────
    def test_deleting_the_lane_section_fails(self) -> None:
        self.assertEqual(MODULE.run(REPO_ROOT, self._doc_without(MODULE.SECTION_HEADING)), 1)

    def test_a_missing_doc_fails(self) -> None:
        self.assertEqual(MODULE.run(REPO_ROOT, self.tmp / "nope.md"), 1)

    def test_every_declared_requirement_is_individually_load_bearing(self) -> None:
        for label, needle in MODULE.SECTION_REQUIREMENTS:
            with self.subTest(label=label):
                self.assertEqual(
                    MODULE.run(REPO_ROOT, self._doc_without(needle)),
                    1,
                    f"lane requirement {label!r} is not load-bearing",
                )

    # ── The rule must stay TRUE ─────────────────────────────────────────────
    def test_moving_api_version_out_of_the_named_module_fails(self) -> None:
        root = self._fake_repo()
        (root / MODULE.OPENAPI_MODULE).unlink()
        self.assertEqual(MODULE.run(root, DOC), 1)

    def test_a_second_api_version_assignment_fails(self) -> None:
        self.assertEqual(MODULE.run(self._fake_repo(api_version_lines=2), DOC), 1)

    def test_a_path_the_section_names_but_the_repo_lacks_fails(self) -> None:
        root = self._fake_repo()
        (root / "scripts" / "check_contract_manifest.py").unlink()
        self.assertEqual(MODULE.run(root, DOC), 1)

    def test_restating_the_current_version_in_the_doc_fails(self) -> None:
        """A fourth copy of the contended scalar is the defect, not the fix."""
        text = DOC.read_text(encoding="utf-8")
        text = text.replace(
            MODULE.SECTION_HEADING,
            MODULE.SECTION_HEADING + '\n\nThe current value is API_VERSION = "0.33.0".\n',
            1,
        )
        path = self.tmp / "restated.md"
        path.write_text(text, encoding="utf-8")
        self.assertEqual(MODULE.run(REPO_ROOT, path), 1)


if __name__ == "__main__":
    unittest.main()
