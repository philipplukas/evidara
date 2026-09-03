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

import asyncio
import copy
import random
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.models.wizard_run import WizardRun

#: How many times a losing writer re-reads and re-applies before giving up.
#:
#: Exactly one writer wins each round, so with N writers arriving together the
#: unluckiest loses up to N-1 rounds, and the fan-out is not bounded:
#: `fetch_scope_shards` caps a *derived* shard list at 20, but an explicit
#: `scope["shards"]` list is uncapped (the remaining half of #561). Without
#: backoff this is quadratic and a 70-shard run really does exhaust the budget —
#: measured: 16 of 70 writers raised, and only 54 shards were recorded.
#:
#: The bound alone cannot fix that; :data:`_MAX_BACKOFF_SECONDS` is what does.
#: Jittered backoff de-synchronises the losers so each round has far fewer
#: contenders, which turns "everyone retries in lockstep forever" into a handful
#: of rounds. The count then only has to cover the tail.
MAX_CAS_ATTEMPTS = 200

#: Jittered backoff after a lost round: `uniform(0, min(2^attempt * base, cap))`.
#: Sleeping a *random* interval is the load-bearing part — a fixed delay would
#: keep the losers synchronised and change nothing.
_BASE_BACKOFF_SECONDS = 0.002
_MAX_BACKOFF_SECONDS = 0.25


class ProgressWriteConflictError(RuntimeError):
    """Raised when a progress write lost :data:`MAX_CAS_ATTEMPTS` races in a row.

    Deliberately an error and not a silent give-up: the whole point of #561 is
    that a dropped progress write used to be invisible. An activity that cannot
    record its progress must fail loudly so Temporal retries it.
    """


async def _backoff(attempt: int) -> None:
    ceiling = min(_BASE_BACKOFF_SECONDS * (2**attempt), _MAX_BACKOFF_SECONDS)
    await asyncio.sleep(random.uniform(0, ceiling))  # noqa: S311 — jitter, not crypto


def _apply(current_progress: dict | None, mutate: Callable[[dict], dict]) -> dict:
    # A deep copy so `mutate` cannot smuggle state between rounds via the dict it
    # was handed, and so a mutation that raises leaves nothing half-applied.
    return mutate(copy.deepcopy(dict(current_progress or {})))


async def _cas_round(
    session: AsyncSession,
    wizard_run_id: str,
    mutate: Callable[[dict], dict],
) -> tuple[dict | None, bool]:
    """One read-mutate-compare-and-set round. Commits. Returns ``(progress, won)``.

    ``(None, True)`` means the wizard run does not exist — nothing to write and
    nothing to retry.
    """
    row = (
        await session.execute(
            select(WizardRun.progress, WizardRun.progress_version).where(
                WizardRun.wizard_run_id == wizard_run_id
            )
        )
    ).one_or_none()
    if row is None:
        return None, True
    current_progress, version = row

    new_progress = _apply(current_progress, mutate)

    result = await session.execute(
        update(WizardRun)
        .where(
            WizardRun.wizard_run_id == wizard_run_id,
            WizardRun.progress_version == version,
        )
        .values(progress=new_progress, progress_version=version + 1)
    )
    await session.commit()
    # rowcount == 0: another writer committed between our read and our write.
    return (new_progress, True) if result.rowcount == 1 else (None, False)


async def update_wizard_progress_in_session(
    session: AsyncSession,
    wizard_run_id: str,
    mutate: Callable[[dict], dict],
) -> dict | None:
    """:func:`update_wizard_progress` for a caller that already owns a session.

    **Commits**, once per round — so call it outside, not inside, a transaction
    the caller still intends to extend.
    """
    for attempt in range(MAX_CAS_ATTEMPTS):
        progress, won = await _cas_round(session, wizard_run_id, mutate)
        if won:
            return progress
        await _backoff(attempt)

    raise ProgressWriteConflictError(
        f"Could not write progress for wizard run {wizard_run_id} after "
        f"{MAX_CAS_ATTEMPTS} attempts: another writer won every round."
    )


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
    async with session_factory() as session:
        return await update_wizard_progress_in_session(session, wizard_run_id, mutate)


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
