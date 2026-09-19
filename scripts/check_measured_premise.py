#!/usr/bin/env python3
"""An issue that asserts production state must carry the command that established it.

## Why

Six tickets worked on 2026-09-19 had premises that were false or stale by the
time anyone acted on them:

- **#953** — the 500 reproduces only under a dev-only seeder.
- **#984** — the file the issue cites is not wired into the running app.
- **#871** — three predictions, all refuted; the corpus had been rebuilt after the fix.
- **#1012** said 58 where there were 116; **#1028**'s 30 records were already
  gone; **#975**'s headline measurement had been overtaken.

None of those were careless. They were true when written. What was missing was
the *command* — with a date and an output — that a later reader could re-run in
one line instead of re-deriving from prose.

So two things are asserted here, and they only work as a pair:

1. **The issue forms ask for it**, required, on every form that can assert state.
2. **The execution recipe re-runs it first.** A required field nobody re-checks
   just moves the stale claim from the body to a labelled box. `.claude/commands/
   issue-execute.md` must re-measure and report `PREMISE: PASS` / `PREMISE: STALE`
   *before* the implement step — and the ordering is checked, because a
   verification step that runs after the code is written is a postmortem.

Exit codes: 0 everything in place, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
DEFAULT_RECIPE = REPO_ROOT / ".claude" / "commands" / "issue-execute.md"

# Forms that can assert something about the running system. `feature_request`,
# `architecture_decision` and `research_workflow_idea` propose rather than
# assert, so they are deliberately out of scope — listing them would make the
# field a formality on the forms where it matters.
FORMS_REQUIRING_MEASURED: tuple[str, ...] = ("bug_report.yml", "component_task.yml")

MEASURED_FIELD_ID = "measured"

# The field is worthless without all three: a bare assertion is what it replaces.
DESCRIPTION_REQUIREMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("the command", ("command",)),
    ("the date it was run", ("date you ran it", "the day")),
    ("its output", ("output", "the rows")),
    ("where the read-only queries live", ("measure-before-you-theorise",)),
    ("an explicit 'not measured' escape", ("not measured",)),
)

RECIPE_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("the PASS verdict", "PREMISE: PASS"),
    ("the STALE verdict", "PREMISE: STALE"),
    ("the instruction to re-run the command today", "Re-run the command it names, today"),
    ("a pointer to the read-only queries", "measure-before-you-theorise"),
    ("the instruction to stop on STALE", "On STALE, **stop and surface it to the user**"),
)

# The premise step must come before this heading, or it is a postmortem.
IMPLEMENT_HEADING = "## 5. Implement + verify"
PREMISE_HEADING = "## 0. Re-measure the premise"


def check_forms(template_dir: Path) -> list[str]:
    problems: list[str] = []
    for name in FORMS_REQUIRING_MEASURED:
        path = template_dir / name
        if not path.exists():
            problems.append(f"{name}: missing — a form that can assert state was deleted")
            continue
        try:
            form = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append(f"{name}: not parseable as YAML ({error})")
            continue

        body = form.get("body") if isinstance(form, dict) else None
        fields = [f for f in (body or []) if isinstance(f, dict)]
        measured = next((f for f in fields if f.get("id") == MEASURED_FIELD_ID), None)
        if measured is None:
            problems.append(
                f"{name}: no field with id '{MEASURED_FIELD_ID}'. Every form that can assert "
                "production state must ask for the command, the date and the output."
            )
            continue
        if measured.get("type") != "textarea":
            problems.append(f"{name}: the '{MEASURED_FIELD_ID}' field must be a textarea")
        if not (measured.get("validations") or {}).get("required"):
            problems.append(
                f"{name}: '{MEASURED_FIELD_ID}' is optional. An optional measurement is the "
                "state we already had — the field must be required."
            )
        description = str((measured.get("attributes") or {}).get("description", ""))
        for label, needles in DESCRIPTION_REQUIREMENTS:
            if not any(needle in description for needle in needles):
                problems.append(
                    f"{name}: the '{MEASURED_FIELD_ID}' description no longer asks for "
                    f"{label} (expected one of {list(needles)})"
                )
    return problems


def check_recipe(recipe: Path) -> list[str]:
    problems: list[str] = []
    if not recipe.exists():
        return [f"{recipe}: missing — the issue-execution recipe is where the premise is re-run"]
    text = recipe.read_text(encoding="utf-8")

    for label, needle in RECIPE_REQUIREMENTS:
        if needle not in text:
            problems.append(f"{recipe.name}: missing {label} (expected {needle!r})")

    premise_at = text.find(PREMISE_HEADING)
    implement_at = text.find(IMPLEMENT_HEADING)
    if premise_at < 0:
        problems.append(f"{recipe.name}: no '{PREMISE_HEADING}' step")
    elif implement_at >= 0 and premise_at > implement_at:
        problems.append(
            f"{recipe.name}: the premise step comes AFTER '{IMPLEMENT_HEADING}'. Verifying a "
            "premise once the code is written is a postmortem, not a gate."
        )
    return problems


def run(template_dir: Path, recipe: Path) -> int:
    problems = check_forms(template_dir) + check_recipe(recipe)
    if problems:
        print("❌ The measured-premise requirement is incomplete:", file=sys.stderr)
        for problem in problems:
            print(f"   {problem}", file=sys.stderr)
        print(
            "\n   Six tickets in one day (2026-09-19) were worked against premises that were\n"
            "   already false. The field and the re-measure step exist together; neither\n"
            "   works alone.",
            file=sys.stderr,
        )
        return 1
    print("✅ issue forms require a Measured section and issue-execute re-runs it first.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE_DIR)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    args = parser.parse_args(argv)
    return run(args.template_dir, args.recipe)


if __name__ == "__main__":
    raise SystemExit(main())
