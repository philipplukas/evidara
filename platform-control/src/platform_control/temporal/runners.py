"""Production rescore runner stubs (#450, M11/A1).

The Temporal worker needs a `TargetedRescoreRunner` factory injected at
startup so `RescoreFromCorrectionActivities` can dispatch to the DI side.
A2 (#451) will replace this with a real DI-backed implementation; for now
the worker uses an in-memory runner that completes deterministically so
the full chain (HTTP trigger → workflow → activity → outcome persist) is
exercisable in production-shaped environments before the Databricks side
lands.

The runner is exported from a production module — the parallel
`InMemoryRescoreScheduler` in test fixtures is for unit tests that mock
the Temporal client. This module's runner runs **inside** the activity.
"""

from __future__ import annotations

from platform_control.temporal.activities import TargetedRescoreRunner


class InMemoryRescoreRunner(TargetedRescoreRunner):
    """No-op runner that returns `("unchanged", None)` deterministically.

    Used by the production worker until A2 (#451) lands the real DI
    implementation. The activity still records the outcome on the
    correction payload, so the chain is visible end-to-end and the
    metrics endpoint counts correctly — just always under `unchanged`.
    """

    async def run_targeted_rescore(
        self,
        *,
        target_entity_type: str,
        target_entity_id: str,
        correction_id: str,
    ) -> tuple[str, str | None]:
        return ("unchanged", None)
