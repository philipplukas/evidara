"""The Alembic-built schema must be the schema the models describe.

This suite has two producers of one schema and only ever tested one of them.

Every other test builds its database with `Base.metadata.create_all` — straight
from the SQLAlchemy models. Production builds its database with
`alembic upgrade head` — from the migration scripts. Nothing compared the two, so
a migration could diverge from its model and every test would still pass.

That is not hypothetical. `20260903_0026`'s own docstring says so:

    `processing_status_updates.status` is a **native PostgreSQL enum** … The model
    declares `native_enum=False`, so it renders a plain VARCHAR — and every test
    builds the schema from the model with `Base.metadata.create_all`, including
    both Testcontainers-Postgres suites. So `quarantined` inserts happily
    everywhere in CI and nothing ever meets the Alembic-built schema this
    migration corrects.

On 2026-09-06 that gap let a production API roll ahead of its migration with no
test, no probe and no gate objecting. #898 makes the *deployed* mismatch visible
at `/ready`; this makes the *authored* divergence visible in CI, before it ships.

It is the same hazard AGENTS.md records for the OpenSearch documents index —
"never hand-maintain a parallel copy" — in the relational half of the system.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from docker.errors import DockerException
from sqlalchemy import create_engine
from testcontainers.core.exceptions import ContainerStartException
from testcontainers.postgres import PostgresContainer

from alembic import command
from platform_control import models as _models  # noqa: F401 - registers every table
from platform_control.config import get_settings
from platform_control.database import reset_database_caches
from platform_control.models.base import Base

PLATFORM_CONTROL_ROOT = Path(__file__).resolve().parents[2]

# Objects Alembic owns and the models deliberately do not describe. Anything else
# appearing in the diff is real divergence, so keep this list minimal and
# justified — a permissive ignore list is how this kind of test stops working.
_ALEMBIC_OWNED_TABLES = {"alembic_version"}

# ── KNOWN DIVERGENCE BASELINE ────────────────────────────────────────────────
#
# These already differed when this test was written. It is a RATCHET, not an
# excuse list: a divergence not named here fails the build, and a name here that
# no longer diverges ALSO fails, so the list can only shrink.
#
# Do not add to it to make a build green. Adding an entry is asserting that a
# newly-authored migration may disagree with its model, which is the thing this
# file exists to stop.
#
# GROUP 1 — native enum vs `native_enum=False`. THIS IS THE 2026-09-06 DEFECT,
# and it is loaded on six columns. The migrations create a real Postgres ENUM
# type; the models declare a VARCHAR with Python-side validation. Postgres
# rejects any label outside the type, so adding a value to any of these enums
# in the model inserts happily in every test (schema built by `create_all`) and
# fails in production on the first write. That is exactly how `quarantined`
# reached a production API that could not store it. Tracked in #899.
_KNOWN_ENUM_DIVERGENCES = frozenset(
    {
        "modify_type:processing_status_updates.status",
        "modify_type:provider_jobs.status",
        "modify_type:runs.mode",
        "modify_type:runs.status",
        "modify_type:source_versions.status",
        "modify_type:sources.status",
    }
)

# GROUP 2 — indexes present in the database that the models do not declare.
# Lower risk than group 1: they do not break writes. But an `alembic revision
# --autogenerate` run today would emit DROP INDEX for every one of them, so the
# next person to use autogenerate silently proposes deleting production indexes.
_KNOWN_INDEX_DIVERGENCES = frozenset(
    {
        "remove_index:captured_resources.ix_captured_resources_source_id",
        "remove_index:commentary_insights.ix_commentary_insights_document_id",
        "remove_index:commentary_insights.ix_commentary_insights_review_state",
        "remove_index:corpora.ix_corpora_status",
        "remove_index:corpora.ix_corpora_tenant_id",
        "remove_index:corrections.ix_corrections_operator_id",
        "remove_index:corrections.ix_corrections_status",
        "remove_index:corrections.ix_corrections_target",
        "remove_index:provider_jobs.ix_provider_jobs_run_id",
        "remove_index:raw_artifacts.ix_raw_artifacts_run_id",
        "remove_index:raw_artifacts.ix_raw_artifacts_source_id",
        "remove_index:review_tasks.ix_review_tasks_status",
        "remove_index:review_tasks.ix_review_tasks_wizard_run_id",
        "remove_index:runs.ix_runs_source_id",
        "remove_index:runs.ix_runs_source_version_id",
        "remove_index:runs.uq_runs_idempotency_key",
        "remove_index:schedules.ix_schedules_enabled_source",
        "remove_index:wizard_runs.ix_wizard_runs_project_id",
        "remove_index:wizard_runs.ix_wizard_runs_state",
    }
)

# GROUP 3 — the same uniqueness expressed two ways: a unique INDEX in the
# migration, a UniqueConstraint on the model. Semantically equivalent in
# Postgres; it pairs with `remove_index:runs.uq_runs_idempotency_key` above.
_KNOWN_CONSTRAINT_DIVERGENCES = frozenset(
    {
        "add_constraint:runs.None",
    }
)

KNOWN_DIVERGENCES = (
    _KNOWN_ENUM_DIVERGENCES | _KNOWN_INDEX_DIVERGENCES | _KNOWN_CONSTRAINT_DIVERGENCES
)


def _sync_url(url: str) -> str:
    """Testcontainers hands back a psycopg URL; Alembic and inspection are sync."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    return url


