from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "scraping_baseline"


def _fixture_paths() -> list[Path]:
    return sorted(_fixture_dir().glob("*.json"))


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_scraping_fixture_baseline_contract_and_handoff_integrity(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    registry = _load_schema_registry()
    manifest_schema = json.loads(
        (_repo_root() / "contracts" / "schemas" / "artifact-bundle-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    event_schema = json.loads(
        (_repo_root() / "contracts" / "events" / "artifact-bundle-available.schema.json").read_text(
            encoding="utf-8"
        )
    )

    manifest = build_artifact_bundle_manifest(
        bundle_manifest_id=fixture["bundle_manifest_id"],
        source_snapshot_id=fixture["source_snapshot_id"],
        source_id=fixture["source_id"],
        source_version_id=fixture["source_version_id"],
        run_id=fixture["run_id"],
        jurisdiction_id=fixture["jurisdiction_id"],
        authority_id=fixture.get("authority_id"),
        upstream_locator=fixture["upstream_locator"],
        artifacts=fixture["artifacts"],
        tenant_id=fixture["tenant_id"],
        corpus_id=fixture["corpus_id"],
        scope_type=fixture["scope_type"],
        source_origin_kind=fixture["source_origin_kind"],
        trust_tier=fixture["trust_tier"],
        language_codes=fixture.get("language_codes", []),
        document_type_hint=fixture.get("document_type_hint"),
    )
    Draft202012Validator(manifest_schema, registry=registry).validate(manifest)

    # Baseline quality assertions for every source-family fixture.
    assert any(a["artifact_role"] == "primary_document" for a in fixture["artifacts"])
    for artifact in fixture["artifacts"]:
        storage_ref = artifact["storage_ref"]
        assert storage_ref["content_type"]
        assert len(storage_ref["checksum"]) == 64
        assert storage_ref["checksum_algorithm"] == "sha256"

    required_provenance = [
        "tenant_id",
        "corpus_id",
        "scope_type",
        "source_id",
        "source_version_id",
        "run_id",
        "source_snapshot_id",
        "bundle_manifest_id",
    ]
    for key in required_provenance:
        assert manifest["provenance"].get(key), f"missing provenance field: {key}"

    manifest_ref = {
        "manifest_id": manifest["bundle_manifest_id"],
        "manifest_type": "artifact_bundle_manifest",
        "manifest_version": 1,
        "storage_ref": fixture["manifest_storage_ref"],
    }
    event = build_artifact_bundle_available_event(
        bundle_manifest_id=manifest["bundle_manifest_id"],
        source_snapshot_id=manifest["source_snapshot_id"],
        source_origin_kind=manifest["source_origin_kind"],
        trust_tier=manifest["trust_tier"],
        provenance=manifest["provenance"],
        bundle_manifest_ref=manifest_ref,
        correlation_id=fixture["run_id"],
    )
    Draft202012Validator(event_schema, registry=registry).validate(event)

    payload_ref = event["payload"]["bundle_manifest_ref"]
    assert payload_ref["manifest_id"] == manifest["bundle_manifest_id"]
    assert payload_ref["manifest_version"] == 1
    assert payload_ref["storage_ref"]["checksum_algorithm"] == "sha256"
    assert len(payload_ref["storage_ref"]["checksum"]) == 64
