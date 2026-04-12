from __future__ import annotations

import pytest

from platform_control.errors import ConflictError, NotFoundError
from platform_control.schemas.corpus import CreateCorpusRequest, UpdateCorpusRequest
from platform_control.services.corpus_service import CorpusService


@pytest.mark.asyncio
async def test_create_corpus_and_get(session) -> None:
    service = CorpusService(session)
    corpus = await service.create_corpus(
        CreateCorpusRequest(
            name="Swiss Public Law",
            tenant_id="tenant_public",
            scope_type="global_public",
        )
    )
    assert corpus.corpus_id.startswith("cps_")
    assert corpus.name == "Swiss Public Law"
    assert corpus.tenant_id == "tenant_public"
    assert corpus.scope_type == "global_public"
    assert corpus.status == "active"

    fetched = await service.get_corpus(corpus.corpus_id)
    assert fetched.corpus_id == corpus.corpus_id


@pytest.mark.asyncio
async def test_create_corpus_duplicate_name_raises_conflict(session) -> None:
    service = CorpusService(session)
    req = CreateCorpusRequest(name="Dupe Corpus", tenant_id="tenant_public")
    await service.create_corpus(req)
    with pytest.raises(ConflictError):
        await service.create_corpus(req)


@pytest.mark.asyncio
async def test_get_corpus_not_found_raises(session) -> None:
    service = CorpusService(session)
    with pytest.raises(NotFoundError):
        await service.get_corpus("cps_nonexistent")


@pytest.mark.asyncio
async def test_list_corpora_filters_by_tenant(session) -> None:
    service = CorpusService(session)
    await service.create_corpus(
        CreateCorpusRequest(name="AT Corpus", tenant_id="tenant_at", scope_type="tenant_private")
    )
    await service.create_corpus(
        CreateCorpusRequest(name="DE Corpus", tenant_id="tenant_de", scope_type="tenant_private")
    )

    at_items, at_total = await service.list_corpora(tenant_id="tenant_at")
    assert at_total == 1
    assert at_items[0].name == "AT Corpus"

    all_items, all_total = await service.list_corpora()
    assert all_total == 2  # noqa: PLR2004


@pytest.mark.asyncio
async def test_update_corpus(session) -> None:
    service = CorpusService(session)
    corpus = await service.create_corpus(
        CreateCorpusRequest(name="Original Name", tenant_id="tenant_public")
    )
    updated = await service.update_corpus(
        corpus.corpus_id,
        UpdateCorpusRequest(name="Updated Name", scope_type="tenant_shared"),
    )
    assert updated.name == "Updated Name"
    assert updated.scope_type == "tenant_shared"


@pytest.mark.asyncio
async def test_archive_corpus_is_idempotent(session) -> None:
    service = CorpusService(session)
    corpus = await service.create_corpus(
        CreateCorpusRequest(name="To Archive", tenant_id="tenant_public")
    )
    archived = await service.archive_corpus(corpus.corpus_id)
    assert archived.status == "archived"

    # Second archive call should be idempotent.
    archived_again = await service.archive_corpus(corpus.corpus_id)
    assert archived_again.status == "archived"


@pytest.mark.asyncio
async def test_update_archived_corpus_raises_conflict(session) -> None:
    service = CorpusService(session)
    corpus = await service.create_corpus(
        CreateCorpusRequest(name="Archived One", tenant_id="tenant_public")
    )
    await service.archive_corpus(corpus.corpus_id)
    with pytest.raises(ConflictError):
        await service.update_corpus(corpus.corpus_id, UpdateCorpusRequest(name="New Name"))


@pytest.mark.asyncio
async def test_list_corpora_excludes_archived_by_default(session) -> None:
    service = CorpusService(session)
    corpus = await service.create_corpus(
        CreateCorpusRequest(name="Will Be Archived", tenant_id="tenant_public")
    )
    await service.archive_corpus(corpus.corpus_id)

    active_items, active_total = await service.list_corpora()
    assert active_total == 0

    all_items, all_total = await service.list_corpora(include_archived=True)
    assert all_total == 1
