from __future__ import annotations

import pytest

from platform_control.errors import NotFoundError
from platform_control.schemas.reference_data import (
    CreateAuthorityRequest,
    CreateJurisdictionRequest,
    UpdateAuthorityRequest,
)
from platform_control.services.reference_data_service import ReferenceDataService


@pytest.mark.asyncio
async def test_create_and_list_reference_data(session) -> None:
    service = ReferenceDataService(session)

    jurisdiction = await service.create_jurisdiction(
        CreateJurisdictionRequest(name="Switzerland", slug="ch")
    )
    authority = await service.create_authority(
        CreateAuthorityRequest(
            jurisdiction_id=jurisdiction.jurisdiction_id,
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )

    jurisdictions = await service.list_jurisdictions()
    authorities = await service.list_authorities()

    assert [item.jurisdiction_id for item in jurisdictions] == [jurisdiction.jurisdiction_id]
    assert [item.authority_id for item in authorities] == [authority.authority_id]


@pytest.mark.asyncio
async def test_update_authority_requires_existing_jurisdiction(session) -> None:
    service = ReferenceDataService(session)
    authority = await service.create_authority(
        CreateAuthorityRequest(name="Federal Supreme Court", slug="federal-supreme-court")
    )

    with pytest.raises(NotFoundError):
        await service.update_authority(
            authority.authority_id,
            UpdateAuthorityRequest(jurisdiction_id="jur_missing"),
        )
