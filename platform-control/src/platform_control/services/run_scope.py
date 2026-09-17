"""What a single run's scope permits, read from the run rather than the template.

`POST /v1/runs` accepts `scope.max_resources` (`schemas/run.py`), and
`RunService` stores it on the run as `run_metadata["scope"]["max_resources"]`.
Until now nothing read it back: every provider took its limits from
`source_version.acquisition_spec`, so the parameter was validated, persisted and
ignored. An operator passing `--max-resources 25` to a fast-loop driver got the
whole corpus — measured 2026-09-17, a `max_resources: 25` acceptance run on
`lexfind_api_zh_full` published 944 documents.

That is the declared-with-no-producer shape AGENTS.md warns about, and it has a
cost beyond tidiness: acceptance evidence only needs to prove the path works, but
an uncapped run makes every acceptance loop as expensive as a full ingest. The
`ch-fedlex-fast-loop.sh` driver waits for every captured document to reach
`canonical_ready` (deliberately — #731), so 944 documents is a two-hour wait to
produce an evidence bundle that 25 would have produced in minutes.
"""

from __future__ import annotations

from typing import Any


def run_scope_max_resources(run: Any) -> int | None:
    """`max_resources` from the run's own scope, or None when unset.

    Defensive about shape on purpose: `run_metadata` is a JSON column written by
    several code paths and read here at acquisition time, where a malformed value
    must not raise out of `start_run`. Anything that is not a usable positive
    integer reads as "no cap", which is the pre-existing behaviour.
    """
    metadata = getattr(run, "run_metadata", None)
    if not isinstance(metadata, dict):
        return None
    scope = metadata.get("scope")
    if not isinstance(scope, dict):
        return None
    raw = scope.get("max_resources")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        # `bool` is an `int` in Python and `True` would otherwise cap a run at 1.
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def effective_resource_cap(run: Any, spec_cap: int | None = None) -> int | None:
    """The smaller of the run's cap and the template's, or whichever exists.

    A run's scope may only NARROW what the template declares, never widen it. The
    template is the reviewed, approved artifact; the run scope is an argument
    someone passed on a command line. Letting a run raise the template's ceiling
    would turn a bounded source into an unbounded one without a version approval,
    which is the opposite of what ADR-0030's two keys are for.
    """
    run_cap = run_scope_max_resources(run)
    caps = [cap for cap in (run_cap, spec_cap) if cap is not None and cap > 0]
    return min(caps) if caps else None
