"""Production rescore runners (#450/#451, M11).

The Temporal worker needs a `TargetedRescoreRunner` factory injected at
startup so `RescoreFromCorrectionActivities` can dispatch to the DI side.
The runner is exported from a production module. The parallel
`InMemoryRescoreScheduler` in test fixtures mocks Temporal scheduling;
the classes here run **inside** the activity.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from platform_control.temporal.activities import TargetedRescoreRunner


class InMemoryRescoreRunner(TargetedRescoreRunner):
    """No-op runner that returns `("unchanged", None)` deterministically.

    Use only for explicit local/test fallback. The activity still records
    the outcome on the correction payload, so the chain is visible
    end-to-end and the metrics endpoint counts correctly.
    """

    async def run_targeted_rescore(
        self,
        *,
        target_entity_type: str,
        target_entity_id: str,
        correction_id: str,
    ) -> tuple[str, str | None]:
        return ("unchanged", None)


class DocumentIntelligenceRuntimeRescoreRunner(TargetedRescoreRunner):
    """DI-backed runner that calls the document-intelligence runtime in-process."""

    def __init__(self) -> None:
        self._rescore_targeted = _load_di_rescore_targeted()
        self._validate_runtime_config()

    async def run_targeted_rescore(
        self,
        *,
        target_entity_type: str,
        target_entity_id: str,
        correction_id: str,
    ) -> tuple[str, str | None]:
        return await self._rescore_targeted(
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            correction_id=correction_id,
        )

    @staticmethod
    def _validate_runtime_config() -> None:
        try:
            from document_intelligence.config.runtime import RuntimeSettings
        except ModuleNotFoundError as error:  # pragma: no cover
            raise RuntimeError(
                "document-intelligence is not installed in the platform-control worker image."
            ) from error

        settings = RuntimeSettings.from_environment()
        if settings.surface_uris is None:
            raise RuntimeError(
                "DocumentIntelligenceRuntimeRescoreRunner requires DI_SURFACES_ROOT_URI "
                "or explicit DI_PUBLISHED_* surface URIs."
            )


def build_rescore_runner_factory(
    backend: Literal["document_intelligence", "in_memory"],
) -> Callable[[], TargetedRescoreRunner]:
    """Return the configured activity runner factory and validate real DI at startup."""

    if backend == "in_memory":
        return InMemoryRescoreRunner
    if backend != "document_intelligence":
        raise ValueError(f"Unknown rescore runner backend: {backend!r}")

    DocumentIntelligenceRuntimeRescoreRunner._validate_runtime_config()
    return DocumentIntelligenceRuntimeRescoreRunner


def _load_di_rescore_targeted():
    try:
        from document_intelligence.processing_runtime import rescore_targeted
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "document-intelligence is not installed in the platform-control worker image."
        ) from error
    return rescore_targeted
