"""The readiness check must fire on a real schema/code mismatch.

On 2026-09-06 a pin bump rolled the API to a commit emitting
`ProcessingStatus.QUARANTINED` while the database was one Alembic revision
behind. `/ready` was `SELECT 1`, so the pod reported ready and served traffic;
the mismatch would have surfaced only when a run tried to write `quarantined`.

Every test below exists so that cannot happen silently again. The MISMATCH case
is the one that matters — delete the comparison in `read_schema_revision` and it
goes red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_control.schema_revision import (
    SchemaRevisionStatus,
    expected_head,
    read_schema_revision,
)


class _FakeResult:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def scalar(self) -> str | None:
        return self._value


class _FakeSession:
    """Minimal stand-in: returns a revision, or raises as a missing table would."""

    def __init__(self, revision: str | None = None, raises: bool = False) -> None:
        self._revision = revision
        self._raises = raises

    async def execute(self, _statement):  # noqa: ANN001 - test double
        if self._raises:
            raise RuntimeError('relation "alembic_version" does not exist')
        return _FakeResult(self._revision)


@pytest.fixture(autouse=True)
def _clear_head_cache():
    expected_head.cache_clear()
    yield
    expected_head.cache_clear()


def test_expected_head_finds_the_single_head_of_the_real_graph() -> None:
    """Reads this repo's actual migrations, not a fixture.

    A fixture would keep passing if the resolver stopped finding the real
    scripts — which is precisely the UNKNOWN-in-production failure that would
    hide a mismatch.
    """
    head = expected_head()
    assert head is not None, "the shipped migration scripts must resolve to a head"
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    assert (versions / f"{head}_processing_status_quarantined.py").exists() or any(
        head in script.name for script in versions.glob("*.py")
    ), f"resolved head {head} does not correspond to a migration file"


@pytest.mark.asyncio
async def test_match_when_database_is_at_the_expected_head() -> None:
    head = expected_head()
    revision = await read_schema_revision(_FakeSession(revision=head))

    assert revision.status is SchemaRevisionStatus.MATCH
    assert revision.actual == head


@pytest.mark.asyncio
async def test_mismatch_names_both_revisions() -> None:
    """The guard. Delete the comparison and this fails.

    Both revisions are named because an operator reading a 503 should not have
    to go and look up which migration is missing.
    """
    head = expected_head()
    revision = await read_schema_revision(_FakeSession(revision="20260903_0025"))

    assert revision.status is SchemaRevisionStatus.MISMATCH
    assert revision.actual == "20260903_0025"
    assert revision.expected == head
    assert "20260903_0025" in revision.detail
    assert head in revision.detail


@pytest.mark.asyncio
async def test_missing_alembic_version_table_is_unknown_not_mismatch() -> None:
    """`create_all` builds no version table — that is normal, not a failure.

    Degrading here would make every test suite and every local run unready,
    which is how a check gets deleted rather than fixed.
    """
    revision = await read_schema_revision(_FakeSession(raises=True))

    assert revision.status is SchemaRevisionStatus.UNKNOWN
    assert revision.actual is None
    assert "alembic_version" in revision.detail


@pytest.mark.asyncio
async def test_unknown_is_still_reported_rather_than_hidden() -> None:
    """An unanswered question must be visible.

    A check that silently abstains is the failure mode ADR-0051 names; the
    detail has to say why it could not answer.
    """
    revision = await read_schema_revision(_FakeSession(raises=True))
    assert revision.detail.strip() != ""
    assert "migrate job has never run" in revision.detail


@pytest.mark.asyncio
async def test_unknown_when_scripts_are_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """No scripts on disk means we cannot state what the code expects."""
    monkeypatch.setattr(
        "platform_control.schema_revision._candidate_script_dirs",
        lambda: [Path("/nonexistent/alembic/versions")],
    )
    expected_head.cache_clear()

    revision = await read_schema_revision(_FakeSession(revision="20260903_0026"))

    assert revision.status is SchemaRevisionStatus.UNKNOWN
    assert revision.expected is None
    assert revision.actual == "20260903_0026"