def _key(diff) -> str:  # noqa: ANN001 - alembic's untyped diff tuples
    """A stable identity for one divergence.

    Deliberately coarse — kind, table and object name only. It must NOT include
    the rendered types, or every unrelated column addition to the same table
    would churn the baseline below and train people to regenerate it wholesale,
    which is how a ratchet stops ratcheting.
    """
    # `modify_*` arrives wrapped in a single-element list.
    if isinstance(diff, list) and len(diff) == 1:
        diff = diff[0]

    if isinstance(diff, tuple) and diff and isinstance(diff[0], str):
        kind = diff[0]
        if kind.startswith("modify_"):
            # (kind, schema, table, column, opts, old, new)
            return f"{kind}:{diff[2]}.{diff[3]}"
        obj = diff[1] if len(diff) > 1 else None
        table = getattr(getattr(obj, "table", None), "name", None)
        name = getattr(obj, "name", None)
        if table or name:
            return f"{kind}:{table}.{name}"
        cols = getattr(obj, "columns", None)
        if cols is not None:
            return f"{kind}:{table}.{tuple(c.name for c in cols)}"
        return f"{kind}:{obj}"
    return str(diff)


def _table_of(diff) -> str | None:  # noqa: ANN001
    key = _key(diff)
    _, _, rest = key.partition(":")
    table, _, _ = rest.partition(".")
    return table or None


@pytest.fixture(scope="module")
def alembic_built_engine():
    """A Postgres whose schema was built by `alembic upgrade head`.

    Deliberately NOT `create_all` — that would compare the models against
    themselves, which is the tautology this test exists to replace.
    """
    try:
        with PostgresContainer("postgres:16-alpine") as postgres:
            url = _sync_url(postgres.get_connection_url())

            # `alembic/env.py` takes its URL from `get_settings().database_url`,
            # NOT from the Config object — setting `sqlalchemy.url` alone silently
            # runs the migrations against the default SQLite database and fails on
            # the first ALTER. The env var plus a settings-cache reset is what
            # actually points Alembic at this container.
            previous = os.environ.get("PLATFORM_CONTROL_DATABASE_URL")
            os.environ["PLATFORM_CONTROL_DATABASE_URL"] = url
            get_settings.cache_clear()
            reset_database_caches()
            try:
                # Config with NO ini path, deliberately. `alembic/env.py` calls
                # `fileConfig(config.config_file_name)` when one is set, and
                # `fileConfig` disables every existing logger by default — which
                # silently broke three unrelated log-assertion tests elsewhere in
                # this suite the first time this ran. `env.py` guards that call on
                # `config_file_name is not None`, so leaving it unset skips it.
                # `script_location` is the only ini setting this needs.
                config = Config()
                config.set_main_option("script_location", str(PLATFORM_CONTROL_ROOT / "alembic"))
                command.upgrade(config, "head")
            finally:
                if previous is None:
                    os.environ.pop("PLATFORM_CONTROL_DATABASE_URL", None)
                else:
                    os.environ["PLATFORM_CONTROL_DATABASE_URL"] = previous
                get_settings.cache_clear()
                reset_database_caches()

            engine = create_engine(url)
            try:
                yield engine
            finally:
                engine.dispose()
    except (ContainerStartException, DockerException, OSError) as exc:
        # Same posture as the other Testcontainers suites here. CI provides a
        # Docker daemon, so this never fires there; locally it reports
        # DID-NOT-RUN rather than a false pass.
        pytest.skip(f"Docker-backed Postgres is unavailable: {exc}")


