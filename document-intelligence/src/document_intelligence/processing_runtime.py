"""Shared runtime helpers for DI entrypoints and consumer services."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from document_intelligence.canonical.models import ProcessingResult
from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.contracts.envelope import ArtifactBundleAvailableEvent
from document_intelligence.errors import ProcessingError
from document_intelligence.events.publisher import EventPublisherConfig, PubSubEventPublisher
from document_intelligence.ingest import resolve_artifact_bundle_event
from document_intelligence.ingest.loaders import BundleLoader
from document_intelligence.persist.sinks import (
    DeltaCanonicalSink,
    InMemoryCanonicalSink,
    SparkDeltaCanonicalSink,
)
from document_intelligence.pipeline import ProcessingPipeline


def _build_llm_metadata_extractor():
    """Construct Instructor- or DSPy-backed metadata extractor, or None if neither stack is installed."""
    from document_intelligence.extractors.profile_config import ExtractionProfileConfig

    profile = ExtractionProfileConfig.from_environment()
    try:
        from document_intelligence.extractors.instructor_metadata_extractor import InstructorMetadataExtractor

        return InstructorMetadataExtractor(profile=profile)
    except ImportError:
        pass

    try:
        from document_intelligence.extractors.dspy_metadata_extractor import DspyMetadataExtractor

        return DspyMetadataExtractor(profile=profile)
    except ImportError:
        return None


def build_processing_pipeline(
    *,
    runtime_settings: RuntimeSettings,
    bundle_loader: BundleLoader | None = None,
) -> ProcessingPipeline:
    if runtime_settings.surface_uris is None:
        sink = InMemoryCanonicalSink()
    elif runtime_settings.use_spark_delta:
        sink = SparkDeltaCanonicalSink(runtime_settings.surface_uris.to_delta_sink_config())
    else:
        sink = DeltaCanonicalSink(runtime_settings.surface_uris.to_delta_sink_config())
    llm_metadata_extractor = None
    if runtime_settings.enable_llm_extractor:
        llm_metadata_extractor = _build_llm_metadata_extractor()

    return ProcessingPipeline(
        bundle_loader=bundle_loader,
        sink=sink,
        processing_version=runtime_settings.processing_version,
        parser_backend=runtime_settings.parser_backend,
        enable_spacy=runtime_settings.enable_spacy,
        spacy_model_name=runtime_settings.spacy_model_name,
        spacy_max_chars_per_section=runtime_settings.spacy_max_chars_per_section,
        spacy_batch_size=runtime_settings.spacy_batch_size,
        enable_llm_extractor=runtime_settings.enable_llm_extractor,
        llm_confidence_threshold=runtime_settings.llm_confidence_threshold,
        llm_metadata_extractor=llm_metadata_extractor,
        enable_commentary_insights=runtime_settings.enable_commentary_insights,
        commentary_insight_min_confidence=runtime_settings.commentary_insight_min_confidence,
    )


def _outbound_pubsub_topic_names() -> tuple[str, str] | None:
    """Return (status_topic, processed_topic) when outbound Pub/Sub publish is enabled."""
    backend = (os.environ.get("DI_EVENT_PUBLISHER_BACKEND") or "").strip().lower()
    if backend in {"none", "off", "noop"}:
        return None
    project_id = (os.environ.get("DI_GCP_PROJECT_ID") or "").strip()
    if not project_id:
        return None
    status_topic = (os.environ.get("DI_STATUS_TOPIC_NAME") or "document-processing-status-updated").strip()
    processed_topic = (
        os.environ.get("DI_PROCESSED_TOPIC_NAME") or os.environ.get("DI_DOCUMENT_PROCESSED_PUBSUB_TOPIC") or ""
    ).strip() or "document-processed"
    return status_topic, processed_topic


def publish_processing_result_to_pubsub(
    result: ProcessingResult,
    *,
    publisher: PubSubEventPublisher | None = None,
) -> None:
    """Publish status and document.processed events (same contract as runtime_consumer)."""
    topic_names = _outbound_pubsub_topic_names()
    if topic_names is None:
        return
    status_topic, processed_topic = topic_names
    project_id = (os.environ.get("DI_GCP_PROJECT_ID") or "").strip()
    assert project_id
    pub = publisher or PubSubEventPublisher(
        EventPublisherConfig(
            project_id=project_id,
            status_topic_name=status_topic,
            processed_topic_name=processed_topic,
        )
    )
    for status_event in result.status_events:
        pub.publish_status_event(status_event)
    pub.publish_document_processed_event(result.document_processed_event)


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
    publish_processing_result_to_pubsub(result)
    return {
        "status": "processed",
        "event_id": event.event_id,
        "bundle_manifest_id": event.payload.bundle_manifest_id,
        "document_id": result.document.document_id,
        "document_revision": result.document.document_revision,
        "processing_manifest_id": result.manifest.processing_manifest_id,
        "sections": len(result.sections),
    }


def targeted_re_extract(
    *,
    target_entity_type: str,
    target_entity_id: str,
    baseline: Mapping[str, Any] | None = None,
    correction_payload: Mapping[str, Any] | None = None,
    runtime_settings: RuntimeSettings | None = None,
    extractor: Any | None = None,
) -> dict[str, Any]:
    """Run a targeted re-extraction for a single corrected entity.

    This is the document-intelligence-side entry point invoked by
    ``RescoreCorrectionWorkflow`` (platform-control, issue #427). It is
    deliberately small and side-effect-free at this stage: the production
    pipeline-replay path will be wired through here once issue #425 lands the
    projection re-emission contract. Until then this entry point exists so:

    1. Platform-control's rescore workflow has a stable callable to invoke,
       and contract changes here are detected by tests rather than at deploy
       time.
    2. Operators can run the full loop end-to-end against a fake / dry
       extractor and still observe the ``triggered`` / ``changed`` /
       ``unchanged`` / ``failed`` outcomes.

    Parameters
    ----------
    target_entity_type, target_entity_id:
        Identify the entity to re-score. The workflow loads the baseline
        snapshot upstream and passes it here; this function only diffs.
    baseline:
        Last-known canonical extraction values. Compared field-by-field
        against the new extraction to decide ``changed`` vs ``unchanged``.
    correction_payload:
        The operator-supplied payload from the *source* correction. Forwarded
        to the extractor so prompt scaffolding can incorporate the hint
        (e.g. "operator says jurisdiction should be CH").
    runtime_settings:
        Honoured for parity with the bundle entrypoint; unused for now.
    extractor:
        Test seam: any callable accepting
        ``(target_entity_type, target_entity_id, correction_payload)`` and
        returning a mapping of new field values.

    Returns
    -------
    dict
        ``{"target_entity_type", "target_entity_id", "extraction_id",
        "fields", "diff", "outcome"}``. ``outcome`` is one of
        ``"changed"``, ``"unchanged"``, ``"failed"``.
    """

    del runtime_settings  # Reserved for the full pipeline-replay path.

    extractor_callable = extractor or _default_targeted_extractor
    try:
        new_fields = extractor_callable(
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            correction_payload=dict(correction_payload or {}),
        )
    except Exception as exc:  # noqa: BLE001 — surface to workflow as failed
        return {
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "extraction_id": None,
            "fields": {},
            "diff": {},
            "outcome": "failed",
            "error": str(exc),
        }

    baseline_dict = dict(baseline or {})
    diff = {
        key: {"before": baseline_dict.get(key), "after": value}
        for key, value in new_fields.items()
        if baseline_dict.get(key) != value
    }
    extraction_id = f"ext_{target_entity_type}_{target_entity_id}_rescore" if new_fields else None
    return {
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "extraction_id": extraction_id,
        "fields": dict(new_fields),
        "diff": diff,
        "outcome": "changed" if diff else "unchanged",
    }


def _default_targeted_extractor(
    *,
    target_entity_type: str,
    target_entity_id: str,
    correction_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Conservative default extractor that echoes the correction payload.

    The production extractor will replace this with a profile-driven LLM /
    deterministic re-extraction once #425 lands the projection plumbing. The
    echo behaviour ensures the rescore workflow always observes a sensible
    diff in tests and demos.
    """

    del target_entity_type, target_entity_id
    after = correction_payload.get("after")
    if isinstance(after, Mapping):
        return dict(after)
    if isinstance(after, dict):
        return after
    return {}
