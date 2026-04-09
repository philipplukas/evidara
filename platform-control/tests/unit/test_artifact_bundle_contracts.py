from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from platform_control.events.artifact_bundle import (
    build_artifact_bundle_available_event,
    build_artifact_bundle_manifest,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_schema_registry() -> Registry:
    contracts_dir = _repo_root() / "contracts"
    resources: dict[str, Resource] = {}
    for path in contracts_dir.rglob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema_id = schema.get("$id")
        if schema_id:
            resources[schema_id] = Resource(contents=schema, specification=DRAFT202012)
    return Registry().with_resources(resources.items())


def test_artifact_bundle_manifest_matches_contract_schema() -> None:
    registry = _load_schema_registry()
    schema = json.loads(
        (_repo_root() / "contracts" / "schemas" / "artifact-bundle-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = build_artifact_bundle_manifest(
        bundle_manifest_id="abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
        source_snapshot_id="snap_01jq7a7n3nbzj6sk7v95p9frz1",
        source_id="src_01jq79xv3wdd6yr8q5bn0m3zfk",
        source_version_id="sv_01jq79zcskf4m3m4gm3t5s59xq",
        run_id="run_01jq7a3s9b7j4dndd9sgv6pb9d",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
        authority_name="Zurich Administrative Court",
        upstream_locator="https://example.com/decisions/1",
        artifacts=[
            {
                "artifact_id": "art_01jq7ab8x4nm7m3qz3b8e9q2fk",
                "artifact_role": "primary_document",
                "storage_ref": {
                    "uri": "gs://bucket/runs/run_01jq7a3s9b7j4dndd9sgv6pb9d/art_01jq7ab8x4nm7m3qz3b8e9q2fk.html",
                    "content_type": "text/html",
                    "byte_size": 10,
                    "checksum": "a" * 64,
                    "checksum_algorithm": "sha256",
                },
            }
        ],
    )

    Draft202012Validator(schema, registry=registry).validate(manifest)


def test_artifact_bundle_available_event_matches_contract_schema() -> None:
    registry = _load_schema_registry()
    schema = json.loads(
        (_repo_root() / "contracts" / "events" / "artifact-bundle-available.schema.json").read_text(
            encoding="utf-8"
        )
    )
    event = build_artifact_bundle_available_event(
        bundle_manifest_id="abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
        source_snapshot_id="snap_01jq7a7n3nbzj6sk7v95p9frz1",
        source_origin_kind="official_primary",
        trust_tier="authoritative",
        correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d",
        provenance={
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_public_ch",
            "scope_type": "global_public",
            "source_id": "src_01jq79xv3wdd6yr8q5bn0m3zfk",
            "source_version_id": "sv_01jq79zcskf4m3m4gm3t5s59xq",
            "run_id": "run_01jq7a3s9b7j4dndd9sgv6pb9d",
            "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
            "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
        },
        bundle_manifest_ref={
            "manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            "manifest_type": "artifact_bundle_manifest",
            "manifest_version": 1,
            "storage_ref": {
                "uri": "gs://bucket/runs/run_01jq7a3s9b7j4dndd9sgv6pb9d/abm_01jq7ab8x4nm7m3qz3b8e9q2fk.json",
                "content_type": "application/json",
                "byte_size": 10,
                "checksum": "b" * 64,
                "checksum_algorithm": "sha256",
            },
        },
    )

    Draft202012Validator(schema, registry=registry).validate(event)