def test_alembic_schema_matches_the_models(alembic_built_engine) -> None:  # noqa: ANN001
    """`alembic upgrade head` must produce what the models declare.

    A non-empty diff means production's schema and the code's expectations have
    drifted. Both directions matter: a column the migrations forgot breaks
    production, and a column the models forgot means an autogenerate will try to
    drop it.
    """
    with alembic_built_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = [
            d
            for d in compare_metadata(context, Base.metadata)
            if _table_of(d) not in _ALEMBIC_OWNED_TABLES
        ]

    found = {_key(d) for d in diffs}

    new = sorted(found - KNOWN_DIVERGENCES)
    assert not new, (
        "A NEW divergence between the Alembic-built schema and the SQLAlchemy models.\n\n"
        "Every other test builds its schema with `Base.metadata.create_all`, so this is\n"
        "the only place the migrations are checked against the models at all. A\n"
        "migration that disagrees with its model passes every other suite and fails in\n"
        "production — that is the 2026-09-06 incident.\n\n"
        "Fix the migration or the model. Do NOT add these to KNOWN_DIVERGENCES to go\n"
        "green; that list is a ratchet for pre-existing drift, not an excuse list.\n\n"
        "New divergences:\n  " + "\n  ".join(new)
    )


def test_the_known_divergence_baseline_has_not_gone_stale(alembic_built_engine) -> None:  # noqa: ANN001
    """A fixed divergence must be removed from the baseline.

    Without this the list only ever grows, entries outlive the problems they
    describe, and it stops being evidence of anything. Fixing drift should
    require deleting a line here — that is the ratchet closing.
    """
    with alembic_built_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = [
            d
            for d in compare_metadata(context, Base.metadata)
            if _table_of(d) not in _ALEMBIC_OWNED_TABLES
        ]

    resolved = sorted(KNOWN_DIVERGENCES - {_key(d) for d in diffs})
    assert not resolved, (
        "These divergences are listed as known but no longer occur. Delete them from\n"
        "KNOWN_DIVERGENCES so the baseline keeps meaning what it says:\n  " + "\n  ".join(resolved)
    )


def test_the_comparison_is_actually_looking_at_something(alembic_built_engine) -> None:  # noqa: ANN001
    """Guard against the test above passing because it compares nothing.

    If the models failed to import, or the migrations built an empty database,
    `compare_metadata` would return an empty diff and the assertion above would
    pass vacuously — the "gate that cannot fail" shape (ADR-0051).
    """
    from sqlalchemy import inspect

    tables = set(inspect(alembic_built_engine).get_table_names())
    model_tables = set(Base.metadata.tables)

    assert "alembic_version" in tables, "migrations did not run against this database"
    assert len(model_tables) > 5, f"models registered only {len(model_tables)} tables"
    assert model_tables - _ALEMBIC_OWNED_TABLES <= tables, (
        "tables declared by the models are absent from the Alembic-built schema: "
        f"{sorted(model_tables - tables - _ALEMBIC_OWNED_TABLES)}"
    )
