from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import ConflictError, NotFoundError
from platform_control.models.corpus import Corpus
from platform_control.schemas.corpus import (
    CreateCorpusRequest,
    UpdateCorpusRequest,
)


class CorpusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_corpus(self, request: CreateCorpusRequest) -> Corpus:
        # Enforce unique (tenant_id, name) to avoid duplicate corpora.
        existing = await self.session.scalar(
            select(Corpus).where(
                Corpus.tenant_id == request.tenant_id,
                Corpus.name == request.name,
                Corpus.status == "active",
            )
        )
        if existing is not None:
            raise ConflictError(
                f"Active corpus named '{request.name}' already exists "
                f"for tenant '{request.tenant_id}'."
            )

        corpus = Corpus(
            name=request.name,
            description=request.description,
            tenant_id=request.tenant_id,
            scope_type=request.scope_type,
            status="active",
        )
        self.session.add(corpus)
        await self.session.commit()
        await self.session.refresh(corpus)
        return corpus

    async def get_corpus(self, corpus_id: str) -> Corpus:
        corpus = await self.session.get(Corpus, corpus_id)
        if corpus is None:
            raise NotFoundError(f"Corpus not found: {corpus_id}")
        return corpus

    async def list_corpora(
        self,
        *,
        tenant_id: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Corpus], int]:
        q = select(Corpus)
        count_q = select(func.count()).select_from(Corpus)
        if tenant_id is not None:
            q = q.where(Corpus.tenant_id == tenant_id)
            count_q = count_q.where(Corpus.tenant_id == tenant_id)
        if not include_archived:
            q = q.where(Corpus.status == "active")
            count_q = count_q.where(Corpus.status == "active")
        total: int = await self.session.scalar(count_q) or 0  # type: ignore[assignment]
        items = list(await self.session.scalars(q.offset(offset).limit(limit)))
        return items, total

    async def update_corpus(self, corpus_id: str, request: UpdateCorpusRequest) -> Corpus:
        corpus = await self.get_corpus(corpus_id)
        if corpus.status == "archived":
            raise ConflictError(f"Cannot update archived corpus: {corpus_id}")
        if request.name is not None:
            corpus.name = request.name
        if request.description is not None:
            corpus.description = request.description
        if request.scope_type is not None:
            corpus.scope_type = request.scope_type
        await self.session.commit()
        await self.session.refresh(corpus)
        return corpus

    async def archive_corpus(self, corpus_id: str) -> Corpus:
        corpus = await self.get_corpus(corpus_id)
        if corpus.status == "archived":
            return corpus  # Idempotent
        corpus.status = "archived"
        await self.session.commit()
        await self.session.refresh(corpus)
        return corpus
