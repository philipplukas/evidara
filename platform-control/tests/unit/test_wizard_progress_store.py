"""The compare-and-set writer for `WizardRun.progress` (#561).

These tests are the narrowest proof that concurrent shard progress writes cannot
lose each other. They do not need Temporal, a worker, or a provider — the bug was
never in the workflow, it was in two statements with a gap between them.

The interleaving is *deterministic*, not raced: `update_wizard_progress` calls its
mutation callback in exactly the window between its read and its write, so a
callback that commits a competing write from a second connection reproduces the
lost update on demand. `asyncio.gather` would only reproduce it sometimes, which
is how it survived review in the first place.
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.services.wizard_progress import (
    MAX_CAS_ATTEMPTS,
    ProgressWriteConflictError,
    roll_up_shard_totals,
    update_wizard_progress,
)


def _sqlite_path() -> str:
    """Filesystem path behind the test session factory's SQLite URL."""
    url = os.environ["PLATFORM_CONTROL_DATABASE_URL"]
    return url.removeprefix("sqlite+aiosqlite:///")


def _commit_competing_write(wizard_run_id: str, progress: dict) -> None:
    """Write `progress` from a second connection, bumping the version as a writer must.

    Stands in for the sibling shard activity that commits while another writer is
    mid-update. Uses stdlib sqlite3 because it must be callable from the
    synchronous mutation callback — i.e. from inside the exact window the bug
    lived in.
    """
    connection = sqlite3.connect(_sqlite_path())
    try:
        connection.execute(
            "UPDATE wizard_runs "
            "SET progress = ?, progress_version = progress_version + 1 "
            "WHERE wizard_run_id = ?",
            (json.dumps(progress), wizard_run_id),
        )
        connection.commit()
    finally:
        connection.close()


async def _make_wizard_run(session_maker) -> str:
    async with session_maker() as session:
        project = WizardProject(name="progress store")
        session.add(project)
        await session.flush()
        run = WizardRun(wizard_project_id=project.wizard_project_id, progress={})
        session.add(run)
        await session.commit()
        return run.wizard_run_id


@pytest.mark.asyncio
async def test_a_competing_write_is_not_lost(session_maker) -> None:
    """The classic lost update: two writers, both writes survive.

    Writer A reads `{}`. Writer B commits `{"shards": {"b": ...}}` before A writes.
    Under the old read-modify-write, A's write clobbered B's and the admin UI
    silently under-reported. Under compare-and-set, A's stale write touches zero
    rows, A re-reads B's state, and re-applies on top of it.
    """
    wizard_run_id = await _make_wizard_run(session_maker)
    mutate_calls: list[dict] = []

    def add_shard_a(progress: dict) -> dict:
        mutate_calls.append(dict(progress))
        if len(mutate_calls) == 1:
            # We are between A's read and A's write. B commits here.
            _commit_competing_write(
                wizard_run_id,
                {"shards": {"b": {"records_accepted": 5}}},
            )
        shards = dict(progress.get("shards") or {})
        shards["a"] = {"records_accepted": 3}
        progress["shards"] = shards
        return roll_up_shard_totals(progress)

    stored = await update_wizard_progress(session_maker, wizard_run_id, add_shard_a)

    assert stored is not None
    # A lost the first round and re-applied on top of B — both shards are present.
    assert len(mutate_calls) == 2
    assert set(stored["shards"]) == {"a", "b"}
    assert stored["accepted_records"] == 8

    async with session_maker() as session:
        persisted = await session.get(WizardRun, wizard_run_id)
        assert persisted is not None
        assert set(persisted.progress["shards"]) == {"a", "b"}
        assert persisted.progress["accepted_records"] == 8
        # Two committed writes, so two version bumps off the initial 0.
        assert persisted.progress_version == 2


@pytest.mark.asyncio
async def test_a_writer_that_never_wins_raises_rather_than_dropping_the_write(
    session_maker,
) -> None:
    """Losing forever must be loud. A silently dropped progress write is the bug."""
    wizard_run_id = await _make_wizard_run(session_maker)
    rounds = 0

    def always_loses(progress: dict) -> dict:
        nonlocal rounds
        rounds += 1
        _commit_competing_write(wizard_run_id, {"round": rounds})
        progress["mine"] = True
        return progress

    with pytest.raises(ProgressWriteConflictError):
        await update_wizard_progress(session_maker, wizard_run_id, always_loses)

    assert rounds == MAX_CAS_ATTEMPTS


@pytest.mark.asyncio
async def test_missing_wizard_run_is_reported_not_invented(session_maker) -> None:
    assert await update_wizard_progress(session_maker, "wrn_does_not_exist", dict) is None


def test_shard_totals_are_derived_so_a_retried_report_cannot_double_count() -> None:
    """`report_shard_progress` retries up to 3×; `+=` counted each retry again."""
    progress = {
        "shards": {
            "zh": {"nodes_discovered": 4, "records_accepted": 3, "records_sent_to_review": 1},
            "be": {"nodes_discovered": 2, "records_accepted": 2, "records_sent_to_review": 0},
        }
    }

    once = roll_up_shard_totals(dict(progress))
    twice = roll_up_shard_totals(roll_up_shard_totals(dict(progress)))

    assert once == twice
    assert once["total_nodes"] == 6
    assert once["accepted_records"] == 5
    assert once["routed_to_review"] == 1
