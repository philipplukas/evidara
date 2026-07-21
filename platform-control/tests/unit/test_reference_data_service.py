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

    jurisdictions, jurisdiction_total = await service.list_jurisdictions()
    authorities, authority_total = await service.list_authorities()

    assert [item.jurisdiction_id for item in jurisdictions] == [jurisdiction.jurisdiction_id]
    assert [item.authority_id for item in authorities] == [authority.authority_id]
    assert jurisdiction_total == 1
    assert authority_total == 1


@pytest.mark.asyncio
async def test_list_reference_data_pages_and_reports_the_full_total(session) -> None:
    """#616 — ``total`` is the hit count, not the page length.

    The admin reads ``total`` to size its pager. If it were the page length,
    every list would report exactly one page and the records past it would be
    unreachable — which is the bug, over 2,169 seeded jurisdictions.
    """
    service = ReferenceDataService(session)
    for index in range(5):
        await service.create_jurisdiction(
            CreateJurisdictionRequest(name=f"Jurisdiction {index}", slug=f"jur-{index}")
        )

    page, total = await service.list_jurisdictions(limit=2, offset=2)

    assert total == 5
    assert len(page) == 2
    # Ordered by name ascending, so offset=2 is the third entry.
    assert [item.name for item in page] == ["Jurisdiction 2", "Jurisdiction 3"]


@pytest.mark.asyncio
async def test_list_reference_data_filters_by_q(session) -> None:
    service = ReferenceDataService(session)
    await service.create_jurisdiction(CreateJurisdictionRequest(name="Zurich", slug="zh"))
    await service.create_jurisdiction(CreateJurisdictionRequest(name="Bern", slug="be"))

    page, total = await service.list_jurisdictions(q="uri")

    assert total == 1
    assert [item.name for item in page] == ["Zurich"]


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


@pytest.mark.asyncio
async def test_create_authority_requires_existing_jurisdiction(session) -> None:
    service = ReferenceDataService(session)

    with pytest.raises(NotFoundError):
        await service.create_authority(
            CreateAuthorityRequest(
                jurisdiction_id="jur_missing",
                name="Ghost Authority",
                slug="ghost-authority",
            )
        )
