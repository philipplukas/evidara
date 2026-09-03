"""Compare-and-set writes to ``WizardRun.progress`` (#561).

``WizardRun.progress`` is a JSON blob that several concurrent shard activities
mutate at once. Every writer used to do a read-modify-write across two
statements with nothing between them:

    progress = dict(wizard_run.progress or {})   # read
    progress["shards"][key] = ...                # modify
    wizard_run.progress = progress               # write

Shards fan out through ``asyncio.gather`` and execute as concurrent activities
on one worker, so two shards finishing near-simultaneously each read the same
``progress``, and the second write silently discards the first shard's entry
*and* its contribution to the aggregate counters. Nothing errors; the admin UI
just reports numbers that are quietly too low.

The fix is a **compare-and-set at the storage layer**, not a narrower
application-level race window:

    UPDATE wizard_runs
       SET progress = :new, progress_version = :v + 1
     WHERE wizard_run_id = :id AND progress_version = :v

The update touches one row only if nobody else committed in between. When it
touches zero rows the caller lost the race, so :func:`update_wizard_progress`
re-reads and re-applies the mutation against the winner's state. No update can
be lost: the losing writer either wins a later round or raises.

WHY CAS AND NOT ``SELECT … FOR UPDATE``
---------------------------------------
A row lock would also be correct on Postgres — and would be a no-op on SQLite,
where SQLAlchemy's dialect silently emits no ``FOR UPDATE`` clause at all. That
is the worst of both worlds: the entire test suite runs on SQLite
(``tests/conftest.py``), so a lock-based fix would be *untested* by every test
that claims to prove it. A version column behaves identically on both engines,
so the test that proves no update is lost proves it on the engine CI runs.

WHY THE MUTATION IS A CALLBACK
------------------------------
Because it is replayed. The caller's function may run more than once — against
whatever state won the previous round — so it must be a pure function of the
progress dict it is handed, never of a snapshot read earlier.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.models.wizard_run import WizardRun

#: How many times a losing writer re-reads and re-applies before giving up.
#:
#: With N writers contending, the unluckiest one can lose at most N-1 rounds, so
#: this has to exceed the realistic shard fan-out — `fetch_scope_shards` caps a
#: *derived* shard list at 20, and an explicit `scope["shards"]` list is not
#: capped at all today (the remaining half of #561). 50 leaves headroom, and each
#: lost round costs one indexed read plus one no-op update, so a generous bound
#: is cheap. Exhausting it raises rather than dropping the write.
MAX_CAS_ATTEMPTS = 50


class ProgressWriteConflictError(RuntimeError):
    """Raised when a progress write lost :data:`MAX_CAS_ATTEMPTS` races in a row.

    Deliberately an error and not a silent give-up: the whole point of #561 is
    that a dropped progress write used to be invisible. An activity that cannot
    record its progress must fail loudly so Temporal retries it.
    """


async def update_wizard_progress(
    session_factory: async_sessionmaker[AsyncSession],
    wizard_run_id: str,
    mutate: Callable[[dict], dict],
) -> dict | None:
    """Apply ``mutate`` to a wizard run's ``progress`` without losing concurrent writes.

    ``mutate`` receives a deep copy of the currently committed progress dict and
    returns the dict to store. It may be called more than once (see the module
    docstring) so it must not depend on anything read outside it.

    Returns the stored progress dict, or ``None`` when the wizard run does not
    exist. Raises :class:`ProgressWriteConflictError` if every attempt loses.
    """
    for _ in range(MAX_CAS_ATTEMPTS):
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(WizardRun.progress, WizardRun.progress_version).where(
                        WizardRun.wizard_run_id == wizard_run_id
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            current_progress, version = row

            new_progress = mutate(copy.deepcopy(dict(current_progress or {})))

            result = await session.execute(
                update(WizardRun)
                .where(
                    WizardRun.wizard_run_id == wizard_run_id,
                    WizardRun.progress_version == version,
                )
                .values(progress=new_progress, progress_version=version + 1)
            )
            await session.commit()
            if result.rowcount == 1:
                return new_progress
            # rowcount == 0: another writer committed between our read and our
            # write. Loop and re-apply `mutate` on top of their result.

    raise ProgressWriteConflictError(
        f"Could not write progress for wizard run {wizard_run_id} after "
        f"{MAX_CAS_ATTEMPTS} attempts: another writer won every round."
    )


def roll_up_shard_totals(progress: dict) -> dict:
    """Recompute the aggregate counters from the per-shard entries, in place.

    Derived, never incremented. ``report_shard_progress`` carries
    ``RetryPolicy(maximum_attempts=3)``, so a ``progress["total_nodes"] += n``
    double-counts every retried shard — a second way the same counters go wrong,
    and one a lock would not have fixed. Summing the shard entries is idempotent:
    running it twice for the same shard yields the same total.
    """
    shards = progress.get("shards") or {}
    progress["total_nodes"] = sum(int(s.get("nodes_discovered", 0) or 0) for s in shards.values())
    progress["accepted_records"] = sum(
        int(s.get("records_accepted", 0) or 0) for s in shards.values()
    )
    progress["routed_to_review"] = sum(
        int(s.get("records_sent_to_review", 0) or 0) for s in shards.values()
    )
    return progress
