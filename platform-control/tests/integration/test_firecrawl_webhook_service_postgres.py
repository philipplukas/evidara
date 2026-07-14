from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.core.exceptions import ContainerStartException
from testcontainers.postgres import PostgresContainer

from platform_control import models as _models  # noqa: F401
from platform_control.domain import ProviderJobStatus, RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import WebhookRetryableError
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.base import Base
from platform_control.models.provider_job import ProviderJob
from platform_control.models.raw_artifact import RawArtifact
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.models.webhook_receipt import WebhookReceipt
from platform_control.services.artifact_store import LocalArtifactStore
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService


class CollectingPublisher(RawArtifactPublisher):
    async def publish_raw_artifact_available(self, artifact: RawArtifact) -> None:
        del artifact

    async def publish_artifact_bundle_available(self, event: dict[str, object]) -> None:
        del event


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def postgres_session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    try:
        with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
            engine = create_async_engine(_to_asyncpg_url(postgres.get_connection_url()))
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            yield async_sessionmaker(engine, expire_on_commit=False)

            await engine.dispose()
    except (ContainerStartException, OSError) as exc:
        pytest.skip(f"Docker-backed Postgres is unavailable: {exc}")


async def _seed_run_graph(session: AsyncSession, *, with_provider_job: bool) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    await session.commit()

    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    session.add(
        Source(
            source_id="src_seed",
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    await session.commit()

    session.add(
        SourceVersion(
            source_version_id="sv_seed",
            source_id="src_seed",
            version_label="v1",
            status=SourceVersionStatus.APPROVED,
            acquisition_spec={"seed_url": "https://example.com/decisions", "mode": "crawl"},
        )
    )
    await session.commit()

    session.add(
        Run(
            run_id="run_seed",
            source_id="src_seed",
            source_version_id="sv_seed",
            mode=RunMode.PREVIEW,
            status=RunStatus.RUNNING,
        )
    )
    await session.commit()

    if with_provider_job:
        await _seed_provider_job(session)


async def _seed_provider_job(session: AsyncSession) -> None:
    session.add(
        ProviderJob(
            provider_job_id="pjob_seed",
            run_id="run_seed",
            external_job_id="crawl_123",
            status=ProviderJobStatus.RUNNING,
            request_payload={},
            response_payload={},
        )
    )
    await session.commit()


def _crawl_page_payload() -> tuple[dict[str, object], bytes, str]:
    payload: dict[str, object] = {
        "type": "crawl.page",
        "id": "crawl_123",
        "data": {
            "url": "https://example.com/decisions/1",
            "metadata": {
                "title": "Decision 1",
                "sourceURL": "https://example.com/decisions/1",
                "contentType": "text/html",
                "statusCode": 200,
                "depth": 1,
            },
        },
    }
    raw_body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = "sha256=" + hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
    return payload, raw_body, signature


@pytest.mark.asyncio
async def test_webhook_dedupe_works_on_postgres(
    postgres_session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with postgres_session_maker() as session:
        await _seed_run_graph(session, with_provider_job=True)
        payload, raw_body, signature = _crawl_page_payload()

        service = FirecrawlWebhookService(
            session=session,
            artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
            publisher=CollectingPublisher(),
            webhook_secret="test-secret",
        )

        await service.process(payload=payload, raw_body=raw_body, signature=signature)
        await service.process(payload=payload, raw_body=raw_body, signature=signature)

        receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
        artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))

        assert receipt_count == 1
        assert artifact_count == 1


@pytest.mark.asyncio
async def test_unapplied_webhook_is_reclaimable_on_postgres(
    postgres_session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """#558 on the real dialect: the dedupe key must survive a delivery we could not apply.

    The reclaim depends on Postgres' `ON CONFLICT ... DO UPDATE ... WHERE processed_at IS
    NULL` semantics (the predicate reads the *existing* row), which SQLite cannot prove.
    """
    async with postgres_session_maker() as session:
        await _seed_run_graph(session, with_provider_job=False)
        payload, raw_body, signature = _crawl_page_payload()

        service = FirecrawlWebhookService(
            session=session,
            artifact_store=LocalArtifactStore(base_dir=tmp_path / "artifacts"),
            publisher=CollectingPublisher(),
            webhook_secret="test-secret",
        )

        # The page beats the ProviderJob commit: refused, but kept reclaimable.
        with pytest.raises(WebhookRetryableError):
            await service.process(payload=payload, raw_body=raw_body, signature=signature)

        receipt = await session.scalar(select(WebhookReceipt))
        assert receipt is not None
        assert receipt.processed_at is None
        assert await session.scalar(select(func.count()).select_from(RawArtifact)) == 0

        # The dispatch transaction lands and Firecrawl redelivers the identical payload.
        await _seed_provider_job(session)
        await service.process(payload=payload, raw_body=raw_body, signature=signature)

        await session.refresh(receipt)
        receipt_count = await session.scalar(select(func.count()).select_from(WebhookReceipt))
        artifact_count = await session.scalar(select(func.count()).select_from(RawArtifact))

        assert receipt.processed_at is not None
        assert receipt_count == 1
        assert artifact_count == 1, "the redelivered page must be captured, not deduped away"
