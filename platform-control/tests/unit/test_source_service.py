from __future__ import annotations

import pytest

from platform_control.domain import SourceVersionStatus
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    FirecrawlAcquisitionSpec,
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
