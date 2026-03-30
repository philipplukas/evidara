from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ProviderJobStatus, RunStatus
from platform_control.errors import SignatureVerificationError
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.webhook_receipt import WebhookReceipt
from platform_control.services.artifact_store import ArtifactStore


class FirecrawlWebhookService:
    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore,
        publisher: RawArtifactPublisher,
        webhook_secret: str | None,
    ) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self.publisher = publisher
        self.webhook_secret = webhook_secret

    async def process(
        self,
        payload: dict[str, Any],
        raw_body: bytes,
        signature: str | None,
    ) -> None:
        self._verify_signature(raw_body, signature)
        payload_sha256 = hashlib.sha256(raw_body).hexdigest()

        existing_receipt = await self.session.scalar(
            select(WebhookReceipt).where(
                WebhookReceipt.provider == "firecrawl",
                WebhookReceipt.payload_sha256 == payload_sha256,
            )
        )
        if existing_receipt is not None:
            return

        receipt = WebhookReceipt(
            provider="firecrawl",
            payload_sha256=payload_sha256,
            signature=signature,
            payload=payload,
            processed_at=datetime.now(UTC),
        )
        self.session.add(receipt)

        external_job_id = str(payload.get("id", ""))
        event_type = str(payload.get("type", ""))
        provider_job = None
        run = None
        if external_job_id:
            provider_job = await self.session.scalar(
                select(ProviderJob).where(ProviderJob.external_job_id == external_job_id)
            )
            if provider_job is not None:
                run = await self.session.get(Run, provider_job.run_id)

        if provider_job is not None:
            provider_job.last_event_type = event_type or None

        if run is not None:
            await self._apply_event(payload, event_type, provider_job, run)

        await self.session.commit()

    def _verify_signature(self, raw_body: bytes, signature: str | None) -> None:
        if not self.webhook_secret:
            raise SignatureVerificationError("Firecrawl webhook secret is not configured.")
        if not signature or not signature.startswith("sha256="):
            raise SignatureVerificationError("Missing Firecrawl signature header.")

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        actual = signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, actual):
            raise SignatureVerificationError("Firecrawl signature verification failed.")

    async def _apply_event(
        self,
        payload: dict[str, Any],
        event_type: str,
        provider_job: ProviderJob,
        run: Run,
    ) -> None:
        if event_type == "crawl.started":
            provider_job.status = ProviderJobStatus.RUNNING
            run.status = RunStatus.RUNNING
            return

        if event_type == "crawl.page":
            pages = payload.get("data", [])
            if isinstance(pages, dict):
                pages = [pages]
            for page in pages:
                page_metadata = page.get("metadata", {})
                source_url = str(page.get("url") or page_metadata.get("sourceURL") or "")
                final_url = str(page_metadata.get("sourceURL") or page.get("url") or "")
                artifact = RawArtifact(
                    run_id=run.run_id,
                    source_id=run.source_id,
                    source_version_id=run.source_version_id,
                    storage_path="",
                    content_type=self._guess_content_type(page),
                    artifact_metadata=page,
                )
                self.session.add(artifact)
                await self.session.flush()

                artifact.storage_path = await self.artifact_store.store_page_payload(
                    run.run_id, artifact.artifact_id, page
                )

                resource = CapturedResource(
                    artifact_id=artifact.artifact_id,
                    run_id=run.run_id,
                    source_id=run.source_id,
                    source_version_id=run.source_version_id,
                    provider_job_id=provider_job.provider_job_id,
                    source_url=source_url,
                    final_url=final_url,
                    title=page_metadata.get("title"),
                    content_type=artifact.content_type,
                    checksum=self._checksum(page),
                    http_status=page_metadata.get("statusCode"),
                    discovery_depth=page_metadata.get("depth"),
                    resource_metadata=page,
                )
                self.session.add(resource)
                run.artifacts_count += 1
                run.captured_resources_count += 1
                await self.publisher.publish_raw_artifact_available(artifact)
            return

        if event_type == "crawl.completed":
            provider_job.status = ProviderJobStatus.COMPLETED
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            return

        if event_type == "crawl.failed":
            provider_job.status = ProviderJobStatus.FAILED
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            run.failure_reason = str(payload.get("error") or "Firecrawl job failed.")

    @staticmethod
    def _checksum(page: dict[str, Any]) -> str:
        return hashlib.sha256(repr(sorted(page.items())).encode("utf-8")).hexdigest()

    @staticmethod
    def _guess_content_type(page: dict[str, Any]) -> str:
        metadata = page.get("metadata", {})
        return str(
            metadata.get("contentType")
            or metadata.get("mimeType")
            or page.get("content_type")
            or "text/html"
        )
