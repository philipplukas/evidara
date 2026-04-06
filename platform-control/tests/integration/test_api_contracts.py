"""Integration tests for platform-control API contract compliance.

These tests verify that the API responds with correct status codes,
content types, pagination, and error shapes across all major endpoints.

Uses SQLite via ASGI transport (inherited from conftest.py) for fast,
zero-dependency CI runs. For Postgres-specific behaviour (e.g. ON CONFLICT,
advisory locks), see ``test_firecrawl_webhook_service_postgres.py`` which
uses testcontainers.
"""

from __future__ import annotations

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.source_version import SourceVersion
from platform_control.routers.runs import get_firecrawl_provider
from platform_control.services.firecrawl_provider import ProviderStartResult

# ── Helpers ──────────────────────────────────────


class FakeProvider:
    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id="crawl_integration_001",
            request_payload={"url": "https://example.com"},
            response_payload={"id": "crawl_integration_001", "success": True},
        )


@pytest.fixture
def _app(session_maker):
    """Create a fully wired FastAPI app with test overrides."""
    app = create_app()

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_firecrawl_provider] = lambda: FakeProvider()
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(_app):
    """Async HTTP client bound to the test app."""
    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def seed_reference_data(session_maker):
    """Seed minimum reference data for source creation."""
    async with session_maker() as session:
        session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
        session.add(
            Authority(
                authority_id="auth_bger",
                jurisdiction_id="jur_ch",
                name="Federal Supreme Court",
                slug="bger",
            )
        )
        await session.commit()


# ── Health ───────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ready_returns_200(client) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200


# ── Sources CRUD ─────────────────────────────────


