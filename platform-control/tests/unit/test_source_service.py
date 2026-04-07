from __future__ import annotations

import pytest

from platform_control.domain import SourceVersionStatus
from platform_control.errors import InvalidStateTransitionError, NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.source import (
    CreateSourceRequest,
    SourceBlueprintPreviewRequest,
    CreateSourceWithVersionRequest,
    CreateSourceVersionRequest,
    FirecrawlAcquisitionSpec,
    UpdateSourceVersionRequest,
)
from platform_control.services.source_service import SourceService


@pytest.mark.asyncio
async def test_create_source_requires_existing_reference_data(session) -> None:
    service = SourceService(session)

    with pytest.raises(NotFoundError):
        await service.create_source(
            CreateSourceRequest(
                name="Test source",
                jurisdiction_id="jur_missing",
                authority_id="auth_missing",
            )
        )


@pytest.mark.asyncio
async def test_approve_source_version_from_draft(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="2026-03 initial",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )

    approved = await service.approve_source_version(version.source_version_id)

    assert approved.status is SourceVersionStatus.APPROVED


@pytest.mark.asyncio
async def test_create_source_version_persists_scope_and_handoff_metadata(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )

    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="2026-04 scope metadata",
            acquisition_spec=FirecrawlAcquisitionSpec(
                seed_url="https://example.com/decisions",
                tenant_id="tenant_public",
                corpus_id="corpus_public_ch_admin_decisions",
                scope_type="global_public",
                source_origin_kind="official_primary",
                trust_tier="authoritative",
                language_codes=["de", "fr"],
                document_type_hint="decision",
            ),
        ),
    )

    assert version.acquisition_spec["tenant_id"] == "tenant_public"
    assert version.acquisition_spec["corpus_id"] == "corpus_public_ch_admin_decisions"
    assert version.acquisition_spec["scope_type"] == "global_public"
    assert version.acquisition_spec["source_origin_kind"] == "official_primary"
    assert version.acquisition_spec["trust_tier"] == "authoritative"
    assert version.acquisition_spec["language_codes"] == ["de", "fr"]
    assert version.acquisition_spec["document_type_hint"] == "decision"


@pytest.mark.asyncio
async def test_reject_source_version_from_draft(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="2026-03 initial",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )

    rejected = await service.reject_source_version(version.source_version_id)

    assert rejected.status is SourceVersionStatus.REJECTED


@pytest.mark.asyncio
async def test_cannot_approve_source_version_twice(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="2026-03 initial",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )
    await service.approve_source_version(version.source_version_id)

    with pytest.raises(InvalidStateTransitionError):
        await service.approve_source_version(version.source_version_id)


@pytest.mark.asyncio
async def test_update_source_version_allows_editing_rejected_draft_content(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="draft-v1",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )
    await service.reject_source_version(version.source_version_id)

    updated = await service.update_source_version(
        version.source_version_id,
        UpdateSourceVersionRequest(
            version_label="draft-v2",
            acquisition_spec=FirecrawlAcquisitionSpec(
                seed_url="https://example.com/cases",
                limit=12,
            ),
        ),
    )

    assert updated.version_label == "draft-v2"
    assert updated.acquisition_spec["seed_url"] == "https://example.com/cases"
    assert updated.acquisition_spec["limit"] == 12


@pytest.mark.asyncio
async def test_update_source_version_rejects_approved_version(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="Zurich decisions",
            jurisdiction_id="jur_ch",
            authority_id="auth_zh_admin",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="draft-v1",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/decisions"),
        ),
    )
    await service.approve_source_version(version.source_version_id)

    with pytest.raises(InvalidStateTransitionError):
        await service.update_source_version(
            version.source_version_id,
            UpdateSourceVersionRequest(version_label="draft-v2"),
        )


@pytest.mark.asyncio
async def test_create_source_version_from_overlay_blueprint(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_at", name="Austria", slug="at"))
    session.add(
        Authority(
            authority_id="auth_at_ris",
            jurisdiction_id="jur_at",
            name="RIS",
            slug="ris",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="AT RIS decisions",
            jurisdiction_id="jur_at",
            authority_id="auth_at_ris",
        )
    )

    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="at-template-v1",
            overlay_id="at",
            provider_template_id="ris_ogd_bundesrecht",
        ),
    )

    assert version.acquisition_spec["provider"] == "ris_ogd"
    assert version.acquisition_spec["base_url"] == "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"


@pytest.mark.asyncio
async def test_update_source_version_can_apply_overlay_blueprint(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_de", name="Germany", slug="de"))
    session.add(
        Authority(
            authority_id="auth_de_bund",
            jurisdiction_id="jur_de",
            name="Bund",
            slug="bund",
        )
    )
    await session.commit()

    service = SourceService(session)
    source = await service.create_source(
        CreateSourceRequest(
            name="DE laws",
            jurisdiction_id="jur_de",
            authority_id="auth_de_bund",
        )
    )
    version = await service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="de-manual-v1",
            acquisition_spec=FirecrawlAcquisitionSpec(seed_url="https://example.com/de"),
        ),
    )

    updated = await service.update_source_version(
        version.source_version_id,
        UpdateSourceVersionRequest(
            overlay_id="de",
            provider_template_id="deterministic_http_bundesrecht",
        ),
    )

    assert updated.acquisition_spec["provider"] == "deterministic_http"
    assert updated.acquisition_spec["seed_urls"] == ["https://www.gesetze-im-internet.de/"]


@pytest.mark.asyncio
async def test_create_source_with_initial_version_from_blueprint(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_at", name="Austria", slug="at"))
    session.add(
        Authority(
            authority_id="auth_at_ris",
            jurisdiction_id="jur_at",
            name="RIS",
            slug="ris",
        )
    )
    await session.commit()

    service = SourceService(session)
    source, version = await service.create_source_with_initial_version(
        CreateSourceWithVersionRequest(
            source=CreateSourceRequest(
                name="AT Source + Version",
                jurisdiction_id="jur_at",
                authority_id="auth_at_ris",
                source_type="api",
            ),
            source_version=CreateSourceVersionRequest(
                version_label="v1",
                overlay_id="at",
                provider_template_id="ris_ogd_bundesrecht",
            ),
        )
    )

    assert source.name == "AT Source + Version"
    assert version.source_id == source.source_id
    assert version.version_label == "v1"
    assert version.acquisition_spec["provider"] == "ris_ogd"


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_expanded_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="de",
            provider_template_id="deterministic_http_bundesrecht",
        )
    )

    assert spec.provider == "deterministic_http"
