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

import re
from pathlib import Path

import pytest

from platform_control.domain import RunMode

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# `sa.Enum("preview", "production", name="run_mode")` — the CREATE TYPE.
_CREATE_RE = re.compile(r"sa\.Enum\(\s*([^)]*?)\s*name=[\"'](?P<name>\w+)[\"']\s*\)", re.DOTALL)
# `ALTER TYPE run_mode ADD VALUE [IF NOT EXISTS] 'acceptance'` — later additions.
_ALTER_RE = re.compile(
    r"ALTER\s+TYPE\s+(?P<name>\w+)\s+ADD\s+VALUE\s+(?:IF\s+NOT\s+EXISTS\s+)?'(?P<label>[^']+)'",
    re.IGNORECASE,
)
_LABEL_RE = re.compile(r"[\"']([^\"']+)[\"']")


def _labels_defined_by_migrations(type_name: str) -> set[str]:
    labels: set[str] = set()
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _CREATE_RE.finditer(text):
            if match.group("name") == type_name:
                labels.update(_LABEL_RE.findall(match.group(1)))
        for match in _ALTER_RE.finditer(text):
            if match.group("name") == type_name:
                labels.add(match.group("label"))
    return labels


@pytest.mark.parametrize(
    ("type_name", "python_enum"),
    [("run_mode", RunMode)],
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
