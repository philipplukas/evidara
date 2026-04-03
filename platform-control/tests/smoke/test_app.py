from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.routers.runs import get_firecrawl_provider
from platform_control.services.firecrawl_provider import ProviderStartResult


@dataclass
class StubProvider:
    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id="crawl_smoke_123",
            request_payload={"url": "https://example.com"},
            response_payload={"id": "crawl_smoke_123", "success": True},
        )


@pytest.mark.asyncio
async def test_create_source_approve_and_trigger_run(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
        seed_session.add(
            Authority(
                authority_id="auth_zh_admin",
                jurisdiction_id="jur_ch",
                name="Zurich Administrative Court",
                slug="zh-admin-court",
            )
        )
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_firecrawl_provider] = lambda: StubProvider()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Zurich decisions",
                "jurisdiction_id": "jur_ch",
                "authority_id": "auth_zh_admin",
            },
        )
        assert source_response.status_code == 201
        source_id = source_response.json()["source_id"]

        version_response = await client.post(
            f"/v1/sources/{source_id}/versions",
            json={
                "version_label": "v1",
                "acquisition_spec": {
                    "seed_url": "https://example.com/decisions",
                    "mode": "crawl",
                    "limit": 5,
                    "tenant_id": "tenant_public",
                    "corpus_id": "corpus_public_ch_admin_decisions",
                    "scope_type": "global_public",
                    "source_origin_kind": "official_primary",
                    "trust_tier": "authoritative",
                    "language_codes": ["de"],
                    "document_type_hint": "decision",
                },
            },
        )
        assert version_response.status_code == 201
        version_body = version_response.json()
        source_version_id = version_body["source_version_id"]
        assert version_body["acquisition_spec"]["tenant_id"] == "tenant_public"
        assert version_body["acquisition_spec"]["corpus_id"] == "corpus_public_ch_admin_decisions"
        assert version_body["acquisition_spec"]["scope_type"] == "global_public"
        assert version_body["acquisition_spec"]["language_codes"] == ["de"]
        assert version_body["acquisition_spec"]["document_type_hint"] == "decision"

        approve_response = await client.post(f"/v1/versions/{source_version_id}/approve")
        assert approve_response.status_code == 200

        run_response = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": source_version_id,
                "mode": "production",
                "scope": {
                    "kind": "discovered_subset",
                    "include_urls": ["https://example.com/decisions"],
                    "max_resources": 10,
                },
                "replay": {
                    "mode": "partial_rerun",
                    "parent_run_id": "run_ancestor123",
                    "reason": "Repair subset after parser changes",
                },
            },
        )
        assert run_response.status_code == 201
        run_body = run_response.json()
        assert run_body["status"] == "running"
        assert run_body["scope"]["kind"] == "discovered_subset"
        assert run_body["scope"]["max_resources"] == 10
        assert run_body["replay"]["mode"] == "partial_rerun"
        assert run_body["replay"]["parent_run_id"] == "run_ancestor123"
        run_id = run_body["run_id"]

        status_event_response = await client.post(
            "/v1/di/events/document-processing-status-updated",
            json={
                "event_type": "document.processing_status.updated",
                "event_version": 1,
                "event_id": "evt_status_smoke_1",
                "occurred_at": "2026-04-02T12:00:00Z",
                "producer": "document-intelligence",
                "correlation_id": run_id,
                "payload": {
                    "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
                    "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
                    "document_revision": 3,
                    "provenance": {
                        "tenant_id": "tenant_public",
                        "corpus_id": "corpus_public_ch_federal_law",
                        "scope_type": "global_public",
                        "source_id": source_id,
                        "source_version_id": source_version_id,
                        "run_id": run_id,
                        "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                        "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
                    },
                    "processing_version": "di_2026_03_29",
                    "status": "canonical_ready",
                    "error_code": None,
                    "error_summary": None,
                },
            },
        )
        assert status_event_response.status_code == 202

        statuses_response = await client.get(f"/v1/runs/{run_id}/processing-status")
        assert statuses_response.status_code == 200
        statuses_body = statuses_response.json()
        assert len(statuses_body["data"]) == 1
        assert statuses_body["data"][0]["status"] == "canonical_ready"
        assert statuses_body["data"][0]["processing_manifest_id"] == "pm_01jq7bhgy7g0pkj4f1d03f8f8c"

        processed_event_response = await client.post(
            "/v1/di/events/document-processed",
            json={
                "event_type": "document.processed",
                "event_version": 1,
                "event_id": "evt_processed_smoke_1",
                "occurred_at": "2026-04-02T12:00:02Z",
                "producer": "document-intelligence",
                "correlation_id": run_id,
                "payload": {
                    "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
                    "document_revision": 3,
                    "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
                    "processing_version": "di_2026_03_29",
                    "provenance": {
                        "tenant_id": "tenant_public",
                        "corpus_id": "corpus_public_ch_federal_law",
                        "scope_type": "global_public",
                        "source_id": source_id,
                        "source_version_id": source_version_id,
                        "run_id": run_id,
                        "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                        "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
                    },
                    "lifecycle_status": "active",
                    "published_document_ref": {
                        "surface_name": "published_documents",
                        "surface_version": 1,
                    },
                    "published_sections_ref": {
                        "surface_name": "published_sections",
                        "surface_version": 1,
                    },
                    "processing_manifest_ref": {
                        "manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8c",
                        "manifest_type": "processing_manifest",
                        "manifest_version": 1,
                        "dataset_ref": {
                            "surface_name": "processing_manifests",
                            "surface_version": 1,
                        },
                    },
                    "supersedes_processing_manifest_id": None,
                },
            },
        )
        assert processed_event_response.status_code == 202

        withdrawn_event_response = await client.post(
            "/v1/di/events/document-withdrawn",
            json={
                "event_type": "document.withdrawn",
                "event_version": 1,
                "event_id": "evt_withdrawn_smoke_1",
                "occurred_at": "2026-04-02T12:00:03Z",
                "producer": "document-intelligence",
                "correlation_id": run_id,
                "payload": {
                    "document_id": "doc_01jq7bdptzqv3xs0c41xpw1ybg",
                    "document_revision": 4,
                    "processing_manifest_id": "pm_01jq7cacd0zdw8r9nm7j7n6cnp",
                    "provenance": {
                        "tenant_id": "tenant_public",
                        "corpus_id": "corpus_public_ch_federal_law",
                        "scope_type": "global_public",
                        "source_id": source_id,
                        "source_version_id": source_version_id,
                        "run_id": run_id,
                        "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                        "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
                    },
                    "reason_code": "operator_withdrawn",
                    "reason_summary": "Operator withdrew this revision.",
                    "search_disposition": "remove",
                },
            },
        )
        assert withdrawn_event_response.status_code == 202

        lifecycle_response = await client.get(f"/v1/runs/{run_id}/document-lifecycle")
        assert lifecycle_response.status_code == 200
        lifecycle_body = lifecycle_response.json()
        assert len(lifecycle_body["data"]) == 2
        assert lifecycle_body["data"][0]["event_type"] == "document.withdrawn"
        assert lifecycle_body["data"][1]["event_type"] == "document.processed"

        invalid_failed_response = await client.post(
            "/v1/di/events/document-processing-status-updated",
            json={
                "event_type": "document.processing_status.updated",
                "event_version": 1,
                "event_id": "evt_status_smoke_invalid",
                "occurred_at": "2026-04-02T12:00:01Z",
                "producer": "document-intelligence",
                "correlation_id": run_id,
                "payload": {
                    "processing_manifest_id": "pm_01jq7bhgy7g0pkj4f1d03f8f8d",
                    "provenance": {
                        "tenant_id": "tenant_public",
                        "corpus_id": "corpus_public_ch_federal_law",
                        "scope_type": "global_public",
                        "source_id": source_id,
                        "source_version_id": source_version_id,
                        "run_id": run_id,
                    },
                    "processing_version": "di_2026_03_29",
                    "status": "failed",
                    "error_code": None,
                    "error_summary": None,
                },
            },
        )
        assert invalid_failed_response.status_code == 422

    app.dependency_overrides.clear()
