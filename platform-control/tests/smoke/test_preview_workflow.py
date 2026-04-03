from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import select

from platform_control.database import get_session
from platform_control.domain import ProviderJobStatus
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.routers.runs import get_firecrawl_provider
from platform_control.services.firecrawl_provider import ProviderStartResult


@dataclass
class StubProvider:
    external_job_id: str = "crawl_preview_123"

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id=self.external_job_id,
            request_payload={"url": "https://example.com"},
            response_payload={"id": self.external_job_id, "success": True},
        )


def _sign(payload: dict[str, object]) -> tuple[bytes, str]:
    raw_body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = "sha256=" + hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
    return raw_body, signature


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(session_maker) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_preview_run_reaches_terminal_state_and_exposes_summary(session_maker) -> None:
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
        source_id = (
            await client.post(
                "/v1/sources",
                json={
                    "name": "Zurich decisions",
                    "jurisdiction_id": "jur_ch",
                    "authority_id": "auth_zh_admin",
                },
            )
        ).json()["source_id"]
        source_version_id = (
            await client.post(
                f"/v1/sources/{source_id}/versions",
                json={
                    "version_label": "preview-v1",
                    "acquisition_spec": {
                        "seed_url": "https://example.com/decisions",
                        "mode": "crawl",
                        "limit": 5,
                    },
                },
            )
        ).json()["source_version_id"]

        run_response = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": source_version_id,
                "mode": "preview",
            },
        )
        assert run_response.status_code == 201
        run_id = run_response.json()["run_id"]

        page_payload = {
            "type": "crawl.page",
            "id": "crawl_preview_123",
            "data": [
                {
                    "url": "https://example.com/decisions/2026-01",
                    "metadata": {
                        "title": "Decision 2026/01",
                        "sourceURL": "https://example.com/decisions/2026-01",
                        "statusCode": 200,
                        "depth": 1,
                        "contentType": "text/html",
                    },
                },
                {
                    "url": "https://example.com/privacy.pdf",
                    "metadata": {
                        "title": "Privacy policy",
                        "sourceURL": "https://example.com/privacy.pdf",
                        "statusCode": 200,
                        "depth": 1,
                        "contentType": "application/pdf",
                    },
                },
            ],
        }
        raw_body, signature = _sign(page_payload)
        page_response = await client.post(
            "/v1/firecrawl/webhooks",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "X-Firecrawl-Signature": signature,
            },
        )
        assert page_response.status_code == 200

        completed_payload = {"type": "crawl.completed", "id": "crawl_preview_123", "data": {}}
        raw_body, signature = _sign(completed_payload)
        completed_response = await client.post(
            "/v1/firecrawl/webhooks",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "X-Firecrawl-Signature": signature,
            },
        )
        assert completed_response.status_code == 200

        run_status = await client.get(f"/v1/runs/{run_id}")
        assert run_status.status_code == 200
        assert run_status.json()["status"] == "completed"

        preview_summary = await client.get(f"/v1/runs/{run_id}/preview-summary")
        assert preview_summary.status_code == 200
        body = preview_summary.json()
        assert body["captured_resources_count"] == 2
        assert body["pdf_count"] == 1
        assert body["likely_decision_page_count"] >= 1
        assert body["likely_boilerplate_page_count"] >= 1

        captured_resources = await client.get(f"/v1/runs/{run_id}/captured-resources")
        assert captured_resources.status_code == 200
        captured_resources_body = captured_resources.json()
        assert captured_resources_body["total"] == 2
        assert captured_resources_body["limit"] == 100
        assert captured_resources_body["offset"] == 0
        assert len(captured_resources_body["data"]) == 2
        by_title = {row["title"]: row for row in captured_resources_body["data"]}
        assert by_title["Decision 2026/01"]["content_type"] == "text/html"
        assert by_title["Privacy policy"]["content_type"] == "application/pdf"

        raw_artifacts_response = await client.get(f"/v1/runs/{run_id}/raw-artifacts")
        assert raw_artifacts_response.status_code == 200
        raw_artifacts_body = raw_artifacts_response.json()
        assert raw_artifacts_body["total"] == 2
        assert raw_artifacts_body["limit"] == 100
        assert raw_artifacts_body["offset"] == 0
        assert len(raw_artifacts_body["data"]) == 2
        assert raw_artifacts_body["data"][0]["storage_path"]
        assert {artifact["content_type"] for artifact in raw_artifacts_body["data"]} == {
            "application/pdf",
            "text/html",
        }

        provider_jobs_response = await client.get(f"/v1/runs/{run_id}/provider-jobs")
        assert provider_jobs_response.status_code == 200
        provider_jobs_body = provider_jobs_response.json()
        assert provider_jobs_body["total"] == 1
        assert provider_jobs_body["limit"] == 100
        assert provider_jobs_body["offset"] == 0
        assert len(provider_jobs_body["data"]) == 1
        assert provider_jobs_body["data"][0]["external_job_id"] == "crawl_preview_123"
        assert provider_jobs_body["data"][0]["status"] == "completed"
        assert provider_jobs_body["data"][0]["last_event_type"] == "crawl.completed"

    async with session_maker() as verification_session:
        provider_job = await verification_session.scalar(
            select(ProviderJob).where(ProviderJob.run_id == run_id)
        )
        raw_artifacts = list(
            await verification_session.scalars(
                select(RawArtifact)
                .where(RawArtifact.run_id == run_id)
                .order_by(RawArtifact.created_at.asc())
            )
        )

    assert provider_job is not None
    assert provider_job.external_job_id == "crawl_preview_123"
    assert provider_job.status is ProviderJobStatus.COMPLETED
    assert provider_job.last_event_type == "crawl.completed"
    assert len(raw_artifacts) == 2
    assert all(artifact.storage_path for artifact in raw_artifacts)
    assert {artifact.content_type for artifact in raw_artifacts} == {
        "application/pdf",
        "text/html",
    }


@pytest.mark.asyncio
async def test_failed_preview_run_is_surfaced(session_maker) -> None:
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
    app.dependency_overrides[get_firecrawl_provider] = lambda: StubProvider(
        external_job_id="crawl_failed_123"
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        source_id = (
            await client.post(
                "/v1/sources",
                json={
                    "name": "Zurich decisions",
                    "jurisdiction_id": "jur_ch",
                    "authority_id": "auth_zh_admin",
                },
            )
        ).json()["source_id"]
        source_version_id = (
            await client.post(
                f"/v1/sources/{source_id}/versions",
                json={
                    "version_label": "preview-v1",
                    "acquisition_spec": {
                        "seed_url": "https://example.com/decisions",
                        "mode": "crawl",
                        "limit": 5,
                    },
                },
            )
        ).json()["source_version_id"]
        run_id = (
            await client.post(
                "/v1/runs",
                json={
                    "source_id": source_id,
                    "source_version_id": source_version_id,
                    "mode": "preview",
                },
            )
        ).json()["run_id"]

        failed_payload = {
            "type": "crawl.failed",
            "id": "crawl_failed_123",
            "error": "Timed out on upstream site",
        }
        raw_body, signature = _sign(failed_payload)
        failed_response = await client.post(
            "/v1/firecrawl/webhooks",
            content=raw_body,
            headers={
                "content-type": "application/json",
                "X-Firecrawl-Signature": signature,
            },
        )
        assert failed_response.status_code == 200

        run_status = await client.get(f"/v1/runs/{run_id}")
        assert run_status.status_code == 200
        body = run_status.json()
        assert body["status"] == "failed"
        assert body["failure_reason"] == "Timed out on upstream site"
