"""Self-test for the measured-premise guard.

Delete `scripts/check_measured_premise.py` and this module errors on import.
Make the Measured field optional, delete it, or move the premise step after the
implement step, and a named test here goes red.

Fixtures are the real issue forms and the real recipe, mutated one property at a
time — per AGENTS.md's classifier rule, a guard is tested against the surface it
classifies, not against a lookalike.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "check_measured_premise.py"

_spec = importlib.util.spec_from_file_location("check_measured_premise", MODULE_PATH)
assert _spec and _spec.loader
MODULE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = MODULE
_spec.loader.exec_module(MODULE)

TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
RECIPE = REPO_ROOT / ".claude" / "commands" / "issue-execute.md"


class MeasuredPremiseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.templates = self.tmp / "ISSUE_TEMPLATE"
        shutil.copytree(TEMPLATE_DIR, self.templates)

    def _mutate_form(self, name: str, mutate) -> None:
        path = self.templates / name
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        mutate(form)
        path.write_text(yaml.safe_dump(form, sort_keys=False), encoding="utf-8")

    def _recipe_without(self, needle: str) -> Path:
        text = RECIPE.read_text(encoding="utf-8")
        self.assertIn(needle, text, f"fixture drift: {needle!r} is no longer in the recipe")
        path = self.tmp / "issue-execute.md"
        path.write_text(text.replace(needle, ""), encoding="utf-8")
        return path

    # ── The repository satisfies the guard ──────────────────────────────────
    def test_the_repository_satisfies_the_measured_premise_guard(self) -> None:
        self.assertEqual(MODULE.run(TEMPLATE_DIR, RECIPE), 0)

    def test_every_listed_form_actually_exists(self) -> None:
        # Otherwise the form loop would pass by iterating over nothing real.
        self.assertTrue(MODULE.FORMS_REQUIRING_MEASURED)
        for name in MODULE.FORMS_REQUIRING_MEASURED:
            self.assertTrue((TEMPLATE_DIR / name).exists(), name)

    # ── The forms ───────────────────────────────────────────────────────────
    def test_a_form_without_the_measured_field_fails(self) -> None:
        self._mutate_form(
            "bug_report.yml",
            lambda form: form.__setitem__(
                "body", [f for f in form["body"] if f.get("id") != "measured"]
            ),
        )
        self.assertEqual(MODULE.run(self.templates, RECIPE), 1)

    def test_an_optional_measured_field_fails(self) -> None:
        def make_optional(form: dict) -> None:
            for field in form["body"]:
                if field.get("id") == "measured":
                    field["validations"]["required"] = False

        self._mutate_form("component_task.yml", make_optional)
        self.assertEqual(MODULE.run(self.templates, RECIPE), 1)

    def test_a_description_that_stops_asking_for_the_output_fails(self) -> None:
        def strip_output(form: dict) -> None:
            for field in form["body"]:
                if field.get("id") == "measured":
                    description = field["attributes"]["description"]
                    for needle in ("output", "the rows"):
                        description = description.replace(needle, "")
                    field["attributes"]["description"] = description

        self._mutate_form("bug_report.yml", strip_output)
        self.assertEqual(MODULE.run(self.templates, RECIPE), 1)

    def test_a_deleted_form_fails(self) -> None:
        (self.templates / "bug_report.yml").unlink()
        self.assertEqual(MODULE.run(self.templates, RECIPE), 1)

    # ── The recipe ──────────────────────────────────────────────────────────
    def test_a_recipe_without_the_stale_verdict_fails(self) -> None:
        self.assertEqual(MODULE.run(TEMPLATE_DIR, self._recipe_without("PREMISE: STALE")), 1)

    def test_a_recipe_without_the_premise_step_fails(self) -> None:
        self.assertEqual(MODULE.run(TEMPLATE_DIR, self._recipe_without(MODULE.PREMISE_HEADING)), 1)

    def test_a_premise_step_after_the_implement_step_fails(self) -> None:
        """A premise verified after the code is written is a postmortem."""
        text = RECIPE.read_text(encoding="utf-8")
        start = text.index(MODULE.PREMISE_HEADING)
        end = text.index("## 1. Scope")
        step = text[start:end]
        reordered = text[:start] + text[end:] + "\n" + step
        path = self.tmp / "reordered.md"
        path.write_text(reordered, encoding="utf-8")
        self.assertEqual(MODULE.run(TEMPLATE_DIR, path), 1)

    def test_a_missing_recipe_fails(self) -> None:
        self.assertEqual(MODULE.run(TEMPLATE_DIR, self.tmp / "nope.md"), 1)

    def test_every_recipe_requirement_is_individually_load_bearing(self) -> None:
        for label, needle in MODULE.RECIPE_REQUIREMENTS:
            with self.subTest(label=label):
                self.assertEqual(
                    MODULE.run(TEMPLATE_DIR, self._recipe_without(needle)),
                    1,
                    f"recipe requirement {label!r} is not load-bearing",
                )


if __name__ == "__main__":
    unittest.main()
