"""Shared runtime helpers for DI entrypoints and consumer services."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.contracts.envelope import ArtifactBundleAvailableEvent
from document_intelligence.errors import ProcessingError
from document_intelligence.ingest import resolve_artifact_bundle_event
from document_intelligence.ingest.loaders import BundleLoader
from document_intelligence.persist.sinks import (
    DeltaCanonicalSink,
    InMemoryCanonicalSink,
)
from document_intelligence.pipeline import ProcessingPipeline


def build_processing_pipeline(
    *,
    runtime_settings: RuntimeSettings,
    bundle_loader: BundleLoader | None = None,
) -> ProcessingPipeline:
    if runtime_settings.surface_uris is None:
        sink = InMemoryCanonicalSink()
    else:
        sink = DeltaCanonicalSink(runtime_settings.surface_uris.to_delta_sink_config())
    return ProcessingPipeline(
        bundle_loader=bundle_loader,
        sink=sink,
        processing_version=runtime_settings.processing_version,
    )


def process_artifact_bundle_event(
    event_payload: Mapping[str, Any],
    *,
    runtime_settings: RuntimeSettings | None = None,
    bundle_loader: BundleLoader | None = None,
    require_surface_uris: bool = False,
) -> dict[str, Any]:
    resolved_event_payload = resolve_artifact_bundle_event(event_payload)
    event = ArtifactBundleAvailableEvent.from_dict(resolved_event_payload)
    effective_settings = runtime_settings or RuntimeSettings.from_environment()
    if require_surface_uris and effective_settings.surface_uris is None:
        raise ProcessingError(
            "missing_runtime_surface_config",
            "runtime ingestion requires DI_SURFACES_ROOT_URI or all three explicit published surface URIs",
        )
    result = build_processing_pipeline(
        runtime_settings=effective_settings,
        bundle_loader=bundle_loader,
    ).process_event(dict(resolved_event_payload))
    return {
        "status": "processed",
        "event_id": event.event_id,
        "bundle_manifest_id": event.payload.bundle_manifest_id,
        "document_id": result.document.document_id,
        "document_revision": result.document.document_revision,
        "processing_manifest_id": result.manifest.processing_manifest_id,
        "sections": len(result.sections),
    }
