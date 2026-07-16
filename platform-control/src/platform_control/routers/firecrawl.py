from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.events.publisher import RawArtifactPublisher
from platform_control.integrations import get_artifact_store, get_raw_artifact_publisher
from platform_control.schemas.run import WebhookAcceptedResponse
from platform_control.services.artifact_store import ArtifactStore
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService

router = APIRouter(prefix="/v1/firecrawl", tags=["firecrawl"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ArtifactStoreDep = Annotated[ArtifactStore, Depends(get_artifact_store)]
PublisherDep = Annotated[RawArtifactPublisher, Depends(get_raw_artifact_publisher)]


@router.post("/webhooks", response_model=WebhookAcceptedResponse)
async def receive_firecrawl_webhook(
    request: Request,
    session: SessionDep,
    artifact_store: ArtifactStoreDep,
    publisher: PublisherDep,
    signature: str | None = Header(default=None, alias="X-Firecrawl-Signature"),
) -> WebhookAcceptedResponse:
    """Accept a Firecrawl crawl webhook.

    `type` is one of `crawl.started`, `crawl.page`, `crawl.completed`, `crawl.failed`.
    The body is Firecrawl's payload, taken verbatim: the handler reads the raw bytes
    because `X-Firecrawl-Signature` is an HMAC over exactly those bytes. It is
    therefore not a typed request model, and this contract does not describe it — the
    shape is Firecrawl's to define, not ours.
    """
    raw_body = await request.body()
    payload = await request.json()
    settings = get_settings()
    service = FirecrawlWebhookService(
        session=session,
        artifact_store=artifact_store,
        publisher=publisher,
        webhook_secret=settings.firecrawl_webhook_secret,
        webhook_record_dir=settings.firecrawl_webhook_record_dir,
    )
    await service.process(payload=payload, raw_body=raw_body, signature=signature)
    return WebhookAcceptedResponse(status="accepted")
