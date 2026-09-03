"""Runtime-local targeted rescore support.

This module is the document-intelligence side of the platform-control
``RescoreFromCorrectionActivities`` protocol. It resolves the current
published target, replays the original artifact bundle through the existing
pipeline, compares semantic output, and persists only changed results.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.canonical.models import CommentaryInsight, ProcessingResult, Section
from document_intelligence.config.runtime import RuntimeSettings, SurfaceUris
from document_intelligence.errors import ProcessingError
from document_intelligence.ingest.loaders import BundleLoader
from document_intelligence.persist.sinks import delta_dataset_filesystem, delta_storage_options
from document_intelligence.processing_runtime import build_processing_pipeline

logger = logging.getLogger(__name__)

_SUPPORTED_TARGET_TYPES = frozenset({"document", "commentary_insight"})


class RescoreSurfaceStore(Protocol):
    """Read current published surfaces needed for targeted rescore."""

    def get_document(
        self,
        document_id: str,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None: ...

    def get_processing_manifest(self, processing_manifest_id: str) -> dict[str, Any] | None: ...

    def get_commentary_insight(self, insight_id: str) -> dict[str, Any] | None: ...


class DeltaRescoreSurfaceStore:
    """Read current target state from Delta-backed published surfaces.

    ``storage_options`` is what maps ``DI_S3_ENDPOINT_URL`` / ``DI_S3_ACCESS_KEY_ID`` /
    ``DI_S3_SECRET_ACCESS_KEY`` onto the ``AWS_*`` keys ``object_store`` reads
    (:func:`delta_storage_options`). Without it ``object_store`` falls back to its own
    credential chain, which the self-hosted deployment does not populate — so every
    read against ``s3://evidara-lakehouse/canonical/...`` failed with *"the credential
    provider was not enabled: no providers in chain provided credentials"* (#847).
    Resolved from the environment by default, exactly as ``DeltaPublishedDocumentStore``
    and ``DeltaCanonicalSink`` do; pass an explicit mapping to override.
    """

    def __init__(
        self,
        surface_uris: SurfaceUris,
        storage_options: Mapping[str, str] | None = None,
    ) -> None:
        self._surface_uris = surface_uris
        self._storage_options = delta_storage_options() if storage_options is None else storage_options

    def get_document(
        self,
        document_id: str,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None:
        dataset_mod = importlib.import_module("pyarrow.dataset")
        filters = [dataset_mod.field("document_id") == document_id]
        if processing_manifest_id is not None:
            filters.append(dataset_mod.field("processing_manifest_id") == processing_manifest_id)
        rows = _read_delta_rows(
            self._surface_uris.published_documents_uri,
            filters,
            storage_options=self._storage_options,
        )
        if not rows:
            return None
        rows.sort(
            key=lambda row: (
                int(row.get("document_revision") or 0),
                str(row.get("processed_at") or ""),
            ),
            reverse=True,
        )
        document = dict(rows[0])
        sections = self._get_sections(
            str(document["document_id"]),
            str(document.get("processing_manifest_id") or ""),
        )
        if sections:
            document["sections"] = sections
        return document

    def get_processing_manifest(self, processing_manifest_id: str) -> dict[str, Any] | None:
        dataset_mod = importlib.import_module("pyarrow.dataset")
        rows = _read_delta_rows(
            self._surface_uris.processing_manifests_uri,
            [dataset_mod.field("processing_manifest_id") == processing_manifest_id],
            storage_options=self._storage_options,
        )
        if not rows:
            return None
        return dict(rows[0])

    def get_commentary_insight(self, insight_id: str) -> dict[str, Any] | None:
        if not self._surface_uris.published_commentary_insights_uri:
            return None
        dataset_mod = importlib.import_module("pyarrow.dataset")
        rows = _read_delta_rows(
            self._surface_uris.published_commentary_insights_uri,
            [dataset_mod.field("insight_id") == insight_id],
            storage_options=self._storage_options,
        )
        if not rows:
            return None
        return dict(rows[0])

    def _get_sections(self, document_id: str, processing_manifest_id: str) -> list[dict[str, Any]]:
        dataset_mod = importlib.import_module("pyarrow.dataset")
        rows = _read_delta_rows(
            self._surface_uris.published_sections_uri,
            [
                dataset_mod.field("document_id") == document_id,
                dataset_mod.field("processing_manifest_id") == processing_manifest_id,
            ],
            storage_options=self._storage_options,
        )
        rows.sort(key=lambda row: (int(row.get("ordinal") or 0), str(row.get("section_id") or "")))
        return [dict(row) for row in rows]


async def rescore_targeted(
    *,
    target_entity_type: str,
    target_entity_id: str,
    correction_id: str,
    runtime_settings: RuntimeSettings | None = None,
    surface_store: RescoreSurfaceStore | None = None,
    bundle_loader: BundleLoader | None = None,
    persist_changes: bool = True,
) -> tuple[str, str | None]:
    """Re-extract a published target and return ``(outcome, run_id)``.

    Expected operational failures are converted to ``("failed", None)`` so
    callers can record a stable outcome. Unexpected process-level failures can
    still be caught by platform-control's Temporal activity wrapper.
    """

    try:
        settings = runtime_settings or RuntimeSettings.from_environment()
        store = surface_store or _store_from_settings(settings)
        target = _resolve_target(store, target_entity_type, target_entity_id)
        event_payload = _build_rescore_event(
            current_document=target.current_document,
            processing_manifest=target.processing_manifest,
            correction_id=correction_id,
        )
        dry_run_settings = replace(settings, surface_uris=None, use_spark_delta=False)
        candidate = build_processing_pipeline(
            runtime_settings=dry_run_settings,
            bundle_loader=bundle_loader,
        ).process_event(event_payload)

        if candidate.is_quarantined:
            # The re-extraction produced no document: this target's manifestation no longer
            # clears ADR-0047's text-level floors. Return before `_target_changed`, which
            # dereferences `candidate.document` and would otherwise raise `AttributeError`
            # into the blanket handler below — a crash reported as a rescore failure, with
            # the actual reason nowhere.
            #
            # Deliberately NOT persisting: a persisting pass would write a `quarantined`
            # manifest while the previously published document row stays newest on the
            # append-only surface, leaving the corpus serving text the manifest says we do
            # not trust.
            #
            # The honest outcome here is `quarantined`, and this returns `failed` instead.
            # That is a constraint, not a judgement: `CorrectionService.record_rescore_outcome`
            # validates the outcome against {changed, unchanged, failed} and
            # `temporal/activities.py:523-529` calls it *outside* its own try/except, so an
            # unrecognised value raises `ValueError` out of the activity and fails the
            # correction workflow — strictly worse than the recorded failure it replaces.
            # Widening that enum is the same platform-control change the `quarantined`
            # processing-status value needs; until then the reason lives in this log line.
            logger.warning(
                "targeted_rescore_quarantined",
                extra={
                    "target_entity_type": target_entity_type,
                    "target_entity_id": target_entity_id,
                    "correction_id": correction_id,
                    "quarantine_reason": (candidate.quarantine or {}).get("reason"),
                    "quarantine_detail": (candidate.quarantine or {}).get("detail"),
                    "processing_manifest_id": candidate.manifest.processing_manifest_id,
                },
            )
            return ("failed", None)

        if not _target_changed(target, candidate):
            return ("unchanged", None)

        if persist_changes:
            build_processing_pipeline(
                runtime_settings=settings,
                bundle_loader=bundle_loader,
            ).process_event(event_payload)
        run_id = str(event_payload["payload"]["provenance"]["run_id"])
        return ("changed", run_id)
    except Exception as exc:
        logger.exception(
            "targeted_rescore_failed",
            extra={
                "target_entity_type": target_entity_type,
                "target_entity_id": target_entity_id,
                "correction_id": correction_id,
            },
        )
        _ = exc
        return ("failed", None)


class _ResolvedTarget:
    def __init__(
        self,
        *,
        target_entity_type: str,
        current_document: dict[str, Any],
        processing_manifest: dict[str, Any],
        current_insight: dict[str, Any] | None = None,
    ) -> None:
        self.target_entity_type = target_entity_type
        self.current_document = current_document
        self.processing_manifest = processing_manifest
        self.current_insight = current_insight


def _store_from_settings(settings: RuntimeSettings) -> RescoreSurfaceStore:
    if settings.surface_uris is None:
        raise ProcessingError(
            "missing_rescore_surface_config",
            "targeted rescore requires DI_SURFACES_ROOT_URI or explicit published surface URIs",
        )
    return DeltaRescoreSurfaceStore(settings.surface_uris)


def _resolve_target(
    store: RescoreSurfaceStore,
    target_entity_type: str,
    target_entity_id: str,
) -> _ResolvedTarget:
    if target_entity_type not in _SUPPORTED_TARGET_TYPES:
        raise ProcessingError(
            "unsupported_rescore_target",
            f"targeted rescore only supports {sorted(_SUPPORTED_TARGET_TYPES)}, got {target_entity_type!r}",
        )

    current_insight = None
    document_id = target_entity_id
    processing_manifest_id = None
    if target_entity_type == "commentary_insight":
        current_insight = store.get_commentary_insight(target_entity_id)
        if current_insight is None:
            raise ProcessingError("rescore_target_missing", f"commentary insight {target_entity_id} not found")
        document_id = _required_str(current_insight, "document_id")
        processing_manifest_id = _optional_str(current_insight.get("processing_manifest_id"))

    current_document = store.get_document(document_id, processing_manifest_id)
    if current_document is None:
        raise ProcessingError("rescore_target_missing", f"document {document_id} not found")
    processing_manifest_id = _required_str(current_document, "processing_manifest_id")
    processing_manifest = store.get_processing_manifest(processing_manifest_id)
    if processing_manifest is None:
        raise ProcessingError(
            "rescore_manifest_missing",
            f"processing manifest {processing_manifest_id} not found",
        )
    return _ResolvedTarget(
        target_entity_type=target_entity_type,
        current_document=current_document,
        processing_manifest=processing_manifest,
        current_insight=current_insight,
    )


def _build_rescore_event(
    *,
    current_document: Mapping[str, Any],
    processing_manifest: Mapping[str, Any],
    correction_id: str,
) -> dict[str, Any]:
    input_ref = processing_manifest.get("input_bundle_manifest_ref")
    if not isinstance(input_ref, Mapping):
        raise ProcessingError("rescore_manifest_invalid", "processing manifest is missing input_bundle_manifest_ref")

    provenance = _mapping_from_first(
        processing_manifest.get("provenance"),
        current_document.get("provenance"),
        field_name="provenance",
    )
    source_snapshot_id = _optional_str(provenance.get("source_snapshot_id"))
    if source_snapshot_id is None:
        raise ProcessingError("rescore_manifest_invalid", "target provenance is missing source_snapshot_id")

    run_id = random_prefixed_id("run")
    event_provenance = dict(provenance)
    event_provenance["run_id"] = run_id
    event_provenance["source_snapshot_id"] = source_snapshot_id
    event_provenance["bundle_manifest_id"] = str(input_ref.get("manifest_id") or provenance.get("bundle_manifest_id"))
    event_provenance.pop("document_id", None)
    event_provenance.pop("document_revision", None)
    event_provenance.pop("processing_manifest_id", None)

    metadata = current_document.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return {
        "event_type": "artifact_bundle.available",
        "event_version": 1,
        "event_id": random_prefixed_id("evt"),
        "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "producer": "platform-control",
        "correlation_id": correction_id,
        "causation_id": correction_id,
        "payload": {
            "bundle_manifest_id": event_provenance["bundle_manifest_id"],
            "source_snapshot_id": source_snapshot_id,
            "provenance": event_provenance,
            "source_origin_kind": str(metadata.get("source_origin_kind") or "unknown"),
            "trust_tier": str(metadata.get("trust_tier") or "unknown"),
            "bundle_manifest_ref": dict(input_ref),
        },
    }


def _target_changed(target: _ResolvedTarget, candidate: ProcessingResult) -> bool:
    if target.target_entity_type == "commentary_insight":
        if target.current_insight is None:
            return True
        current = _insight_semantic(target.current_insight)
        candidates = {_insight_semantic(insight.to_dict()) for insight in candidate.commentary_insights}
        return current not in candidates

    current_document = _document_semantic(target.current_document)
    candidate_document = _candidate_document_semantic(candidate)
    return current_document != candidate_document


def _document_semantic(document: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _optional_str(document.get("title")),
        _optional_str(document.get("document_type")),
        _optional_str(document.get("jurisdiction_id")),
        _optional_str(document.get("authority_id")),
        _optional_str(document.get("full_text")),
        _optional_str(document.get("body_text")),
        tuple(_section_semantic(section) for section in document.get("sections") or []),
    )


def _candidate_document_semantic(candidate: ProcessingResult) -> tuple[Any, ...]:
    document = candidate.document
    if document is None:
        # Unreachable via `rescore_targeted`, which returns on `is_quarantined` first. Kept
        # as an explicit contract rather than an implicit one: `ProcessingResult.document` is
        # `None` exactly when quarantined (ADR-0047), and this module runs behind a blanket
        # `except Exception`, so an AttributeError here would surface as an unexplained
        # "failed" rescore instead of a diagnosable error.
        raise ValueError("cannot compare a quarantined candidate: no document was produced")
    return (
        document.title,
        document.document_type,
        document.jurisdiction_id,
        document.authority_id,
        document.full_text,
        document.body_text,
        tuple(_section_semantic(section) for section in candidate.sections),
    )


def _section_semantic(section: Mapping[str, Any] | Section) -> tuple[Any, ...]:
    if isinstance(section, Section):
        return (section.ordinal, section.depth, section.title, section.content, section.section_type)
    return (
        int(section.get("ordinal") or 0),
        int(section.get("depth") or 0),
        _optional_str(section.get("title")),
        _optional_str(section.get("content")),
        _optional_str(section.get("section_type")),
    )


def _insight_semantic(insight: Mapping[str, Any] | CommentaryInsight) -> tuple[Any, ...]:
    if isinstance(insight, CommentaryInsight):
        insight = insight.to_dict()
    return (
        _optional_str(insight.get("insight_type")),
        _optional_str(insight.get("claim")),
        _optional_str(insight.get("display_text")),
        _optional_str(insight.get("language")),
        _optional_str(insight.get("jurisdiction_id")),
        round(float(insight.get("confidence") or 0.0), 6),
        _json_stable(insight.get("referenced_authorities")),
        _json_stable(insight.get("support")),
    )


def _read_delta_rows(
    uri: str,
    filters: list[Any],
    *,
    storage_options: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Read the rows of one published Delta surface that match ``filters``.

    Two arguments carry the whole weight of this function and neither used to be passed:

    - ``storage_options`` are the credentials. Every other Delta reader in
      document-intelligence threads them (``DeltaPublishedDocumentStore``,
      ``DeltaCanonicalSink``); this one did not, so on the self-hosted deployment —
      MinIO reached through ``DI_S3_*`` and nothing else — every rescore read failed
      outright (#847). Not latent: that is the production configuration.
    - ``filesystem`` is the native Arrow filesystem. Without it ``to_pyarrow_dataset()``
      builds ``PyFileSystem(DeltaStorageHandler(...))`` and Arrow's C++ IO pool calls
      back into Python during the scan; losing that race at interpreter shutdown aborts
      the process with ``terminate called without an active exception`` *after* the work
      succeeded (#825). :func:`delta_dataset_filesystem` returns ``None`` for any URI
      shape it does not claim, and ``deltalake``'s own handler stays in charge.
    """
    deltalake = importlib.import_module("deltalake")
    expr = filters[0]
    for item in filters[1:]:
        expr = expr & item
    table_kwargs = {"storage_options": storage_options} if storage_options else {}
    table = deltalake.DeltaTable(uri, **table_kwargs).to_pyarrow_dataset(
        filesystem=delta_dataset_filesystem(uri, storage_options)
    )
    return table.to_table(filter=expr).to_pylist()


def _mapping_from_first(*values: Any, field_name: str) -> Mapping[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return value
    raise ProcessingError("rescore_manifest_invalid", f"target is missing {field_name}")


def _required_str(mapping: Mapping[str, Any], field_name: str) -> str:
    value = mapping.get(field_name)
    if not isinstance(value, str) or not value:
        raise ProcessingError("rescore_manifest_invalid", f"target is missing {field_name}")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _json_stable(value: Any) -> str:
    import json

    def scrub(inner: Any) -> Any:
        if isinstance(inner, Mapping):
            return {
                str(key): scrub(val)
                for key, val in sorted(inner.items())
                if key not in {"document_id", "section_id", "citation_id", "processing_manifest_id"}
            }
        if isinstance(inner, list):
            return [scrub(item) for item in inner]
        return inner

    return json.dumps(scrub(value), sort_keys=True, separators=(",", ":"), default=str)
