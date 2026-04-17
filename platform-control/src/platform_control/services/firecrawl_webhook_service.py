from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ProviderJobStatus, RunStatus
from platform_control.errors import SignatureVerificationError
from platform_control.events.artifact_bundle import (
    build_artifact_bundle_available_event,
    build_artifact_bundle_manifest,
    build_bundle_extraction_hints,
)
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.ids import generate_prefixed_id
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.models.webhook_receipt import WebhookReceipt
from platform_control.services.artifact_store import ArtifactStore
from platform_control.services.replay_checkpoint import merge_run_replay_checkpoint


class FirecrawlWebhookService:
    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore,
        publisher: RawArtifactPublisher,
        webhook_secret: str | None,
        *,
        webhook_record_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self.publisher = publisher
        self.webhook_secret = webhook_secret
        self.webhook_record_dir = webhook_record_dir

    async def process(
        self,
        payload: dict[str, Any],
        raw_body: bytes,
        signature: str | None,
    ) -> None:
        """HTTP entrypoint: verify the Firecrawl signature, then delegate to ``process_payload``."""
        self._verify_signature(raw_body, signature)
        payload_sha256 = hashlib.sha256(raw_body).hexdigest()
        await self.process_payload(
            payload,
            signature=signature,
            payload_sha256=payload_sha256,
        )

    async def process_payload(
        self,
        payload: dict[str, Any],
        *,
        signature: str | None = None,
        payload_sha256: str | None = None,
    ) -> None:
        """Pure ingest entrypoint: apply a Firecrawl webhook payload without HTTP context.

        Callable from fixture-based replay (``pc ingest --from-fixture``) and from the
        HTTP handler's ``process`` wrapper. ``payload_sha256`` is used for idempotent
        dedupe against ``webhook_receipts``; when omitted it is derived from a canonical
        JSON serialization of ``payload``.
        """
        if payload_sha256 is None:
            payload_sha256 = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        # Atomic dedupe: attempt insert and skip if the (provider, payload_sha256)
        # unique constraint already exists. This keeps webhook replay handling safe
        # on both local SQLite and production Postgres.
        insert_fn = self._insert_for_current_dialect()
        stmt = (
            insert_fn(WebhookReceipt)
            .values(
                webhook_receipt_id=generate_prefixed_id("whr"),
                provider="firecrawl",
                payload_sha256=payload_sha256,
                signature=signature,
                payload=payload,
                received_at=datetime.now(UTC),
                processed_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(
                index_elements=["provider", "payload_sha256"],
            )
        )
        result = await self.session.execute(stmt)

        # If no row was inserted the webhook was already processed — skip.
        if result.rowcount == 0:
            return

        # Mirror the payload to disk when a record directory is configured, so
        # a production crawl is replayable offline via ``pc ingest --from-fixture``.
        # Best-effort: record failures never break the ingest path.
        self._record_payload_to_disk(payload)

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

    def _record_payload_to_disk(self, payload: dict[str, Any]) -> None:
        if self.webhook_record_dir is None:
            return
        try:
            external_job_id = str(payload.get("id") or "unknown")
            event_type = str(payload.get("type") or "unknown").replace(".", "_")
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            target_dir = self.webhook_record_dir / external_job_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{timestamp}_{event_type}.json"
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            # Recording is an operator convenience; swallow disk errors so they
            # never surface as a failed webhook back to Firecrawl.
            return

    def _insert_for_current_dialect(self):
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as insert_fn

            return insert_fn

        from sqlalchemy.dialects.sqlite import insert as insert_fn

        return insert_fn

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
            merge_run_replay_checkpoint(
                run,
                last_firecrawl_event_type=event_type,
            )
            return

        if event_type == "crawl.page":
            pages = payload.get("data", [])
            if isinstance(pages, dict):
                pages = [pages]
            for page in pages:
                if not isinstance(page, dict):
                    # Ignore malformed page entries so one bad payload item
                    # does not fail processing for the entire webhook.
                    continue
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
            merge_run_replay_checkpoint(
                run,
                last_firecrawl_event_type=event_type,
                pages_ingested=run.captured_resources_count,
            )
            return

        if event_type == "crawl.completed":
            provider_job.status = ProviderJobStatus.COMPLETED
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            merge_run_replay_checkpoint(
                run,
                last_firecrawl_event_type=event_type,
                pages_ingested=run.captured_resources_count,
            )
            await self._publish_bundle_manifest(run)
            return

        if event_type == "crawl.failed":
            provider_job.status = ProviderJobStatus.FAILED
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            run.failure_reason = str(payload.get("error") or "Firecrawl job failed.")
            merge_run_replay_checkpoint(
                run,
                last_firecrawl_event_type=event_type,
                pages_ingested=run.captured_resources_count,
                extra={"terminal": True},
            )

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

    async def _publish_bundle_manifest(self, run: Run) -> None:
        artifacts = list(
            await self.session.scalars(
                select(RawArtifact)
                .where(RawArtifact.run_id == run.run_id)
                .order_by(RawArtifact.created_at.asc())
            )
        )
        if not artifacts:
            return

        source = await self.session.get(Source, run.source_id)
        source_version = await self.session.get(SourceVersion, run.source_version_id)
        if source is None or source_version is None:
            return

        source_snapshot_id = generate_prefixed_id("snap")
        bundle_manifest_id = generate_prefixed_id("abm")
        upstream_locator = self._upstream_locator(artifacts[0].artifact_metadata)

        manifest_artifacts: list[dict[str, Any]] = []
        for index, artifact in enumerate(artifacts):
            if artifact.content_type.startswith("application/json"):
                role = "metadata"
            elif index == 0:
                role = "primary_document"
            else:
                role = "attachment"
            manifest_artifacts.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_role": role,
                    "storage_ref": self._build_storage_ref_for_artifact(artifact),
                }
            )

        acquisition_spec = source_version.acquisition_spec or {}
        tenant_id = str(acquisition_spec.get("tenant_id") or "tenant_public")
        corpus_id = str(acquisition_spec.get("corpus_id") or f"corpus_{source.jurisdiction_id}")
        scope_type = str(acquisition_spec.get("scope_type") or "global_public")
        source_origin_kind = str(acquisition_spec.get("source_origin_kind") or "official_primary")
        trust_tier = str(acquisition_spec.get("trust_tier") or "authoritative")
        authority_name = await self._resolve_authority_name(source.authority_id)
        attribution = await self._resolve_attribution(source.jurisdiction_id)

        manifest = build_artifact_bundle_manifest(
            bundle_manifest_id=bundle_manifest_id,
            source_snapshot_id=source_snapshot_id,
            source_id=source.source_id,
            source_version_id=source_version.source_version_id,
            run_id=run.run_id,
            jurisdiction_id=source.jurisdiction_id,
            authority_id=source.authority_id,
            authority_name=authority_name,
            upstream_locator=upstream_locator,
            artifacts=manifest_artifacts,
            tenant_id=tenant_id,
            corpus_id=corpus_id,
            scope_type=scope_type,
            source_origin_kind=source_origin_kind,
            trust_tier=trust_tier,
            language_codes=acquisition_spec.get("language_codes") or [],
            document_type_hint=acquisition_spec.get("document_type_hint"),
            bundle_metadata={
                "extraction_hints": build_bundle_extraction_hints(
                    artifact_metadata=artifacts[0].artifact_metadata,
                    document_type_hint=acquisition_spec.get("document_type_hint"),
                    authority_display_hint=authority_name,
                ),
            },
            attribution=attribution,
            snapshot_captured_at=run.completed_at or datetime.now(UTC),
        )
        reference_snapshot_set = self._build_reference_snapshot_set(
            source=source,
            source_version=source_version,
            run=run,
            manifest_provenance=manifest["provenance"],
        )
        reference_snapshot_set_id = str(reference_snapshot_set["reference_snapshot_set_id"])
        reference_snapshot_storage_ref = await self.artifact_store.store_bundle_manifest(
            run_id=run.run_id,
            bundle_manifest_id=reference_snapshot_set_id,
            payload=reference_snapshot_set,
        )
        manifest.setdefault("bundle_metadata", {})
        manifest["bundle_metadata"]["reference_snapshot_export"] = {
            "reference_snapshot_set_id": reference_snapshot_set_id,
            "storage_ref": reference_snapshot_storage_ref,
        }
        manifest_storage_ref = await self.artifact_store.store_bundle_manifest(
            run_id=run.run_id,
            bundle_manifest_id=bundle_manifest_id,
            payload=manifest,
        )
        manifest_ref = {
            "manifest_id": bundle_manifest_id,
            "manifest_type": "artifact_bundle_manifest",
            "manifest_version": 1,
            "storage_ref": manifest_storage_ref,
        }
        event = build_artifact_bundle_available_event(
            bundle_manifest_id=bundle_manifest_id,
            source_snapshot_id=source_snapshot_id,
            source_origin_kind=source_origin_kind,
            trust_tier=trust_tier,
            provenance=manifest["provenance"],
            bundle_manifest_ref=manifest_ref,
            correlation_id=run.run_id,
            occurred_at=run.completed_at or datetime.now(UTC),
        )
        await self.publisher.publish_artifact_bundle_available(event)

    @staticmethod
    def _upstream_locator(artifact_metadata: dict[str, Any]) -> str:
        metadata = artifact_metadata.get("metadata", {})
        return str(
            artifact_metadata.get("url")
            or metadata.get("sourceURL")
            or metadata.get("url")
            or "https://unknown.local/resource"
        )

    async def _resolve_authority_name(self, authority_id: str | None) -> str | None:
        if not authority_id:
            return None
        authority = await self.session.get(Authority, authority_id)
        return authority.name if authority is not None else None

    async def _resolve_attribution(
        self, jurisdiction_id: str | None
    ) -> dict[str, Any] | None:
        """Return the attribution block for the manifest when the jurisdiction
        requires it. Absent policy or ``attribution_required=False`` -> ``None``.
        """
        if not jurisdiction_id:
            return None
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None or jurisdiction.compliance_policy_id is None:
            return None
        policy = await self.session.get(CompliancePolicy, jurisdiction.compliance_policy_id)
        if policy is None or not policy.attribution_required:
            return None
        return {
            "required": True,
            "text": policy.attribution_text,
            "contact_url": policy.contact_url,
        }

    @staticmethod
    def _build_storage_ref_for_artifact(artifact: RawArtifact) -> dict[str, Any]:
        uri = artifact.storage_path
        byte_size = int(artifact.artifact_metadata.get("byte_size") or 0)
        checksum = str(artifact.artifact_metadata.get("checksum") or "")
        checksum_algorithm = str(artifact.artifact_metadata.get("checksum_algorithm") or "sha256")

        if "://" not in uri:
            file_path = Path(uri).resolve()
            uri = f"file://{file_path}"
            if file_path.exists():
                hasher = hashlib.sha256()
                byte_size = 0
                with file_path.open("rb") as handle:
                    while chunk := handle.read(65536):
                        byte_size += len(chunk)
                        hasher.update(chunk)
                checksum = hasher.hexdigest()
                checksum_algorithm = "sha256"

        if not checksum:
            checksum = hashlib.sha256(uri.encode("utf-8")).hexdigest()
            checksum_algorithm = "uri-hash"

        return {
            "uri": uri,
            "content_type": artifact.content_type,
            "byte_size": byte_size,
            "checksum": checksum,
            "checksum_algorithm": checksum_algorithm,
            "created_at": artifact.created_at.isoformat(),
        }

    @staticmethod
    def _build_reference_snapshot_set(
        *,
        source: Source,
        source_version: SourceVersion,
        run: Run,
        manifest_provenance: dict[str, Any],
    ) -> dict[str, Any]:
        acquisition_spec = source_version.acquisition_spec or {}
        return {
            "reference_snapshot_set_id": generate_prefixed_id("rss"),
            "generated_at": (run.completed_at or datetime.now(UTC)).isoformat(),
            "provenance": {
                "run_id": run.run_id,
                "source_id": source.source_id,
                "source_version_id": source_version.source_version_id,
                "tenant_id": manifest_provenance.get("tenant_id"),
                "corpus_id": manifest_provenance.get("corpus_id"),
                "scope_type": manifest_provenance.get("scope_type"),
            },
            "jurisdictions": [{"jurisdiction_id": source.jurisdiction_id}],
            "authorities": ([{"authority_id": source.authority_id}] if source.authority_id else []),
            "extractor_profile_hint": acquisition_spec.get("extractor_profile_hint"),
            "language_codes": acquisition_spec.get("language_codes") or [],
            "document_type_hint": acquisition_spec.get("document_type_hint"),
        }
