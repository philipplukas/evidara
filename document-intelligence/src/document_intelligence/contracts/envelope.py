"""Contract models for the bundle-based document-intelligence boundary."""

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional


class EnvelopeError(ValueError):
    """Raised when an inbound event or manifest is unusable."""


@dataclass(frozen=True)
class StorageObjectRef:
    uri: str
    content_type: str
    byte_size: int
    checksum: str
    checksum_algorithm: str
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StorageObjectRef":
        required_fields = [
            "uri",
            "content_type",
            "byte_size",
            "checksum",
            "checksum_algorithm",
        ]
        _raise_for_missing_fields(data, required_fields, "storage object ref")
        return cls(
            uri=str(data["uri"]),
            content_type=str(data["content_type"]),
            byte_size=int(data["byte_size"]),
            checksum=str(data["checksum"]),
            checksum_algorithm=str(data["checksum_algorithm"]),
            created_at=_optional_string(data.get("created_at")),
        )

    def to_dict(self) -> Dict[str, Any]:
        output = {
            "uri": self.uri,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "checksum": self.checksum,
            "checksum_algorithm": self.checksum_algorithm,
        }
        if self.created_at is not None:
            output["created_at"] = self.created_at
        return output


@dataclass(frozen=True)
class ManifestRef:
    manifest_id: str
    manifest_type: str
    manifest_version: int
    storage_ref: Optional[StorageObjectRef] = None
    dataset_ref: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManifestRef":
        required_fields = ["manifest_id", "manifest_type", "manifest_version"]
        _raise_for_missing_fields(data, required_fields, "manifest ref")
        storage_ref = data.get("storage_ref")
        dataset_ref = data.get("dataset_ref")
        if storage_ref is None and dataset_ref is None:
            raise EnvelopeError(
                "manifest ref requires either storage_ref or dataset_ref"
            )
        return cls(
            manifest_id=str(data["manifest_id"]),
            manifest_type=str(data["manifest_type"]),
            manifest_version=int(data["manifest_version"]),
            storage_ref=(
                StorageObjectRef.from_dict(storage_ref)
                if isinstance(storage_ref, Mapping)
                else None
            ),
            dataset_ref=dict(dataset_ref) if isinstance(dataset_ref, Mapping) else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        output = {
            "manifest_id": self.manifest_id,
            "manifest_type": self.manifest_type,
            "manifest_version": self.manifest_version,
        }
        if self.storage_ref is not None:
            output["storage_ref"] = self.storage_ref.to_dict()
        if self.dataset_ref is not None:
            output["dataset_ref"] = dict(self.dataset_ref)
        return output


@dataclass(frozen=True)
class Provenance:
    tenant_id: str
    corpus_id: str
    scope_type: str
    source_id: str
    source_version_id: str
    run_id: str
    source_snapshot_id: Optional[str] = None
    bundle_manifest_id: Optional[str] = None
    artifact_id: Optional[str] = None
    document_id: Optional[str] = None
    document_revision: Optional[int] = None
    processing_manifest_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Provenance":
        required_fields = [
            "tenant_id",
            "corpus_id",
            "scope_type",
            "source_id",
            "source_version_id",
            "run_id",
        ]
        _raise_for_missing_fields(data, required_fields, "provenance")
        return cls(
            tenant_id=str(data["tenant_id"]),
            corpus_id=str(data["corpus_id"]),
            scope_type=str(data["scope_type"]),
            source_id=str(data["source_id"]),
            source_version_id=str(data["source_version_id"]),
            run_id=str(data["run_id"]),
            source_snapshot_id=_optional_string(data.get("source_snapshot_id")),
            bundle_manifest_id=_optional_string(data.get("bundle_manifest_id")),
            artifact_id=_optional_string(data.get("artifact_id")),
            document_id=_optional_string(data.get("document_id")),
            document_revision=_optional_int(data.get("document_revision")),
            processing_manifest_id=_optional_string(data.get("processing_manifest_id")),
        )

    def with_updates(self, **kwargs: Any) -> "Provenance":
        return replace(self, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        output = {
            "tenant_id": self.tenant_id,
            "corpus_id": self.corpus_id,
            "scope_type": self.scope_type,
            "source_id": self.source_id,
            "source_version_id": self.source_version_id,
            "run_id": self.run_id,
        }
        if self.source_snapshot_id is not None:
            output["source_snapshot_id"] = self.source_snapshot_id
        if self.bundle_manifest_id is not None:
            output["bundle_manifest_id"] = self.bundle_manifest_id
        if self.artifact_id is not None:
            output["artifact_id"] = self.artifact_id
        if self.document_id is not None:
            output["document_id"] = self.document_id
        if self.document_revision is not None:
            output["document_revision"] = self.document_revision
        if self.processing_manifest_id is not None:
            output["processing_manifest_id"] = self.processing_manifest_id
        return output


@dataclass(frozen=True)
class ArtifactBundleAvailablePayload:
    bundle_manifest_id: str
    source_snapshot_id: str
    provenance: Provenance
    source_origin_kind: str
    trust_tier: str
    bundle_manifest_ref: ManifestRef
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactBundleAvailablePayload":
        required_fields = [
            "bundle_manifest_id",
            "source_snapshot_id",
            "provenance",
            "source_origin_kind",
            "trust_tier",
            "bundle_manifest_ref",
        ]
        _raise_for_missing_fields(data, required_fields, "artifact bundle payload")

        provenance = data.get("provenance")
        manifest_ref = data.get("bundle_manifest_ref")
        if not isinstance(provenance, Mapping):
            raise EnvelopeError("artifact bundle payload provenance must be an object")
        if not isinstance(manifest_ref, Mapping):
            raise EnvelopeError(
                "artifact bundle payload bundle_manifest_ref must be an object"
            )

        known_fields = {
            "bundle_manifest_id",
            "source_snapshot_id",
            "provenance",
            "source_origin_kind",
            "trust_tier",
            "bundle_manifest_ref",
        }
        return cls(
            bundle_manifest_id=str(data["bundle_manifest_id"]),
            source_snapshot_id=str(data["source_snapshot_id"]),
            provenance=Provenance.from_dict(provenance),
            source_origin_kind=str(data["source_origin_kind"]),
            trust_tier=str(data["trust_tier"]),
            bundle_manifest_ref=ManifestRef.from_dict(manifest_ref),
            extra_fields={
                key: value for key, value in data.items() if key not in known_fields
            },
        )


@dataclass(frozen=True)
class ArtifactBundleAvailableEvent:
    payload: ArtifactBundleAvailablePayload
    event_type: str
    event_version: int
    event_id: str
    occurred_at: str
    producer: str
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactBundleAvailableEvent":
        required_fields = [
            "event_type",
            "event_version",
            "event_id",
            "occurred_at",
            "producer",
            "payload",
        ]
        _raise_for_missing_fields(data, required_fields, "artifact bundle event")

        payload = data.get("payload")
        if not isinstance(payload, Mapping):
            raise EnvelopeError("artifact_bundle.available payload must be an object")

        event_type = str(data["event_type"])
        if event_type != "artifact_bundle.available":
            raise EnvelopeError(
                "unexpected event type: {event_type}".format(event_type=event_type)
            )

        producer = str(data["producer"])
        if producer != "platform-control":
            raise EnvelopeError(
                "unexpected producer for artifact_bundle.available: {producer}".format(
                    producer=producer
                )
            )

        known_fields = {
            "event_type",
            "event_version",
            "event_id",
            "occurred_at",
            "producer",
            "correlation_id",
            "causation_id",
            "payload",
        }
        return cls(
            payload=ArtifactBundleAvailablePayload.from_dict(payload),
            event_type=event_type,
            event_version=int(data["event_version"]),
            event_id=str(data["event_id"]),
            occurred_at=str(data["occurred_at"]),
            producer=producer,
            correlation_id=_optional_string(data.get("correlation_id")),
            causation_id=_optional_string(data.get("causation_id")),
            extra_fields={
                key: value for key, value in data.items() if key not in known_fields
            },
        )


@dataclass(frozen=True)
class ArtifactBundleManifestArtifact:
    artifact_id: str
    artifact_role: str
    storage_ref: StorageObjectRef
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactBundleManifestArtifact":
        required_fields = ["artifact_id", "artifact_role", "storage_ref"]
        _raise_for_missing_fields(
            data, required_fields, "artifact bundle manifest artifact"
        )

        storage_ref = data.get("storage_ref")
        if not isinstance(storage_ref, Mapping):
            raise EnvelopeError("artifact storage_ref must be an object")

        known_fields = {"artifact_id", "artifact_role", "storage_ref"}
        return cls(
            artifact_id=str(data["artifact_id"]),
            artifact_role=str(data["artifact_role"]),
            storage_ref=StorageObjectRef.from_dict(storage_ref),
            extra_fields={
                key: value for key, value in data.items() if key not in known_fields
            },
        )


@dataclass(frozen=True)
class ArtifactBundleManifest:
    bundle_manifest_id: str
    manifest_version: int
    provenance: Provenance
    source_snapshot_id: str
    source_origin_kind: str
    trust_tier: str
    snapshot_captured_at: str
    source_defaults: Dict[str, Any]
    parser_hints: Dict[str, Any]
    reference_context: Dict[str, Any]
    artifacts: List[ArtifactBundleManifestArtifact]
    snapshot_external_id: Optional[str] = None
    upstream_locator: Optional[str] = None
    di_overrides: Dict[str, Any] = field(default_factory=dict)
    bundle_metadata: Dict[str, Any] = field(default_factory=dict)
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactBundleManifest":
        required_fields = [
            "bundle_manifest_id",
            "manifest_version",
            "provenance",
            "source_snapshot_id",
            "source_origin_kind",
            "trust_tier",
            "snapshot_captured_at",
            "source_defaults",
            "parser_hints",
            "reference_context",
            "artifacts",
        ]
        _raise_for_missing_fields(data, required_fields, "artifact bundle manifest")

        provenance = data.get("provenance")
        artifacts = data.get("artifacts")
        if not isinstance(provenance, Mapping):
            raise EnvelopeError("artifact bundle manifest provenance must be an object")
        if not isinstance(artifacts, list) or not artifacts:
            raise EnvelopeError(
                "artifact bundle manifest artifacts must be a non-empty array"
            )

        known_fields = {
            "bundle_manifest_id",
            "manifest_version",
            "provenance",
            "source_snapshot_id",
            "snapshot_external_id",
            "upstream_locator",
            "source_origin_kind",
            "trust_tier",
            "snapshot_captured_at",
            "source_defaults",
            "parser_hints",
            "di_overrides",
            "reference_context",
            "artifacts",
            "bundle_metadata",
        }
        return cls(
            bundle_manifest_id=str(data["bundle_manifest_id"]),
            manifest_version=int(data["manifest_version"]),
            provenance=Provenance.from_dict(provenance),
            source_snapshot_id=str(data["source_snapshot_id"]),
            snapshot_external_id=_optional_string(data.get("snapshot_external_id")),
            upstream_locator=_optional_string(data.get("upstream_locator")),
            source_origin_kind=str(data["source_origin_kind"]),
            trust_tier=str(data["trust_tier"]),
            snapshot_captured_at=str(data["snapshot_captured_at"]),
            source_defaults=_copy_dict(data.get("source_defaults"), "source_defaults"),
            parser_hints=_copy_dict(data.get("parser_hints"), "parser_hints"),
            di_overrides=_copy_dict(data.get("di_overrides") or {}, "di_overrides"),
            reference_context=_copy_dict(
                data.get("reference_context"), "reference_context"
            ),
            artifacts=[
                ArtifactBundleManifestArtifact.from_dict(artifact)
                for artifact in artifacts
                if isinstance(artifact, Mapping)
            ],
            bundle_metadata=_copy_dict(
                data.get("bundle_metadata") or {}, "bundle_metadata"
            ),
            extra_fields={
                key: value for key, value in data.items() if key not in known_fields
            },
        )


def _copy_dict(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EnvelopeError(
            "{field_name} must be an object".format(field_name=field_name)
        )
    return dict(value)


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _raise_for_missing_fields(
    data: Mapping[str, Any], required_fields: List[str], entity_name: str
) -> None:
    missing_fields = [name for name in required_fields if data.get(name) is None]
    if missing_fields:
        raise EnvelopeError(
            "{entity_name} missing required fields: {fields}".format(
                entity_name=entity_name, fields=", ".join(sorted(missing_fields))
            )
        )
