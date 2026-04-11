from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.corpus import (
    CorpusListResponse,
    CorpusResponse,
    CreateCorpusRequest,
    UpdateCorpusRequest,
)
from platform_control.services.corpus_service import CorpusService

router = APIRouter(prefix="/v1/corpora", tags=["corpora"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=CorpusListResponse)
async def list_corpora(
    session: SessionDep,
    tenant_id: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CorpusListResponse:
    service = CorpusService(session)
    items, total = await service.list_corpora(
        tenant_id=tenant_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return CorpusListResponse(
        data=[CorpusResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CorpusResponse, status_code=status.HTTP_201_CREATED)
async def create_corpus(
    request: CreateCorpusRequest,
    session: SessionDep,
) -> CorpusResponse:
    service = CorpusService(session)
    corpus = await service.create_corpus(request)
    return CorpusResponse.model_validate(corpus)


@router.get("/{corpus_id}", response_model=CorpusResponse)
async def get_corpus(
    corpus_id: str,
    session: SessionDep,
) -> CorpusResponse:
    service = CorpusService(session)
    corpus = await service.get_corpus(corpus_id)
    return CorpusResponse.model_validate(corpus)


@router.patch("/{corpus_id}", response_model=CorpusResponse)
async def update_corpus(
    corpus_id: str,
    request: UpdateCorpusRequest,
    session: SessionDep,
) -> CorpusResponse:
    service = CorpusService(session)
    corpus = await service.update_corpus(corpus_id, request)
    return CorpusResponse.model_validate(corpus)


@router.post("/{corpus_id}/archive", response_model=CorpusResponse)
async def archive_corpus(
    corpus_id: str,
    session: SessionDep,
) -> CorpusResponse:
    service = CorpusService(session)
    corpus = await service.archive_corpus(corpus_id)
    return CorpusResponse.model_validate(corpus)
