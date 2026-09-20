"""Integration tests for platform-control API contract compliance.

These tests verify that the API responds with correct status codes,
content types, pagination, and error shapes across all major endpoints.

Uses SQLite via ASGI transport (inherited from conftest.py) for fast,
zero-dependency CI runs. For Postgres-specific behaviour (e.g. ON CONFLICT,
advisory locks), see ``test_firecrawl_webhook_service_postgres.py`` which
uses testcontainers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from conftest import dispatchable_compliance_policy

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.run import Run
from platform_control.models.source import Source
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
        policy = dispatchable_compliance_policy()
        session.add(policy)
        session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch",
                name="Switzerland",
                slug="ch",
                compliance_policy_id=policy.compliance_policy_id,
            )
        )
        session.add(
            Authority(
                authority_id="auth_bger",
                jurisdiction_id="jur_ch",
                name="Federal Supreme Court",
                slug="bger",
            )
        )
        await session.commit()


@pytest.fixture
async def seed_fedlex_reference_data(session_maker):
    async with session_maker() as session:
        session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch_federal",
                name="Switzerland Federal",
                slug="ch-federal",
            )
        )
        session.add(
            Authority(
                authority_id="auth_fedlex",
                jurisdiction_id="jur_ch_federal",
                name="Fedlex",
                slug="fedlex",
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


@pytest.mark.asyncio
async def test_stats_recent_runs_carry_started_at(client, session_maker) -> None:
    """`/stats` must expose `started_at`, or the dashboard cannot state a duration.

    Without it the only elapsed time the dashboard could compute is
    `created_at -> completed_at` — queue wait plus execution — which it labelled
    "Duration". Three Fedlex runs read "2m 20s" against a real execution of
    ~0.3s, and the run detail page (which uses `started_at`) read "273ms" for
    the same run under the same column name (#674).
    """
    created = datetime(2026, 7, 18, 17, 43, 4, tzinfo=UTC)
    started = datetime(2026, 7, 18, 17, 45, 24, 412000, tzinfo=UTC)
    completed = datetime(2026, 7, 18, 17, 45, 24, 685000, tzinfo=UTC)

    async with session_maker() as session:
        session.add(Jurisdiction(jurisdiction_id="jur_stats", name="Switzerland", slug="ch-stats"))
        session.add(
            Authority(
                authority_id="auth_stats",
                jurisdiction_id="jur_stats",
                name="Fedlex",
                slug="fedlex-stats",
            )
        )
        session.add_all(
            [
                Source(
                    source_id="src_stats",
                    name="Stats source",
                    jurisdiction_id="jur_stats",
                    authority_id="auth_stats",
                ),
                SourceVersion(
                    source_version_id="sv_stats",
                    source_id="src_stats",
                    version_label="v1",
                    acquisition_spec={"provider": "firecrawl", "mode": "crawl"},
                ),
                Run(
                    run_id="run_stats",
                    source_id="src_stats",
                    source_version_id="sv_stats",
                    created_at=created,
                    started_at=started,
                    completed_at=completed,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/stats")
    assert response.status_code == 200

    recent = next(r for r in response.json()["recent_runs"] if r["run_id"] == "run_stats")
    assert recent["started_at"] is not None
    # The queue wait is real, and still available — it is just not the duration.
    assert recent["created_at"] != recent["started_at"]


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
async def test_create_source_with_initial_version_returns_201(client, seed_reference_data) -> None:
    response = await client.post(
        "/v1/sources/with-version",
        json={
            "source": {
                "name": "AT Combined Wizard Source",
                "jurisdiction_id": "jur_ch",
                "authority_id": "auth_bger",
                "source_type": "website",
            },
            "source_version": {
                "version_label": "v1",
                "overlay_id": "at",
                "provider_template_id": "ris_ogd_bundesrecht",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"]["name"] == "AT Combined Wizard Source"
    assert body["source_version"]["version_label"] == "v1"
    assert body["source_version"]["acquisition_spec"]["provider"] == "ris_ogd"


@pytest.mark.asyncio
async def test_create_source_with_initial_version_unknown_template_returns_404(
    client, seed_reference_data
) -> None:
    response = await client.post(
        "/v1/sources/with-version",
        json={
            "source": {
                "name": "Invalid template source",
                "jurisdiction_id": "jur_ch",
                "authority_id": "auth_bger",
            },
            "source_version": {
                "version_label": "v1",
                "overlay_id": "at",
                "provider_template_id": "ris_ogd_missing_template",
            },
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_expanded_acquisition_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "de",
            "provider_template_id": "deterministic_http_bundesrecht",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "de"
    assert body["provider_template_id"] == "deterministic_http_bundesrecht"
    assert body["acquisition_spec"]["provider"] == "deterministic_http"


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_ris_ogd_narrow_html_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "at",
            "provider_template_id": "ris_ogd_bundesrecht_narrow_html",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "at"
    assert body["provider_template_id"] == "ris_ogd_bundesrecht_narrow_html"
    assert body["acquisition_spec"]["provider"] == "ris_ogd"
    assert body["acquisition_spec"]["applikation"] == "BrKons"
    assert body["acquisition_spec"]["preferred_formats"] == ["Html", "Xml"]
    assert body["acquisition_spec"]["request_timeout_seconds"] == 15.0
    assert body["acquisition_spec"]["page_size"] == 1
    assert body["acquisition_spec"]["max_pages"] == 1


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_ris_ogd_small_batch_html_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "at",
            "provider_template_id": "ris_ogd_bundesrecht_small_batch_html",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "at"
    assert body["provider_template_id"] == "ris_ogd_bundesrecht_small_batch_html"
    assert body["acquisition_spec"]["provider"] == "ris_ogd"
    assert body["acquisition_spec"]["applikation"] == "BrKons"
    assert body["acquisition_spec"]["preferred_formats"] == ["Html", "Xml"]
    assert body["acquisition_spec"]["request_timeout_seconds"] == 15.0
    assert body["acquisition_spec"]["page_size"] == 5
    assert body["acquisition_spec"]["max_pages"] == 1


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_fedlex_sparql_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "ch",
            "provider_template_id": "fedlex_sparql_constitution_de",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "ch"
    assert body["provider_template_id"] == "fedlex_sparql_constitution_de"
    assert body["acquisition_spec"]["provider"] == "fedlex_sparql"
    assert body["acquisition_spec"]["seed_url"] == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    assert body["acquisition_spec"]["preferred_languages"] == ["de"]


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_fedlex_sparql_vwvg_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "ch",
            "provider_template_id": "fedlex_sparql_vwvg_de",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "ch"
    assert body["provider_template_id"] == "fedlex_sparql_vwvg_de"
    assert body["acquisition_spec"]["provider"] == "fedlex_sparql"
    assert body["acquisition_spec"]["seed_url"] == (
        "https://fedlex.data.admin.ch/eli/cc/1969/737_757_755"
    )
    assert body["acquisition_spec"]["preferred_languages"] == ["de"]


@pytest.mark.asyncio
async def test_source_blueprint_preview_returns_fedlex_sparql_small_batch_spec(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "ch",
            "provider_template_id": "fedlex_sparql_federal_law_batch_de",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overlay_id"] == "ch"
    assert body["provider_template_id"] == "fedlex_sparql_federal_law_batch_de"
    assert body["acquisition_spec"]["provider"] == "fedlex_sparql"
    assert body["acquisition_spec"]["seed_urls"] == [
        "https://fedlex.data.admin.ch/eli/cc/1999/404",
        "https://fedlex.data.admin.ch/eli/cc/1969/737_757_755",
    ]
    assert body["acquisition_spec"]["preferred_languages"] == ["de"]


@pytest.mark.asyncio
async def test_source_blueprint_preview_unknown_template_returns_404(client) -> None:
    response = await client.post(
        "/v1/sources/blueprint-preview",
        json={
            "overlay_id": "de",
            "provider_template_id": "deterministic_http_missing_template",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_source_blueprint_templates_returns_data(client) -> None:
    response = await client.get("/v1/sources/blueprint-templates")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert any(row["overlay_id"] == "at" for row in body["data"])
    assert any(
        row["provider_template_id"] == "deterministic_http_bundesrecht" for row in body["data"]
    )


@pytest.mark.asyncio
async def test_blueprint_template_inventory_reports_config_key_provenance(client) -> None:
    """The inventory must distinguish "never touched" from "an operator flipped it" (#668).

    Without `source`, the admin inventory cannot tell a template running on the
    shipped default from one an operator deliberately turned on (or off) — which
    is the whole point of an evidence-gated coverage surface.

    Driven in the *closing* direction because that is the harder provenance case and
    the one the panel used to render wrong (#854): `enabled: false, source: default`
    is a key nobody ever turned, which ADR-0030's acceptance waiver still dispatches
    at; `enabled: false, source: override` is an operator's kill switch, which it does
    not (#768). Both read `enabled: false`. Arming the key needs cited acceptance
    evidence and is driven end to end in `tests/smoke/test_app.py`.
    """
    before = await client.get("/v1/sources/blueprint-templates")
    assert before.status_code == 200
    row = next(
        r
        for r in before.json()["data"]
        if (r["overlay_id"], r["provider_template_id"]) == ("de", "bundesland_http_bayern")
    )
    assert row["source"] == "default"
    assert row["enabled"] is False
    assert row["note"] is None
    assert row["updated_by"] is None

    flip = await client.put(
        "/v1/sources/blueprint-templates/de/bundesland_http_bayern/enablement",
        json={"enabled": False, "note": "shut pending 2026-07-19 terms review"},
    )
    assert flip.status_code == 200

    after = await client.get("/v1/sources/blueprint-templates")
    flipped = next(
        r
        for r in after.json()["data"]
        if (r["overlay_id"], r["provider_template_id"]) == ("de", "bundesland_http_bayern")
    )
    assert flipped["source"] == "override"
    assert flipped["enabled"] is False
    assert flipped["default_enabled"] is False
    assert flipped["note"] == "shut pending 2026-07-19 terms review"
    assert flipped["updated_at"] is not None


@pytest.mark.asyncio
async def test_create_source_version_rejects_mixed_spec_and_blueprint(
    client, seed_reference_data
) -> None:
    source = await client.post(
        "/v1/sources",
        json={
            "name": "Mixed payload test",
            "jurisdiction_id": "jur_ch",
            "authority_id": "auth_bger",
        },
    )
    source_id = source.json()["source_id"]
    response = await client.post(
        f"/v1/sources/{source_id}/versions",
        json={
            "version_label": "v1",
            "overlay_id": "at",
            "provider_template_id": "ris_ogd_bundesrecht",
            "acquisition_spec": {
                "seed_url": "https://example.com",
                "mode": "crawl",
            },
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_source_with_initial_version_returns_201_for_fedlex_sparql(
    client, seed_fedlex_reference_data
) -> None:
    response = await client.post(
        "/v1/sources/with-version",
        json={
            "source": {
                "name": "CH Fedlex legislation thin slice",
                "jurisdiction_id": "jur_ch_federal",
                "authority_id": "auth_fedlex",
                "source_type": "website",
            },
            "source_version": {
                "version_label": "ch-fedlex-v1",
                "overlay_id": "ch",
                "provider_template_id": "fedlex_sparql_constitution_de",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"]["jurisdiction_id"] == "jur_ch_federal"
    assert body["source_version"]["acquisition_spec"]["provider"] == "fedlex_sparql"
    assert body["source_version"]["acquisition_spec"]["seed_url"] == (
        "https://fedlex.data.admin.ch/eli/cc/1999/404"
    )


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
        "Acquisition spec must define seed_url, seed_urls, or base_url."
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
    # `stalled` is the fifth value, for a run that ended with downstream stages that
    # never reported (#951). The field is an open string in the contract, so this set
    # is the only place the server states what it may actually send.
    assert body["overall_status"] in {"ok", "in_progress", "blocked", "failed", "stalled"}
    assert isinstance(body["stages"], list)
    stage_names = {stage["stage"] for stage in body["stages"]}
    assert stage_names == {"acquisition", "document_intelligence", "projection", "search"}


# ── DI Events ────────────────────────────────────


@pytest.mark.asyncio
async def test_di_processing_status_pubsub_push_envelope_accepted(client) -> None:
    import base64
    import json

    run_id = "run_01jq7a3s9b7j4dndd9sgv6pb9d"
    inner = {
        "event_type": "document.processing_status.updated",
        "event_version": 1,
        "event_id": "evt_pubsub_wrap_1",
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
                "source_id": "src_01jq79xv3wdd6yr8q5bn0m3zfk",
                "source_version_id": "sv_01jq79zcskf4m3m4gm3t5s59xq",
                "run_id": run_id,
                "source_snapshot_id": "snap_01jq7a7n3nbzj6sk7v95p9frz1",
                "bundle_manifest_id": "abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
            },
            "processing_version": "di_2026_03_29",
            "status": "canonical_ready",
            "error_code": None,
            "error_summary": None,
        },
    }
    wrapped = {
        "message": {
            "data": base64.b64encode(json.dumps(inner).encode("utf-8")).decode("ascii"),
            "messageId": "2070443601311540",
        },
        "subscription": "projects/test/subscriptions/s",
    }
    response = await client.post(
        "/v1/di/events/document-processing-status-updated",
        json=wrapped,
    )
    assert response.status_code == 202


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
