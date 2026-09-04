from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from conftest import dispatchable_compliance_policy

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
        policy = dispatchable_compliance_policy()
        seed_session.add(policy)
        seed_session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch",
                name="Switzerland",
                slug="ch",
                compliance_policy_id=policy.compliance_policy_id,
            )
        )
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

        update_approved_version_response = await client.patch(
            f"/v1/versions/{source_version_id}",
            json={"version_label": "should-not-work"},
        )
        assert update_approved_version_response.status_code == 409

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

        runs_response = await client.get("/v1/runs")
        assert runs_response.status_code == 200
        runs_body = runs_response.json()
        assert len(runs_body["data"]) == 1
        assert runs_body["data"][0]["run_id"] == run_id
        assert runs_body["data"][0]["mode"] == "production"
        assert runs_body["data"][0]["status"] == "running"
        assert runs_body["data"][0]["source_name"] == "Zurich decisions"
        assert runs_body["data"][0]["version_label"] == "v1"

        production_runs_response = await client.get("/v1/runs", params={"mode": "production"})
        assert production_runs_response.status_code == 200
        assert len(production_runs_response.json()["data"]) == 1

        preview_runs_response = await client.get("/v1/runs", params={"mode": "preview"})
        assert preview_runs_response.status_code == 200
        assert preview_runs_response.json()["data"] == []

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


@pytest.mark.asyncio
async def test_sync_hierarchy_endpoint(session_maker) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/reference-data/hierarchy/sync?dry_run=true")
        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["jurisdictions"]["created"] >= 1
        assert body["authorities"]["created"] >= 1
        assert "scrape_targets" not in body

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_two_key_lock_rejects_scaffold_and_disabled_template_with_400(session_maker) -> None:
    """The ADR-0030 lock must surface as a client error, never a 500 (#559).

    Two runs, one per key: a hand-written spec naming the `canton_http` scaffold
    (live_ready = False) and a version created from a `enabled: false` blueprint
    template whose provider IS live_ready. Both must be refused before any
    request leaves the process, with a 400 the admin UI can render.
    """
    async with session_maker() as seed_session:
        policy = dispatchable_compliance_policy()
        seed_session.add(policy)
        seed_session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch",
                name="Switzerland",
                slug="ch",
                compliance_policy_id=policy.compliance_policy_id,
            )
        )
        seed_session.add(
            Authority(
                authority_id="auth_zh",
                jurisdiction_id="jur_ch",
                name="Canton of Zurich",
                slug="zh",
            )
        )
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Zurich legislation",
                "jurisdiction_id": "jur_ch",
                "authority_id": "auth_zh",
            },
        )
        assert source_response.status_code == 201
        source_id = source_response.json()["source_id"]

        # Key 1 (code owner): scaffold provider, hand-written spec.
        scaffold_version = await client.post(
            f"/v1/sources/{source_id}/versions",
            json={
                "version_label": "scaffold",
                "acquisition_spec": {
                    "provider": "canton_http",
                    "canton_code": "CH-ZH",
                    "seed_urls": ["https://www.zh.ch/de/politik-staat/gesetze-beschluesse.html"],
                    "language_codes": ["de"],
                },
            },
        )
        assert scaffold_version.status_code == 201
        scaffold_run = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": scaffold_version.json()["source_version_id"],
                "mode": "preview",
            },
        )
        assert scaffold_run.status_code == 400
        assert "scaffold" in scaffold_run.json()["detail"]

        # Key 2 (config owner): live_ready provider, template not enabled.
        disabled_version = await client.post(
            f"/v1/sources/{source_id}/versions",
            json={
                "version_label": "disabled-template",
                "overlay_id": "de",
                "provider_template_id": "bundesland_http_bayern",
            },
        )
        assert disabled_version.status_code == 201
        disabled_run = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": disabled_version.json()["source_version_id"],
                "mode": "preview",
            },
        )
        assert disabled_run.status_code == 400
        assert "not enabled" in disabled_run.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_operator_can_flip_the_config_key_over_the_api(session_maker) -> None:
    """#632: the ADR-0030 config key is operator-reachable, with an audit trail.

    #632's central claim was that no operator path flips `enabled` — both keys
    were source code, so the Nth source cost an engineer and a deploy. This
    drives the path end to end over HTTP: a disabled template refuses, readiness
    says so instead of lying (#634), a PUT flips the key and records who/why,
    and readiness then goes green. No repo edit, no redeploy.
    """
    async with session_maker() as seed_session:
        seed_session.add(Jurisdiction(jurisdiction_id="jur_de", name="Germany", slug="de"))
        seed_session.add(
            Authority(
                authority_id="auth_de_by",
                jurisdiction_id="jur_de",
                name="Freistaat Bayern",
                slug="bayern",
            )
        )
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Bayern legislation",
                "jurisdiction_id": "jur_de",
                "authority_id": "auth_de_by",
            },
        )
        assert source_response.status_code == 201
        source_id = source_response.json()["source_id"]

        version_response = await client.post(
            f"/v1/sources/{source_id}/versions",
            json={
                "version_label": "bayern-v1",
                "overlay_id": "de",
                "provider_template_id": "bundesland_http_bayern",
            },
        )
        assert version_response.status_code == 201
        source_version_id = version_response.json()["source_version_id"]

        readiness_params = {
            "source_id": source_id,
            "source_version_id": source_version_id,
        }
        locked = await client.get("/v1/runs/readiness", params=readiness_params)
        assert locked.status_code == 200
        locked_body = locked.json()
        assert locked_body["ready"] is False
        lock_check = next(
            check for check in locked_body["checks"] if check["code"] == "acquisition_lock_open"
        )
        assert lock_check["ok"] is False
        assert "not enabled" in lock_check["detail"]

        # Refusals leave evidence: a terminal FAILED run, not silence (#634).
        refused = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": source_version_id,
                "mode": "preview",
            },
        )
        assert refused.status_code == 400
        failed_runs = await client.get("/v1/runs", params={"source_id": source_id})
        assert failed_runs.status_code == 200
        refused_rows = [row for row in failed_runs.json()["data"] if row["status"] == "failed"]
        assert len(refused_rows) == 1

        flip = await client.put(
            "/v1/sources/blueprint-templates/de/bundesland_http_bayern/enablement",
            json={"enabled": True, "note": "acceptance run 2026-07-18: 42/42 acts parsed"},
        )
        assert flip.status_code == 200
        flipped = flip.json()
        assert flipped["enabled"] is True
        assert flipped["default_enabled"] is False
        assert flipped["source"] == "override"
        assert flipped["note"] == "acceptance run 2026-07-18: 42/42 acts parsed"
        assert flipped["updated_by"] == "op_00000000000000000000000001"

        unlocked = await client.get("/v1/runs/readiness", params=readiness_params)
        assert unlocked.status_code == 200
        unlocked_check = next(
            check for check in unlocked.json()["checks"] if check["code"] == "acquisition_lock_open"
        )
        assert unlocked_check["ok"] is True

    app.dependency_overrides.clear()
