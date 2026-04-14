from __future__ import annotations

import pytest

from platform_control.domain import SourceVersionStatus
from platform_control.errors import InvalidStateTransitionError, NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    CreateSourceWithVersionRequest,
    FirecrawlAcquisitionSpec,
    SourceBlueprintPreviewRequest,
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


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_ris_ogd_narrow_html_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="at",
            provider_template_id="ris_ogd_bundesrecht_narrow_html",
        )
    )

    assert spec.provider == "ris_ogd"
    assert str(spec.base_url) == "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
    assert spec.applikation == "BrKons"
    assert spec.preferred_formats == ["Html", "Xml"]
    assert spec.page_size == 1
    assert spec.max_pages == 1
    assert spec.document_type_hint == "legislation"


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_ris_ogd_small_batch_html_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="at",
            provider_template_id="ris_ogd_bundesrecht_small_batch_html",
        )
    )

    assert spec.provider == "ris_ogd"
    assert str(spec.base_url) == "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
    assert spec.applikation == "BrKons"
    assert spec.preferred_formats == ["Html", "Xml"]
    assert spec.page_size == 5
    assert spec.max_pages == 1
    assert spec.document_type_hint == "legislation"


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_fedlex_sparql_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="ch",
            provider_template_id="fedlex_sparql_constitution_de",
        )
    )

    assert spec.provider == "fedlex_sparql"
    assert str(spec.seed_url) == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    assert str(spec.sparql_endpoint) == "https://fedlex.data.admin.ch/sparqlendpoint"
    assert spec.preferred_languages == ["de"]
    assert spec.document_type_hint == "legislation"


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_fedlex_sparql_vwvg_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="ch",
            provider_template_id="fedlex_sparql_vwvg_de",
        )
    )

    assert spec.provider == "fedlex_sparql"
    assert str(spec.seed_url) == "https://fedlex.data.admin.ch/eli/cc/1969/737_757_755"
    assert str(spec.sparql_endpoint) == "https://fedlex.data.admin.ch/sparqlendpoint"
    assert spec.preferred_languages == ["de"]
    assert spec.document_type_hint == "legislation"


@pytest.mark.asyncio
async def test_preview_source_blueprint_returns_fedlex_sparql_small_batch_spec(session) -> None:
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="ch",
            provider_template_id="fedlex_sparql_federal_law_batch_de",
        )
    )

    assert spec.provider == "fedlex_sparql"
    assert [str(url) for url in spec.seed_urls] == [
        "https://fedlex.data.admin.ch/eli/cc/1999/404",
        "https://fedlex.data.admin.ch/eli/cc/1969/737_757_755",
    ]
    assert str(spec.sparql_endpoint) == "https://fedlex.data.admin.ch/sparqlendpoint"
    assert spec.preferred_languages == ["de"]
    assert spec.document_type_hint == "legislation"


@pytest.mark.asyncio
async def test_create_source_with_initial_version_from_fedlex_sparql_blueprint(
    session,
) -> None:
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch_federal",
            name="Switzerland Federal",
            slug="ch-federal",
        )
    )
    session.add(
        Authority(
            authority_id="auth_fedlex",
            jurisdiction_id="jur_ch_federal",
            name="Fedlex",
            slug="fedlex",
        )
    )
    await session.commit()

    service = SourceService(session)
    source, version = await service.create_source_with_initial_version(
        CreateSourceWithVersionRequest(
            source=CreateSourceRequest(
                name="CH Fedlex legislation thin slice",
                jurisdiction_id="jur_ch_federal",
                authority_id="auth_fedlex",
                source_type="website",
            ),
            source_version=CreateSourceVersionRequest(
                version_label="ch-fedlex-v1",
                overlay_id="ch",
                provider_template_id="fedlex_sparql_constitution_de",
            ),
        )
    )

    assert source.jurisdiction_id == "jur_ch_federal"
    assert version.version_label == "ch-fedlex-v1"
    assert version.acquisition_spec["provider"] == "fedlex_sparql"
    assert version.acquisition_spec["seed_url"] == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    assert (
        version.acquisition_spec["sparql_endpoint"] == "https://fedlex.data.admin.ch/sparqlendpoint"
    )