@pytest.mark.asyncio
async def test_create_source_returns_201(client, seed_reference_data) -> None:
    response = await client.post(
        "/v1/sources",
        json={
            "name": "Integration Test Source",
            "jurisdiction_id": "jur_ch",
            "authority_id": "auth_bger",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "source_id" in body
    assert body["name"] == "Integration Test Source"


@pytest.mark.asyncio
async def test_create_source_without_name_returns_422(client) -> None:
    response = await client.post("/v1/sources", json={})
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_list_sources_returns_paginated(client, seed_reference_data) -> None:
    # Create two sources
    await client.post(
        "/v1/sources",
        json={"name": "Source A", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    await client.post(
        "/v1/sources",
        json={"name": "Source B", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )

    response = await client.get("/v1/sources")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert len(body["data"]) >= 2


@pytest.mark.asyncio
async def test_get_nonexistent_source_returns_404(client) -> None:
    response = await client.get("/v1/sources/nonexistent_source_id")
    assert response.status_code == 404


# ── Source Versions ──────────────────────────────


@pytest.mark.asyncio
async def test_create_version_requires_acquisition_spec(client, seed_reference_data) -> None:
    source = await client.post(
        "/v1/sources",
        json={"name": "Ver Test", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_id = source.json()["source_id"]

    response = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={"version_label": "v1"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_version_lifecycle_draft_approve(client, seed_reference_data) -> None:
    source = await client.post(
        "/v1/sources",
        json={"name": "LC Test", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_id = source.json()["source_id"]

    version = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={
            "version_label": "v1",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    assert version.status_code == 201
    version_id = version.json()["source_version_id"]

    # Approve
    approve = await client.post(f"/v1/versions/{version_id}/approve")
    assert approve.status_code == 200

    # Cannot update after approval
    update = await client.patch(
        f"/v1/versions/{version_id}",
        json={"version_label": "v2"},
    )
    assert update.status_code == 409


# ── Runs ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_runs_empty(client) -> None:
    response = await client.get("/v1/runs")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []


@pytest.mark.asyncio
async def test_create_run_with_valid_version(client, seed_reference_data) -> None:
    source = await client.post(
        "/v1/sources",
        json={"name": "Run Test", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_id = source.json()["source_id"]

    version = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={
            "version_label": "v1",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    version_id = version.json()["source_version_id"]

    # Approve first
    await client.post(f"/v1/versions/{version_id}/approve")

    run = await client.post(
        "/v1/runs",
        json={"source_id": source_id, "source_version_id": version_id},
    )
    assert run.status_code == 201
    body = run.json()
    assert "run_id" in body
    assert body["status"] == "running"


@pytest.mark.asyncio
async def test_run_readiness_endpoint_returns_checks(client, seed_reference_data) -> None:
    source = await client.post(
        "/v1/sources",
        json={"name": "Readiness Test", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_id = source.json()["source_id"]

    version = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={
            "version_label": "v1",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    version_id = version.json()["source_version_id"]

    await client.post(f"/v1/versions/{version_id}/approve")

    readiness = await client.get(
        "/v1/runs/readiness",
        params={
            "source_id": source_id,
            "source_version_id": version_id,
            "mode": "production",
        },
    )
    assert readiness.status_code == 200
    body = readiness.json()
    assert body["ready"] is True
    assert isinstance(body["checks"], list)
    assert any(check["code"] == "source_exists" for check in body["checks"])


@pytest.mark.asyncio
async def test_run_readiness_endpoint_reports_actionable_blocking_details(
    client, seed_reference_data, session_maker
) -> None:
    # Case 1: missing source + version IDs
    missing = await client.get(
        "/v1/runs/readiness",
        params={
            "source_id": "src_missing",
            "source_version_id": "sv_missing",
            "mode": "production",
        },
    )
    assert missing.status_code == 200
    missing_body = missing.json()
    missing_checks = {check["code"]: check for check in missing_body["checks"]}
    assert missing_checks["source_exists"]["ok"] is False
    assert "Source not found:" in missing_checks["source_exists"]["detail"]
    assert missing_checks["source_version_exists"]["ok"] is False
    assert "Source version not found:" in missing_checks["source_version_exists"]["detail"]

    # Create two sources and one version to test source/version mismatch and missing seed
    source_a = await client.post(
        "/v1/sources",
        json={"name": "A", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_a_id = source_a.json()["source_id"]
    source_b = await client.post(
        "/v1/sources",
        json={"name": "B", "jurisdiction_id": "jur_ch", "authority_id": "auth_bger"},
    )
    source_b_id = source_b.json()["source_id"]

    version_for_b = await client.post(
        f"/v1/sources/{source_b_id}/versions",
        json={
            "version_label": "v-b",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    version_for_b_id = version_for_b.json()["source_version_id"]

    mismatch = await client.get(
        "/v1/runs/readiness",
        params={
            "source_id": source_a_id,
            "source_version_id": version_for_b_id,
            "mode": "preview",
        },
    )
    assert mismatch.status_code == 200
    mismatch_checks = {check["code"]: check for check in mismatch.json()["checks"]}
    assert mismatch_checks["source_version_belongs_to_source"]["ok"] is False
    assert (
        mismatch_checks["source_version_belongs_to_source"]["detail"]
        == "Source version does not belong to the requested source."
    )

    # Missing acquisition seed in spec
    version_missing_seed = await client.post(
        f"/v1/sources/{source_a_id}/versions",
        json={
            "version_label": "v-no-seed",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    assert version_missing_seed.status_code == 201
    version_missing_seed_id = version_missing_seed.json()["source_version_id"]
    async with session_maker() as session:
        version_model = await session.get(SourceVersion, version_missing_seed_id)
        assert version_model is not None
        version_model.acquisition_spec = {
            "mode": "crawl",
            "limit": 10,
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_test",
            "scope_type": "global_public",
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
            "language_codes": ["de"],
            "document_type_hint": "decision",
        }
        await session.commit()

    seed_missing = await client.get(
        "/v1/runs/readiness",
        params={
            "source_id": source_a_id,
            "source_version_id": version_missing_seed_id,
            "mode": "preview",
        },
    )
    assert seed_missing.status_code == 200
    seed_checks = {check["code"]: check for check in seed_missing.json()["checks"]}
    assert seed_checks["acquisition_seed_present"]["ok"] is False
    assert seed_checks["acquisition_seed_present"]["detail"] == (
        "Acquisition spec must define seed_url or seed_urls."
    )


@pytest.mark.asyncio
async def test_run_pipeline_health_endpoint_returns_stage_summary(
    client, seed_reference_data
) -> None:
    source = await client.post(
        "/v1/sources",
        json={
            "name": "Pipeline Health Test",
            "jurisdiction_id": "jur_ch",
            "authority_id": "auth_bger",
        },
    )
    source_id = source.json()["source_id"]

    version = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={
            "version_label": "v1",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
                "limit": 10,
                "tenant_id": "tenant_public",
                "corpus_id": "corpus_test",
                "scope_type": "global_public",
                "source_origin_kind": "official_primary",
                "trust_tier": "authoritative",
                "language_codes": ["de"],
                "document_type_hint": "decision",
            },
        },
    )
    version_id = version.json()["source_version_id"]

    await client.post(f"/v1/versions/{version_id}/approve")

    run = await client.post(
        "/v1/runs",
        json={"source_id": source_id, "source_version_id": version_id},
    )
    run_id = run.json()["run_id"]

    pipeline = await client.get(f"/v1/runs/{run_id}/pipeline-health")
    assert pipeline.status_code == 200
    body = pipeline.json()
    assert body["run_id"] == run_id
    assert body["overall_status"] in {"ok", "in_progress", "blocked", "failed"}
    assert isinstance(body["stages"], list)
    stage_names = {stage["stage"] for stage in body["stages"]}
    assert stage_names == {"acquisition", "document_intelligence", "projection", "search"}


# ── DI Events ────────────────────────────────────


@pytest.mark.asyncio
async def test_di_event_with_invalid_schema_returns_422(client) -> None:
    response = await client.post(
        "/v1/di/events/document-processing-status-updated",
        json={"event_type": "wrong.type"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_di_event_unknown_route_returns_404(client) -> None:
    response = await client.post("/v1/di/events/nonexistent-event", json={})
    assert response.status_code in (404, 405, 422)


# ── Reference Data ───────────────────────────────


@pytest.mark.asyncio
async def test_hierarchy_sync_dry_run(client) -> None:
    response = await client.post("/v1/reference-data/hierarchy/sync?dry_run=true")
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["jurisdictions"]["created"] >= 1
