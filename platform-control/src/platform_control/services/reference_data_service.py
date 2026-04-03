from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.reference_data import (
    CreateAuthorityRequest,
    CreateJurisdictionRequest,
    UpdateAuthorityRequest,
    UpdateJurisdictionRequest,
)


class ReferenceDataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_jurisdictions(self) -> list[Jurisdiction]:
        result = await self.session.scalars(select(Jurisdiction).order_by(Jurisdiction.name.asc()))
        return list(result)

    async def create_jurisdiction(self, request: CreateJurisdictionRequest) -> Jurisdiction:
        jurisdiction = Jurisdiction(name=request.name, slug=request.slug)
        self.session.add(jurisdiction)
        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction

    async def update_jurisdiction(
        self,
        jurisdiction_id: str,
        request: UpdateJurisdictionRequest,
    ) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")

        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(jurisdiction, field, value)

        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction

    async def list_authorities(self) -> list[Authority]:
        result = await self.session.scalars(select(Authority).order_by(Authority.name.asc()))
        return list(result)

    async def create_authority(self, request: CreateAuthorityRequest) -> Authority:
        if request.jurisdiction_id is not None:
            await self._require_jurisdiction(request.jurisdiction_id)

        authority = Authority(
            jurisdiction_id=request.jurisdiction_id,
            name=request.name,
            slug=request.slug,
        )
        self.session.add(authority)
        await self.session.commit()
        await self.session.refresh(authority)
        return authority

    async def update_authority(
        self,
        authority_id: str,
        request: UpdateAuthorityRequest,
    ) -> Authority:
        authority = await self.session.get(Authority, authority_id)
        if authority is None:
            raise NotFoundError(f"Authority not found: {authority_id}")

        payload = request.model_dump(exclude_unset=True)
        if "jurisdiction_id" in payload and payload["jurisdiction_id"] is not None:
            await self._require_jurisdiction(payload["jurisdiction_id"])

        for field, value in payload.items():
            setattr(authority, field, value)

        await self.session.commit()
        await self.session.refresh(authority)
        return authority

    async def _require_jurisdiction(self, jurisdiction_id: str) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")
        return jurisdiction
