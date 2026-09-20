"""Native PG enum columns must not drift from their Python enum (#743 review).

`runs.mode` is a **native PostgreSQL enum** created by the initial migration,
while `models/run.py` declares `native_enum=False` and therefore renders a plain
VARCHAR. Two producers define one column, and the test suite only ever meets the
model's: `conftest.py` builds the schema with `Base.metadata.create_all` against
SQLite, and the Testcontainers-Postgres suites do the same.

So adding `RunMode.ACCEPTANCE` passed 583 tests while every acceptance run would
have failed in production with `invalid input value for enum run_mode`. The
refusal path would have failed too, since it also inserts a Run row.

This is the #675/#713 pattern — a second producer of a schema, silently winning
in the environment nobody tests — and the repo's answer to it is a drift gate
rather than a rule people are asked to remember. This is that gate. It reads the
labels the migrations actually create and compares them to the Python enum, so a
new member without a migration fails here instead of in production.

Deliberately parses the migration text rather than running Alembic: it must work
with no database, in the unit tier, on every run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from platform_control.domain import ProcessingStatus, RunMode

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# `ALTER TYPE run_mode ADD VALUE [IF NOT EXISTS] 'acceptance'` — later additions.
_ALTER_RE = re.compile(
    r"ALTER\s+TYPE\s+(?P<name>\w+)\s+ADD\s+VALUE\s+(?:IF\s+NOT\s+EXISTS\s+)?'(?P<label>[^']+)'",
    re.IGNORECASE,
)


def _labels_in_source(source: str, type_name: str) -> set[str]:
    """Labels a single migration module gives the native enum `type_name`.

    Parsed as **code**, not text, for a reason found while extending this gate to
    `processing_status` (#1045): the old regex read
    `sa.Enum("accepted", …, name="processing_status")` out of migration 0026's
    *docstring*, where it appears as prose describing what an earlier migration did. It
    reported one label from a sentence and none from the six-label `CREATE TYPE` two
    files over, whose closing paren carries a trailing comma the pattern did not allow.
    A gate that a comment can satisfy is a gate that can be silenced by writing about it.

    `ast` cannot make that mistake: a docstring is an `Expr` statement and is never the
    callee or argument of a `Call`.
    """
    labels: set[str] = set()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # `sa.Enum(...)` / `postgresql.ENUM(...)` — the CREATE TYPE.
        func = node.func
        callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if callee.lower() == "enum":
            named = next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            if named == type_name:
                labels.update(
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                )

        # `op.execute("ALTER TYPE ... ADD VALUE ...")` — later additions. Any string
        # handed to any call is fair game; only statement-level strings (docstrings)
        # are excluded, which is exactly the distinction that was missing.
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                for match in _ALTER_RE.finditer(arg.value):
                    if match.group("name") == type_name:
                        labels.add(match.group("label"))

    return labels


def _labels_defined_by_migrations(type_name: str) -> set[str]:
    labels: set[str] = set()
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        labels |= _labels_in_source(path.read_text(encoding="utf-8"), type_name)
    return labels


def test_prose_about_an_enum_does_not_count_as_defining_it() -> None:
    """MUTATION: parse the migrations as text again and this fails.

    Without it, the fix above is invisible: every other assertion in this file passes
    just as well with the old regex, because it happened to find enough labels.
    """
    prose = '"""Mentions sa.Enum("mentioned", name="fake_type") and nothing more."""\n'
    assert _labels_in_source(prose, "fake_type") == set()

    # ... and the real form still reads, trailing comma and all.
    real = 'sa.Column("status", sa.Enum(\n    "one",\n    "two",\n    name="fake_type",\n),)\n'
    assert _labels_in_source(real, "fake_type") == {"one", "two"}

    alter = "op.execute(\"ALTER TYPE fake_type ADD VALUE 'three'\")"
    assert _labels_in_source(alter, "fake_type") == {"three"}


@pytest.mark.parametrize(
    ("type_name", "python_enum"),
    [
        ("run_mode", RunMode),
        # `processing_status` IS a native enum (`models/processing_status_update.py`
        # declares `native_enum=True`), so a member the migrations never added is a
        # production-only `invalid input value for enum processing_status`. Unexercised
        # until #1045: `quarantined` had been in the Python enum since #731 and nothing
        # emitted it, so nothing ever tried to insert it.
        ("processing_status", ProcessingStatus),
    ],
)
def test_native_enum_labels_match_the_python_enum(type_name: str, python_enum: type) -> None:
    migration_labels = _labels_defined_by_migrations(type_name)
    # A typo in the regexes would make this vacuously pass, which is the failure
    # mode this file exists to prevent — so assert we found the type at all.
    assert migration_labels, (
        f"No migration defines the '{type_name}' enum. Either the type was renamed "
        f"or this gate's parsing broke — do not silence it by deleting the case."
    )

    python_labels = {member.value for member in python_enum}
    missing = python_labels - migration_labels
    assert not missing, (
        f"{python_enum.__name__} has {sorted(missing)} but no migration adds "
        f"{'it' if len(missing) == 1 else 'them'} to the native '{type_name}' type. "
        f"Postgres will reject the INSERT even though every test passes, because the "
        f"test schema is built from the model (native_enum=False -> VARCHAR), not from "
        f"Alembic. Add `ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '...'`."
    )
