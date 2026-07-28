"""Every test under `scripts/tests/` must be reachable by the runner CI actually uses.

CI runs ``python -m unittest discover -s scripts/tests -p "test_*.py"``
(`.github/workflows/docs-and-contracts.yml:93`), and `unittest` collects **only**
methods on `TestCase` subclasses. A file written as module-level ``def test_*()``
functions passes a local ``pytest`` run and executes nowhere in CI.

That is not hypothetical. `test_check_visual_baseline_provenance.py` — the self-test for
the guard that stops silently blessed VRT baselines — was written that way, and its eight
assertions had never run in CI. Converting it took the suite from 187 tests to 199.

`check_test_reachability.py` cannot catch this: it asks whether a *file* sits under a
gated path, and this one always did. The defect is one level down, in whether the runner
can see the tests inside it.

The rule is deliberately shallow — a file declaring `test_*` functions at module level
and no `TestCase` is uncollectable, full stop. It does not try to import anything, so it
stays fast and cannot be defeated by an import-time error.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

MODULE_LEVEL_TEST = re.compile(r"^def\s+test_\w*\s*\(", re.MULTILINE)
DECLARES_TESTCASE = re.compile(r"unittest\.TestCase|\(TestCase\)")


class ScriptsTestsAreCollectableTests(unittest.TestCase):
    def test_no_test_file_relies_on_pytest_style_collection(self) -> None:
        offenders: list[str] = []
        checked = 0
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            checked += 1
            if MODULE_LEVEL_TEST.search(text) and not DECLARES_TESTCASE.search(text):
                offenders.append(path.name)

        self.assertTrue(checked, "no test files were scanned — this would pass vacuously")
        self.assertEqual(
            offenders,
            [],
            "these files declare module-level `test_*` functions and no TestCase, so "
            "`unittest discover` — the runner CI uses — collects nothing from them:\n  "
            + "\n  ".join(offenders),
        )

    def test_module_level_functions_alongside_a_testcase_are_also_flagged(self) -> None:
        """A mixed file silently drops the loose functions, which is worse than all-or-nothing.

        Asserted against the real tree rather than a fixture: a file that grows one stray
        module-level test later is exactly how this returns.
        """
        offenders = [
            path.name
            for path in sorted(TESTS_DIR.glob("test_*.py"))
            if MODULE_LEVEL_TEST.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(
            offenders,
            [],
            "module-level `test_*` functions are never collected by `unittest discover`, "
            "even in a file that also defines a TestCase:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
